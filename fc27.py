import logging
import re
import time
from html import unescape

import discord
import requests
from discord.ext import commands

log = logging.getLogger('lyra_bot.fc27')

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; LyraBot/1.0)'}
CACHE_TTL = 1200  # 20 minutes

NEWS_URL = 'https://www.ea.com/games/ea-sports-fc/fc-27/news'
MAX_ARTICLES_CHECKED = 8

SBC_LIST_URL = 'https://www.fut.gg/sbc/'
SBC_ITEM_PREFIX = 'https://www.fut.gg/sbc/challenges/'

_news_cache = {'time': 0, 'articles': []}
_sbc_cache = {'time': 0, 'entries': []}


def _fetch_news_slugs():
    resp = requests.get(NEWS_URL, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    slugs = []
    for slug in re.findall(r'news/([a-z0-9-]+)', resp.text):
        if slug not in slugs:
            slugs.append(slug)
    return slugs[:MAX_ARTICLES_CHECKED]


def _fetch_article(slug):
    url = f'{NEWS_URL}/{slug}'
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    title_match = re.search(r'<title[^>]*>([^<]*)</title>', resp.text)
    date_match = re.search(r'<meta content="([^"]+)" property="article:published_time"', resp.text)
    return {
        'title': unescape(title_match.group(1)) if title_match else slug,
        'url': url,
        'published': date_match.group(1) if date_match else '',
    }


def _refresh_news():
    articles = []
    for slug in _fetch_news_slugs():
        try:
            articles.append(_fetch_article(slug))
        except requests.RequestException:
            log.warning('Article FC 27 illisible : %s', slug, exc_info=True)
    articles.sort(key=lambda a: a['published'], reverse=True)
    _news_cache['articles'] = articles
    _news_cache['time'] = time.time()


def _fetch_sbc_challenges():
    resp = requests.get(SBC_LIST_URL, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    html = resp.text
    images = {}
    for m in re.finditer(r'href="(https://game-assets\.fut\.gg/[^"]*?/sbcs/(\d+)\.png)"', html):
        images.setdefault(m.group(2), m.group(1))
    entries, seen = [], set()
    pattern = re.compile(r'href="/sbc/challenges/([a-z0-9-]+)/"(?:(?!</a>).)*?<h3[^>]*>([^<]+)</h3>', re.S)
    for m in pattern.finditer(html):
        slug, title = m.group(1), unescape(m.group(2))
        if slug in seen:
            continue
        seen.add(slug)
        id_match = re.match(r'\d+-(\d+)-', slug)
        image = images.get(id_match.group(1)) if id_match else None
        entries.append({'title': title, 'url': f'{SBC_ITEM_PREFIX}{slug}/', 'image': image})
    return entries


def _refresh_sbc():
    _sbc_cache['entries'] = _fetch_sbc_challenges()
    _sbc_cache['time'] = time.time()


async def get_news(loop, limit=5):
    if time.time() - _news_cache['time'] > CACHE_TTL:
        await loop.run_in_executor(None, _refresh_news)
    return _news_cache['articles'][:limit]


async def get_sbc(loop, limit=5):
    if time.time() - _sbc_cache['time'] > CACHE_TTL:
        await loop.run_in_executor(None, _refresh_sbc)
    return _sbc_cache['entries'][:limit]


def register(bot):
    @bot.command(name='fc27', help='Voir les dernières actus officielles d’EA SPORTS FC 27.')
    async def fc27(ctx: commands.Context):
        await ctx.defer()
        try:
            articles = await get_news(bot.loop)
        except Exception:
            log.warning('Récupération des actus FC 27 échouée', exc_info=True)
            await ctx.send('Impossible de récupérer les actus FC 27 pour le moment.')
            return
        if not articles:
            await ctx.send('Aucune actu trouvée pour le moment.')
            return
        embed = discord.Embed(title='⚽ Actus EA SPORTS FC 27', color=0x00A650, url=NEWS_URL)
        for a in articles:
            date = a['published'][:10] if a['published'] else '?'
            embed.add_field(name=f"{date} — {a['title']}", value=a['url'], inline=False)
        embed.set_footer(text='Source : ea.com (officiel)')
        await ctx.send(embed=embed)

    @bot.command(name='sbc', help='Voir les SBC (Squad Building Challenges) actifs, avec image.')
    async def sbc(ctx: commands.Context):
        await ctx.defer()
        try:
            entries = await get_sbc(bot.loop)
        except Exception:
            log.warning('Récupération des SBC échouée', exc_info=True)
            await ctx.send('Impossible de récupérer les SBC pour le moment.')
            return
        if not entries:
            await ctx.send(f'Aucun SBC actif trouvé. Voir directement : {SBC_LIST_URL}')
            return
        embeds = []
        for e in entries:
            embed = discord.Embed(title=e['title'], url=e['url'], color=0x00A650)
            if e['image']:
                embed.set_image(url=e['image'])
            embeds.append(embed)
        embeds[-1].set_footer(text='Source : FUT.GG (non officiel, mis à jour toutes les 20 min)')
        await ctx.send(embeds=embeds)
