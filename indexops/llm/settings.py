from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OllamaProfileSettings:
    model: str = "qwen3:8b"
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 120.0
    num_ctx: int = 4096
    num_predict: int = 512
    keep_alive: str = "5m"
    temperature: float = 0.0
    ollama_format: str = "json"
    retries: int = 1


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool = False
    max_files_per_run: int = 20
    text_chars_for_prompt: int = 3500
    min_text_chars: int = 80
    release_model_after_batch: bool = True
    profile: OllamaProfileSettings = OllamaProfileSettings()


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_profile(raw: Any, *, defaults: OllamaProfileSettings) -> OllamaProfileSettings:
    if not isinstance(raw, dict):
        return defaults
    return OllamaProfileSettings(
        model=str(raw.get("model", defaults.model)).strip() or defaults.model,
        base_url=str(raw.get("base_url", defaults.base_url)).strip() or defaults.base_url,
        timeout_seconds=_coerce_float(raw.get("timeout_seconds"), defaults.timeout_seconds),
        num_ctx=_coerce_int(raw.get("num_ctx"), defaults.num_ctx),
        num_predict=_coerce_int(raw.get("num_predict"), defaults.num_predict),
        keep_alive=str(raw.get("keep_alive", defaults.keep_alive)).strip() or defaults.keep_alive,
        temperature=_coerce_float(raw.get("temperature"), defaults.temperature),
        ollama_format=str(raw.get("format", raw.get("ollama_format", defaults.ollama_format))).strip().casefold()
        or defaults.ollama_format,
        retries=_coerce_int(raw.get("retries"), defaults.retries),
    )


def parse_llm_config(raw: Any) -> LlmConfig:
    if not isinstance(raw, dict):
        return LlmConfig()
    enrich_defaults = OllamaProfileSettings(
        model="qwen3:8b",
        timeout_seconds=120.0,
        num_ctx=4096,
        num_predict=512,
        ollama_format="json",
        keep_alive="5m",
    )
    profile = _parse_profile(raw.get("enrich") or raw.get("profile"), defaults=enrich_defaults)
    return LlmConfig(
        enabled=bool(raw.get("enabled", False)),
        max_files_per_run=_coerce_int(raw.get("max_files_per_run"), 20),
        text_chars_for_prompt=_coerce_int(raw.get("text_chars_for_prompt"), 3500),
        min_text_chars=_coerce_int(raw.get("min_text_chars"), 80),
        release_model_after_batch=bool(raw.get("release_model_after_batch", True)),
        profile=profile,
    )
