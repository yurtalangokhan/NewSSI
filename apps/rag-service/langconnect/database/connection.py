"""PGVector / vectorstore connection helpers.

Exposes synchronous helpers for creating PGVector vectorstore
instances used by the collection layer.
"""

import logging
from typing import Any, Optional, Union

import sqlalchemy
from langchain_core.embeddings import Embeddings
from langchain_postgres.vectorstores import PGVector
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine

from langconnect import config

logger = logging.getLogger(__name__)


def get_vectorstore_engine(
    host: str = config.POSTGRES_HOST,
    port: str = config.POSTGRES_PORT,
    user: str = config.POSTGRES_USER,
    password: str = config.POSTGRES_PASSWORD,
    dbname: str = config.POSTGRES_DB,
) -> Engine:
    """Creates and returns a **sync** SQLAlchemy engine for PGVector."""
    connection_string = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(connection_string)


DBConnection = Union[sqlalchemy.engine.Engine, str]


def get_vectorstore(
    collection_name: str = config.DEFAULT_COLLECTION_NAME,
    embeddings: Embeddings = config.DEFAULT_EMBEDDINGS,
    engine: Optional[Union[DBConnection, Engine, AsyncEngine]] = None,
    collection_metadata: Optional[dict[str, Any]] = None,
) -> PGVector:
    """Initialise and return a PGVector store for a specific collection."""
    if engine is None:
        engine = get_vectorstore_engine()

    return PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=engine,
        use_jsonb=True,
        collection_metadata=collection_metadata,
    )
