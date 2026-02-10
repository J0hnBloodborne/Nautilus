"""
Primewire — Blowfish decryption of embed links, IMDB-based.
Enabled, rank 110. Delegates to mixdrop/voe/upstream/streamvid/dood/dropload/filelions/vtube.
"""
from __future__ import annotations
import re, base64, struct
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

PW_BASE = "https://primewire.tf"
PW_API_KEY = base64.b64decode("bHpRUHNYU0tjRw==").decode()  # 'lzQPsXSKcG'

# ─── Blowfish cipher (pure Python) ──────────────────────────────────
_SBOX0 = [
    0xd1310ba6,0x98dfb5ac,0x2ffd72db,0xd01adfb7,0xb8e1afed,0x6a267e96,0xba7c9045,0xf12c7f99,
    0x24a19947,0xb3916cf7,0x0801f2e2,0x858efc16,0x636920d8,0x71574e69,0xa458fea3,0xf4933d7e,
    0x0d95748f,0x728eb658,0x718bcd58,0x82154aee,0x7b54a41d,0xc25a59b5,0x9c30d539,0x2af26013,
    0xc5d1b023,0x286085f0,0xca417918,0xb8db38ef,0x8e79dcb0,0x603a180e,0x6c9e0e8b,0xb01e8a3e,
    0xd71577c1,0xbd314b27,0x78af2fda,0x55605c60,0xe65525f3,0xaa55ab94,0x57489862,0x63e81440,
    0x55ca396a,0x2aab10b6,0xb4cc5c34,0x1141e8ce,0xa15486af,0x7c72e993,0xb3ee1411,0x636fbc2a,
    0x2ba9c55d,0x741831f6,0xce5c3e16,0x9b87931e,0xafd6ba33,0x6c24cf5c,0x7a325381,0x28958677,
    0x3b8f4898,0x6b4bb9af,0xc4bfe81b,0x66282193,0x61d809cc,0xfb21a991,0x487cac60,0x5dec8032,
    0xef845d5d,0xe98575b1,0xdc262302,0xeb651b88,0x23893e81,0xd396acc5,0x0f6d6ff3,0x83f44239,
    0x2e0b4482,0xa4842004,0x69c8f04a,0x9e1f9b5e,0x21c66842,0xf6e96c9a,0x670c9c61,0xabd388f0,
    0x6a51a0d2,0xd8542f68,0x960fa728,0xab5133a3,0x6eef0b6c,0x137a3be4,0xba3bf050,0x7efb2a98,
    0xa1f1651d,0x39af0176,0x66ca593e,0x82430e88,0x8cee8619,0x456f9fb4,0x7d84a5c3,0x3b8b5ebe,
    0xe06f75d8,0x85c12073,0x401a449f,0x56c16aa6,0x4ed3aa62,0x363f7706,0x1bfedf72,0x429b023d,
    0x37d0d724,0xd00a1248,0xdb0fead3,0x49f1c09b,0x075372c9,0x80991b7b,0x25d479d8,0xf6e8def7,
    0xe3fe501a,0xb6794c3b,0x976ce0bd,0x04c006ba,0xc1a94fb6,0x409f60c4,0x5e5c9ec2,0x196a2463,
    0x68fb6faf,0x3e6c53b5,0x1339b2eb,0x3b52ec6f,0x6dfc511f,0x9b30952c,0xcc814544,0xaf5ebd09,
    0xbee3d004,0xde334afd,0x660f2807,0x192e4bb3,0xc0cba857,0x45c8740f,0xd20b5f39,0xb9d3fbdb,
    0x5579c0bd,0x1a60320a,0xd6a100c6,0x402c7279,0x679f25fe,0xfb1fa3cc,0x8ea5e9f8,0xdb3222f8,
    0x3c7516df,0xfd616b15,0x2f501ec8,0xad0552ab,0x323db5fa,0xfd238760,0x53317b48,0x3e00df82,
    0x9e5c57bb,0xca6f8ca0,0x1a87562e,0xdf1769db,0xd542a8f6,0x287effc3,0xac6732c6,0x8c4f5573,
    0x695b27b0,0xbbca58c8,0xe1ffa35d,0xb8f011a0,0x10fa3d98,0xfd2183b8,0x4afcb56c,0x2dd1d35b,
    0x9a53e479,0xb6f84565,0xd28e49bc,0x4bfb9790,0xe1ddf2da,0xa4cb7e33,0x62fb1341,0xcee4c6e8,
    0xef20cada,0x36774c01,0xd07e9efe,0x2bf11fb4,0x95dbda4d,0xae909198,0xeaad8e71,0x6b93d5a0,
    0xd08ed1d0,0xafc725e0,0x8e3c5b2f,0x8e7594b7,0x8ff6e2fb,0xf2122b64,0x8888b812,0x900df01c,
    0x4fad5ea0,0x688fc31c,0xd1cff191,0xb3a8c1ad,0x2f2f2218,0xbe0e1777,0xea752dfe,0x8b021fa1,
    0xe5a0cc0f,0xb56f74e8,0x18acf3d6,0xce89e299,0xb4a84fe0,0xfd13e0b7,0x7cc43b81,0xd2ada8d9,
    0x165fa266,0x80957705,0x93cc7314,0x211a1477,0xe6ad2065,0x77b5fa86,0xc75442f5,0xfb9d35cf,
    0xebcdaf0c,0x7b3e89a0,0xd6411bd3,0xae1e7e49,0x00250e2d,0x2071b35e,0x226800bb,0x57b8e0af,
    0x2464369b,0xf009b91e,0x5563911d,0x59dfa6aa,0x78c14389,0xd95a537f,0x207d5ba2,0x02e5b9c5,
    0x83260376,0x6295cfa9,0x11c81968,0x4e734a41,0xb3472dca,0x7b14a94a,0x1b510052,0x9a532915,
    0xd60f573f,0xbc9bc6e4,0x2b60a476,0x81e67400,0x08ba6fb5,0x571be91f,0xf296ec6b,0x2a0dd915,
    0xb6636521,0xe7b9f9b6,0xff34052e,0xc5855664,0x53b02d5d,0xa99f8fa1,0x08ba4799,0x6e85076a,
]

_P_INIT = [
    0x243f6a88,0x85a308d3,0x13198a2e,0x03707344,0xa4093822,0x299f31d0,
    0x082efa98,0xec4e6c89,0x452821e6,0x38d01377,0xbe5466cf,0x34e90c6c,
    0xc0ac29b7,0xc97c50dd,0x3f84d5b5,0xb5470917,0x9216d5d9,0x8979fb1b,
]

KEY_STR = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
M = 0xFFFFFFFF


class _Blowfish:
    def __init__(self, key: str):
        self.s = [list(_SBOX0) for _ in range(4)]  # 4 copies
        self.p = list(_P_INIT)
        self._generate_subkeys(key)

    def _f(self, x):
        d = x & 0xFF
        x >>= 8
        c = x & 0xFF
        x >>= 8
        b = x & 0xFF
        a = (x >> 8) & 0xFF
        r = (self.s[0][a] + self.s[1][b]) & M
        r ^= self.s[2][c]
        r = (r + self.s[3][d]) & M
        return r

    def _block_encrypt(self, l, r):
        for i in range(16):
            l ^= self.p[i]
            l &= M
            r ^= self._f(l)
            r &= M
            l, r = r, l
        l, r = r, l
        r ^= self.p[16]
        l ^= self.p[17]
        return l & M, r & M

    def _block_decrypt(self, l, r):
        for i in range(17, 1, -1):
            l ^= self.p[i]
            l &= M
            r ^= self._f(l)
            r &= M
            l, r = r, l
        l, r = r, l
        r ^= self.p[1]
        l ^= self.p[0]
        return l & M, r & M

    def _generate_subkeys(self, key: str):
        key_bytes = [ord(c) for c in key]
        j = 0
        for i in range(18):
            data = 0
            for _ in range(4):
                data = ((data << 8) | key_bytes[j]) & M
                j = (j + 1) % len(key_bytes)
            self.p[i] ^= data

        l = r = 0
        for i in range(0, 18, 2):
            l, r = self._block_encrypt(l, r)
            self.p[i] = l
            self.p[i + 1] = r

        for i in range(4):
            for j in range(0, 256, 2):
                l, r = self._block_encrypt(l, r)
                self.s[i][j] = l
                self.s[i][j + 1] = r

    def decrypt(self, data: str) -> str:
        result = []
        for i in range(0, len(data), 8):
            block = data[i:i + 8]
            if len(block) < 8:
                block += "\0" * (8 - len(block))
            l = (ord(block[0]) << 24) | (ord(block[1]) << 16) | (ord(block[2]) << 8) | ord(block[3])
            r = (ord(block[4]) << 24) | (ord(block[5]) << 16) | (ord(block[6]) << 8) | ord(block[7])
            l, r = self._block_decrypt(l, r)
            result.extend([
                chr((l >> 24) & 0xFF), chr((l >> 16) & 0xFF), chr((l >> 8) & 0xFF), chr(l & 0xFF),
                chr((r >> 24) & 0xFF), chr((r >> 16) & 0xFF), chr((r >> 8) & 0xFF), chr(r & 0xFF),
            ])
        # Strip null padding
        decoded = "".join(result)
        while decoded.endswith("\x00"):
            decoded = decoded[:-1]
        return decoded

    def utf8_decode(self, data: str) -> str:
        result = []
        i = 0
        while i < len(data):
            c = ord(data[i])
            if c < 128:
                result.append(chr(c))
            elif c > 191 and c < 224:
                c2 = ord(data[i + 1])
                result.append(chr(((31 & c) << 6) | (63 & c2)))
                i += 1
            else:
                c2 = ord(data[i + 1])
                c3 = ord(data[i + 2])
                result.append(chr(((15 & c) << 12) | ((63 & c2) << 6) | (63 & c3)))
                i += 2
            i += 1
        return "".join(result)

    def base64_decode(self, e: str) -> str:
        s = ""
        i = 0
        root = re.sub(r'[^A-Za-z0-9+/=]', '', e)
        while i < len(root):
            t_idx = KEY_STR.index(root[i]) if i < len(root) else 0
            i += 1
            i_idx = KEY_STR.index(root[i]) if i < len(root) else 0
            i += 1
            o_idx = KEY_STR.index(root[i]) if i < len(root) else 0
            i += 1
            a_idx = KEY_STR.index(root[i]) if i < len(root) else 0
            i += 1

            t = (t_idx << 2) | (i_idx >> 4)
            n = ((15 & i_idx) << 4) | (o_idx >> 2)
            r = ((3 & o_idx) << 6) | a_idx

            s += chr(t)
            if o_idx != 64:
                s += chr(n)
            if a_idx != 64:
                s += chr(r)
        return s


def _get_links(encrypted: str) -> list:
    key = encrypted[-10:]
    data = encrypted[:-10]
    cipher = _Blowfish(key)
    decoded = cipher.base64_decode(data)
    decrypted = cipher.decrypt(decoded)
    # Split into 5-char link IDs
    links = re.findall(r'.{1,5}', decrypted)
    return links


HOST_TO_EMBED = {
    "mixdrop.co": "mixdrop",
    "voe.sx": "voe",
    "upstream.to": "upstream",
    "streamvid.net": "streamvid",
    "dood.watch": "dood",
    "dropload.io": "dropload",
    "filelions.to": "filelions",
    "vtube.to": "vtube",
}


@register_source
class Primewire:
    id = "primewire"
    name = "Primewire"
    rank = 90
    media_types = ["movie", "tv"]

    async def _get_streams(self, html: str) -> list:
        """Extract embed URLs from page using Blowfish decryption."""
        # Find user-data
        ud_m = re.search(r'id="user-data"[^>]*v="([^"]+)"', html)
        if not ud_m:
            raise ValueError("Primewire: user-data not found")

        links = _get_links(ud_m.group(1))
        embeds = []

        for link_id in links:
            # Find matching .propper-link element
            link_re = re.compile(
                rf'class="propper-link"[^>]*link_version="{re.escape(link_id)}".*?'
                r'class="version-host[^"]*"[^>]*>([^<]+)',
                re.DOTALL,
            )
            m = link_re.search(html)
            if not m:
                continue
            host = m.group(1).strip()
            embed_id = HOST_TO_EMBED.get(host)
            if embed_id:
                embeds.append(EmbedRef(
                    embed_id=embed_id,
                    url=f"{PW_BASE}/links/go/{link_id}",
                ))

        return embeds

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        if not ctx.imdb_id:
            raise ValueError("Primewire requires IMDB ID")

        # Search by IMDB
        search_res = await fetcher.get_json(
            f"{PW_BASE}/api/v1/show/",
            params={"key": PW_API_KEY, "imdb_id": ctx.imdb_id},
        )
        show_id = search_res.get("id")
        if not show_id:
            raise ValueError("Primewire: show not found")

        if ctx.media_type == "movie":
            page_html = await fetcher.get(f"{PW_BASE}/movie/{show_id}")
        else:
            # Get season page, find episode link
            season_html = await fetcher.get(f"{PW_BASE}/tv/{show_id}")
            ep_pattern = re.compile(
                rf'show_season[^>]*data-id="{ctx.season}".*?href="([^"]*-episode-{ctx.episode}[^"]*)"',
                re.DOTALL,
            )
            ep_m = ep_pattern.search(season_html)
            if not ep_m:
                raise ValueError("Primewire: episode not found")
            page_html = await fetcher.get(ep_m.group(1), base_url=PW_BASE)

        embeds = await self._get_streams(page_html)
        return SourceResult(embeds=embeds)
