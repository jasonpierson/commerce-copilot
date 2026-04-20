from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class IngestionConfig:
    corpus_root: Path
    artifacts_dir: Path
    allowed_extensions: tuple[str, ...] = (".md", ".txt")
    target_tokens: int = 350
    soft_max_tokens: int = 550
    hard_max_tokens: int = 700
    overlap_tokens: int = 60
    batch_size: int = 32
    replace_existing_chunks: bool = True
    dry_run: bool = False
    db_url: str | None = None



def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run corpus ingestion.")
    parser.add_argument("--corpus-root", default=os.getenv("CORPUS_ROOT", "./corpus"))
    parser.add_argument("--artifacts-dir", default=os.getenv("ARTIFACTS_DIR", "./artifacts"))
    parser.add_argument("--dry-run", action="store_true")
    return parser



def load_config_from_env_and_args(argv: list[str] | None = None) -> IngestionConfig:
    parser = build_parser()
    args = parser.parse_args(argv)
    return IngestionConfig(
        corpus_root=Path(args.corpus_root).resolve(),
        artifacts_dir=Path(args.artifacts_dir).resolve(),
        target_tokens=int(os.getenv("TARGET_TOKENS", "350")),
        soft_max_tokens=int(os.getenv("SOFT_MAX_TOKENS", "550")),
        hard_max_tokens=int(os.getenv("HARD_MAX_TOKENS", "700")),
        overlap_tokens=int(os.getenv("OVERLAP_TOKENS", "60")),
        batch_size=int(os.getenv("BATCH_SIZE", "32")),
        replace_existing_chunks=_env_bool("REPLACE_EXISTING_CHUNKS", True),
        dry_run=bool(args.dry_run),
        db_url=os.getenv("SUPABASE_DB_URL"),
    )
