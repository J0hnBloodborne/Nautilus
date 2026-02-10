"""
WarezCDN embed common — decrypt stream ID from player page.
"""
from __future__ import annotations
import re, json, base64
from ..fetcher import Fetcher

WAREZCDN_PLAYER_BASE = "https://warezcdn.com/player"
WAREZCDN_EMBED_BASE = "https://warezcdn.com/embed"


def _decrypt_warezcdn(input_str: str) -> str:
    """Base64 decode, trim, reverse, splice last-5-chars trick."""
    output = base64.b64decode(input_str).decode("utf-8").strip()
    output = output[::-1]  # reverse
    last5 = output[-5:][::-1]  # last 5 reversed
    output = output[:-5] + last5
    return output


async def get_decrypted_id(embed_url: str, fetcher: Fetcher) -> str:
    """Fetch player page, extract allowanceKey, POST for stream ID, decrypt."""
    from urllib.parse import urlencode

    referer_params = urlencode({"id": embed_url, "sv": "warezcdn"})
    referer = f"{WAREZCDN_EMBED_BASE}/getEmbed.php?{referer_params}"

    page = await fetcher.get(
        f"{WAREZCDN_PLAYER_BASE}/player.php",
        params={"id": embed_url},
        headers={"Referer": referer},
    )

    ak_m = re.search(r'let allowanceKey = "([^"]+)"', page)
    if not ak_m:
        raise ValueError("WarezCDN: allowanceKey not found")

    stream_data = await fetcher.post(
        f"{WAREZCDN_PLAYER_BASE}/functions.php",
        data={"getVideo": embed_url, "key": ak_m.group(1)},
    )

    stream = json.loads(stream_data)
    if not stream.get("id"):
        raise ValueError("WarezCDN: no stream id")

    return _decrypt_warezcdn(stream["id"])
