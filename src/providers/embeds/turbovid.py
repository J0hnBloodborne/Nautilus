"""Turbovid — encrypted stream decoding via juice_key."""
from __future__ import annotations
import re, json
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed


def _hex_to_char(hex_str: str) -> str:
    return "".join(chr(int(hex_str[i:i+2], 16)) for i in range(0, len(hex_str), 2))


def _decrypt(data: str, key: str) -> str:
    result = []
    for i, ch in enumerate(data):
        key_char = key[i % len(key)]
        result.append(chr(ord(ch) ^ ord(key_char)))
    return "".join(result)


@register_embed
class Turbovid:
    id = "turbovid"
    name = "Turbovid"
    rank = 122

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        from urllib.parse import urlparse
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        html = await fetcher.get(url)

        apkey_m = re.search(r'const\s+apkey\s*=\s*"([^"]+)"', html)
        xxid_m = re.search(r'const\s+xxid\s*=\s*"([^"]+)"', html)
        if not apkey_m or not xxid_m:
            raise Exception("Turbovid apkey/xxid not found")

        apkey = apkey_m.group(1)
        xxid = xxid_m.group(1)

        # Get juice key
        key_text = await fetcher.get(f"{base_url}/api/cucked/juice_key",
                                     headers={"Referer": url})
        try:
            juice_key = json.loads(key_text).get("juice", "")
        except Exception:
            raise Exception("Turbovid juice_key parse failed")

        # Get encrypted data
        data_text = await fetcher.get(f"{base_url}/api/cucked/the_juice/",
                                      headers={"Referer": url},
                                      params={apkey: xxid})
        try:
            enc_data = json.loads(data_text).get("data", "")
        except Exception:
            raise Exception("Turbovid data parse failed")

        playlist = _decrypt(enc_data, juice_key)
        if not playlist or "m3u8" not in playlist:
            # Try hex decode first
            try:
                playlist = _decrypt(_hex_to_char(enc_data), juice_key)
            except Exception:
                raise Exception("Turbovid decrypt failed")

        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=playlist,
                   headers={"Referer": f"{base_url}/", "Origin": base_url})
        ])
