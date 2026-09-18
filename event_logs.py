import logging
import os

import discord

log = logging.getLogger('lyra_bot.event_logs')

LOG_CHANNEL_ID = int(os.getenv('EVENT_LOG_CHANNEL_ID', '1109409973714296895').strip())

_cache = {}


async def _channel(client):
    channel = _cache.get('channel')
    if channel is not None:
        return channel
    channel = client.get_channel(LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await client.fetch_channel(LOG_CHANNEL_ID)
        except discord.HTTPException:
            log.warning('Salon de logs %s introuvable ou inaccessible.', LOG_CHANNEL_ID)
            return None
    _cache['channel'] = channel
    return channel


async def send(client, embed):
    channel = await _channel(client)
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        log.warning('Envoi du log échoué dans %s', LOG_CHANNEL_ID, exc_info=True)


def base_embed(title, color, guild=None):
    embed = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
    if guild is not None:
        embed.set_footer(text=f'{guild.name} • {guild.id}')
    return embed


def register(bot):
    @bot.event
    async def on_member_join(member):
        embed = base_embed('📥 Arrivée', 0x57F287, member.guild)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name='Membre', value=f'{member} ({member.id})', inline=False)
        embed.add_field(name='Compte créé', value=discord.utils.format_dt(member.created_at, 'R'))
        embed.add_field(name='Effectif', value=str(member.guild.member_count))
        await send(bot, embed)

    @bot.event
    async def on_member_remove(member):
        embed = base_embed('📤 Départ', 0xED4245, member.guild)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name='Membre', value=f'{member} ({member.id})', inline=False)
        joined = discord.utils.format_dt(member.joined_at, 'R') if member.joined_at else 'Inconnu'
        embed.add_field(name='Arrivé', value=joined)
        roles = ', '.join(r.mention for r in member.roles if not r.is_default())
        embed.add_field(name='Rôles', value=roles or 'Aucun', inline=False)
        embed.add_field(name='Effectif', value=str(member.guild.member_count))
        await send(bot, embed)

    @bot.event
    async def on_member_update(before, after):
        guild = after.guild
        if before.nick != after.nick:
            embed = base_embed('✏️ Pseudo modifié', 0xFEE75C, guild)
            embed.add_field(name='Membre', value=f'{after} ({after.id})', inline=False)
            embed.add_field(name='Avant', value=before.nick or before.name)
            embed.add_field(name='Après', value=after.nick or after.name)
            await send(bot, embed)
        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            if added or removed:
                embed = base_embed('🎭 Rôles modifiés', 0xEB459E, guild)
                embed.add_field(name='Membre', value=f'{after} ({after.id})', inline=False)
                if added:
                    embed.add_field(name='Ajoutés', value=', '.join(r.mention for r in added), inline=False)
                if removed:
                    embed.add_field(name='Retirés', value=', '.join(r.mention for r in removed), inline=False)
                await send(bot, embed)
        if before.timed_out_until != after.timed_out_until and after.timed_out_until:
            embed = base_embed('⏳ Mise en timeout (Discord)', 0xE67E22, guild)
            embed.add_field(name='Membre', value=f'{after} ({after.id})', inline=False)
            embed.add_field(name='Jusqu’au', value=discord.utils.format_dt(after.timed_out_until, 'F'))
            await send(bot, embed)

    @bot.event
    async def on_member_ban(guild, user):
        embed = base_embed('🔨 Bannissement (Discord)', 0x992D22, guild)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name='Utilisateur', value=f'{user} ({user.id})', inline=False)
        await send(bot, embed)

    @bot.event
    async def on_member_unban(guild, user):
        embed = base_embed('🕊️ Débannissement (Discord)', 0x2ECC71, guild)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name='Utilisateur', value=f'{user} ({user.id})', inline=False)
        await send(bot, embed)

    @bot.event
    async def on_message_delete(message):
        if not message.guild or message.author.bot:
            return
        embed = base_embed('🗑️ Message supprimé', 0xED4245, message.guild)
        embed.add_field(name='Auteur', value=f'{message.author} ({message.author.id})', inline=False)
        embed.add_field(name='Salon', value=message.channel.mention, inline=False)
        content = message.content or '*(contenu vide ou non mis en cache)*'
        embed.add_field(name='Contenu', value=content[:1000], inline=False)
        if message.attachments:
            embed.add_field(name='Pièces jointes', value='\n'.join(a.url for a in message.attachments)[:1000], inline=False)
        await send(bot, embed)

    @bot.event
    async def on_message_edit(before, after):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = base_embed('📝 Message modifié', 0xFEE75C, before.guild)
        embed.add_field(name='Auteur', value=f'{before.author} ({before.author.id})', inline=False)
        embed.add_field(name='Salon', value=before.channel.mention, inline=False)
        embed.add_field(name='Avant', value=(before.content or '*(vide)*')[:500], inline=False)
        embed.add_field(name='Après', value=(after.content or '*(vide)*')[:500], inline=False)
        embed.add_field(name='Lien', value=after.jump_url, inline=False)
        await send(bot, embed)

    @bot.event
    async def on_voice_state_update(member, before, after):
        if before.channel == after.channel:
            return
        embed = base_embed('🔊 Vocal', 0x5865F2, member.guild)
        embed.add_field(name='Membre', value=f'{member} ({member.id})', inline=False)
        embed.add_field(name='Avant', value=before.channel.mention if before.channel else 'Aucun')
        embed.add_field(name='Après', value=after.channel.mention if after.channel else 'Aucun')
        await send(bot, embed)

    @bot.event
    async def on_guild_channel_create(channel):
        embed = base_embed('➕ Salon créé', 0x57F287, channel.guild)
        embed.add_field(name='Salon', value=f'{channel.mention} ({channel.id})', inline=False)
        embed.add_field(name='Type', value=str(channel.type))
        await send(bot, embed)

    @bot.event
    async def on_guild_channel_delete(channel):
        embed = base_embed('➖ Salon supprimé', 0xED4245, channel.guild)
        embed.add_field(name='Salon', value=f'#{channel.name} ({channel.id})', inline=False)
        embed.add_field(name='Type', value=str(channel.type))
        await send(bot, embed)
