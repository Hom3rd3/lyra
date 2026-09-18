import logging
import os
import sqlite3
import time
from datetime import timedelta
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

import event_logs
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


class LyraBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        # Logs détaillés (arrivées/départs, contenu des messages modifiés/supprimés) :
        # active "Server Members Intent" et "Message Content Intent" dans le portail développeur.
        intents.members = True
        intents.message_content = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        guild_id = os.getenv('GUILD_ID', '').strip()
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        log.info('Connecté : %s', self.user)

    async def on_message(self, message):
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


async def reply(interaction, text):
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


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


async def guard(i, member, timeout=False):
    actor = await i.guild.fetch_member(i.user.id)
    target = await i.guild.fetch_member(member.id)
    me = await i.guild.fetch_member(bot.user.id)
    if not target_allowed(actor.id, i.guild.owner_id, actor.top_role, target.id,
                          target.top_role, me.id, me.top_role):
        raise app_commands.CheckFailure('Cible protégée : propriétaire, toi-même, bot ou rôle supérieur/égal.')
    if timeout and target.guild_permissions.administrator:
        raise app_commands.CheckFailure('Un administrateur ne peut pas être placé en timeout.')
    return target


@bot.tree.command(description='Configurer le journal et activer ou désactiver l’antispam.')
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def config(i: discord.Interaction, journal: discord.TextChannel, antispam: bool = False):
    perms = journal.permissions_for(i.guild.me)
    if not (perms.view_channel and perms.send_messages and perms.embed_links):
        raise app_commands.CheckFailure('Il me faut Voir le salon, Envoyer des messages et Intégrer des liens dans le journal.')
    db.execute('INSERT INTO config VALUES (?,?,?) ON CONFLICT(guild) DO UPDATE SET channel=excluded.channel, antispam=excluded.antispam',
               (i.guild_id, journal.id, int(antispam)))
    db.commit()
    await reply(i, f'Journal : {journal.mention}. Antispam : {"activé" if antispam else "désactivé"}.')


@bot.tree.command(description='Expulser un membre.')
@app_commands.guild_only()
@app_commands.default_permissions(kick_members=True)
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.checks.bot_has_permissions(kick_members=True)
async def kick(i: discord.Interaction, membre: discord.Member, raison: app_commands.Range[str, 1, 400]):
    await i.response.defer(ephemeral=True)
    member = await guard(i, membre)
    await member.kick(reason=f'{i.user.id} : {raison}')
    await reply(i, f'{member} a été expulsé.')
    await audit(i.guild, 'Expulsion', member.id, i.user.id, raison)


@bot.tree.command(description='Bannir un membre sans supprimer son historique de messages.')
@app_commands.guild_only()
@app_commands.default_permissions(ban_members=True)
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def ban(i: discord.Interaction, membre: discord.Member, raison: app_commands.Range[str, 1, 400]):
    await i.response.defer(ephemeral=True)
    member = await guard(i, membre)
    await member.ban(reason=f'{i.user.id} : {raison}', delete_message_seconds=0)
    await reply(i, f'{member} a été banni.')
    await audit(i.guild, 'Bannissement', member.id, i.user.id, raison)


@bot.tree.command(description='Débannir un utilisateur par son identifiant Discord.')
@app_commands.guild_only()
@app_commands.default_permissions(ban_members=True)
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def unban(i: discord.Interaction, identifiant: str, raison: app_commands.Range[str, 1, 400]):
    if not identifiant.isdecimal() or not 1 <= int(identifiant) < 2**64:
        raise app_commands.CheckFailure('Identifiant Discord invalide.')
    await i.response.defer(ephemeral=True)
    await i.guild.unban(discord.Object(id=int(identifiant)), reason=f'{i.user.id} : {raison}')
    await reply(i, 'Utilisateur débanni.')
    await audit(i.guild, 'Débannissement', identifiant, i.user.id, raison)


@bot.tree.command(description='Timeout en minutes (0 pour le retirer, maximum 28 jours).')
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.checks.bot_has_permissions(moderate_members=True)
async def timeout(i: discord.Interaction, membre: discord.Member, minutes: app_commands.Range[int, 0, 40320], raison: app_commands.Range[str, 1, 400]):
    await i.response.defer(ephemeral=True)
    member = await guard(i, membre, timeout=True)
    await member.timeout(timedelta(minutes=minutes) if minutes else None, reason=f'{i.user.id} : {raison}')
    await reply(i, f'Timeout : {minutes} minute(s) pour {member}.')
    await audit(i.guild, 'Timeout', member.id, i.user.id, f'{minutes} min : {raison}')


@bot.tree.command(description='Supprimer jusqu’à 100 messages récents non épinglés.')
@app_commands.guild_only()
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def clear(i: discord.Interaction, nombre: app_commands.Range[int, 1, 100]):
    if not isinstance(i.channel, (discord.TextChannel, discord.Thread)):
        raise app_commands.CheckFailure('Utilise cette commande dans un salon textuel.')
    await i.response.defer(ephemeral=True)
    cutoff = discord.utils.utcnow() - timedelta(days=13)
    deleted = await i.channel.purge(limit=nombre, check=lambda m: not m.pinned and m.created_at > cutoff)
    await reply(i, f'{len(deleted)} message(s) supprimé(s). Les messages épinglés ou de plus de 13 jours sont conservés.')
    await audit(i.guild, 'Nettoyage', i.channel_id, i.user.id, f'{len(deleted)} messages supprimés')


@bot.tree.command(description='Ajouter un avertissement conservé en base locale.')
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(i: discord.Interaction, membre: discord.Member, raison: app_commands.Range[str, 1, 400]):
    await i.response.defer(ephemeral=True)
    member = await guard(i, membre)
    cursor = db.execute('INSERT INTO warnings(guild,member,moderator,reason) VALUES (?,?,?,?)', (i.guild_id, member.id, i.user.id, raison))
    db.commit()
    await reply(i, f'Avertissement #{cursor.lastrowid} ajouté pour {member}.')
    await audit(i.guild, 'Avertissement', member.id, i.user.id, raison)


@bot.tree.command(description='Afficher les 5 derniers avertissements d’un membre.')
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def warnings(i: discord.Interaction, membre: discord.Member):
    rows = db.execute('SELECT id,reason,created FROM warnings WHERE guild=? AND member=? ORDER BY id DESC LIMIT 5', (i.guild_id, membre.id)).fetchall()
    await reply(i, '\n'.join(f'#{r[0]} — {r[2]} — {discord.utils.escape_markdown(r[1][:150])}' for r in rows) or 'Aucun avertissement.')


@bot.tree.command(description='Supprimer un avertissement par son numéro.')
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def delwarn(i: discord.Interaction, numero: int):
    row = db.execute('SELECT member FROM warnings WHERE guild=? AND id=?', (i.guild_id, numero)).fetchone()
    if not row:
        await reply(i, 'Avertissement introuvable.')
        return
    db.execute('DELETE FROM warnings WHERE guild=? AND id=?', (i.guild_id, numero))
    db.commit()
    await reply(i, f'Avertissement #{numero} supprimé.')
    await audit(i.guild, 'Retrait d’avertissement', row[0], i.user.id, f'#{numero}')


@bot.tree.error
async def on_error(i: discord.Interaction, error: app_commands.AppCommandError):
    cause = getattr(error, 'original', error)
    if isinstance(cause, (app_commands.MissingPermissions, app_commands.BotMissingPermissions)):
        text = 'Permissions manquantes : ' + ', '.join(cause.missing_permissions)
    elif isinstance(cause, app_commands.CheckFailure):
        text = str(cause)
    elif isinstance(cause, discord.Forbidden):
        text = 'Discord refuse cette action. Vérifie mes permissions et la position de mon rôle.'
    elif isinstance(cause, discord.NotFound):
        text = 'Ce membre, message ou bannissement n’existe plus.'
    else:
        log.error('Erreur de commande', exc_info=(type(cause), cause, cause.__traceback__))
        text = 'Une erreur est survenue. Consulte la console du bot avant de réessayer.'
    await reply(i, text)


if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN', '').strip()
    if not token or token == 'colle_le_token_ici':
        raise SystemExit('Renseigne DISCORD_TOKEN dans le fichier .env, puis relance le bot.')
    bot.run(token)
