from __future__ import annotations
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


@dataclass
class AISummaryConfig:
    enabled: bool
    characters_api_url: str
    irina_character_id: str
    cathy_api_url: str
    cathy_api_key: Optional[str]
    timeout_seconds: float
    connect_timeout_seconds: float
    max_tokens: int
    temperature: float
    top_p: float
    max_render_attempts: int
    min_seconds_between_calls: int
    fallback_system_prompt: str


class AISummaryRenderer:
    def __init__(self, cfg: AISummaryConfig):
        self.cfg = cfg
        self._last_call_ts: float = 0.0
        self._cached_irina_prompt: Optional[str] = None
        self._cached_irina_etag: Optional[str] = None

    def _rate_limited(self) -> bool:
        now = time.time()
        if (now - self._last_call_ts) < self.cfg.min_seconds_between_calls:
            return True
        self._last_call_ts = now
        return False

    async def _fetch_irina_system_prompt(self) -> str:
        base = self.cfg.characters_api_url.rstrip("/")
        url = f"{base}/characters/{self.cfg.irina_character_id}?view=private"

        headers = {}
        if self._cached_irina_etag:
            headers["If-None-Match"] = self._cached_irina_etag

        timeout = httpx.Timeout(
            timeout=self.cfg.timeout_seconds,
            connect=self.cfg.connect_timeout_seconds,
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers=headers)
            if r.status_code == 304 and self._cached_irina_prompt:
                return self._cached_irina_prompt
            r.raise_for_status()

            data = r.json()
            prompt = (
                data.get("system_prompt")
                or data.get("prompt")
                or data.get("background")
                or ""
            ).strip()

            if not prompt:
                return self.cfg.fallback_system_prompt.strip()

            self._cached_irina_prompt = prompt
            self._cached_irina_etag = r.headers.get("ETag")
            return prompt

    def _build_user_prompt(self, summary_payload: Dict[str, Any]) -> str:
        payload_str = json.dumps(summary_payload, ensure_ascii=False, sort_keys=True)
        return (
            "You will be given a JSON payload with facts about a Catcord cleaner run.\n"
            "Write a short ops update in Irina's voice.\n\n"
            "STRICT RULES:\n"
            "- Only use facts present in the JSON.\n"
            "- Do NOT invent deletions, rooms, users, causes, or numbers.\n"
            "- Do NOT add new metrics.\n"
            "- Keep it under ~700 characters.\n"
            "- Include the key numeric facts exactly as provided (counts, freed_gb, disk_percent_before/after).\n"
            "- If deleted_count is 0, say so plainly.\n"
            "- No markdown tables; plain text only.\n\n"
            f"JSON:\n{payload_str}\n"
        )

    async def render(self, summary_payload: Dict[str, Any]) -> Optional[str]:
        if not self.cfg.enabled:
            return None
        if self._rate_limited():
            return None

        attempts = max(1, int(self.cfg.max_render_attempts))
        for _ in range(attempts):
            try:
                system_prompt = await self._fetch_irina_system_prompt()
                user_prompt = self._build_user_prompt(summary_payload)

                timeout = httpx.Timeout(
                    timeout=self.cfg.timeout_seconds,
                    connect=self.cfg.connect_timeout_seconds,
                )

                headers = {"Content-Type": "application/json"}
                if self.cfg.cathy_api_key:
                    headers["Authorization"] = f"Bearer {self.cfg.cathy_api_key}"

                body = {
                    "model": "cathy",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self.cfg.temperature,
                    "top_p": self.cfg.top_p,
                    "max_tokens": self.cfg.max_tokens,
                    "stream": False,
                }

                async with httpx.AsyncClient(timeout=timeout) as client:
                    r = await client.post(
                        f"{self.cfg.cathy_api_url.rstrip('/')}/v1/chat/completions",
                        headers=headers,
                        json=body,
                    )
                    r.raise_for_status()
                    data = r.json()
                    text = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                    if text:
                        return text
                    return None

            except Exception:
                return None

        return None
