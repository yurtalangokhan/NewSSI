import re
from threading import Lock
from uuid import uuid4

from langchain_community.vectorstores import Milvus  # noqa: PLC0415
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings

from core.env import env
from core.logger import get_logger

logger = get_logger(__name__)

_VECTOR_STORE_CACHE: dict[str, Milvus] = {}
_VECTOR_STORE_LOCK = Lock()


def _to_milvus_collection_name(raw_name: str) -> str:
    """Normalize arbitrary collection labels to valid Milvus collection names.

    Milvus requires names to contain only letters, numbers and underscores,
    and the first character must be a letter or underscore.
    """
    name = (raw_name or "").strip()
    # Replace all unsupported characters (spaces, dashes, punctuation, etc.)
    # with underscores and collapse consecutive underscores for readability.
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")

    if not name:
        name = "collection"
    if name[0].isdigit():
        name = f"c_{name}"
    return name


def _get_milvus_connection_args() -> dict:
    """Build Milvus connection args from environment."""
    return {
        "host": env.get("MILVUS_HOST", "localhost"),
        "port": env.get("MILVUS_PORT", "9765"),
        "user": env.get("MILVUS_USER", ""),
        "password": env.get("MILVUS_PASSWORD", ""),
        "secure": False,
    }


def _count_milvus_entities_batch(collection_names: list[str]) -> dict[str, int]:
    """Count Milvus entities for multiple collections using one shared connection."""
    names = [n for n in collection_names if n]
    if not names:
        return {}
    from pymilvus import Collection, connections, utility

    alias = f"milvus-batch-{uuid4().hex[:8]}"
    result: dict[str, int] = {n: 0 for n in names}
    try:
        connections.connect(alias=alias, **_get_milvus_connection_args())
        for name in names:
            try:
                milvus_name = _to_milvus_collection_name(name)
                if utility.has_collection(milvus_name, using=alias):
                    result[name] = int(Collection(name=milvus_name, using=alias).num_entities or 0)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            connections.disconnect(alias)
        except Exception:
            pass
    return result


def _query_milvus_collection(collection_name: str, sample_limit: int = 0) -> tuple[int, list[dict]]:
    """Get entity count and optional chunk samples from a Milvus collection in one connection."""
    if not collection_name:
        return 0, []
    from pymilvus import Collection, connections, utility

    alias = f"milvus-query-{uuid4().hex[:8]}"
    try:
        connections.connect(alias=alias, **_get_milvus_connection_args())
        milvus_name = _to_milvus_collection_name(collection_name)
        if not utility.has_collection(milvus_name, using=alias):
            return 0, []
        col = Collection(name=milvus_name, using=alias)
        count = int(col.num_entities or 0)
        rows: list[dict] = []
        if sample_limit > 0 and count > 0:
            queried = col.query(
                expr="pk >= 0",
                output_fields=["pk", "text", "metadata"],
                limit=sample_limit,
            )
            rows = queried if isinstance(queried, list) else []
        return count, rows
    except Exception:
        return 0, []
    finally:
        try:
            connections.disconnect(alias)
        except Exception:
            pass


def get_embeddings():
    """Get the configured embeddings model."""
    try:
        openai_key = env.get("OPENAI_API_KEY")
        if openai_key:
            return OpenAIEmbeddings(api_key=openai_key)
        else:
            base_url = env.OLLAMA_BASE_URL or "http://host.docker.internal:11434"
            return OllamaEmbeddings(base_url=base_url, model="nomic-embed-text")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Embeddings: {e}") from e


def load_vector_store(collection_name: str):
    """Load a Milvus vector store for a specific collection.

    Reuses vector store instances per collection to avoid repeatedly creating
    fresh connections under concurrent chat load.
    """
    cached = _VECTOR_STORE_CACHE.get(collection_name)
    if cached is not None:
        return cached

    with _VECTOR_STORE_LOCK:
        cached = _VECTOR_STORE_CACHE.get(collection_name)
        if cached is not None:
            return cached

        embeddings = get_embeddings()
        connection_args = _get_milvus_connection_args()

        milvus_collection_name = _to_milvus_collection_name(collection_name)

        vector_store = Milvus(
            embedding_function=embeddings,
            collection_name=milvus_collection_name,
            connection_args=connection_args,
            auto_id=True,
            metadata_field="metadata",
        )
        _VECTOR_STORE_CACHE[collection_name] = vector_store
        return vector_store
