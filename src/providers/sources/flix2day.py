"""
Flix2Day — Highest-coverage streaming provider.

Flow:
  1. ww2.moviesapi.to/api/movie/{tmdb_id}  → JSON with flix2day hash + subtitles
     or  /api/tv/{tmdb_id}/{season}/{episode}
  2. flix2day.xyz/api/v1/video?id={hash}    → AES-CBC encrypted hex
  3. Decrypt with static key/IV             → JSON with CDN source URLs
  4. Return direct HLS m3u8 + Cloudflare CDN stream

Covers virtually ALL movies and TV shows (~100% coverage).
Streams: 1080p + 720p HLS via direct servers and Cloudflare CDN.
"""
from __future__ import annotations
import json
import logging
import re
from urllib.parse import unquote

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from ..base import MediaContext, SourceResult, Stream, Caption
from ..fetcher import Fetcher
from ..runner import register_source

log = logging.getLogger("nautilus.providers.flix2day")

MOVIESAPI_TO = "https://ww2.moviesapi.to"
FLIX2DAY     = "https://flix2day.xyz"

# AES-128-CBC key/IV — derived from flix2day.xyz JS bundle
_AES_KEY = b"kiemtienmua911ca"   # 16 bytes
_AES_IV  = b"1234567890oiuytr"   # 16 bytes


def _decrypt(hex_data: str) -> str:
    """Decrypt AES-CBC encrypted hex response from flix2day API."""
    data = bytes.fromhex(hex_data.strip())
    cipher = Cipher(algorithms.AES(_AES_KEY), modes.CBC(_AES_IV),
                    backend=default_backend())
    decryptor = cipher.decryptor()
    plain = decryptor.update(data) + decryptor.finalize()
    # Remove PKCS7 padding
    pad = plain[-1]
    if 1 <= pad <= 16:
        plain = plain[:-pad]
    return plain.decode("utf-8")


@register_source
class Flix2Day:
    id   = "flix2day"
    name = "Flix2Day"
    rank = 500                  # highest priority — near-universal coverage
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # ── Step 1: get video hash + subtitle data ──
        if ctx.media_type == "movie":
            api_url = f"{MOVIESAPI_TO}/api/movie/{ctx.tmdb_id}"
        else:
            api_url = f"{MOVIESAPI_TO}/api/tv/{ctx.tmdb_id}/{ctx.season}/{ctx.episode}"

        log.info("[flix2day] fetching metadata %s", api_url)
        meta_text = await fetcher.get(api_url, headers={
            "Referer": "https://moviesapi.club/"
        })

        try:
            meta = json.loads(meta_text)
        except (json.JSONDecodeError, ValueError):
            log.warning("[flix2day] invalid JSON from moviesapi.to")
            return SourceResult()

        video_url = meta.get("video_url", "")
        if "#" not in video_url:
            log.warning("[flix2day] no flix2day hash in video_url: %s", video_url[:80])
            return SourceResult()

        # Extract hash: "https://flix2day.xyz/#3un3d1&poster=..." → "3un3d1"
        fragment = video_url.split("#", 1)[1]
        video_hash = fragment.split("&", 1)[0]
        if not video_hash:
            log.warning("[flix2day] empty video hash")
            return SourceResult()

        log.info("[flix2day] video hash: %s", video_hash)

        # ── Step 2: fetch + decrypt video data ──
        encrypted = await fetcher.get(
            f"{FLIX2DAY}/api/v1/video?id={video_hash}",
            headers={"Referer": f"{FLIX2DAY}/"}
        )

        try:
            video_data = json.loads(_decrypt(encrypted))
        except Exception as e:
            log.warning("[flix2day] decryption/parse failed: %s", e)
            return SourceResult()

        # ── Step 3: extract streams ──
        streams = []
        captions = _extract_captions(meta, video_data)

        # Primary: direct HLS source (time-limited signed URL)
        source_url = video_data.get("source", "")
        if source_url:
            log.info("[flix2day] direct source: %s", source_url[:120])
            streams.append(Stream(
                stream_type="hls",
                playlist=source_url,
                captions=captions,
                headers={
                    "Referer": f"{FLIX2DAY}/",
                    "Origin": FLIX2DAY,
                },
            ))

        # Secondary: Cloudflare CDN (usually more stable)
        cf_url = video_data.get("cf", "")
        if cf_url:
            # Add Cloudflare auth params from streamingConfig
            try:
                config = json.loads(video_data.get("streamingConfig", "{}"))
                cf_params = config.get("adjust", {}).get("Cloudflare", {}).get("params", {})
                if cf_params and isinstance(cf_params, dict):
                    sep = "&" if "?" in cf_url else "?"
                    cf_url += sep + "&".join(f"{k}={v}" for k, v in cf_params.items())
            except (json.JSONDecodeError, AttributeError):
                pass

            log.info("[flix2day] cloudflare source: %s", cf_url[:120])
            streams.append(Stream(
                stream_type="hls",
                playlist=cf_url,
                captions=captions,
                headers={
                    "Referer": f"{FLIX2DAY}/",
                    "Origin": FLIX2DAY,
                },
            ))

        if streams:
            log.info("[flix2day] returning %d stream(s)", len(streams))
        else:
            log.warning("[flix2day] no streams found in decrypted data")

        return SourceResult(streams=streams)


def _extract_captions(meta: dict, video_data: dict) -> list[Caption]:
    """Extract subtitles from both moviesapi.to metadata and flix2day video data."""
    captions = []
    seen = set()

    # 1. From flix2day video data (higher quality — VTT with proper paths)
    subs = video_data.get("subtitle", {})
    if isinstance(subs, dict):
        for lang, path in subs.items():
            # Path like "/token/path/en.vtt#en" — strip anchor
            vtt_path = path.split("#")[0]
            if vtt_path and vtt_path not in seen:
                # Build full URL using flix2day domain
                url = f"{FLIX2DAY}{vtt_path}" if vtt_path.startswith("/") else vtt_path
                captions.append(Caption(url=url, lang=lang, format="vtt"))
                seen.add(vtt_path)

    # 2. From moviesapi.to metadata (OpenSubtitles links)
    raw_subs = meta.get("subtitles", [])
    if isinstance(raw_subs, str):
        # URL-encoded JSON array in the video_url fragment
        try:
            frag = meta.get("video_url", "")
            if "subs=" in frag:
                subs_encoded = frag.split("subs=", 1)[1]
                raw_subs = json.loads(unquote(subs_encoded))
        except (json.JSONDecodeError, ValueError):
            raw_subs = []

    if isinstance(raw_subs, list):
        for sub in raw_subs:
            url = sub.get("url", "")
            label = sub.get("label", "")
            lang = _label_to_iso(label) if label else "unknown"
            if url and url not in seen:
                captions.append(Caption(url=url, lang=lang, format="srt"))
                seen.add(url)

    return captions


_LANG_MAP = {
    "english": "en", "spanish": "es", "portuguese": "pt",
    "portuguese (br)": "pt", "french": "fr", "german": "de",
    "italian": "it", "dutch": "nl", "russian": "ru",
    "japanese": "ja", "korean": "ko", "chinese": "zh",
    "arabic": "ar", "turkish": "tr", "greek": "el",
    "czech": "cs", "danish": "da", "finnish": "fi",
    "norwegian": "no", "swedish": "sv", "hungarian": "hu",
    "polish": "pl", "romanian": "ro", "croatian": "hr",
    "slovenian": "sl", "bulgarian": "bg", "serbian": "sr",
    "hebrew": "he", "thai": "th", "indonesian": "id",
    "malay": "ms", "vietnamese": "vi", "hindi": "hi",
    "icelandic": "is", "bengali": "bn",
}


def _label_to_iso(label: str) -> str:
    lower = label.strip().lower()
    return _LANG_MAP.get(lower, lower[:2])
