import random

import discord
from discord import app_commands

CHOICES = ['pierre', 'papier', 'ciseaux']
BEATS = {'pierre': 'ciseaux', 'papier': 'pierre', 'ciseaux': 'papier'}

QUESTIONS = [
    ('Quelle est la capitale de la France ?', ['Paris', 'Lyon', 'Marseille', 'Nice'], 0),
    ('Combien de continents compte la Terre ?', ['5', '6', '7', '8'], 2),
    ('Quel est le plus grand océan du monde ?', ['Atlantique', 'Indien', 'Arctique', 'Pacifique'], 3),
    ('En quelle année a eu lieu la Révolution française ?', ['1789', '1804', '1815', '1848'], 0),
    ('Quel est le symbole chimique de l’oxygène ?', ['Or', 'O', 'Os', 'Og'], 1),
    ('Combien de joueurs compte une équipe de football sur le terrain ?', ['9', '10', '11', '12'], 2),
    ('Quelle planète est la plus proche du Soleil ?', ['Vénus', 'Mercure', 'Mars', 'Terre'], 1),
]

LETTERS = ['A', 'B', 'C', 'D']


class QuizView(discord.ui.View):
    def __init__(self, bonne):
        super().__init__(timeout=30)
        self.bonne = bonne
        self.repondu = False
        for idx, letter in enumerate(LETTERS):
            bouton = discord.ui.Button(label=letter, style=discord.ButtonStyle.secondary)
            bouton.callback = self._make_callback(idx)
            self.add_item(bouton)

    def _make_callback(self, idx):
        async def callback(interaction):
            await self.resoudre(interaction, idx)
        return callback

    async def resoudre(self, interaction, idx):
        if self.repondu:
            await interaction.response.send_message('Quelqu’un a déjà répondu.', ephemeral=True)
            return
        self.repondu = True
        for enfant in self.children:
            enfant.disabled = True
        if idx == self.bonne:
            self.children[idx].style = discord.ButtonStyle.success
            texte = f'✅ {interaction.user.mention} trouve la bonne réponse !'
        else:
            self.children[idx].style = discord.ButtonStyle.danger
            self.children[self.bonne].style = discord.ButtonStyle.success
            texte = f'❌ Raté, {interaction.user.mention}. La bonne réponse est surlignée.'
        await interaction.response.edit_message(content=texte, view=self)
        self.stop()

    async def on_timeout(self):
        for enfant in self.children:
            enfant.disabled = True


def register(bot):
    @bot.tree.command(name='pfc', description='Pierre-papier-ciseaux contre le bot.')
    @app_commands.guild_only()
    @app_commands.choices(choix=[app_commands.Choice(name=c, value=c) for c in CHOICES])
    async def pfc(i: discord.Interaction, choix: app_commands.Choice[str]):
        bot_choice = random.choice(CHOICES)
        joueur = choix.value
        if joueur == bot_choice:
            resultat = 'Égalité !'
        elif BEATS[joueur] == bot_choice:
            resultat = f'{i.user.mention} gagne !'
        else:
            resultat = 'Le bot gagne !'
        await i.response.send_message(f'Toi : **{joueur}** — Bot : **{bot_choice}**\n{resultat}')

    @bot.tree.command(name='pile', description='Pile ou face, avec pari facultatif.')
    @app_commands.guild_only()
    @app_commands.choices(pari=[app_commands.Choice(name='pile', value='pile'), app_commands.Choice(name='face', value='face')])
    async def pile(i: discord.Interaction, pari: app_commands.Choice[str] = None):
        resultat = random.choice(['pile', 'face'])
        texte = f'🪙 Résultat : **{resultat}**'
        if pari:
            texte += ' — Gagné !' if pari.value == resultat else ' — Perdu.'
        await i.response.send_message(texte)

    @bot.tree.command(name='deviner', description='Devine le nombre secret entre 1 et 20.')
    @app_commands.guild_only()
    async def deviner(i: discord.Interaction, nombre: app_commands.Range[int, 1, 20]):
        secret = random.randint(1, 20)
        if nombre == secret:
            await i.response.send_message(f'🎯 Le nombre était **{secret}** — Bravo, tu as trouvé !')
        else:
            indice = 'plus grand' if secret > nombre else 'plus petit'
            await i.response.send_message(f'❌ Perdu ! Le nombre était **{secret}** ({indice} que {nombre}).')

    @bot.tree.command(name='quiz', description='Question de culture générale, premier à répondre gagne.')
    @app_commands.guild_only()
    async def quiz(i: discord.Interaction):
        question, reponses, bonne = random.choice(QUESTIONS)
        view = QuizView(bonne)
        texte = question + '\n' + '\n'.join(f'{l} — {r}' for l, r in zip(LETTERS, reponses))
        await i.response.send_message(texte, view=view)
