"""Migrate existing PGVector-backed chunks into Milvus collections.

This script reads rows from langchain_pg_embedding and re-indexes documents
into Milvus using the same logical collection mapping used by the API.

Usage:
  python -m langconnect.scripts.migrate_pgvector_to_milvus --dry-run
  python -m langconnect.scripts.migrate_pgvector_to_milvus --batch-size 200
  python -m langconnect.scripts.migrate_pgvector_to_milvus --collection-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document
from langchain_community.vectorstores import Milvus
from sqlalchemy import Select, select

from langconnect import config
from langconnect.database.postgres.models import PgCollection, PgEmbedding
from langconnect.database.postgres.repositories.base import BaseRepository

logger = logging.getLogger("pgvector_to_milvus")


@dataclass
class ChunkRow:
    """Container for one PG chunk row."""

    id: str
    collection_id: str
    collection_table_name: str
    document: str
    metadata: dict[str, Any]


class _ReadRepo(BaseRepository):
    """Read-only helpers for migration queries."""

    async def fetch_candidate_chunks(self, collection_id: str | None = None) -> list[ChunkRow]:
        """Fetch chunks that still have pgvector embeddings.

        Rows with non-null embedding are treated as originating from PGVector.
        Rows inserted during Milvus mode generally have embedding=NULL and are skipped.
        """
        async with self._session() as session:
            stmt: Select[tuple[PgEmbedding, PgCollection]] = (
                select(PgEmbedding, PgCollection)
                .join(PgCollection, PgEmbedding.collection_id == PgCollection.uuid)
                .where(PgEmbedding.embedding.is_not(None))
                .where(PgEmbedding.document.is_not(None))
            )
            if collection_id:
                stmt = stmt.where(PgEmbedding.collection_id == collection_id)

            rows = (await session.execute(stmt)).all()

        chunks: list[ChunkRow] = []
        for emb, col in rows:
            meta = emb.cmetadata if isinstance(emb.cmetadata, dict) else {}
            chunks.append(
                ChunkRow(
                    id=str(emb.id),
                    collection_id=str(col.uuid),
                    collection_table_name=col.name,
                    document=emb.document or "",
                    metadata=meta.copy(),
                )
            )
        return chunks


def _build_milvus_store(collection_table_name: str) -> Milvus:
    """Create a Milvus vector store using app config."""
    milvus_collection_name = collection_table_name.replace("-", "_")
    if milvus_collection_name and milvus_collection_name[0].isdigit():
        milvus_collection_name = f"c_{milvus_collection_name}"

    return Milvus(
        embedding_function=config.DEFAULT_EMBEDDINGS,
        collection_name=milvus_collection_name,
        connection_args={
            "host": config.MILVUS_HOST,
            "port": str(config.MILVUS_PORT),
            "user": config.MILVUS_USER,
            "password": config.MILVUS_PASSWORD,
            "secure": False,
        },
        auto_id=True,
        metadata_field="metadata",
    )


def _chunked(seq: list[ChunkRow], size: int) -> list[list[ChunkRow]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


async def migrate(*, batch_size: int, dry_run: bool, collection_id: str | None) -> None:
    """Run migration from PGVector rows to Milvus collections."""
    repo = _ReadRepo()
    rows = await repo.fetch_candidate_chunks(collection_id=collection_id)

    if not rows:
        logger.info("No PGVector chunks found to migrate.")
        return

    by_collection: dict[str, list[ChunkRow]] = defaultdict(list)
    for row in rows:
        by_collection[row.collection_id].append(row)

    logger.info(
        "Found %d chunks across %d collection(s).",
        len(rows),
        len(by_collection),
    )

    total_written = 0

    for cid, chunks in by_collection.items():
        table_name = chunks[0].collection_table_name
        logger.info(
            "Collection %s (table=%s): %d chunk(s)",
            cid,
            table_name,
            len(chunks),
        )

        if dry_run:
            continue

        store = _build_milvus_store(table_name)
        for batch in _chunked(chunks, batch_size):
            docs = [
                Document(
                    page_content=row.document,
                    metadata={**row.metadata, "source_pg_id": row.id},
                )
                for row in batch
            ]
            ids = store.add_documents(docs)
            total_written += len(ids)

        logger.info("Migrated %d chunk(s) for collection %s.", len(chunks), cid)

    if dry_run:
        logger.info("Dry-run complete. No data written to Milvus.")
    else:
        logger.info("Migration complete. Total migrated chunks: %d", total_written)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate PGVector chunks into Milvus")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Number of chunks to embed/write per batch (default: 200)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be migrated, do not write to Milvus",
    )
    parser.add_argument(
        "--collection-id",
        type=str,
        default=None,
        help="Optional collection UUID filter",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _build_parser().parse_args()

    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be > 0")

    asyncio.run(
        migrate(
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            collection_id=args.collection_id,
        )
    )


if __name__ == "__main__":
    main()
