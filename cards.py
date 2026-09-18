import random
import time

import discord
from discord.ext import commands

PACK_COST = 40
DAILY_MIN, DAILY_MAX = 20, 40
DAILY_COOLDOWN = 86400

RARITY_WEIGHTS = {'Commune': 60, 'Rare': 28, 'Épique': 10, 'Légendaire': 2}
RARITY_COLORS = {'Commune': 0x99AAB5, 'Rare': 0x3498DB, 'Épique': 0x9B59B6, 'Légendaire': 0xF1C40F}

CARDS = [
    {'id': 'braise', 'nom': 'Braisillon', 'rarete': 'Commune', 'emoji': '🔥', 'description': 'Un petit lézard toujours prêt à faire des étincelles.'},
    {'id': 'goutte', 'nom': 'Gouttelin', 'rarete': 'Commune', 'emoji': '💧', 'description': 'Une créature aquatique curieuse et joueuse.'},
    {'id': 'pousse', 'nom': 'Poussael', 'rarete': 'Commune', 'emoji': '🌱', 'description': 'Une graine ambulante qui adore le soleil.'},
    {'id': 'roche', 'nom': 'Rocaillou', 'rarete': 'Commune', 'emoji': '🪨', 'description': 'Solide comme un roc, littéralement.'},
    {'id': 'brise', 'nom': 'Brisillon', 'rarete': 'Commune', 'emoji': '🍃', 'description': 'Léger comme l’air, il file au moindre courant.'},
    {'id': 'etinc', 'nom': 'Étincelet', 'rarete': 'Commune', 'emoji': '⚡', 'description': 'Un poil hérissé qui crépite à chaque pas.'},
    {'id': 'sable', 'nom': 'Sablona', 'rarete': 'Commune', 'emoji': '🏜️', 'description': 'Elle se déplace en laissant une traînée dorée.'},
    {'id': 'nuage', 'nom': 'Nuageon', 'rarete': 'Commune', 'emoji': '☁️', 'description': 'Toujours la tête dans les nuages, au sens propre.'},
    {'id': 'lune', 'nom': 'Lunaris', 'rarete': 'Rare', 'emoji': '🌙', 'description': 'Elle ne sort que les nuits claires.'},
    {'id': 'corail', 'nom': 'Coralia', 'rarete': 'Rare', 'emoji': '🪸', 'description': 'Gardienne discrète des récifs oubliés.'},
    {'id': 'foudre', 'nom': 'Foudroy', 'rarete': 'Rare', 'emoji': '🌩️', 'description': 'Chaque grondement de tonnerre annonce son arrivée.'},
    {'id': 'crystal', 'nom': 'Cristalie', 'rarete': 'Rare', 'emoji': '💎', 'description': 'Son corps translucide reflète toutes les couleurs.'},
    {'id': 'flamme', 'nom': 'Flammeko', 'rarete': 'Rare', 'emoji': '🔆', 'description': 'Une flamme vivante qui ne s’éteint jamais vraiment.'},
    {'id': 'aurore', 'nom': 'Auroria', 'rarete': 'Épique', 'emoji': '🌌', 'description': 'On dit qu’elle peint les aurores boréales.'},
    {'id': 'abysse', 'nom': 'Abyssia', 'rarete': 'Épique', 'emoji': '🐙', 'description': 'Née dans les profondeurs les plus sombres.'},
    {'id': 'phenix', 'nom': 'Phénixor', 'rarete': 'Légendaire', 'emoji': '🦅', 'description': 'Selon la légende, il renaît de ses propres cendres.'},
]

CARDS_BY_ID = {c['id']: c for c in CARDS}
POOL = [c['id'] for c in CARDS]
WEIGHTS = [RARITY_WEIGHTS[c['rarete']] for c in CARDS]


def setup_db(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS wallet (
     guild INTEGER, member INTEGER, coins INTEGER NOT NULL DEFAULT 0,
     last_daily REAL NOT NULL DEFAULT 0, PRIMARY KEY (guild, member));
    CREATE TABLE IF NOT EXISTS collection (
     guild INTEGER, member INTEGER, card_id TEXT, count INTEGER NOT NULL DEFAULT 0,
     PRIMARY KEY (guild, member, card_id));
    ''')


def get_balance(db, guild, member):
    row = db.execute('SELECT coins FROM wallet WHERE guild=? AND member=?', (guild, member)).fetchone()
    return row[0] if row else 0


def add_coins(db, guild, member, amount, last_daily=None):
    if last_daily is None:
        db.execute('''INSERT INTO wallet(guild, member, coins) VALUES (?,?,?)
                      ON CONFLICT(guild, member) DO UPDATE SET coins=coins+excluded.coins''',
                   (guild, member, amount))
    else:
        db.execute('''INSERT INTO wallet(guild, member, coins, last_daily) VALUES (?,?,?,?)
                      ON CONFLICT(guild, member) DO UPDATE SET coins=coins+excluded.coins, last_daily=excluded.last_daily''',
                   (guild, member, amount, last_daily))
    db.commit()


def get_last_daily(db, guild, member):
    row = db.execute('SELECT last_daily FROM wallet WHERE guild=? AND member=?', (guild, member)).fetchone()
    return row[0] if row else 0


def get_card_count(db, guild, member, card_id):
    row = db.execute('SELECT count FROM collection WHERE guild=? AND member=? AND card_id=?', (guild, member, card_id)).fetchone()
    return row[0] if row else 0


def add_card(db, guild, member, card_id, delta):
    db.execute('''INSERT INTO collection(guild, member, card_id, count) VALUES (?,?,?,?)
                  ON CONFLICT(guild, member, card_id) DO UPDATE SET count = count + excluded.count''',
               (guild, member, card_id, delta))
    db.commit()


class TradeView(discord.ui.View):
    def __init__(self, db, sender, receiver, sender_card, receiver_card):
        super().__init__(timeout=300)
        self.db = db
        self.sender, self.receiver = sender, receiver
        self.sender_card, self.receiver_card = sender_card, receiver_card
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.receiver.id:
            await interaction.response.send_message('Seule la personne visée peut répondre à cette proposition.', ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(content='⌛ Proposition d’échange expirée.', embed=None, view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label='Accepter', style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild_id
        if (get_card_count(self.db, guild_id, self.sender.id, self.sender_card) < 1
                or get_card_count(self.db, guild_id, self.receiver.id, self.receiver_card) < 1):
            await interaction.response.edit_message(content='❌ Échange annulé : une des cartes n’est plus disponible.', embed=None, view=None)
            self.stop()
            return
        add_card(self.db, guild_id, self.sender.id, self.sender_card, -1)
        add_card(self.db, guild_id, self.sender.id, self.receiver_card, 1)
        add_card(self.db, guild_id, self.receiver.id, self.receiver_card, -1)
        add_card(self.db, guild_id, self.receiver.id, self.sender_card, 1)
        await interaction.response.edit_message(
            content=f'✅ Échange conclu entre {self.sender.mention} et {self.receiver.mention} !', embed=None, view=None)
        self.stop()

    @discord.ui.button(label='Refuser', style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content='🚫 Échange refusé.', embed=None, view=None)
        self.stop()


def register(bot, db):
    setup_db(db)

    @bot.hybrid_command(name='quotidien', description='Récupérer tes pièces quotidiennes.')
    @commands.guild_only()
    async def quotidien(ctx: commands.Context):
        now = time.time()
        last = get_last_daily(db, ctx.guild.id, ctx.author.id)
        remaining = DAILY_COOLDOWN - (now - last)
        if remaining > 0:
            heures, minutes = int(remaining // 3600), int((remaining % 3600) // 60)
            await ctx.send(f'⏳ Prochaine récompense dans {heures} h {minutes} min.', ephemeral=True)
            return
        gain = random.randint(DAILY_MIN, DAILY_MAX)
        add_coins(db, ctx.guild.id, ctx.author.id, gain, last_daily=now)
        await ctx.send(f'💰 +{gain} pièces ! Solde : {get_balance(db, ctx.guild.id, ctx.author.id)}.')

    @bot.hybrid_command(name='solde', description='Voir ton solde de pièces.')
    @commands.guild_only()
    async def solde(ctx: commands.Context):
        await ctx.send(f'💰 Solde de {ctx.author.display_name} : {get_balance(db, ctx.guild.id, ctx.author.id)} pièces.')

    @bot.hybrid_command(name='ouvrir', description=f'Ouvrir un paquet de cartes ({PACK_COST} pièces).')
    @commands.guild_only()
    async def ouvrir(ctx: commands.Context):
        solde_actuel = get_balance(db, ctx.guild.id, ctx.author.id)
        if solde_actuel < PACK_COST:
            await ctx.send(
                f'Il te faut {PACK_COST} pièces (tu en as {solde_actuel}). Utilise `++quotidien` pour en gagner.', ephemeral=True)
            return
        add_coins(db, ctx.guild.id, ctx.author.id, -PACK_COST)
        card_id = random.choices(POOL, weights=WEIGHTS)[0]
        add_card(db, ctx.guild.id, ctx.author.id, card_id, 1)
        card = CARDS_BY_ID[card_id]
        embed = discord.Embed(title=f"{card['emoji']} {card['nom']}", description=card['description'],
                              color=RARITY_COLORS[card['rarete']])
        embed.add_field(name='Rareté', value=card['rarete'])
        embed.add_field(name='Identifiant', value=f"`{card['id']}`")
        embed.set_footer(text=f'Tiré par {ctx.author.display_name}')
        await ctx.send(embed=embed)

    @bot.hybrid_command(name='cartes', description='Voir une collection de cartes.')
    @commands.guild_only()
    async def cartes(ctx: commands.Context, membre: discord.Member = None):
        cible = membre or ctx.author
        rows = db.execute(
            'SELECT card_id, count FROM collection WHERE guild=? AND member=? AND count>0 ORDER BY card_id',
            (ctx.guild.id, cible.id)).fetchall()
        if not rows:
            await ctx.send(f'{cible.display_name} n’a aucune carte. Utilise `++ouvrir` pour en obtenir.', ephemeral=True)
            return
        lignes = [f"{CARDS_BY_ID[cid]['emoji']} **{CARDS_BY_ID[cid]['nom']}** (`{cid}`, {CARDS_BY_ID[cid]['rarete']}) x{count}"
                  for cid, count in rows if cid in CARDS_BY_ID]
        embed = discord.Embed(title=f'Collection de {cible.display_name}', description='\n'.join(lignes)[:4000], color=0x5865F2)
        await ctx.send(embed=embed)

    @bot.hybrid_command(name='echanger', description='Proposer un échange de cartes avec un membre.')
    @commands.guild_only()
    async def echanger(ctx: commands.Context, membre: discord.Member, ma_carte: str, sa_carte: str):
        if membre.id == ctx.author.id or membre.bot:
            await ctx.send('Choisis un autre membre à qui proposer l’échange.', ephemeral=True)
            return
        if ma_carte not in CARDS_BY_ID or sa_carte not in CARDS_BY_ID:
            await ctx.send('Identifiant de carte inconnu. Utilise `++cartes` pour voir les identifiants.', ephemeral=True)
            return
        if get_card_count(db, ctx.guild.id, ctx.author.id, ma_carte) < 1:
            await ctx.send('Tu ne possèdes pas cette carte.', ephemeral=True)
            return
        if get_card_count(db, ctx.guild.id, membre.id, sa_carte) < 1:
            await ctx.send(f'{membre.display_name} ne possède pas cette carte.', ephemeral=True)
            return
        embed = discord.Embed(title='🔄 Proposition d’échange', color=0xFEE75C)
        embed.add_field(name=f'{ctx.author.display_name} offre', value=f"{CARDS_BY_ID[ma_carte]['emoji']} {CARDS_BY_ID[ma_carte]['nom']}")
        embed.add_field(name=f'{membre.display_name} offre', value=f"{CARDS_BY_ID[sa_carte]['emoji']} {CARDS_BY_ID[sa_carte]['nom']}")
        view = TradeView(db, ctx.author, membre, ma_carte, sa_carte)
        message = await ctx.send(content=membre.mention, embed=embed, view=view)
        view.message = message
