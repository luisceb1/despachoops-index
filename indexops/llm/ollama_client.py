from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from indexops.llm.settings import OllamaProfileSettings

LOGGER = logging.getLogger(__name__)

ENRICH_SYSTEM_PROMPT = (
    "Eres un archivista de un despacho de abogados en España. "
    "Analiza el extracto y devuelve SOLO JSON válido con las claves: "
    "tipo_documental (string), area (Fiscal|Laboral|Judicial|Contabilidad|Mercantil|Administrativo|General), "
    "resumen (máx 280 caracteres), palabras_clave (array de strings, máx 8), "
    "confianza (número 0-1), necesita_revision (boolean). "
    "No inventes NIF, fechas ni nombres que no aparezcan en el texto. Si hay duda, necesita_revision=true."
)


@dataclass(frozen=True)
class OllamaChatResult:
    content: str
    error: str | None = None


@dataclass(frozen=True)
class OllamaClientConfig:
    base_url: str
    model: str
    timeout_seconds: float
    retries: int
    temperature: float
    num_ctx: int
    num_predict: int
    keep_alive: str
    use_json_format: bool


def profile_to_client_config(profile: OllamaProfileSettings) -> OllamaClientConfig:
    return OllamaClientConfig(
        base_url=profile.base_url.rstrip("/"),
        model=profile.model,
        timeout_seconds=profile.timeout_seconds,
        retries=max(0, profile.retries),
        temperature=profile.temperature,
        num_ctx=profile.num_ctx,
        num_predict=profile.num_predict,
        keep_alive=profile.keep_alive,
        use_json_format=profile.ollama_format == "json",
    )


class OllamaClient:
    def __init__(self, config: OllamaClientConfig) -> None:
        self.config = config

    def preflight(self) -> tuple[bool, str]:
        url = f"{self.config.base_url}/api/tags"
        try:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=min(self.config.timeout_seconds, 30.0)) as response:
                body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(body)
            names = {
                str(item.get("name", "")).strip()
                for item in (parsed.get("models") or [])
                if isinstance(item, dict) and item.get("name")
            }
            model = self.config.model
            if model not in names and not any(n.startswith(f"{model}:") for n in names):
                return False, f"modelo_no_disponible:{model}"
            return True, ""
        except urllib.error.URLError as exc:
            if _is_timeout(exc):
                return False, "preflight_timeout"
            return False, "preflight_conexion_ollama"
        except Exception as exc:  # noqa: BLE001
            return False, f"preflight_error_{type(exc).__name__}"

    def chat_json(self, user_prompt: str) -> OllamaChatResult:
        return self._chat(user_prompt, system=ENRICH_SYSTEM_PROMPT)

    def release_model(self) -> None:
        url = f"{self.config.base_url}/api/generate"
        payload = {"model": self.config.model, "prompt": "", "keep_alive": 0}
        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=min(self.config.timeout_seconds, 30.0)):
                return
        except Exception:  # noqa: BLE001
            LOGGER.debug("release_model best-effort failed")

    def _chat(self, user_prompt: str, *, system: str) -> OllamaChatResult:
        cfg = self.config
        payload: dict[str, Any] = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "keep_alive": cfg.keep_alive,
            "options": {
                "temperature": cfg.temperature,
                "num_ctx": cfg.num_ctx,
                "num_predict": cfg.num_predict,
            },
        }
        if cfg.use_json_format:
            payload["format"] = "json"

        url = f"{cfg.base_url}/api/chat"
        last_error = "ollama_error"
        for attempt in range(cfg.retries + 1):
            try:
                request = urllib.request.Request(
                    url,
                    data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=cfg.timeout_seconds) as response:
                    body = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(body)
                message = parsed.get("message") if isinstance(parsed, dict) else None
                content = ""
                if isinstance(message, dict):
                    content = str(message.get("content", "") or "").strip()
                if content:
                    return OllamaChatResult(content=content)
                last_error = "respuesta_vacia"
            except urllib.error.URLError as exc:
                if _is_timeout(exc):
                    return OllamaChatResult(content="", error="timeout")
                last_error = "conexion_ollama"
            except (TimeoutError, socket.timeout):
                return OllamaChatResult(content="", error="timeout")
            except json.JSONDecodeError:
                last_error = "json_respuesta_invalido"
            except Exception as exc:  # noqa: BLE001
                last_error = f"error_{type(exc).__name__}"
            if attempt < cfg.retries:
                import time

                time.sleep(0.3)
        return OllamaChatResult(content="", error=last_error)


def _is_timeout(exc: urllib.error.URLError) -> bool:
    reason = exc.reason
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return True
    text = str(reason).casefold()
    return "timed out" in text or "timeout" in text
