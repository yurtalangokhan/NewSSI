"""Vector store connection helpers.

Provides a factory that returns a Milvus (default) or PGVector vectorstore
instance depending on the VECTOR_DB_PROVIDER environment variable.

Postgres is still used for collection metadata (langchain_pg_collection /
langchain_pg_embedding tables) — the switch only affects where embedding
vectors are stored and searched.
"""

import logging
from typing import Any, Optional, Union

import sqlalchemy
from langchain_core.embeddings import Embeddings
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from langconnect import config

logger = logging.getLogger(__name__)

DBConnection = Union[sqlalchemy.engine.Engine, str]


def _get_milvus_connection_args() -> dict[str, Any]:
    """Build Milvus connection args from config."""
    return {
        "host": config.MILVUS_HOST,
        "port": str(config.MILVUS_PORT),
        "user": config.MILVUS_USER,
        "password": config.MILVUS_PASSWORD,
        "secure": False,
    }


def get_vectorstore(
    collection_name: str = config.DEFAULT_COLLECTION_NAME,
    embeddings: Embeddings = config.DEFAULT_EMBEDDINGS,
    engine: Optional[Union[DBConnection, Engine, AsyncEngine]] = None,
    collection_metadata: Optional[dict[str, Any]] = None,
):
    """Initialise and return a vector store for a specific collection.

    With VECTOR_DB_PROVIDER=milvus (default), returns a Milvus store.
    With VECTOR_DB_PROVIDER=pgvector, returns a PGVector store (legacy).
    """
    provider = config.VECTOR_DB_PROVIDER.lower()

    if provider == "pgvector":
        from langchain_postgres.vectorstores import PGVector
        from sqlalchemy import create_engine

        if engine is None:
            connection_string = (
                f"postgresql+psycopg://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}"
                f"@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
            )
            engine = create_engine(connection_string)
        return PGVector(
            embeddings=embeddings,
            collection_name=collection_name,
            connection=engine,
            use_jsonb=True,
            collection_metadata=collection_metadata,
        )

    # Default: Milvus
    from langchain_community.vectorstores import Milvus  # noqa: PLC0415

    # Milvus collection names only allow [a-zA-Z0-9_] and must start with a letter/underscore
    milvus_collection_name = collection_name.replace("-", "_")
    if milvus_collection_name and milvus_collection_name[0].isdigit():
        milvus_collection_name = "c_" + milvus_collection_name

    connection_args = _get_milvus_connection_args()
    return Milvus(
        embedding_function=embeddings,
        collection_name=milvus_collection_name,
        connection_args=connection_args,
        auto_id=True,
        # metadata_field stores the entire metadata dict as JSON in one field
        metadata_field="metadata",
    )
