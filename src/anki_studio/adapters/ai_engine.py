"""Hexagonal Smart Card & Ollama Cloud Adapter for BrainDeck (Local/Cloud LLM + Fail-Closed Fallback).

Supports:
1. Ollama Cloud (`https://ollama.com/api/chat`) with `glm-5.3-flash`, `deepseek-v4.1-flash`,
   `gemma4:31b`, and `glm-5.3` for Photo/PDF document card synthesis and note structuring.
2. Fail-Closed Model Policy: permanently blocks `kimi-*` and `minimax-*` models.
3. 100% zero-latency deterministic synthesis fallback when offline or unconfigured.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import urllib.error
import urllib.request

from anki_studio.domain.ai_learning import (
    GeneratedCardSpec,
    build_ai_card_generation_prompt,
    extract_smart_cards_deterministic,
    parse_ai_generated_cards,
)
from anki_studio.domain.document_deck_builder import DocumentBlock

OLLAMA_CLOUD_DEFAULT_URL = "https://ollama.com"
OLLAMA_CLOUD_DEFAULT_MODEL = "glm-5.3-flash"

OLLAMA_CLOUD_MODELS_CATALOG: Tuple[Dict[str, Any], ...] = (
    {
        "id": "glm-5.3-flash",
        "label": "☁️ Ollama Cloud · GLM-5.3 Flash (초고속 핵심 카드)",
        "provider": "ollama_cloud",
        "supports_vision": False,
        "recommended": True,
    },
    {
        "id": "deepseek-v4.1-flash",
        "label": "☁️ Ollama Cloud · DeepSeek-v4.1 Flash (정밀 빈칸·문맥)",
        "provider": "ollama_cloud",
        "supports_vision": False,
        "recommended": False,
    },
    {
        "id": "gemma4:31b",
        "label": "☁️ Ollama Cloud · Gemma-4 31B (시각·표·문서 정밀 분석)",
        "provider": "ollama_cloud",
        "supports_vision": True,
        "recommended": False,
    },
    {
        "id": "glm-5.3",
        "label": "☁️ Ollama Cloud · GLM-5.3 (심화·전공 서술 카드)",
        "provider": "ollama_cloud",
        "supports_vision": False,
        "recommended": False,
    },
    {
        "id": "local_rule",
        "label": "⚡ 기기 내장 초고속 엔진 (오프라인 · 0초)",
        "provider": "local_rule",
        "supports_vision": False,
        "recommended": False,
    },
)

_BLOCKED_MODEL_PREFIXES = ("kimi", "minimax")


def is_ollama_cloud_model_blocked(model_name: str | None) -> bool:
    """Fail-Closed Model Policy: permanently block Kimi 2.x/K3 and MiniMax 2.7/M3 families."""
    norm = str(model_name or "").strip().lower()
    if not norm:
        return False
    return any(norm.startswith(prefix) or f"/{prefix}" in norm for prefix in _BLOCKED_MODEL_PREFIXES)


def resolve_ollama_cloud_credentials() -> Tuple[str, List[str]]:
    """Resolve Ollama Cloud base URL and API key pool from environment or LifeOS .env."""
    base_url = (
        os.environ.get("OLLAMA_CLOUD_URL")
        or os.environ.get("OLLAMA_HOST")
        or OLLAMA_CLOUD_DEFAULT_URL
    ).strip().rstrip("/")
    if not base_url.startswith("http"):
        base_url = f"https://{base_url}"

    raw_keys = (
        os.environ.get("OLLAMA_CLOUD_API_KEYS")
        or os.environ.get("OLLAMA_API_KEY")
        or ""
    ).strip()

    if not raw_keys:
        env_candidates = [
            Path("/Users/choyoungseo/LifeOS_System/LifeOS-System/.env"),
            Path.home() / "LifeOS_System" / "LifeOS-System" / ".env",
        ]
        for env_path in env_candidates:
            try:
                if env_path.is_file():
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        stripped = line.strip()
                        if stripped.startswith("OLLAMA_CLOUD_API_KEYS="):
                            raw_keys = stripped.split("=", 1)[1].strip().strip("'\"")
                            break
                    if raw_keys:
                        break
            except OSError:
                pass

    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    return base_url, keys


class AICardSynthesizer:
    """Adapter that synthesizes high-yield flashcards from raw notes or Photo/PDF documents with Ollama Cloud & Fail-Closed fallback."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        model_name: str | None = None,
        timeout_sec: float = 6.5,
        ollama_http_sender: Optional[Callable[[str, Dict[str, Any], Dict[str, str], float], str]] = None,
    ) -> None:
        self.endpoint_url = (endpoint_url or os.environ.get("ANKI_STUDIO_AI_URL") or "").strip()
        self.model_name = (model_name or os.environ.get("ANKI_STUDIO_AI_MODEL") or OLLAMA_CLOUD_DEFAULT_MODEL).strip()
        self.timeout_sec = float(timeout_sec)
        self._ollama_http_sender = ollama_http_sender

    @staticmethod
    def list_ollama_cloud_models() -> Dict[str, Any]:
        base_url, keys = resolve_ollama_cloud_credentials()
        return {
            "ok": True,
            "default_model": OLLAMA_CLOUD_DEFAULT_MODEL,
            "cloud_url": base_url,
            "cloud_configured": len(keys) > 0,
            "models": [dict(m) for m in OLLAMA_CLOUD_MODELS_CATALOG],
        }

    def _call_ollama_cloud_chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        timeout_sec: Optional[float] = None,
    ) -> str:
        if is_ollama_cloud_model_blocked(model):
            raise ValueError(f"BLOCKED_MODEL:{model}")

        base_url, keys = resolve_ollama_cloud_credentials()
        url = f"{base_url}/api/chat"
        payload_dict: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }
        eff_timeout = float(timeout_sec or self.timeout_sec)

        if self._ollama_http_sender is not None:
            headers = {"Content-Type": "application/json"}
            if keys:
                headers["Authorization"] = f"Bearer {keys[0]}"
            return self._ollama_http_sender(url, payload_dict, headers, eff_timeout)

        if not keys:
            raise RuntimeError("OLLAMA_CLOUD_API_KEYS_UNCONFIGURED")

        last_exc: Exception | None = None
        data_bytes = json.dumps(payload_dict).encode("utf-8")
        for key in keys[:2]:
            try:
                req = urllib.request.Request(
                    url,
                    data=data_bytes,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=eff_timeout) as resp:
                    raw_body = json.loads(resp.read().decode("utf-8"))
                    if isinstance(raw_body.get("message"), dict):
                        return str(raw_body["message"].get("content") or "")
                    if isinstance(raw_body.get("choices"), list) and raw_body["choices"]:
                        return str(raw_body["choices"][0].get("message", {}).get("content") or "")
                    return ""
            except Exception as exc:
                last_exc = exc
        raise RuntimeError(f"OllamaCloud call failed: {last_exc}")

    def synthesize_document_cards_with_ollama_cloud(
        self,
        blocks: Sequence[DocumentBlock],
        base_cards: List[Dict[str, Any]],
        ollama_cloud_model: str = OLLAMA_CLOUD_DEFAULT_MODEL,
        difficulty_level: str = "standard",
        max_cards: int = 30,
    ) -> Dict[str, Any]:
        """Synthesize grounded flashcards from extracted Photo/PDF blocks using Ollama Cloud (`glm-5.3-flash` / `deepseek-v4.1-flash`)."""
        t0 = time.perf_counter()
        norm_model = str(ollama_cloud_model or OLLAMA_CLOUD_DEFAULT_MODEL).strip()
        if is_ollama_cloud_model_blocked(norm_model):
            return {
                "ok": False,
                "status": "BLOCKED",
                "error_code": "BLOCKED_MODEL",
                "ollama_cloud_model": norm_model,
                "ollama_cloud_used": False,
                "provider": "blocked_model_policy",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "cards": [],
            }

        if not norm_model or norm_model.lower() in ("local_rule", "off", "none", "local"):
            return {
                "ok": True,
                "status": "OK",
                "error_code": None,
                "ollama_cloud_model": "local_rule",
                "ollama_cloud_used": False,
                "provider": "local_rule",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "cards": base_cards[:max_cards],
            }

        page_lines: List[str] = []
        blocks_by_page: Dict[int, List[str]] = {}
        for b in blocks:
            txt = str(b.text or "").strip()
            if not txt:
                continue
            pg = max(1, int(b.page or 1))
            blocks_by_page.setdefault(pg, []).append(txt)
            page_lines.append(f"[p.{pg}] {txt}")

        joined_doc = "\n".join(page_lines[:80]).strip()
        if not joined_doc:
            return {
                "ok": True,
                "status": "OK",
                "error_code": None,
                "ollama_cloud_model": norm_model,
                "ollama_cloud_used": False,
                "provider": "local_rule",
                "fallback_reason": "empty_blocks",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "cards": base_cards[:max_cards],
            }

        sys_prompt = (
            "당신은 사진·PDF 학습 문서에서 핵심 개념 플래시카드를 정밀 추출하는 전문가입니다.\n"
            "반드시 원문에 등장하는 사실과 용어만 사용하여 JSON 객체로 응답하세요.\n"
            '형식: {"cards": [{"front_text": "질문 또는 {{c1::정답::힌트}} 문장", "back_text": "핵심 정답\\n\\n💡 해설: 원문 요약", "note_type": "basic|cloze", "source_page": 1, "source_excerpt": "원문 발췌"}]}'
        )
        user_prompt = (
            f"난이도 모드: {difficulty_level} | 최대 카드 수: {max_cards}\n"
            "다음 문서 블록에서 시험 출제 가치가 높은 핵심 카드를 JSON으로 추출하세요:\n\n"
            f"{joined_doc}"
        )

        try:
            raw_content = self._call_ollama_cloud_chat(
                model=norm_model,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
            )
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_content.strip(), flags=re.IGNORECASE)
            parsed = json.loads(cleaned)
            raw_items = parsed.get("cards") if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
            cloud_cards: List[Dict[str, Any]] = []
            if isinstance(raw_items, list):
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    front = str(item.get("front_text") or item.get("front") or "").strip()
                    back = str(item.get("back_text") or item.get("back") or "").strip()
                    if not front or not back:
                        continue
                    pg = max(1, int(item.get("source_page") or 1))
                    if pg not in blocks_by_page and blocks_by_page:
                        pg = min(blocks_by_page.keys())
                    excerpt = str(item.get("source_excerpt") or "").strip()
                    if not excerpt:
                        page_txts = blocks_by_page.get(pg) or [joined_doc[:140]]
                        excerpt = page_txts[0][:160]
                    ntype = "cloze" if "{{c" in front else str(item.get("note_type") or "basic").lower()
                    if ntype not in ("basic", "cloze"):
                        ntype = "basic"
                    raw_tags = item.get("tags") if isinstance(item.get("tags"), list) else []
                    tags = list(dict.fromkeys([str(t) for t in raw_tags if t] + ["ollama-cloud", f"model:{norm_model}", f"diff_{difficulty_level}"]))
                    cloud_cards.append(
                        {
                            "front_text": front,
                            "back_text": back,
                            "note_type": ntype,
                            "tags": tags,
                            "rationale": f"Ollama Cloud ({norm_model}) 구조화 카드",
                            "pattern": str(item.get("pattern") or "ollama_cloud_grounded"),
                            "source_page": pg,
                            "source_excerpt": excerpt,
                        }
                    )
            if cloud_cards:
                return {
                    "ok": True,
                    "status": "OK",
                    "error_code": None,
                    "ollama_cloud_model": norm_model,
                    "ollama_cloud_used": True,
                    "provider": f"ollama_cloud:{norm_model}",
                    "fallback_reason": None,
                    "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                    "cards": cloud_cards[:max_cards],
                }
        except Exception as exc:
            fallback_err = type(exc).__name__
        else:
            fallback_err = "EmptyCloudCards"

        # Graceful Fail-Closed fallback to grounded base_cards tagged with requested model fallback
        enriched_base: List[Dict[str, Any]] = []
        for c in base_cards[:max_cards]:
            copy_c = dict(c)
            tags = list(copy_c.get("tags") or [])
            if f"ollama_fallback:{norm_model}" not in tags:
                tags.append(f"ollama_fallback:{norm_model}")
            copy_c["tags"] = tags
            enriched_base.append(copy_c)

        return {
            "ok": True,
            "status": "OK",
            "error_code": None,
            "ollama_cloud_model": norm_model,
            "ollama_cloud_used": False,
            "provider": f"local_grounded_fallback({norm_model})",
            "fallback_reason": f"ollama_cloud_fallback:{fallback_err}",
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "cards": enriched_base,
        }

    def synthesize_cards(
        self,
        raw_text: str,
        domain_mode: str = "auto",
        max_cards: int = 10,
        difficulty_level: str = "standard",
        ollama_cloud_model: str | None = None,
    ) -> Dict[str, Any]:
        """Synthesize cards using Ollama Cloud / configured LLM endpoint, or fall back to deterministic engine."""
        t0 = time.perf_counter()
        text = (raw_text or "").strip()
        if not text:
            return {
                "engine": "none",
                "provider": "none",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "fallback_reason": "empty_input",
                "error_code": None,
                "cards": [],
            }

        requested_cloud = (ollama_cloud_model or "").strip()
        if requested_cloud and is_ollama_cloud_model_blocked(requested_cloud):
            return {
                "engine": "blocked",
                "provider": "blocked_model_policy",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "fallback_reason": "blocked_model",
                "error_code": "BLOCKED_MODEL",
                "cards": [],
            }

        fallback_reason = "endpoint_unconfigured"
        error_code: str | None = None

        # 1. If Ollama Cloud model is explicitly requested (e.g. glm-5.3-flash, deepseek-v4.1-flash)
        if requested_cloud and requested_cloud.lower() not in ("local_rule", "off", "none", "local"):
            try:
                prompt = build_ai_card_generation_prompt(text, domain_mode=domain_mode, max_cards=max_cards)
                raw_resp = self._call_ollama_cloud_chat(
                    model=requested_cloud,
                    system_prompt="당신은 학습 노트에서 핵심 플래시카드를 생성하는 전문가입니다. JSON 배열 또는 {\"cards\": [...]} 형식으로 응답하세요.",
                    user_prompt=prompt,
                )
                specs = parse_ai_generated_cards(
                    text,
                    raw_resp,
                    domain_mode=domain_mode,
                    max_cards=max_cards,
                )
                if specs:
                    return {
                        "engine": f"ollama_cloud:{requested_cloud}",
                        "provider": f"ollama_cloud:{requested_cloud}",
                        "ollama_cloud_model": requested_cloud,
                        "ollama_cloud_used": True,
                        "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                        "fallback_reason": None,
                        "error_code": None,
                        "cards": [self._spec_to_dict(s) for s in specs[:max_cards]],
                    }
                fallback_reason = "empty_ollama_cloud_output"
            except Exception as exc:
                fallback_reason = "ollama_cloud_error"
                error_code = type(exc).__name__

        # 2. Custom OpenAI-compatible endpoint if configured
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
                        text,
                        content,
                        domain_mode=domain_mode,
                        max_cards=max_cards,
                    )
                    if specs:
                        return {
                            "engine": f"llm:{self.model_name}",
                            "provider": "llm",
                            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                            "fallback_reason": None,
                            "error_code": None,
                            "cards": [self._spec_to_dict(s) for s in specs[:max_cards]],
                        }
                    fallback_reason = "empty_llm_output"
                    error_code = "EmptyLLMOutput"
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
                fallback_reason = "endpoint_error"
                error_code = type(exc).__name__

        specs = extract_smart_cards_deterministic(
            text,
            domain_mode=domain_mode,
            max_cards=max_cards,
            difficulty_level=difficulty_level,
        )
        return {
            "engine": "deterministic-nlp-zero-quota",
            "provider": "deterministic_nlp",
            "ollama_cloud_model": requested_cloud or "local_rule",
            "ollama_cloud_used": False,
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "fallback_reason": fallback_reason,
            "error_code": error_code,
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
