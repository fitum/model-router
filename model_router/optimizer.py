"""Token optimizer -- compresses prompts and caches results to reduce costs."""

from __future__ import annotations

import hashlib
import re
import time


class TokenOptimizer:
    def __init__(self, cache_ttl_seconds: int = 300) -> None:
        self._cache: dict[str, tuple[str, float]] = {}  # key -> (result, expiry)
        self._cache_ttl = cache_ttl_seconds

    # ------------------------------------------------------------------
    # Prompt compression
    # ------------------------------------------------------------------

    def compress_prompt(self, prompt: str, target_tokens: int) -> str:
        """
        Three-pass lossless-first compression.
        Pass 1: whitespace (free, lossless)
        Pass 2: strip boilerplate examples beyond the 5th
        Pass 3: middle-truncation (preserves first+last 35%)
        Stops as soon as the prompt is under target_tokens.
        """
        # Rough estimate: 1 token ~ 4 chars
        if len(prompt) / 4 <= target_tokens:
            return prompt

        text = self._pass1_whitespace(prompt)
        if len(text) / 4 <= target_tokens:
            return text

        text = self._pass2_strip_examples(text)
        if len(text) / 4 <= target_tokens:
            return text

        text = self._pass3_middle_truncate(text, target_tokens)
        return text

    @staticmethod
    def _pass1_whitespace(text: str) -> str:
        # Collapse 3+ blank lines to 2, strip trailing spaces
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        return text.strip()

    @staticmethod
    def _pass2_strip_examples(text: str) -> str:
        # Remove numbered list items beyond the 5th occurrence
        items = re.split(r"\n(?=\d+\. )", text)
        if len(items) > 6:
            items = items[:6] + ["\n_(additional examples omitted)_"]
        return "\n".join(items)

    @staticmethod
    def _pass3_middle_truncate(text: str, target_tokens: int) -> str:
        target_chars = target_tokens * 4
        if len(text) <= target_chars:
            return text
        keep = int(target_chars * 0.35)
        head = text[:keep]
        tail = text[-keep:]
        omitted = len(text) - 2 * keep
        return f"{head}\n\n...[{omitted} characters omitted for token efficiency]...\n\n{tail}"

    # ------------------------------------------------------------------
    # Context window trimming
    # ------------------------------------------------------------------

    def trim_context(
        self, messages: list[dict], max_tokens: int, chars_per_token: float = 4.0
    ) -> list[dict]:
        """
        Sliding window that drops old messages when accumulated tokens exceed max.
        Always preserves: system message (index 0), first user message, last 3 exchanges.
        """
        if not messages:
            return messages

        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        max_chars = int(max_tokens * chars_per_token)

        if total_chars <= max_chars:
            return messages

        # Identify protected indices
        protected: set[int] = {0}  # system prompt
        if len(messages) > 1:
            protected.add(1)  # first user message
        protected.update(range(max(0, len(messages) - 6), len(messages)))  # last 3 exchanges

        trimmed = []
        dropped = 0
        for i, msg in enumerate(messages):
            if i in protected:
                trimmed.append(msg)
            elif total_chars > max_chars:
                total_chars -= len(str(msg.get("content", "")))
                dropped += 1
            else:
                trimmed.append(msg)

        if dropped:
            # Insert a notice after the first message
            trimmed.insert(1, {
                "role": "system",
                "content": f"[{dropped} earlier message(s) trimmed to fit context window]",
            })

        return trimmed

    # ------------------------------------------------------------------
    # Result caching
    # ------------------------------------------------------------------

    def build_cache_key(self, prompt: str, model: str) -> str:
        normalized = re.sub(r"\s+", " ", prompt.strip().lower())
        raw = f"{model}::{normalized}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get_cached(self, key: str) -> str | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        result, expiry = entry
        if time.time() > expiry:
            del self._cache[key]
            return None
        return result

    def set_cached(self, key: str, result: str, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._cache_ttl
        self._cache[key] = (result, time.time() + ttl)

    def clear_expired(self) -> int:
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[k]
        return len(expired)

    @property
    def cache_size(self) -> int:
        return len(self._cache)
