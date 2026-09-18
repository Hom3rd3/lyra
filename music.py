import asyncio
import logging
from collections import deque

import discord
import yt_dlp
from discord.ext import commands

log = logging.getLogger('lyra_bot.music')

YDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'ytsearch',
    'quiet': True,
    'no_warnings': True,
    'source_address': '0.0.0.0',
}
FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

players = {}


class Track:
    def __init__(self, url, title, webpage_url, requester):
        self.url = url
        self.title = title
        self.webpage_url = webpage_url
        self.requester = requester


class Player:
    def __init__(self):
        self.queue = deque()
        self.voice = None
        self.current = None


def get_player(guild_id):
    return players.setdefault(guild_id, Player())


async def extract(query):
    loop = asyncio.get_event_loop()

    def run():
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            return info

    return await loop.run_in_executor(None, run)


def register(bot):
    async def play_next(guild_id):
        player = players.get(guild_id)
        if not player or not player.queue:
            if player:
                player.current = None
            return
        track = player.queue.popleft()
        player.current = track

        def after(error):
            if error:
                log.warning('Erreur de lecture pour %s', guild_id, exc_info=error)
            asyncio.run_coroutine_threadsafe(play_next(guild_id), bot.loop)

        try:
            source = discord.FFmpegOpusAudio(track.url, **FFMPEG_OPTS)
            player.voice.play(source, after=after)
        except discord.ClientException:
            log.warning('Lecture impossible pour %s', guild_id, exc_info=True)
            await play_next(guild_id)

    @bot.command(name='jouer', help='Jouer une musique depuis YouTube (recherche ou lien).')
    @commands.guild_only()
    async def jouer(ctx: commands.Context, *, recherche: str):
        if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send('Rejoins un salon vocal avant d’utiliser cette commande.', ephemeral=True)
            return
        await ctx.defer()
        player = get_player(ctx.guild.id)
        channel = ctx.author.voice.channel
        if player.voice and player.voice.is_connected() and player.voice.channel != channel:
            await ctx.send('Le bot est déjà en train de jouer dans un autre salon vocal.')
            return
        if not player.voice or not player.voice.is_connected():
            try:
                player.voice = await channel.connect()
            except discord.ClientException:
                await ctx.send('Impossible de rejoindre ce salon vocal.')
                return
        try:
            info = await extract(recherche)
        except Exception:
            log.warning('Extraction yt-dlp échouée pour %r', recherche, exc_info=True)
            await ctx.send('Impossible de récupérer cette musique (lien invalide ou indisponible).')
            return
        track = Track(info['url'], info.get('title', 'Inconnu'), info.get('webpage_url', ''), ctx.author)
        player.queue.append(track)
        if not player.voice.is_playing() and not player.voice.is_paused():
            await play_next(ctx.guild.id)
            await ctx.send(f'▶️ Lecture : **{track.title}**')
        else:
            await ctx.send(f'➕ Ajouté à la file : **{track.title}** (position {len(player.queue)})')

    @bot.command(name='pause', help='Mettre la lecture en pause.')
    @commands.guild_only()
    async def pause(ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or not player.voice or not player.voice.is_playing():
            await ctx.send('Rien n’est en cours de lecture.', ephemeral=True)
            return
        player.voice.pause()
        await ctx.send('⏸️ Pause.')

    @bot.command(name='reprendre', help='Reprendre la lecture après une pause.')
    @commands.guild_only()
    async def reprendre(ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or not player.voice or not player.voice.is_paused():
            await ctx.send('Rien n’est en pause.', ephemeral=True)
            return
        player.voice.resume()
        await ctx.send('▶️ Reprise.')

    @bot.command(name='suivant', help='Passer à la musique suivante de la file.')
    @commands.guild_only()
    async def suivant(ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or not player.voice or not (player.voice.is_playing() or player.voice.is_paused()):
            await ctx.send('Rien n’est en cours de lecture.', ephemeral=True)
            return
        player.voice.stop()
        await ctx.send('⏭️ Musique suivante.')

    @bot.command(name='stop', help='Arrêter la lecture, vider la file et quitter le vocal.')
    @commands.guild_only()
    async def stop(ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or not player.voice:
            await ctx.send('Le bot n’est pas connecté à un salon vocal.', ephemeral=True)
            return
        player.queue.clear()
        player.current = None
        if player.voice.is_connected():
            await player.voice.disconnect()
        player.voice = None
        await ctx.send('⏹️ Lecture arrêtée, bot déconnecté.')

    @bot.command(name='file', help='Voir la file d’attente de musique.')
    @commands.guild_only()
    async def file_attente(ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or (not player.current and not player.queue):
            await ctx.send('La file est vide.', ephemeral=True)
            return
        lignes = []
        if player.current:
            lignes.append(f'▶️ **{player.current.title}** (en cours, demandé par {player.current.requester.display_name})')
        for idx, t in enumerate(player.queue, start=1):
            lignes.append(f'{idx}. {t.title} — demandé par {t.requester.display_name}')
        await ctx.send('\n'.join(lignes)[:2000])
