from __future__ import annotations
import asyncio
import json
import re
import time
from typing import Any, Dict, Optional

import httpx


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
        cathy_api_model: str = "phi3.5:latest",
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

    async def _fetch_system_prompt(self) -> str:
        base = self.characters_api_url.rstrip("/")
        url = f"{base}/characters/{self.character_id}?view=private"

        headers = {}
        if self.characters_api_key:
            headers[self.characters_api_key_header] = self.characters_api_key
        if self._cached_etag:
            headers["If-None-Match"] = self._cached_etag

        timeout = httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.timeout_seconds,
            write=self.timeout_seconds,
            pool=self.timeout_seconds,
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
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

    def _validate_output(self, summary_payload: Dict[str, Any], text: str) -> tuple[bool, str]:
        """Validate AI output contains required facts from JSON. Returns (ok, reason)."""
        tlow = text.lower()
        
        disk = summary_payload.get("disk") or {}
        actions = summary_payload.get("actions") or {}
        
        percent_before = disk.get("percent_before")
        pressure_threshold = disk.get("pressure_threshold")
        deleted_count = actions.get("deleted_count")
        freed_gb = actions.get("freed_gb")
        
        # Must match required format
        pattern = r"^Disk usage: .*% \(threshold .*%\)\. No deletions\. Freed: .* GB\.$"
        if not re.match(pattern, text.strip()):
            return False, "does not match required output format"
        
        # Check banned phrases
        banned_phrases = ["operational since", "uptime", "elapsed", "today", "yesterday", "since '", 'since "']
        for phrase in banned_phrases:
            if phrase in tlow:
                return False, f"contains banned phrase '{phrase}'"
        
        # Must include key numbers (allow rounding/formatting)
        if percent_before is not None:
            pb_str = str(percent_before).rstrip("0").rstrip(".")
            if pb_str not in text and f"{percent_before:.1f}" not in text:
                return False, f"missing required number: {percent_before}"
        
        if pressure_threshold is not None:
            pt_str = str(pressure_threshold).rstrip("0").rstrip(".")
            pt_pct = str(int(pressure_threshold)) if pressure_threshold == int(pressure_threshold) else str(pressure_threshold)
            if pt_str not in text and pt_pct not in text:
                return False, f"missing required threshold: {pressure_threshold}"
            if "threshold" not in tlow:
                return False, "missing word 'threshold' for pressure_threshold"
        
        # Must include literal "no deletions" when count is 0
        if deleted_count == 0:
            if "no deletions" not in tlow:
                return False, "missing 'No deletions' literal"
        
        # Require freed_gb number match whenever freed_gb is present in JSON
        if freed_gb is not None:
            fg_str = str(freed_gb).rstrip("0").rstrip(".")
            if fg_str not in text and f"{freed_gb:.1f}" not in text and f"{freed_gb:.2f}" not in text:
                return False, f"missing required freed_gb: {freed_gb}"
        
        return True, ""

    def _build_user_prompt(self, summary_payload: Dict[str, Any]) -> str:
        payload_str = json.dumps(summary_payload, ensure_ascii=False, sort_keys=True)
        return (
            "Return ONLY a JSON object with this schema:\n"
            '{"text": "<ONE LINE MESSAGE>"}\n\n'
            "The text value MUST be exactly one line and must follow this exact format:\n"
            "Disk usage: <percent_before>% (threshold <pressure_threshold>%). No deletions. Freed: <freed_gb> GB.\n\n"
            "STRICT RULES:\n"
            "- Only use facts present in the JSON payload below.\n"
            "- Do NOT invent deletions, rooms, users, causes, or numbers.\n"
            "- Do NOT mention uptime, 'since', 'operational since', 'elapsed', or any timestamps.\n"
            "- Do NOT use relative time words like 'today' or 'yesterday'.\n"
            "- If actions.deleted_count is 0, you MUST say 'No deletions'.\n"
            "- If actions.deleted_count > 0, you MUST include deleted_count and freed_gb.\n"
            "- Include key numeric facts exactly as provided.\n\n"
            f"JSON payload:\n{payload_str}\n"
        )

    async def render(self, summary_payload: Dict[str, Any]) -> Optional[str]:
        if self._rate_limited():
            return None

        try:
            system_prompt = await self._fetch_system_prompt()
            user_prompt = self._build_user_prompt(summary_payload)

            timeout = httpx.Timeout(
                connect=self.connect_timeout_seconds,
                read=self.timeout_seconds,
                write=self.timeout_seconds,
                pool=self.timeout_seconds,
            )

            headers = {"Content-Type": "application/json"}
            if self.cathy_api_key:
                headers["Authorization"] = f"Bearer {self.cathy_api_key}"

            base_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            last_reject_reason = None

            async with httpx.AsyncClient(timeout=timeout) as client:
                for attempt in range(2):
                    try:
                        text = ""
                        messages = list(base_messages)
                        
                        if attempt == 1 and last_reject_reason:
                            disk = summary_payload.get("disk") or {}
                            actions = summary_payload.get("actions") or {}
                            forbidden = ["today", "yesterday", "operational since", "operational", "uptime", "since", "elapsed"]
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"Your previous draft violated rules: {last_reject_reason}\n"
                                    f"Forbidden words/phrases: {', '.join(forbidden)}\n"
                                    "Rewrite using ONLY facts from the JSON. Plain text.\n"
                                    "Use this exact structure (fill in numbers):\n"
                                    "Disk usage: <percent_before>% (threshold <pressure_threshold>%). "
                                    "No deletions. Freed: <freed_gb> GB.\n"
                                    f"Numbers to use exactly: percent_before={disk.get('percent_before')}, "
                                    f"pressure_threshold={disk.get('pressure_threshold')}, "
                                    f"freed_gb={actions.get('freed_gb')}, "
                                    f"deleted_count={actions.get('deleted_count')}.\n"
                                    "Keep it to ONE short sentence."
                                )
                            })
                        
                        if self.cathy_api_mode.lower() == "ollama":
                            body = {
                                "model": self.cathy_api_model,
                                "stream": False,
                                "format": "json",
                                "messages": messages,
                                "options": {
                                    "temperature": 0.0,
                                    "num_predict": 80,
                                    "num_ctx": 768,
                                },
                            }
                            r = await client.post(
                                f"{self.cathy_api_url.rstrip('/')}/api/chat",
                                headers=headers,
                                json=body,
                            )
                            r.raise_for_status()
                            data = r.json()
                            raw = (data.get("message") or {}).get("content", "").strip()
                            if not raw:
                                done = data.get("done_reason") if isinstance(data, dict) else None
                                print(f"PersonalityRenderer: empty ollama content (attempt={attempt}) done={done}")
                                text = ""
                            else:
                                try:
                                    obj = json.loads(raw)
                                    text = str(obj.get("text") or "").strip()
                                except Exception as e:
                                    print(f"PersonalityRenderer: non-json output (attempt={attempt}): {raw[:120]!r}")
                                    text = ""
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
                            text = (
                                data.get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                                .strip()
                            )
                        
                        if not text and attempt == 0:
                            await asyncio.sleep(0.3)
                            last_reject_reason = "empty output"
                            continue
                        
                        if not text:
                            return None
                        
                        ok, reason = self._validate_output(summary_payload, text)
                        if not ok:
                            print(f"PersonalityRenderer: rejected (attempt={attempt}): {reason} - {text[:100]!r}")
                            if attempt == 0:
                                last_reject_reason = reason
                                continue
                            return None

                        print(f"PersonalityRenderer: accepted (attempt={attempt})")
                        return text
                    
                    except httpx.TimeoutException as e:
                        print(f"PersonalityRenderer: Timeout (attempt={attempt}): {e!r}")
                        if attempt == 0:
                            last_reject_reason = "timeout"
                            continue
                        return None

                return None

        except Exception as e:
            print(f"PersonalityRenderer exception: {e!r}")
            return None
