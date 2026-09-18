import random
from typing import Literal, Optional

import discord
from discord.ext import commands

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
    @bot.command(name='pfc', help='Pierre-papier-ciseaux contre le bot.')
    async def pfc(ctx: commands.Context, choix: Literal['pierre', 'papier', 'ciseaux']):
        bot_choice = random.choice(CHOICES)
        if choix == bot_choice:
            resultat = 'Égalité !'
        elif BEATS[choix] == bot_choice:
            resultat = f'{ctx.author.mention} gagne !'
        else:
            resultat = 'Le bot gagne !'
        await ctx.send(f'Toi : **{choix}** — Bot : **{bot_choice}**\n{resultat}')

    @bot.command(name='pile', help='Pile ou face, avec pari facultatif.')
    async def pile(ctx: commands.Context, pari: Optional[Literal['pile', 'face']] = None):
        resultat = random.choice(['pile', 'face'])
        texte = f'🪙 Résultat : **{resultat}**'
        if pari:
            texte += ' — Gagné !' if pari == resultat else ' — Perdu.'
        await ctx.send(texte)

    @bot.command(name='deviner', help='Devine le nombre secret entre 1 et 20.')
    async def deviner(ctx: commands.Context, nombre: commands.Range[int, 1, 20]):
        secret = random.randint(1, 20)
        if nombre == secret:
            await ctx.send(f'🎯 Le nombre était **{secret}** — Bravo, tu as trouvé !')
        else:
            indice = 'plus grand' if secret > nombre else 'plus petit'
            await ctx.send(f'❌ Perdu ! Le nombre était **{secret}** ({indice} que {nombre}).')

    @bot.command(name='quiz', help='Question de culture générale, premier à répondre gagne.')
    async def quiz(ctx: commands.Context):
        question, reponses, bonne = random.choice(QUESTIONS)
        view = QuizView(bonne)
        texte = question + '\n' + '\n'.join(f'{l} — {r}' for l, r in zip(LETTERS, reponses))
        await ctx.send(texte, view=view)
