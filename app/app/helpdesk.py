"""Helpdesk API client with retry and backoff."""
from pathlib import Path
import asyncio
import os
import time
from typing import Any

import httpx


def _load_env_if_missing():
    if not os.environ.get("HELPDESK_TOKEN"):
        for env_path in [Path(".env"), Path("../.env"), Path(__file__).resolve().parent.parent.parent / ".env"]:
            if env_path.is_file():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
                break


class HelpdeskClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        _load_env_if_missing()
        self.base_url = (base_url or os.environ.get("HELPDESK_URL", "http://localhost:4010")).rstrip("/")
        self.token = token or os.environ.get("HELPDESK_TOKEN", "")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def get(self, path: str, params: dict | None = None, max_retries: int = 5) -> dict[str, Any]:
        """GET a path synchronously and return parsed JSON, with 429 backoff."""
        url = self.base_url + path
        for attempt in range(max_retries):
            response = httpx.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=15.0,
            )
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 1.0))
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            return response.json()
        response.raise_for_status()
        return response.json()

    async def async_get(
        self,
        path: str,
        params: dict | None = None,
        client: httpx.AsyncClient | None = None,
        max_retries: int = 5,
    ) -> dict[str, Any]:
        """GET a path asynchronously and return parsed JSON, with 429 backoff."""
        url = self.base_url + path
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=15.0)
            should_close = True

        try:
            for attempt in range(max_retries):
                response = await client.get(
                    url,
                    params=params,
                    headers=self._headers(),
                )
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 1.0))
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response.json()
            response.raise_for_status()
            return response.json()
        finally:
            if should_close:
                await client.aclose()
