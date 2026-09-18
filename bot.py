import logging
import os
import sqlite3
import time
from datetime import timedelta
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import cards
import event_logs
import fc27
import games
import music
from core import SpamDetector, target_allowed

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('lyra_bot')
db = sqlite3.connect(ROOT / 'guardian.sqlite3')
db.executescript('''
CREATE TABLE IF NOT EXISTS config (
 guild INTEGER PRIMARY KEY, channel INTEGER, antispam INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS warnings (
 id INTEGER PRIMARY KEY AUTOINCREMENT, guild INTEGER, member INTEGER,
 moderator INTEGER, reason TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
''')
spam = SpamDetector()

PREFIX = '++'


class LyraBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # Logs détaillés + commandes texte : active "Server Members Intent" et
        # "Message Content Intent" dans le portail développeur.
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix=PREFIX, intents=intents,
                         allowed_mentions=discord.AllowedMentions.none(), help_command=None)

    async def setup_hook(self):
        # Aucune commande slash : seul le préfixe texte ++ doit répondre.
        # On efface toute commande slash publiée par une version précédente du bot.
        guild_id = os.getenv('GUILD_ID', '').strip()
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
        self.tree.clear_commands(guild=None)
        await self.tree.sync()

    async def on_ready(self):
        log.info('Connecté : %s', self.user)

    async def on_message(self, message):
        await self.process_commands(message)
        if not message.guild or message.author.bot or not isinstance(message.author, discord.Member):
            return
        member, guild = message.author, message.guild
        config = db.execute('SELECT antispam FROM config WHERE guild=?', (guild.id,)).fetchone()
        if not config or not config[0] or member.guild_permissions.manage_messages or member.guild_permissions.moderate_members:
            return
        me = guild.me
        if (member.id == guild.owner_id or member.guild_permissions.administrator
                or member.top_role >= me.top_role or not me.guild_permissions.moderate_members):
            return
        if not spam.hit((guild.id, member.id), time.monotonic()):
            return
        try:
            await member.timeout(timedelta(minutes=1), reason='Antispam : 6 messages en 8 secondes')
        except discord.HTTPException:
            log.warning('Échec antispam dans %s', guild.id, exc_info=True)
            return
        await audit(guild, 'Antispam', member.id, self.user.id, 'Timeout 1 minute : 6 messages en 8 secondes')


bot = LyraBot()
event_logs.register(bot)
games.register(bot)
cards.register(bot, db)
music.register(bot)
fc27.register(bot)


async def audit(guild, action, target, moderator, reason):
    embed = discord.Embed(title=f'🛡️ {action}', color=0x5865F2, timestamp=discord.utils.utcnow())
    embed.add_field(name='Membre', value=str(target))
    embed.add_field(name='Modérateur', value=str(moderator))
    embed.add_field(name='Raison', value=reason[:1000], inline=False)
    embed.set_footer(text=f'{guild.name} • {guild.id}')

    row = db.execute('SELECT channel FROM config WHERE guild=?', (guild.id,)).fetchone()
    if row and row[0]:
        channel = guild.get_channel(row[0])
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                log.warning('Action réussie, journal indisponible dans %s', guild.id)

    await event_logs.send(bot, embed)


async def guard(ctx, member, timeout=False):
    actor = await ctx.guild.fetch_member(ctx.author.id)
    target = await ctx.guild.fetch_member(member.id)
    me = await ctx.guild.fetch_member(bot.user.id)
    if not target_allowed(actor.id, ctx.guild.owner_id, actor.top_role, target.id,
                          target.top_role, me.id, me.top_role):
        raise commands.CheckFailure('Cible protégée : propriétaire, toi-même, bot ou rôle supérieur/égal.')
    if timeout and target.guild_permissions.administrator:
        raise commands.CheckFailure('Un administrateur ne peut pas être placé en timeout.')
    return target


@bot.command(name='config', help='Configurer le journal et activer ou désactiver l’antispam.')
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def config(ctx: commands.Context, journal: discord.TextChannel, antispam: bool = False):
    perms = journal.permissions_for(ctx.guild.me)
    if not (perms.view_channel and perms.send_messages and perms.embed_links):
        raise commands.CheckFailure('Il me faut Voir le salon, Envoyer des messages et Intégrer des liens dans le journal.')
    db.execute('INSERT INTO config VALUES (?,?,?) ON CONFLICT(guild) DO UPDATE SET channel=excluded.channel, antispam=excluded.antispam',
               (ctx.guild.id, journal.id, int(antispam)))
    db.commit()
    await ctx.send(f'Journal : {journal.mention}. Antispam : {"activé" if antispam else "désactivé"}.', ephemeral=True)


@bot.command(name='kick', help='Expulser un membre.')
@commands.guild_only()
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def kick(ctx: commands.Context, membre: discord.Member, *, raison: app_commands.Range[str, 1, 400]):
    await ctx.defer(ephemeral=True)
    member = await guard(ctx, membre)
    await member.kick(reason=f'{ctx.author.id} : {raison}')
    await ctx.send(f'{member} a été expulsé.', ephemeral=True)
    await audit(ctx.guild, 'Expulsion', member.id, ctx.author.id, raison)


@bot.command(name='ban', help='Bannir un membre sans supprimer son historique de messages.')
@commands.guild_only()
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def ban(ctx: commands.Context, membre: discord.Member, *, raison: app_commands.Range[str, 1, 400]):
    await ctx.defer(ephemeral=True)
    member = await guard(ctx, membre)
    await member.ban(reason=f'{ctx.author.id} : {raison}', delete_message_seconds=0)
    await ctx.send(f'{member} a été banni.', ephemeral=True)
    await audit(ctx.guild, 'Bannissement', member.id, ctx.author.id, raison)


@bot.command(name='unban', help='Débannir un utilisateur par son identifiant Discord.')
@commands.guild_only()
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def unban(ctx: commands.Context, identifiant: str, *, raison: app_commands.Range[str, 1, 400]):
    if not identifiant.isdecimal() or not 1 <= int(identifiant) < 2**64:
        raise commands.CheckFailure('Identifiant Discord invalide.')
    await ctx.defer(ephemeral=True)
    await ctx.guild.unban(discord.Object(id=int(identifiant)), reason=f'{ctx.author.id} : {raison}')
    await ctx.send('Utilisateur débanni.', ephemeral=True)
    await audit(ctx.guild, 'Débannissement', identifiant, ctx.author.id, raison)


@bot.command(name='timeout', help='Timeout en minutes (0 pour le retirer, maximum 28 jours).')
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def timeout(ctx: commands.Context, membre: discord.Member, minutes: app_commands.Range[int, 0, 40320], *, raison: app_commands.Range[str, 1, 400]):
    await ctx.defer(ephemeral=True)
    member = await guard(ctx, membre, timeout=True)
    await member.timeout(timedelta(minutes=minutes) if minutes else None, reason=f'{ctx.author.id} : {raison}')
    await ctx.send(f'Timeout : {minutes} minute(s) pour {member}.', ephemeral=True)
    await audit(ctx.guild, 'Timeout', member.id, ctx.author.id, f'{minutes} min : {raison}')


@bot.command(name='clear', help='Supprimer jusqu’à 100 messages récents non épinglés.')
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True, read_message_history=True)
async def clear(ctx: commands.Context, nombre: app_commands.Range[int, 1, 100]):
    if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
        raise commands.CheckFailure('Utilise cette commande dans un salon textuel.')
    await ctx.defer(ephemeral=True)
    cutoff = discord.utils.utcnow() - timedelta(days=13)
    deleted = await ctx.channel.purge(limit=nombre, check=lambda m: not m.pinned and m.created_at > cutoff)
    await ctx.send(f'{len(deleted)} message(s) supprimé(s). Les messages épinglés ou de plus de 13 jours sont conservés.', ephemeral=True)
    await audit(ctx.guild, 'Nettoyage', ctx.channel.id, ctx.author.id, f'{len(deleted)} messages supprimés')


@bot.command(name='warn', help='Ajouter un avertissement conservé en base locale.')
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
async def warn(ctx: commands.Context, membre: discord.Member, *, raison: app_commands.Range[str, 1, 400]):
    await ctx.defer(ephemeral=True)
    member = await guard(ctx, membre)
    cursor = db.execute('INSERT INTO warnings(guild,member,moderator,reason) VALUES (?,?,?,?)', (ctx.guild.id, member.id, ctx.author.id, raison))
    db.commit()
    await ctx.send(f'Avertissement #{cursor.lastrowid} ajouté pour {member}.', ephemeral=True)
    await audit(ctx.guild, 'Avertissement', member.id, ctx.author.id, raison)


@bot.command(name='warnings', help='Afficher les 5 derniers avertissements d’un membre.')
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
async def warnings(ctx: commands.Context, membre: discord.Member):
    rows = db.execute('SELECT id,reason,created FROM warnings WHERE guild=? AND member=? ORDER BY id DESC LIMIT 5', (ctx.guild.id, membre.id)).fetchall()
    texte = '\n'.join(f'#{r[0]} — {r[2]} — {discord.utils.escape_markdown(r[1][:150])}' for r in rows) or 'Aucun avertissement.'
    await ctx.send(texte, ephemeral=True)


@bot.command(name='delwarn', help='Supprimer un avertissement par son numéro.')
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
async def delwarn(ctx: commands.Context, numero: int):
    row = db.execute('SELECT member FROM warnings WHERE guild=? AND id=?', (ctx.guild.id, numero)).fetchone()
    if not row:
        await ctx.send('Avertissement introuvable.', ephemeral=True)
        return
    db.execute('DELETE FROM warnings WHERE guild=? AND id=?', (ctx.guild.id, numero))
    db.commit()
    await ctx.send(f'Avertissement #{numero} supprimé.', ephemeral=True)
    await audit(ctx.guild, 'Retrait d’avertissement', row[0], ctx.author.id, f'#{numero}')


HELP_SECTIONS = [
    ('🛡️ Modération', [
        ('config <journal> [antispam]', 'Choisir le journal et activer/désactiver l’antispam'),
        ('kick <membre> <raison>', 'Expulser un membre'),
        ('ban <membre> <raison>', 'Bannir un membre'),
        ('unban <identifiant> <raison>', 'Débannir par identifiant'),
        ('timeout <membre> <minutes> <raison>', 'Timeout (0 pour retirer)'),
        ('clear <nombre>', 'Supprimer des messages récents'),
        ('warn <membre> <raison>', 'Ajouter un avertissement'),
        ('warnings <membre>', 'Voir les avertissements'),
        ('delwarn <numero>', 'Retirer un avertissement'),
    ]),
    ('🎮 Jeux', [
        ('pfc <choix>', 'Pierre-papier-ciseaux'),
        ('pile [pari]', 'Pile ou face'),
        ('deviner <nombre>', 'Deviner un nombre entre 1 et 20'),
        ('quiz', 'Question de culture générale'),
    ]),
    ('🃏 Cartes', [
        ('quotidien', 'Récupérer des pièces (1x/24h)'),
        ('solde', 'Voir son solde'),
        ('ouvrir', 'Ouvrir un paquet de cartes'),
        ('cartes [membre]', 'Voir une collection'),
        ('echanger <membre> <ma_carte> <sa_carte>', 'Proposer un échange'),
    ]),
    ('🎵 Musique', [
        ('jouer <recherche>', 'Jouer une musique YouTube'),
        ('pause / reprendre', 'Mettre en pause / reprendre'),
        ('suivant', 'Passer à la musique suivante'),
        ('stop', 'Arrêter et quitter le vocal'),
        ('file', 'Voir la file d’attente'),
    ]),
    ('⚽ EA SPORTS FC 27', [
        ('fc27', 'Voir les dernières actus officielles'),
        ('sbc', 'Voir les SBC actifs avec leur image (FUT.GG)'),
    ]),
]


@bot.command(name='help', aliases=['aide'], help='Afficher la liste des commandes.')
async def help_command(ctx: commands.Context):
    embed = discord.Embed(title='📖 Commandes de Lyra Bot',
                          description=f'Préfixe texte : `{PREFIX}` (ex. `{PREFIX}help`).',
                          color=0x5865F2)
    for titre, commandes in HELP_SECTIONS:
        valeur = '\n'.join(f'`{PREFIX}{nom}` — {desc}' for nom, desc in commandes)
        embed.add_field(name=titre, value=valeur, inline=False)
    await ctx.send(embed=embed, ephemeral=True)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    cause = getattr(error, 'original', error)
    if isinstance(cause, (commands.MissingPermissions, commands.BotMissingPermissions)):
        text = 'Permissions manquantes : ' + ', '.join(cause.missing_permissions)
    elif isinstance(cause, commands.MemberNotFound):
        text = 'Membre introuvable.'
    elif isinstance(cause, commands.MissingRequiredArgument):
        text = f'Argument manquant : {cause.param.name}.'
    elif isinstance(cause, commands.CheckFailure):
        text = str(cause) or 'Action refusée.'
    elif isinstance(cause, discord.Forbidden):
        text = 'Discord refuse cette action. Vérifie mes permissions et la position de mon rôle.'
    elif isinstance(cause, discord.NotFound):
        text = 'Ce membre, message ou bannissement n’existe plus.'
    else:
        log.error('Erreur de commande', exc_info=(type(cause), cause, cause.__traceback__))
        text = 'Une erreur est survenue. Consulte la console du bot avant de réessayer.'
    try:
        await ctx.send(text, ephemeral=True)
    except discord.HTTPException:
        pass


if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN', '').strip()
    if not token or token == 'colle_le_token_ici':
        raise SystemExit('Renseigne DISCORD_TOKEN dans le fichier .env, puis relance le bot.')
    bot.run(token)
