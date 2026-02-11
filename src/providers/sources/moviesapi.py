"""
MoviesAPI — scrapes moviesapi.club → vidora.stream for direct HLS streams.

Flow:
  1. moviesapi.club/movie/{tmdb_id}  → HTML with vidora.stream iframe
  2. vidora.stream/embed/{code}      → HTML with packed eval(p,a,c,k,e,d) JS
  3. Unpack the JS → extract JW Player sources[] → HLS m3u8 URL

This is currently one of the most reliable providers — no Cloudflare
or VRF tokens needed, just HTML scraping + JS unpacking.
"""
from __future__ import annotations
import re
import logging

from ..base import MediaContext, SourceResult, Stream, Caption
from ..fetcher import Fetcher
from ..runner import register_source
from ..unpacker import detect, unpack

log = logging.getLogger("nautilus.providers.moviesapi")

BASE = "https://moviesapi.club"
VIDORA = "https://vidora.stream"


@register_source
class MoviesAPI:
    id = "moviesapi"
    name = "MoviesAPI"
    rank = 400                            # highest priority — actually works
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # ── Step 1: get embed iframe URL from moviesapi.club ──
        if ctx.media_type == "movie":
            page_url = f"{BASE}/movie/{ctx.tmdb_id}"
        else:
            page_url = f"{BASE}/tv/{ctx.tmdb_id}-{ctx.season}-{ctx.episode}"

        log.info("[moviesapi] fetching %s", page_url)
        html = await fetcher.get(page_url, headers={"Referer": f"{BASE}/"})

        # Find vidora.stream iframe
        iframes = re.findall(r'src=["\']([^"\']*vidora\.stream[^"\']*)["\']', html)
        if not iframes:
            # Also try other embed patterns
            iframes = re.findall(r'src=["\']([^"\']*(?:filemoon|streamwish|upstream|dood)[^"\']*)["\']', html)
            if not iframes:
                log.warning("[moviesapi] no embed iframe found")
                return SourceResult()

        embed_url = iframes[0]
        if not embed_url.startswith("http"):
            embed_url = "https:" + embed_url

        log.info("[moviesapi] found embed: %s", embed_url)

        # ── Step 2: fetch the embed page ──
        embed_html = await fetcher.get(
            embed_url,
            headers={"Referer": page_url},
        )

        # ── Step 3: unpack eval(p,a,c,k,e,d) and extract HLS URL ──
        streams = []
        captions = []

        if detect(embed_html):
            unpacked = unpack(embed_html)
            log.debug("[moviesapi] unpacked %d chars", len(unpacked))
        else:
            unpacked = embed_html
            log.debug("[moviesapi] no packed JS found, using raw HTML")

        # Extract m3u8 URLs from JW Player sources or file attributes
        m3u8_urls = re.findall(
            r'(?:file|src|source)\s*[=:]\s*["\']'
            r'(https?://[^\s"\']+\.m3u8[^\s"\']*)["\']',
            unpacked,
        )

        if not m3u8_urls:
            # Also try broader pattern
            m3u8_urls = re.findall(
                r'(https?://[^\s"\'\\]+\.m3u8[^\s"\'\\]*)',
                unpacked,
            )

        if m3u8_urls:
            hls_url = m3u8_urls[0]
            log.info("[moviesapi] found HLS: %s", hls_url[:120])

            # Extract captions / subtitles (VTT files)
            vtt_matches = re.findall(
                r'file:\s*["\']'
                r'(https?://[^\s"\']+\.(?:vtt|srt)[^\s"\']*)["\']'
                r'[^}]*?label:\s*["\']([^"\']+)["\']',
                unpacked,
            )
            if not vtt_matches:
                # Fallback: just grab all VTT urls and their labels
                vtt_blocks = re.findall(
                    r'\{[^}]*?file:\s*["\']'
                    r'(https?://[^\s"\']+\.(?:vtt|srt)[^\s"\']*)["\']'
                    r'[^}]*?label:\s*["\']([^"\']+)["\']'
                    r'[^}]*?\}',
                    unpacked,
                )
                vtt_matches = vtt_blocks

            for vtt_url, label in vtt_matches:
                # Skip thumbnails / slider VTTs
                if "sli" in vtt_url or "thumb" in label.lower():
                    continue
                # Guess ISO lang code from label
                lang = _label_to_lang(label)
                fmt = "vtt" if ".vtt" in vtt_url else "srt"
                captions.append(Caption(url=vtt_url, lang=lang, format=fmt))

            streams.append(Stream(
                stream_type="hls",
                playlist=hls_url,
                captions=captions,
                headers={"Referer": embed_url, "Origin": VIDORA},
            ))

        # Also check for direct mp4
        if not streams:
            mp4_urls = re.findall(
                r'(https?://[^\s"\'\\]+\.mp4[^\s"\'\\]*)',
                unpacked,
            )
            if mp4_urls:
                from ..base import StreamFile
                streams.append(Stream(
                    stream_type="file",
                    qualities=[StreamFile(url=mp4_urls[0], quality="unknown")],
                    captions=captions,
                    headers={"Referer": embed_url},
                ))

        if streams:
            log.info("[moviesapi] returning %d stream(s)", len(streams))
        else:
            log.warning("[moviesapi] no streams extracted from %s", embed_url)

        return SourceResult(streams=streams)


# ── Utility ──────────────────────────────────────────────

_LANG_MAP = {
    "english": "en", "spanish": "es", "portuguese": "pt",
    "french": "fr", "german": "de", "italian": "it",
    "dutch": "nl", "russian": "ru", "japanese": "ja",
    "korean": "ko", "chinese": "zh", "arabic": "ar",
    "turkish": "tr", "greek": "el", "czech": "cs",
    "danish": "da", "finnish": "fi", "norwegian": "no",
    "swedish": "sv", "hungarian": "hu", "polish": "pl",
    "romanian": "ro", "croatian": "hr", "slovenian": "sl",
    "bulgarian": "bg", "serbian": "sr", "hebrew": "he",
    "thai": "th", "indonesian": "id", "malay": "ms",
    "vietnamese": "vi", "hindi": "hi", "bengali": "bn",
}


def _label_to_lang(label: str) -> str:
    """Convert subtitle label like 'English' to ISO 639-1 code."""
    lower = label.strip().lower()
    return _LANG_MAP.get(lower, lower[:2])
