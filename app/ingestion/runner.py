from __future__ import annotations

import logging
from pathlib import Path
from openai import RateLimitError

from .chunker import build_chunks, validate_chunks
from .config import IngestionConfig, load_config_from_env_and_args
from .embedder import build_embedder
from .loader import discover_corpus_files, load_source_document
from .models import IngestionReport
from .normalizer import normalize_document, validate_source_document
from .report import write_ingestion_report
from .repository import Repository
from .segmenter import segment_document
from app.common.config import EmbeddingConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def is_insufficient_quota_error(exc: RateLimitError) -> bool:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", {})
        if isinstance(error, dict) and error.get("code") == "insufficient_quota":
            return True

    # fallback in case body shape changes
    return "insufficient_quota" in str(exc)


def run_ingestion(config: IngestionConfig, embedding_config: EmbeddingConfig) -> IngestionReport:
    report = IngestionReport.start()
    repository = Repository(db_url=config.db_url, dry_run=config.dry_run)
    embedder = build_embedder(embedding_config)

    files = discover_corpus_files(config.corpus_root, config.allowed_extensions)
    logger.info("Discovered %s corpus files", len(files))

    for file_path in files:
        logger.info("Processing %s", file_path)
        try:
            source_doc = load_source_document(file_path)
            validate_source_document(source_doc)

            normalized_doc = normalize_document(source_doc)
            sections = segment_document(normalized_doc)
            chunks = build_chunks(
                document=normalized_doc,
                sections=sections,
                target_tokens=config.target_tokens,
                soft_max_tokens=config.soft_max_tokens,
                hard_max_tokens=config.hard_max_tokens,
                overlap_tokens=config.overlap_tokens,
            )
            validate_chunks(chunks, config.hard_max_tokens)

            embeddings = embedder.embed_texts([chunk.chunk_text for chunk in chunks])
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                chunk.embedding = embedding

            document_id = repository.upsert_document_record(normalized_doc)
            if config.replace_existing_chunks:
                repository.delete_existing_chunks_for_document(document_id)
            repository.insert_chunk_records(document_id, chunks, embedding_config.model)

            report.add_success(file_path=str(file_path), doc_key=normalized_doc.doc_key, chunks=chunks)

        except RateLimitError as exc:
            if is_insufficient_quota_error(exc):
                logger.error(
                    "OpenAI returned insufficient_quota while processing %s. "
                    "Aborting ingestion immediately.",
                    file_path,
                )
                report.add_failure(
                    file_path=str(file_path),
                    error="OpenAI insufficient_quota: ingestion aborted",
                )
                report.finished_at = IngestionReport.utc_now_iso()
                write_ingestion_report(report, config.artifacts_dir / "ingestion_report.json")
                raise RuntimeError(
                    "OpenAI API insufficient_quota: ingestion aborted after first failure."
                ) from exc

            logger.exception("Rate limit error while ingesting %s", file_path)
            report.add_failure(file_path=str(file_path), error=str(exc))

        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to ingest %s", file_path)
            report.add_failure(file_path=str(file_path), error=str(exc))

    report.finished_at = IngestionReport.utc_now_iso()
    write_ingestion_report(report, config.artifacts_dir / "ingestion_report.json")
    return report



def main(argv: list[str] | None = None) -> int:
    config = load_config_from_env_and_args(argv)
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)

    embedding_config = EmbeddingConfig()

    report = run_ingestion(config, embedding_config)

    logger.info("Documents succeeded: %s", len(report.successes))
    logger.info("Documents failed: %s", len(report.failures))
    return 1 if report.failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
