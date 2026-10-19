"""Hexagonal AI Adapter for Anki Studio (Local LLM / Cloud LLM + Fail-Closed Deterministic Fallback).

Supports optional OpenAI-compatible local/cloud endpoints (e.g. Ollama / Mac Studio)
 via environment variables `ANKI_STUDIO_AI_URL` and `ANKI_STUDIO_AI_MODEL`, while
guaranteeing 100% zero-latency deterministic synthesis when offline or unconfigured.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List
import urllib.error
import urllib.request

from anki_studio.domain.ai_learning import (
    GeneratedCardSpec,
    build_ai_card_generation_prompt,
    extract_smart_cards_deterministic,
    parse_ai_generated_cards,
)


class AICardSynthesizer:
    """Adapter that synthesizes high-yield flashcards from raw notes with Fail-Closed fallback."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        model_name: str | None = None,
        timeout_sec: float = 4.5,
    ) -> None:
        self.endpoint_url = (endpoint_url or os.environ.get("ANKI_STUDIO_AI_URL") or "").strip()
        self.model_name = (model_name or os.environ.get("ANKI_STUDIO_AI_MODEL") or "glm-5.3-flash").strip()
        self.timeout_sec = float(timeout_sec)

    def synthesize_cards(
        self,
        raw_text: str,
        domain_mode: str = "auto",
        max_cards: int = 10,
    ) -> Dict[str, Any]:
        """Synthesize cards using configured LLM endpoint, or fall back to deterministic NLP engine."""
        text = (raw_text or "").strip()
        if not text:
            return {"engine": "none", "cards": []}

        if self.endpoint_url:
            try:
                prompt = build_ai_card_generation_prompt(text, domain_mode=domain_mode, max_cards=max_cards)
                payload = json.dumps(
                    {
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    self.endpoint_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    content = (
                        body.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    specs = parse_ai_generated_cards(
                        content,
                        fallback_source_text=text,
                        domain_mode=domain_mode,
                    )
                    if specs:
                        return {
                            "engine": f"llm:{self.model_name}",
                            "cards": [self._spec_to_dict(s) for s in specs[:max_cards]],
                        }
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError):
                pass

        specs = extract_smart_cards_deterministic(text, domain_mode=domain_mode, max_cards=max_cards)
        return {
            "engine": "deterministic-nlp-zero-quota",
            "cards": [self._spec_to_dict(s) for s in specs],
        }

    @staticmethod
    def _spec_to_dict(spec: GeneratedCardSpec) -> Dict[str, Any]:
        return {
            "note_type": spec.note_type,
            "front_text": spec.front_text,
            "back_text": spec.back_text,
            "tags": list(spec.tags),
            "rationale": spec.rationale,
        }
