from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

LONG_PATH_THRESHOLD = 240

SKIP_DIRS = frozenset(
    {".git", ".venv", "__pycache__", "node_modules", "dist", "build"}
)

SKIP_NAME_PATTERNS = (
    "~$*",
    "Thumbs.db",
    ".DS_Store",
    "desktop.ini",
    "*.tmp",
    "*.lock",
    "*.crdownload",
    "*.part",
)

# Ruido web / assets estáticos (no documentación de despacho)
SKIP_EXTENSIONS = frozenset(
    {
        ".gif",
        ".css",
        ".js",
        ".map",
        ".ico",
        ".svg",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".less",
        ".scss",
    }
)

SKIP_PATH_PATTERNS = (
    "*/.git/*",
    "*/node_modules/*",
)

DOCUMENT_EXTENSIONS = frozenset({".pdf", ".docx", ".xlsx", ".xls", ".txt", ".csv"})
TEXT_EXTENSIONS = frozenset({".txt", ".csv"})
TEXT_PREVIEW_MAX = 4000
TEXT_FTS_MAX = 20000


@dataclass(frozen=True)
class ScanFilters:
    exclude_dirs: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    exclude_path_patterns: tuple[str, ...] = ()
    exclude_extensions: tuple[str, ...] = ()

    def merged_dirs(self) -> frozenset[str]:
        return frozenset({d.lower() for d in self.exclude_dirs} | SKIP_DIRS)

    def merged_name_patterns(self) -> tuple[str, ...]:
        return self.exclude_patterns + SKIP_NAME_PATTERNS

    def merged_path_patterns(self) -> tuple[str, ...]:
        return self.exclude_path_patterns + SKIP_PATH_PATTERNS

    def merged_extensions(self) -> frozenset[str]:
        extra = {
            e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in self.exclude_extensions
        }
        return SKIP_EXTENSIONS | extra


@dataclass(frozen=True)
class IndexOptions:
    root: Path
    db_path: Path
    limit: int = 0
    include_text: bool = False
    incremental: bool = False
    use_ocr_cache: bool = False
    ocr_cache_dir: Path | None = None
    skip_large_files_mb: int = 0
    exclude_dirs: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    exclude_path_patterns: tuple[str, ...] = ()
    exclude_extensions: tuple[str, ...] = ()

    def to_scan_filters(self) -> ScanFilters:
        return ScanFilters(
            exclude_dirs=self.exclude_dirs,
            exclude_patterns=self.exclude_patterns,
            exclude_path_patterns=self.exclude_path_patterns,
            exclude_extensions=self.exclude_extensions,
        )


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


@dataclass(frozen=True)
class AppConfig:
    scan_root: Path
    data_dir: Path
    index_db_path: Path
    log_dir: Path
    ocr_cache_dir: Path
    ocr_queue_path: Path
    worker_lock_path: Path
    recursive: bool
    max_files_per_index_run: int
    max_files_per_ocr_run: int
    catalog_each_night_cycle: bool
    index_text_enabled: bool
    index_skip_large_files_mb: int
    ocr_skip_large_files_mb: int
    ocr_worker_enabled: bool
    ocr_max_pages_per_file: int
    ocr_languages: str
    night_window_start: str
    night_window_end: str
    require_idle_minutes: int
    exclude_dirs: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    exclude_path_patterns: tuple[str, ...]
    exclude_extensions: tuple[str, ...]
    llm: LlmConfig
    worker_enabled: bool
    worker_interval_seconds: int
    worker_stale_lock_minutes: int
    config_source: Path | None = None

    def to_index_options(self, *, include_text: bool | None = None, limit: int | None = None) -> IndexOptions:
        return IndexOptions(
            root=self.scan_root,
            db_path=self.index_db_path,
            limit=limit if limit is not None else self.max_files_per_index_run,
            include_text=self.index_text_enabled if include_text is None else include_text,
            incremental=True,
            use_ocr_cache=True,
            ocr_cache_dir=self.ocr_cache_dir,
            skip_large_files_mb=self.index_skip_large_files_mb,
            exclude_dirs=self.exclude_dirs,
            exclude_patterns=self.exclude_patterns,
            exclude_path_patterns=self.exclude_path_patterns,
            exclude_extensions=self.exclude_extensions,
        )

    def to_scan_filters(self) -> ScanFilters:
        return ScanFilters(
            exclude_dirs=self.exclude_dirs,
            exclude_patterns=self.exclude_patterns,
            exclude_path_patterns=self.exclude_path_patterns,
            exclude_extensions=self.exclude_extensions,
        )


def resolve_paths(root: str | Path, db: str | Path) -> IndexOptions:
    return IndexOptions(
        root=Path(root).expanduser().resolve(),
        db_path=Path(db).expanduser().resolve(),
    )


def load_app_config(path: Path | str = "config.yaml") -> AppConfig:
    source = Path(path).resolve()
    raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    data_dir = Path(str(raw.get("data_dir") or "data")).expanduser()
    worker = raw.get("worker") or {}
    return AppConfig(
        scan_root=Path(str(raw.get("scan_root") or ".")).expanduser(),
        data_dir=data_dir,
        index_db_path=Path(str(raw["index_db_path"])) if raw.get("index_db_path") else data_dir / "despacho_index.sqlite",
        log_dir=Path(str(raw["log_dir"])) if raw.get("log_dir") else data_dir / "logs",
        ocr_cache_dir=Path(str(raw["ocr_cache_dir"])) if raw.get("ocr_cache_dir") else data_dir / "ocr_cache",
        ocr_queue_path=Path(str(raw["ocr_queue_path"])) if raw.get("ocr_queue_path") else data_dir / "ocr_jobs.csv",
        worker_lock_path=Path(str(raw["worker_lock_path"])) if raw.get("worker_lock_path") else data_dir / ".despachoops_index.lock",
        recursive=bool(raw.get("recursive", True)),
        max_files_per_index_run=int(raw.get("max_files_per_index_run", 5000)),
        max_files_per_ocr_run=int(raw.get("max_files_per_ocr_run", 150)),
        catalog_each_night_cycle=bool(raw.get("catalog_each_night_cycle", False)),
        index_text_enabled=bool(raw.get("index_text_enabled", True)),
        index_skip_large_files_mb=int(raw.get("index_skip_large_files_mb", 80)),
        ocr_skip_large_files_mb=int(raw.get("ocr_skip_large_files_mb", 120)),
        ocr_worker_enabled=bool(raw.get("ocr_worker_enabled", True)),
        ocr_max_pages_per_file=int(raw.get("ocr_max_pages_per_file", 15)),
        ocr_languages=str(raw.get("ocr_languages", "spa+eng")),
        night_window_start=str(raw.get("night_window_start", "23:00")),
        night_window_end=str(raw.get("night_window_end", "06:00")),
        require_idle_minutes=int(raw.get("require_idle_minutes", 10)),
        exclude_dirs=_tuple(raw.get("exclude_dirs")),
        exclude_patterns=_tuple(raw.get("exclude_patterns")),
        exclude_path_patterns=_tuple(raw.get("exclude_path_patterns")),
        exclude_extensions=_tuple(raw.get("exclude_extensions")),
        llm=_parse_llm(raw.get("llm")),
        worker_enabled=bool(worker.get("enabled", True)),
        worker_interval_seconds=int(worker.get("interval_seconds", 600)),
        worker_stale_lock_minutes=int(worker.get("stale_lock_minutes", 180)),
        config_source=source,
    )


def _parse_llm(raw: Any) -> LlmConfig:
    if not isinstance(raw, dict):
        return LlmConfig()
    defaults = OllamaProfileSettings()
    enrich = raw.get("enrich") or raw.get("profile") or {}
    profile = _parse_profile(enrich, defaults) if isinstance(enrich, dict) else defaults
    return LlmConfig(
        enabled=bool(raw.get("enabled", False)),
        max_files_per_run=int(raw.get("max_files_per_run", 20)),
        text_chars_for_prompt=int(raw.get("text_chars_for_prompt", 3500)),
        min_text_chars=int(raw.get("min_text_chars", 80)),
        release_model_after_batch=bool(raw.get("release_model_after_batch", True)),
        profile=profile,
    )


def _parse_profile(raw: dict, defaults: OllamaProfileSettings) -> OllamaProfileSettings:
    return OllamaProfileSettings(
        model=str(raw.get("model", defaults.model)).strip() or defaults.model,
        base_url=str(raw.get("base_url", defaults.base_url)).strip() or defaults.base_url,
        timeout_seconds=float(raw.get("timeout_seconds", defaults.timeout_seconds)),
        num_ctx=int(raw.get("num_ctx", defaults.num_ctx)),
        num_predict=int(raw.get("num_predict", defaults.num_predict)),
        keep_alive=str(raw.get("keep_alive", defaults.keep_alive)),
        temperature=float(raw.get("temperature", defaults.temperature)),
        ollama_format=str(raw.get("format", raw.get("ollama_format", defaults.ollama_format))).lower(),
        retries=int(raw.get("retries", defaults.retries)),
    )


def _tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(str(x) for x in value)
