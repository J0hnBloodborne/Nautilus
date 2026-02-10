"""
HTTP fetcher for provider scrapers. Wraps aiohttp with common defaults,
headers, timeout, and optional proxy support.
"""
from __future__ import annotations
import aiohttp
import asyncio
from typing import Optional
from urllib.parse import urljoin, urlencode

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

class Fetcher:
    def __init__(self, *, timeout: int = 10, proxy: str | None = None):
        self.timeout = aiohttp.ClientTimeout(total=timeout, connect=4)
        self.proxy = proxy
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"User-Agent": DEFAULT_UA},
                connector=aiohttp.TCPConnector(ssl=False),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── convenience methods ──────────────────

    async def get(
        self,
        url: str,
        *,
        base_url: str | None = None,
        headers: dict | None = None,
        params: dict | None = None,
        follow_redirects: bool = True,
    ) -> str:
        full = urljoin(base_url, url) if base_url else url
        session = await self._get_session()
        async with session.get(
            full,
            headers=headers or {},
            params=params,
            allow_redirects=follow_redirects,
            proxy=self.proxy,
        ) as resp:
            return await resp.text()

    async def get_json(
        self,
        url: str,
        *,
        base_url: str | None = None,
        headers: dict | None = None,
        params: dict | None = None,
    ) -> dict | list:
        full = urljoin(base_url, url) if base_url else url
        session = await self._get_session()
        async with session.get(
            full,
            headers=headers or {},
            params=params,
            proxy=self.proxy,
        ) as resp:
            return await resp.json(content_type=None)

    async def post(
        self,
        url: str,
        *,
        base_url: str | None = None,
        headers: dict | None = None,
        data: dict | str | None = None,
        json_body: dict | None = None,
    ) -> str:
        full = urljoin(base_url, url) if base_url else url
        session = await self._get_session()
        async with session.post(
            full,
            headers=headers or {},
            data=data,
            json=json_body,
            proxy=self.proxy,
        ) as resp:
            return await resp.text()

    async def head(
        self,
        url: str,
        *,
        base_url: str | None = None,
        headers: dict | None = None,
    ) -> int:
        """Returns status code."""
        full = urljoin(base_url, url) if base_url else url
        session = await self._get_session()
        async with session.head(
            full,
            headers=headers or {},
            allow_redirects=True,
            proxy=self.proxy,
        ) as resp:
            return resp.status

    async def get_final_url(
        self,
        url: str,
        *,
        base_url: str | None = None,
        headers: dict | None = None,
    ) -> str:
        """Follow redirects and return the final URL."""
        full = urljoin(base_url, url) if base_url else url
        session = await self._get_session()
        async with session.get(
            full,
            headers=headers or {},
            allow_redirects=True,
            proxy=self.proxy,
        ) as resp:
            return str(resp.url)
