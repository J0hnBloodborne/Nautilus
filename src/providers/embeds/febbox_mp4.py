"""
Febbox MP4 — showbox API → quality list → direct MP4 streams.
Depends on showbox sendRequest crypto.
"""
from __future__ import annotations
import hashlib, json, time, random, string, base64
from ..base import EmbedResult, Stream, StreamFile, Caption
from ..fetcher import Fetcher
from ..runner import register_embed

# Showbox / Febbox crypto constants
_IV = base64.b64decode("d0VpcGhUbiE=").decode()  # "wEiphTn!"
_KEY = base64.b64decode("MTIzZDZjZWRmNjI2ZHk1NDIzM2FhMXc2").decode()
_API_URLS = [
    base64.b64decode("aHR0cHM6Ly9zaG93Ym94LnNoZWd1Lm5ldC9hcGkvYXBpX2NsaWVudC9pbmRleC8=").decode(),
    base64.b64decode("aHR0cHM6Ly9tYnBhcGkuc2hlZ3UubmV0L2FwaS9hcGlfY2xpZW50L2luZGV4Lw==").decode(),
]
_APP_KEY = base64.b64decode("bW92aWVib3g=").decode()  # "moviebox"
_APP_ID = base64.b64decode("Y29tLnRkby5zaG93Ym94").decode()

ALLOWED_QUALITIES = ["360", "480", "720", "1080", "4k"]


def _3des_encrypt(plaintext: str) -> str:
    """Triple DES encrypt (CryptoJS-compatible)."""
    try:
        from Crypto.Cipher import DES3
        from Crypto.Util.Padding import pad
        key_bytes = _KEY.encode("utf-8")[:24]
        iv_bytes = _IV.encode("utf-8")[:8]
        cipher = DES3.new(key_bytes, DES3.MODE_CBC, iv_bytes)
        padded = pad(plaintext.encode("utf-8"), 8)
        encrypted = cipher.encrypt(padded)
        return base64.b64encode(encrypted).decode()
    except ImportError:
        raise RuntimeError("pycryptodome required: pip install pycryptodome")


def _get_verify(enc_data: str, app_key: str, key: str):
    if enc_data:
        inner = hashlib.md5(app_key.encode()).hexdigest()
        return hashlib.md5((inner + key + enc_data).encode()).hexdigest()
    return None


def _random_hex(n=32):
    return "".join(random.choices("0123456789abcdef", k=n))


async def _send_request(fetcher: Fetcher, data: dict, alt_api=False) -> dict:
    """Send encrypted request to showbox/febbox API."""
    default_data = {
        "childmode": "0",
        "app_version": "11.5",
        "appid": _APP_ID,
        "lang": "en",
        "expired_date": str(int(time.time()) + 60 * 60 * 12),
        "platform": "android",
        "channel": "Website",
    }
    merged = {**default_data, **data}
    enc_data = _3des_encrypt(json.dumps(merged))
    app_key_hash = hashlib.md5(_APP_KEY.encode()).hexdigest()
    verify = _get_verify(enc_data, _APP_KEY, _KEY)

    body = json.dumps({"app_key": app_key_hash, "verify": verify, "encrypt_data": enc_data})
    b64_body = base64.b64encode(body.encode()).decode()

    form_data = {
        "data": b64_body,
        "appid": "27",
        "platform": "android",
        "version": "129",
        "medium": "Website",
        "token": _random_hex(32),
    }

    api_url = _API_URLS[1] if alt_api else _API_URLS[0]
    resp_text = await fetcher.post(
        api_url,
        data=form_data,
        headers={
            "Platform": "android",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "okhttp/3.2.0",
        },
    )
    return json.loads(resp_text)


def _parse_input_url(url: str):
    """Parse /movie/id or /show/id/season/episode."""
    parts = url.strip("/").split("/")
    media_type = parts[0] if parts else "movie"
    mid = parts[1] if len(parts) > 1 else ""
    season = int(parts[2]) if len(parts) > 2 and parts[2] else None
    episode = int(parts[3]) if len(parts) > 3 and parts[3] else None
    return media_type, mid, season, episode


@register_embed
class FebboxMp4:
    id = "febbox-mp4"
    name = "Febbox (MP4)"
    rank = 190

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        media_type, mid, season, episode = _parse_input_url(url)

        if media_type == "movie":
            api_query = {"uid": "", "module": "Movie_downloadurl_v3", "mid": mid, "oss": "1", "group": ""}
        else:
            api_query = {
                "uid": "", "module": "TV_downloadurl_v3",
                "tid": mid, "season": str(season or 1),
                "episode": str(episode or 1), "oss": "1", "group": "",
            }

        media_res = await _send_request(fetcher, api_query)
        quality_list = media_res.get("data", {}).get("list", [])

        qualities = []
        for q in quality_list:
            real_q = q.get("real_quality", "").replace("p", "").lower()
            path = q.get("path", "")
            if real_q in ALLOWED_QUALITIES and path:
                qualities.append(StreamFile(url=path, quality=real_q))

        if not qualities:
            raise ValueError("Febbox MP4: no qualities found")

        return EmbedResult(streams=[
            Stream(stream_type="file", qualities=qualities)
        ])
