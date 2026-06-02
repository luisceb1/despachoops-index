from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from despachoops_index.config import OllamaProfileSettings

ENRICH_SYSTEM = (
    "Archivista despacho abogados España. Devuelve SOLO JSON: "
    "tipo_documental, area (Fiscal|Laboral|Judicial|Contabilidad|Mercantil|Administrativo|General), "
    "resumen (max 280 chars), palabras_clave (array max 8), confianza (0-1), necesita_revision (bool). "
    "No inventes datos."
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


def profile_to_client(profile: OllamaProfileSettings) -> OllamaClientConfig:
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
            with urllib.request.urlopen(urllib.request.Request(url), timeout=30.0) as resp:
                body = json.loads(resp.read().decode())
            names = {m.get("name", "") for m in body.get("models", []) if isinstance(m, dict)}
            m = self.config.model
            if m not in names and not any(n.startswith(f"{m}:") for n in names):
                return False, f"modelo_no_disponible:{m}"
            return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, f"preflight_{type(exc).__name__}"

    def chat_json(self, prompt: str) -> OllamaChatResult:
        return self._chat(prompt, ENRICH_SYSTEM)

    def release_model(self) -> None:
        url = f"{self.config.base_url}/api/generate"
        payload = {"model": self.config.model, "prompt": "", "keep_alive": 0}
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=30.0)
        except Exception:  # noqa: BLE001
            pass

    def _chat(self, user: str, system: str) -> OllamaChatResult:
        cfg = self.config
        payload: dict[str, Any] = {
            "model": cfg.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "keep_alive": cfg.keep_alive,
            "options": {"temperature": cfg.temperature, "num_ctx": cfg.num_ctx, "num_predict": cfg.num_predict},
        }
        if cfg.use_json_format:
            payload["format"] = "json"
        url = f"{cfg.base_url}/api/chat"
        err = "ollama_error"
        for attempt in range(cfg.retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:
                    parsed = json.loads(resp.read().decode())
                content = (parsed.get("message") or {}).get("content", "") if isinstance(parsed, dict) else ""
                if str(content).strip():
                    return OllamaChatResult(str(content).strip())
                err = "respuesta_vacia"
            except urllib.error.URLError as exc:
                if "timed out" in str(exc.reason).casefold():
                    return OllamaChatResult("", "timeout")
                err = "conexion_ollama"
            except (TimeoutError, socket.timeout):
                return OllamaChatResult("", "timeout")
            except json.JSONDecodeError:
                err = "json_invalido"
        return OllamaChatResult("", err)
