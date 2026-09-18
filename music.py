import asyncio
import logging
from collections import deque

import discord
import yt_dlp
from discord import app_commands

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

    @bot.tree.command(name='jouer', description='Jouer une musique depuis YouTube (recherche ou lien).')
    @app_commands.guild_only()
    async def jouer(i: discord.Interaction, recherche: str):
        if not isinstance(i.user, discord.Member) or not i.user.voice or not i.user.voice.channel:
            await i.response.send_message('Rejoins un salon vocal avant d’utiliser cette commande.', ephemeral=True)
            return
        await i.response.defer()
        player = get_player(i.guild_id)
        channel = i.user.voice.channel
        if player.voice and player.voice.is_connected() and player.voice.channel != channel:
            await i.followup.send('Le bot est déjà en train de jouer dans un autre salon vocal.')
            return
        if not player.voice or not player.voice.is_connected():
            try:
                player.voice = await channel.connect()
            except discord.ClientException:
                await i.followup.send('Impossible de rejoindre ce salon vocal.')
                return
        try:
            info = await extract(recherche)
        except Exception:
            log.warning('Extraction yt-dlp échouée pour %r', recherche, exc_info=True)
            await i.followup.send('Impossible de récupérer cette musique (lien invalide ou indisponible).')
            return
        track = Track(info['url'], info.get('title', 'Inconnu'), info.get('webpage_url', ''), i.user)
        player.queue.append(track)
        if not player.voice.is_playing() and not player.voice.is_paused():
            await play_next(i.guild_id)
            await i.followup.send(f'▶️ Lecture : **{track.title}**')
        else:
            await i.followup.send(f'➕ Ajouté à la file : **{track.title}** (position {len(player.queue)})')

    @bot.tree.command(name='pause', description='Mettre la lecture en pause.')
    @app_commands.guild_only()
    async def pause(i: discord.Interaction):
        player = players.get(i.guild_id)
        if not player or not player.voice or not player.voice.is_playing():
            await i.response.send_message('Rien n’est en cours de lecture.', ephemeral=True)
            return
        player.voice.pause()
        await i.response.send_message('⏸️ Pause.')

    @bot.tree.command(name='reprendre', description='Reprendre la lecture après une pause.')
    @app_commands.guild_only()
    async def reprendre(i: discord.Interaction):
        player = players.get(i.guild_id)
        if not player or not player.voice or not player.voice.is_paused():
            await i.response.send_message('Rien n’est en pause.', ephemeral=True)
            return
        player.voice.resume()
        await i.response.send_message('▶️ Reprise.')

    @bot.tree.command(name='suivant', description='Passer à la musique suivante de la file.')
    @app_commands.guild_only()
    async def suivant(i: discord.Interaction):
        player = players.get(i.guild_id)
        if not player or not player.voice or not (player.voice.is_playing() or player.voice.is_paused()):
            await i.response.send_message('Rien n’est en cours de lecture.', ephemeral=True)
            return
        player.voice.stop()
        await i.response.send_message('⏭️ Musique suivante.')

    @bot.tree.command(name='stop', description='Arrêter la lecture, vider la file et quitter le vocal.')
    @app_commands.guild_only()
    async def stop(i: discord.Interaction):
        player = players.get(i.guild_id)
        if not player or not player.voice:
            await i.response.send_message('Le bot n’est pas connecté à un salon vocal.', ephemeral=True)
            return
        player.queue.clear()
        player.current = None
        if player.voice.is_connected():
            await player.voice.disconnect()
        player.voice = None
        await i.response.send_message('⏹️ Lecture arrêtée, bot déconnecté.')

    @bot.tree.command(name='file', description='Voir la file d’attente de musique.')
    @app_commands.guild_only()
    async def file_attente(i: discord.Interaction):
        player = players.get(i.guild_id)
        if not player or (not player.current and not player.queue):
            await i.response.send_message('La file est vide.', ephemeral=True)
            return
        lignes = []
        if player.current:
            lignes.append(f'▶️ **{player.current.title}** (en cours, demandé par {player.current.requester.display_name})')
        for idx, t in enumerate(player.queue, start=1):
            lignes.append(f'{idx}. {t.title} — demandé par {t.requester.display_name}')
        await i.response.send_message('\n'.join(lignes)[:2000])
