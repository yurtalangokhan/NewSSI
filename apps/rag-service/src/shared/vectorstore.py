"""Vector store connection helpers.

Provides a factory that returns a Milvus (default) or PGVector vectorstore
instance depending on the VECTOR_DB_PROVIDER environment variable.

Postgres is used only for collection metadata (langchain_pg_collection).
All embedding / chunk data lives exclusively in Milvus.
"""

from collections import OrderedDict
from functools import cache
import re
from typing import Any

from config_manager import env
import httpx
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
import ollama
import openai
from pymilvus import MilvusException
import sqlalchemy
from sqlalchemy import URL, Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from src.shared.observability import get_logger

logger = get_logger(__name__)

DBConnection = sqlalchemy.engine.Engine | str

VECTOR_STORE_ERRORS: tuple[type[Exception], ...] = (
    MilvusException,
    httpx.HTTPError,
    openai.OpenAIError,
    ollama.ResponseError,
    OSError,
)


def to_milvus_collection_name(raw_name: str) -> str:
    """Normalize arbitrary collection labels to valid Milvus collection names.

    Milvus only allows [a-zA-Z0-9_] with a letter/underscore as the first char.
    Must match the normalization used in agent-service so both services address
    the same Milvus collection.
    """
    name = re.sub(r"[^a-zA-Z0-9_]", "_", (raw_name or "").strip())
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        name = "collection"
    if name[0].isdigit():
        name = f"c_{name}"
    return name


def _get_milvus_connection_args() -> dict[str, Any]:
    """Build Milvus connection args from env."""
    return {
        "host": env.MILVUS_HOST,
        "port": str(env.MILVUS_PORT),
        "user": env.MILVUS_USER,
        "password": env.MILVUS_PASSWORD,
        "secure": False,
    }


def _build_pgvector_url() -> str:
    """Build a PGVector connection string using SQLAlchemy URL.create."""
    return URL.create(
        drivername="postgresql+psycopg",
        username=env.POSTGRES_RAG_SERVICE_USER,
        password=env.POSTGRES_RAG_SERVICE_PASSWORD,
        host=env.POSTGRES_HOST,
        port=env.POSTGRES_PORT,
        database=env.POSTGRES_RAG_SERVICE_DB,
    ).render_as_string(hide_password=False)


def _build_pgvector_store(
    *,
    collection_name: str,
    embeddings: Embeddings,
    engine: DBConnection | Engine | AsyncEngine | None,
    collection_metadata: dict[str, Any] | None,
) -> VectorStore:
    """Construct a PGVector store (legacy provider)."""
    from langchain_postgres.vectorstores import PGVector
    from sqlalchemy import create_engine

    if engine is None:
        engine = create_engine(_build_pgvector_url())
    return PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=engine,
        use_jsonb=True,
        collection_metadata=collection_metadata,
    )


@cache
def chunk_id_milvus_class() -> type[VectorStore]:
    """Milvus whose parsed rows keep the primary key as ``Document.id``.

    The library's ``_parse_document`` keeps only the text and metadata fields,
    so search results lost the chunk's identity and callers fell back to the
    file id, making every chunk of a file indistinguishable.
    """
    from langchain_community.vectorstores import Milvus

    class ChunkIdMilvus(Milvus):
        def _parse_document(self, data: dict[str, Any]) -> Document:
            primary_key = data.get(self._primary_field)
            document = super()._parse_document(data)
            if primary_key is not None:
                document.id = str(primary_key)
            return document

    return ChunkIdMilvus


def _build_milvus_store(
    milvus_collection_name: str,
    embeddings: Embeddings,
    *,
    index_params: dict[str, Any] | None = None,
    search_params: dict[str, Any] | None = None,
) -> VectorStore:
    """Construct a Milvus store for an already-normalised collection name.

    index_params/search_params are None by default, which lets the library
    fall back to its own default (L2 distance) -- callers whose scores need
    to mean something more interpretable than a raw distance (e.g. a
    similarity threshold) pass an explicit metric, most commonly COSINE.
    """
    return chunk_id_milvus_class()(
        embedding_function=embeddings,
        collection_name=milvus_collection_name,
        connection_args=_get_milvus_connection_args(),
        auto_id=True,
        # metadata_field stores the entire metadata dict as JSON in one field
        metadata_field="metadata",
        index_params=index_params,
        search_params=search_params,
    )


#: Milvus stores, keyed by normalised collection name. Constructing one
#: registers a connection alias and round-trips to the server for the
#: collection's schema, and every operation on a collection used to
#: construct a fresh one. Bounded so a deployment with many collections
#: cannot grow this without limit.
_MILVUS_STORES: "OrderedDict[str, VectorStore]" = OrderedDict()
_MILVUS_STORE_CACHE_SIZE = 128


def clear_vectorstore_cache() -> None:
    """Drop every cached store. For tests and for shutdown."""
    _MILVUS_STORES.clear()


def forget_vectorstore(collection_name: str) -> None:
    """Drop the cached store of one collection, after its Milvus table was dropped.

    A LangChain Milvus store keeps the field list of the table it was built on
    and appends to it when it initialises again, so a store that outlived its
    table cannot create the table anew (the insert fails on a schema mismatch).
    The next ``get_vectorstore`` call builds a fresh store instead.
    """
    _MILVUS_STORES.pop(to_milvus_collection_name(collection_name), None)


def get_vectorstore(
    collection_name: str = env.DEFAULT_COLLECTION_NAME,
    embeddings: Embeddings | None = None,
    engine: DBConnection | Engine | AsyncEngine | None = None,
    collection_metadata: dict[str, Any] | None = None,
    index_params: dict[str, Any] | None = None,
    search_params: dict[str, Any] | None = None,
):
    """Initialise and return a vector store for a specific collection.

    With VECTOR_DB_PROVIDER=milvus (default), returns a Milvus store,
    reused across calls for the same collection. With
    VECTOR_DB_PROVIDER=pgvector, returns a freshly built PGVector store
    (legacy); those are cheap and take a caller-supplied engine, so there
    is nothing to share.

    index_params/search_params configure the collection's similarity
    metric (e.g. COSINE instead of the library's default L2 distance).
    They only matter at collection-creation time, but a caller supplying
    them is asking for behavior distinct from the shared default store, so
    (like a custom embeddings) it is never served from or added to the
    default cache.

    ``embeddings=None`` means this service's own default embedding
    (``env.DEFAULT_EMBEDDINGS``) — the one embedding a store may be shared
    across calls with. It is resolved here rather than as a default argument
    because a default argument binds whatever the module imported at load time:
    a reloaded or repatched ``config`` would then make every default call look
    like a caller-supplied embedding and silently stop sharing stores.
    """
    default_embeddings = env.DEFAULT_EMBEDDINGS
    resolved_embeddings = default_embeddings if embeddings is None else embeddings
    provider = env.VECTOR_DB_PROVIDER.lower()

    if provider == "pgvector":
        return _build_pgvector_store(
            collection_name=collection_name,
            embeddings=resolved_embeddings,
            engine=engine,
            collection_metadata=collection_metadata,
        )

    milvus_collection_name = to_milvus_collection_name(collection_name)

    # Only the default embeddings AND default index/search params are
    # shareable: a caller that brings its own must not be handed a store
    # wired to someone else's model or metric, and must not evict the
    # shared one either.
    if resolved_embeddings is not default_embeddings or index_params is not None or search_params is not None:
        return _build_milvus_store(
            milvus_collection_name,
            resolved_embeddings,
            index_params=index_params,
            search_params=search_params,
        )

    cached = _MILVUS_STORES.get(milvus_collection_name)
    if cached is not None:
        _MILVUS_STORES.move_to_end(milvus_collection_name)
        return cached

    store = _build_milvus_store(milvus_collection_name, resolved_embeddings)

    # A store whose collection does not exist on the server yet carries
    # col=None and never learns otherwise unless it is the instance that
    # creates it. Caching that would pin an "empty collection" answer for
    # the life of the process, so it is left out until it is real.
    if getattr(store, "col", None) is not None:
        _MILVUS_STORES[milvus_collection_name] = store
        while len(_MILVUS_STORES) > _MILVUS_STORE_CACHE_SIZE:
            _MILVUS_STORES.popitem(last=False)

    return store
