from __future__ import annotations
import asyncio
import json
import re
import time
from typing import Any, Dict, Optional

import httpx
from catcord_bots.formatting import format_retention_stats, format_pressure_stats, storage_status_label


class PersonalityRenderer:
    def __init__(
        self,
        characters_api_url: str,
        character_id: str,
        cathy_api_url: str,
        fallback_system_prompt: str,
        cathy_api_key: Optional[str] = None,
        characters_api_key: Optional[str] = None,
        characters_api_key_header: str = "X-API-Key",
        timeout_seconds: float = 60,
        connect_timeout_seconds: float = 3,
        max_tokens: int = 180,
        temperature: float = 0.2,
        top_p: float = 0.9,
        min_seconds_between_calls: int = 0,
        cathy_api_mode: str = "ollama",
        cathy_api_model: str = "gemma2:2b",
    ):
        self.characters_api_url = characters_api_url
        self.character_id = character_id
        self.cathy_api_url = cathy_api_url
        self.fallback_system_prompt = fallback_system_prompt
        self.cathy_api_key = cathy_api_key
        self.characters_api_key = characters_api_key
        self.characters_api_key_header = characters_api_key_header
        self.timeout_seconds = timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.min_seconds_between_calls = min_seconds_between_calls
        self.cathy_api_mode = cathy_api_mode
        self.cathy_api_model = cathy_api_model
        self._last_call_ts: float = 0.0
        self._cached_prompt: Optional[str] = None
        self._cached_etag: Optional[str] = None

    def _rate_limited(self) -> bool:
        now = time.time()
        if (now - self._last_call_ts) < self.min_seconds_between_calls:
            return True
        self._last_call_ts = now
        return False

    async def _fetch_system_prompt(self, client: httpx.AsyncClient) -> str:
        base = self.characters_api_url.rstrip("/")
        url = f"{base}/characters/{self.character_id}?view=private"

        headers = {}
        if self.characters_api_key:
            headers[self.characters_api_key_header] = self.characters_api_key
        if self._cached_etag:
            headers["If-None-Match"] = self._cached_etag

        try:
            r = await client.get(url, headers=headers)
        except httpx.TimeoutException as e:
            print(f"PersonalityRenderer: characters_api timeout: {e!r}")
            return self.fallback_system_prompt.strip()
        
        if r.status_code == 304 and self._cached_prompt:
            return self._cached_prompt
        r.raise_for_status()

        data = r.json()
        prompt = (
            data.get("system_prompt")
            or data.get("prompt")
            or data.get("background")
            or ""
        ).strip()

        if not prompt:
            return self.fallback_system_prompt.strip()

        self._cached_prompt = prompt
        self._cached_etag = r.headers.get("ETag")
        return prompt

    def _clean_prefix(self, s: str) -> str:
        s = s.strip()
        s = s.strip('"').strip("'")
        return s.strip()

    def _get_storage_category(self, payload: dict) -> str:
        """Get word-only storage category for AI context."""
        disk = payload.get("disk") or {}
        pb = disk.get("percent_before", 0.0)
        pt = disk.get("pressure_threshold", 85.0)
        et = disk.get("emergency_threshold", 92.0)
        return storage_status_label(pb, pt, et)

    def _validate_prefix(self, text: str) -> tuple[bool, str]:
        """Validate AI prefix is safe and contains no numbers. Returns (ok, reason)."""
        t = text.strip()
        tlow = t.lower()

        if not t:
            return False, "empty"

        if "\n" in t:
            return False, "newline"

        if len(t) > 180:
            return False, "too long"

        if re.search(r"[.!?].+[A-Z]", t):
            return False, "likely multiple sentences"

        bad_ack = ["ok", "understood", "please provide"]
        if any(tlow.startswith(x) for x in bad_ack):
            return False, "acknowledgement/assistant filler"

        banned = ["today", "yesterday", "uptime", "operational since", "elapsed"]
        for b in banned:
            if re.search(rf"\b{re.escape(b)}\b", tlow):
                return False, f"banned phrase '{b}'"

        if re.search(r"\d", t):
            return False, "contains digits"

        bad_actions = ["deleted", "removed", "purged", "redacted", "cleared"]
        if any(w in tlow for w in bad_actions):
            return False, "claims deletion"

        return True, ""



    def _validate_output(self, summary_payload: Dict[str, Any], text: str) -> tuple[bool, str]:
        """Deprecated - kept for compatibility."""
        return True, ""

    def _build_user_prompt(self, summary_payload: Dict[str, Any]) -> str:
        """Build AI prompt for prefix generation only."""
        mode = summary_payload.get("mode", "unknown")
        actions = summary_payload.get("actions") or {}
        deleted = actions.get("deleted_count", 0)
        storage_cat = self._get_storage_category(summary_payload)
        
        if mode == "pressure":
            if deleted == 0:
                return (
                    f"You are Irina. Storage is {storage_cat}. Write 2-6 words concluding logs are clear.\n"
                    "No digits, no percentages, no GB, no timestamps, no quotes.\n"
                )
            else:
                return (
                    f"You are Irina. Storage was {storage_cat}. Write 2-6 words concluding cleanup performed.\n"
                    "No digits, no percentages, no GB, no timestamps, no quotes.\n"
                )
        else:
            if deleted == 0:
                return (
                    f"You are Irina. You reviewed logs. Storage is {storage_cat}.\n"
                    "Write ONE short sentence (max 110 chars).\n"
                    "Meaning: Reviewed logs, no action needed.\n"
                    "No digits, no percentages, no GB, no timestamps, no quotes.\n"
                )
            else:
                return (
                    f"You are Irina. You reviewed logs. Storage was {storage_cat}.\n"
                    "Write ONE short sentence (max 110 chars).\n"
                    "Meaning: Reviewed logs, retention sweep performed.\n"
                    "No digits, no percentages, no GB, no timestamps, no quotes.\n"
                )

    async def render(self, summary_payload: Dict[str, Any]) -> Optional[str]:
        if self._rate_limited():
            return None

        try:
            timeout = httpx.Timeout(
                connect=self.connect_timeout_seconds,
                read=self.timeout_seconds,
                write=self.timeout_seconds,
                pool=self.timeout_seconds,
            )

            headers = {"Content-Type": "application/json"}
            if self.cathy_api_key:
                headers["Authorization"] = f"Bearer {self.cathy_api_key}"

            async with httpx.AsyncClient(timeout=timeout) as client:
                system_prompt = await self._fetch_system_prompt(client)
                user_prompt = self._build_user_prompt(summary_payload)

                base_messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                last_reject_reason = None
                for attempt in range(2):
                    try:
                        text = ""
                        prefix = ""
                        messages = list(base_messages)
                        
                        if attempt == 1 and last_reject_reason:
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"Your previous prefix violated a rule: {last_reject_reason}\n"
                                    "Rewrite the prefix.\n\n"
                                    "PREFIX RULES (must follow):\n"
                                    "- ONE sentence only.\n"
                                    "- No digits at all.\n"
                                    "- No numbers, %, GB, thresholds, IDs, timestamps.\n"
                                    "- Do not claim files were deleted.\n"
                                    "- Do not mention cleanup operations.\n"
                                    "- Do not use: today, yesterday, since, uptime, operational.\n"
                                    "- Plain text only.\n\n"
                                    "Good examples:\n"
                                    "Master, I reviewed the logs: below threshold; no action required.\n"
                                    "Logs reviewed: pressure is low; standing by.\n"
                                )
                            })
                        
                        if self.cathy_api_mode.lower() == "ollama":
                            body = {
                                "model": self.cathy_api_model,
                                "stream": False,
                                "messages": messages,
                                "options": {
                                    "temperature": 0.2,
                                    "num_predict": 32,
                                    "num_ctx": 384,
                                    "stop": ["\n"],
                                },
                            }
                            t0 = time.time()
                            r = await client.post(
                                f"{self.cathy_api_url.rstrip('/')}/api/chat",
                                headers=headers,
                                json=body,
                            )
                            elapsed = time.time() - t0
                            r.raise_for_status()
                            data = r.json()
                            prefix = (data.get("message") or {}).get("content", "").strip()
                            prefix = self._clean_prefix(prefix)
                            if prefix and "\n" in prefix:
                                prefix = prefix.split("\n", 1)[0].strip()
                            print(f"PersonalityRenderer: call took {elapsed:.2f}s, raw prefix (attempt={attempt}): {prefix!r}", flush=True)
                        else:
                            body = {
                                "model": self.cathy_api_model,
                                "messages": messages,
                                "temperature": self.temperature,
                                "top_p": self.top_p,
                                "max_tokens": self.max_tokens,
                                "stream": False,
                            }
                            r = await client.post(
                                f"{self.cathy_api_url.rstrip('/')}/v1/chat/completions",
                                headers=headers,
                                json=body,
                            )
                            r.raise_for_status()
                            data = r.json()
                            prefix = (
                                data.get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                                .strip()
                            )
                            prefix = self._clean_prefix(prefix)
                            if prefix and "\n" in prefix:
                                prefix = prefix.split("\n", 1)[0].strip()
                            print(f"PersonalityRenderer: raw prefix (attempt={attempt}): {prefix!r}", flush=True)
                        
                        if not prefix and attempt == 0:
                            await asyncio.sleep(0.3)
                            last_reject_reason = "empty output"
                            continue
                        
                        if not prefix:
                            print(f"PersonalityRenderer: empty prefix (attempt={attempt})", flush=True)
                            last_reject_reason = "empty output"
                            continue
                        
                        ok, reason = self._validate_prefix(prefix)
                        if not ok:
                            print(f"PersonalityRenderer: rejected prefix (attempt={attempt}) reason={reason} prefix={prefix[:200]!r}", flush=True)
                            if attempt == 0:
                                last_reject_reason = reason
                                continue
                            last_reject_reason = reason
                            continue

                        print(f"PersonalityRenderer: accepted (attempt={attempt}) prefix={prefix!r}", flush=True)
                        return prefix.strip()
                    
                    except httpx.TimeoutException as e:
                        print(f"PersonalityRenderer: Timeout (attempt={attempt}): {e!r}", flush=True)
                        if attempt == 0:
                            last_reject_reason = "timeout"
                            continue
                        last_reject_reason = "timeout"
                        continue
                    except httpx.HTTPStatusError as e:
                        print(f"PersonalityRenderer: HTTP error (attempt={attempt}): status={e.response.status_code} body={e.response.text[:200]!r}", flush=True)
                        if attempt == 0:
                            last_reject_reason = "http_error"
                            continue
                        last_reject_reason = "http_error"
                        continue

                print(f"PersonalityRenderer: exhausted retries -> None", flush=True)
                return None

        except Exception as e:
            print(f"PersonalityRenderer exception -> None: {e!r}", flush=True)
            return None
