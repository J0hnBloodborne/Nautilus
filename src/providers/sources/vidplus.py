"""
VidPlus — Streaming provider via player.vidplus.to API.

Flow:
  1. /api/server?id={tmdb_id}&sr={server}&args={title}*{year}*{imdb_id}
  2. Response JSON has encrypted 'data' field (base64 → AES-256-CBC)
  3. Encryption is self-decrypting: key, salt, iv, iterations are in the payload
  4. Decrypted JSON contains HLS playlist (.txt) or MP4 URLs + subtitle tracks

Servers:
  - sr=5: HLS via claravonartisan.sbs (M3U8 playlists disguised as .txt)
  - sr=3: MP4 via hakunaymatata.com (multiple qualities, needs Referer)
  - sr=1: HLS via Asia CDN (sometimes unavailable)
  - sr=2: HLS fallback (sometimes 403)

Priority: HLS (server 5) first, then file/MP4 (server 3) as fallback.
"""
from __future__ import annotations
import json
import logging
import base64
import re
from binascii import unhexlify
from urllib.parse import quote, unquote

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ..base import MediaContext, SourceResult, Stream, StreamFile, Caption
from ..fetcher import Fetcher
from ..runner import register_source

log = logging.getLogger("nautilus.providers.vidplus")

VIDPLUS_API = "https://player.vidplus.to"

# Server order: prefer HLS, fallback to MP4
_SERVERS = [5, 3, 1, 2, 4]


def _decrypt_response(encrypted_b64: str) -> dict:
    """
    Decrypt vidplus.to AES-256-CBC response.
    The base64 payload contains the key alongside the ciphertext (self-decrypting).
    """
    obj = json.loads(base64.b64decode(encrypted_b64))

    salt = unhexlify(obj["salt"])
    iv = unhexlify(obj["iv"])
    iterations = obj["iterations"]
    key_password = obj["key"].encode("utf-8")

    # PBKDF2-SHA256 key derivation (CryptoJS keySize=8 = 32 bytes)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=default_backend(),
    )
    derived_key = kdf.derive(key_password)

    # AES-256-CBC decrypt
    cipher = Cipher(
        algorithms.AES(derived_key),
        modes.CBC(iv),
        backend=default_backend(),
    )
    decryptor = cipher.decryptor()
    ciphertext = base64.b64decode(obj["encryptedData"])
    decrypted_padded = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove PKCS7 padding
    unpadder = sym_padding.PKCS7(128).unpadder()
    decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()

    return json.loads(decrypted.decode("utf-8"))


def _extract_direct_url(proxy_url: str) -> tuple[str, dict]:
    """
    Extract actual MP4 URL from worker-mp4-proxy wrapper.
    Returns (direct_url, {required_headers}).
    """
    url_match = re.search(r"url=([^&]+)", proxy_url)
    referer_match = re.search(r"referer=([^&]+)", proxy_url)

    if not url_match:
        return proxy_url, {}

    direct = unquote(url_match.group(1))
    referer = unquote(referer_match.group(1)) if referer_match else ""

    headers = {}
    if referer:
        headers["Referer"] = referer
        # Origin = scheme + host of referer
        origin_match = re.match(r"(https?://[^/]+)", referer)
        if origin_match:
            headers["Origin"] = origin_match.group(1)

    return direct, headers


def _extract_captions(result: dict) -> list[Caption]:
    """Extract subtitle tracks from vidplus decrypted data."""
    captions = []
    seen = set()

    tracks = result.get("tracks", [])
    if not isinstance(tracks, list):
        return captions

    for track in tracks:
        if not isinstance(track, dict):
            continue
        url = track.get("url", "")
        lang_label = track.get("lang", "Unknown")
        if not url or url in seen:
            continue
        seen.add(url)

        # Parse lang label: "English - FlowCast" → lang="en"
        lang_name = lang_label.split(" - ")[0].strip()
        lang_code = _label_to_iso(lang_name)

        # Determine format from URL
        fmt = "vtt" if ".vtt" in url else "srt"

        captions.append(Caption(url=url, lang=lang_code, format=fmt))

    return captions


@register_source
class VidPlus:
    id = "vidplus"
    name = "VidPlus"
    rank = 450               # high priority — good coverage, multi-quality
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        streams = []

        # Build args param: title*year*imdb_id
        args_parts = []
        if ctx.title:
            args_parts.append(ctx.title)
        args_parts.append(str(ctx.year) if ctx.year else "0")
        if ctx.imdb_id:
            args_parts.append(ctx.imdb_id)
        args = "*".join(args_parts)

        for sr in _SERVERS:
            try:
                stream = await self._try_server(ctx, fetcher, sr, args)
                if stream:
                    streams.append(stream)
                    # If we got HLS, that's ideal — still try more for fallbacks
                    if stream.stream_type == "hls" and len(streams) >= 2:
                        break
            except Exception as e:
                log.debug("[vidplus] Server %d failed: %s", sr, e)
                continue

        if streams:
            log.info("[vidplus] Returning %d stream(s)", len(streams))
        else:
            log.warning("[vidplus] No streams found for TMDB %d", ctx.tmdb_id)

        return SourceResult(streams=streams)

    async def _try_server(
        self, ctx: MediaContext, fetcher: Fetcher, sr: int, args: str
    ) -> Stream | None:
        # Build API URL
        api_url = f"{VIDPLUS_API}/api/server?id={ctx.tmdb_id}&sr={sr}"
        if ctx.media_type == "tv":
            api_url += f"&ep={ctx.episode}&ss={ctx.season}"
        if args:
            api_url += f"&args={quote(args)}"

        log.info("[vidplus] Trying server %d: %s", sr, api_url)

        resp_text = await fetcher.get(api_url, headers={
            "Referer": f"{VIDPLUS_API}/embed/movie/{ctx.tmdb_id}",
        })

        try:
            resp = json.loads(resp_text)
        except (json.JSONDecodeError, ValueError):
            log.debug("[vidplus] Server %d: invalid JSON", sr)
            return None

        if "error" in resp:
            log.debug("[vidplus] Server %d: %s", sr, resp["error"])
            return None

        if "data" not in resp:
            log.debug("[vidplus] Server %d: no data field", sr)
            return None

        # Decrypt
        try:
            result = _decrypt_response(resp["data"])
        except Exception as e:
            log.warning("[vidplus] Server %d decrypt failed: %s", sr, e)
            return None

        video_url = result.get("url", "")
        if not video_url:
            return None

        captions = _extract_captions(result)
        has_txt = result.get("_hasTxtFiles", False)

        # ── HLS stream (server 5 typically returns .txt M3U8 playlists) ──
        if has_txt or video_url.endswith(".txt"):
            log.info("[vidplus] Server %d: HLS playlist at %s", sr, video_url[:80])
            return Stream(
                stream_type="hls",
                playlist=video_url,
                captions=captions,
            )

        # ── Check if direct URL is M3U8 ──
        if ".m3u8" in video_url:
            log.info("[vidplus] Server %d: direct M3U8 at %s", sr, video_url[:80])
            return Stream(
                stream_type="hls",
                playlist=video_url,
                captions=captions,
            )

        # ── MP4 file stream (server 3 typically) ──
        qualities_data = result.get("quality", [])
        if isinstance(qualities_data, list) and qualities_data:
            quality_files = []
            headers = {}

            for q in qualities_data:
                if not isinstance(q, dict):
                    continue
                q_url = q.get("url", "")
                q_label = str(q.get("label", q.get("quality", "unknown")))

                # Extract direct URL from worker proxy wrapper
                if "worker-mp4-proxy" in q_url or "workers.dev" in q_url:
                    q_url, headers = _extract_direct_url(q_url)

                if q_url:
                    quality_files.append(StreamFile(url=q_url, quality=q_label))

            if quality_files:
                log.info("[vidplus] Server %d: %d MP4 qualities", sr, len(quality_files))
                return Stream(
                    stream_type="file",
                    qualities=quality_files,
                    captions=captions,
                    headers=headers,
                )

        # ── Single MP4 URL fallback ──
        if "worker-mp4-proxy" in video_url or "workers.dev" in video_url:
            direct_url, headers = _extract_direct_url(video_url)
        else:
            direct_url, headers = video_url, {}

        if direct_url:
            log.info("[vidplus] Server %d: single MP4 at %s", sr, direct_url[:80])
            return Stream(
                stream_type="file",
                qualities=[StreamFile(url=direct_url, quality="unknown")],
                captions=captions,
                headers=headers,
            )

        return None


# ── Language mapping ──
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
    "vietnamese": "vi", "hindi": "hi", "filipino": "fil",
    "bengali": "bn", "urdu": "ur", "persian": "fa",
    "unknown": "und",
}


def _label_to_iso(label: str) -> str:
    """Convert a language name to ISO 639-1 code."""
    lower = label.strip().lower()
    if lower in _LANG_MAP:
        return _LANG_MAP[lower]
    # Try first two chars as code
    if len(lower) == 2:
        return lower
    return "und"
