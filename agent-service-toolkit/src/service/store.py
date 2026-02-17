import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

# Global store instance
_STORE_INSTANCE = None

class PostgresStore:
    def __init__(self, connection_string: str, min_size=1, max_size=5):
        self.connection_string = connection_string
        self.min_size = min_size
        self.max_size = max_size
        self.pool = None

    async def setup(self):
        """Initialize connection pool."""
        self.pool = AsyncConnectionPool(
            self.connection_string, 
            min_size=self.min_size, 
            max_size=self.max_size,
            kwargs={"autocommit": True, "row_factory": dict_row}
        )
        logger.info("PostgresStore pool initialized")

    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()

    async def list_assistants(self) -> List[Dict]:
        if not self.pool: return []
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM assistant ORDER BY updated_at DESC")
                rows = await cur.fetchall()
                # Convert rows to dicts compatible with API
                results = []
                for row in rows:
                    results.append({
                        "assistant_id": str(row["assistant_id"]),
                        "graph_id": row["graph_id"],
                        "config": row.get("config", {}),
                        "metadata": row.get("metadata", {}),
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                        "name": row.get("name") or row.get("graph_id"), # Fallback
                        "version": row.get("version", 1)
                    })
                return results

    async def get_assistant(self, assistant_id: str) -> Optional[Dict]:
        if not self.pool: return None
        
        # Validate UUID to prevent Postgres errors
        try:
            uuid.UUID(str(assistant_id))
        except ValueError:
            return None
            
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM assistant WHERE assistant_id = %s", (assistant_id,))
                row = await cur.fetchone()
                if not row: return None
                return {
                    "assistant_id": str(row["assistant_id"]),
                    "graph_id": row["graph_id"],
                    "config": row.get("config", {}),
                    "metadata": row.get("metadata", {}),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                     "name": row.get("name") or row.get("graph_id"),
                    "version": row.get("version", 1)
                }

    async def save_assistant(self, assistant: Dict):
        if not self.pool: return
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # Upsert
                await cur.execute("""
                    INSERT INTO assistant (assistant_id, graph_id, name, config, metadata, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (assistant_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        config = EXCLUDED.config,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                """, (
                    assistant["assistant_id"],
                    assistant["graph_id"],
                    assistant.get("name"), 
                    json.dumps(assistant.get("config", {})),
                    json.dumps(assistant.get("metadata", {})),
                    assistant["created_at"],
                    assistant["updated_at"]
                ))

    async def delete_assistant(self, assistant_id: str) -> bool:
        if not self.pool: return False
        
        try:
            uuid.UUID(str(assistant_id))
        except ValueError:
            return False
            
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM assistant WHERE assistant_id = %s", (assistant_id,))
                return cur.rowcount > 0

    async def add_thread(self, thread: Dict):
        if not self.pool: return
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO thread (thread_id, metadata, created_at, updated_at, status)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (thread_id) DO UPDATE SET
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at,
                        status = EXCLUDED.status
                """, (
                    thread["thread_id"],
                    json.dumps(thread.get("metadata", {})),
                    thread["created_at"],
                    thread["updated_at"],
                    thread.get("status", "idle")
                ))

    async def get_thread(self, thread_id: str) -> Optional[Dict]:
        if not self.pool: return None
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM thread WHERE thread_id = %s", (thread_id,))
                row = await cur.fetchone()
                if not row: return None
                return {
                    "thread_id": str(row["thread_id"]),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                    "metadata": row.get("metadata", {}),
                    "status": row.get("status", "idle")
                }

    async def list_threads(self, limit: int = 100, offset: int = 0, metadata: Optional[Dict] = None) -> List[Dict]:
        if not self.pool: return []
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # Basic listing, metadata filtering is simple subset check application-side if needed, 
                # or JSONB contains query if performant.
                query = "SELECT * FROM thread ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                params = [limit, offset]
                
                # If metadata filter, use @> operator
                if metadata:
                    query = "SELECT * FROM thread WHERE metadata @> %s::jsonb ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                    params = [json.dumps(metadata), limit, offset]
                
                await cur.execute(query, params)
                rows = await cur.fetchall()
                results = []
                for row in rows:
                    results.append({
                        "thread_id": str(row["thread_id"]),
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                        "metadata": row.get("metadata", {}),
                        "status": row.get("status", "idle")
                    })
                return results

    async def update_thread(self, thread_id: str, updates: Dict) -> Optional[Dict]:
        # Fetch, update, save
        current = await self.get_thread(thread_id)
        if not current: return None
        
        if "metadata" in updates and updates["metadata"]:
             # Merge metadata logic needed? Client typically sends full or partial.
             # Python dict update:
             current["metadata"].update(updates["metadata"])
        
        if "status" in updates:
            current["status"] = updates["status"]
            
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.add_thread(current)
        return current

    async def delete_thread(self, thread_id: str) -> bool:
         if not self.pool: return False
         async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM thread WHERE thread_id = %s", (thread_id,))
                return cur.rowcount > 0


def set_global_store(store):
    """Set the global store instance."""
    global _STORE_INSTANCE
    _STORE_INSTANCE = store

def get_store():
    """Get the global store instance."""
    return _STORE_INSTANCE

# Global checkpointer instance
_CHECKPOINTER_INSTANCE = None

def set_global_checkpointer(checkpointer):
    """Set the global checkpointer instance."""
    global _CHECKPOINTER_INSTANCE
    _CHECKPOINTER_INSTANCE = checkpointer

def get_checkpointer():
    """Get the global checkpointer instance."""
    return _CHECKPOINTER_INSTANCE


# Wrapper functions matching old API
async def load_assistants_store_async() -> Dict[str, Dict]:
    assistants = await _STORE_INSTANCE.list_assistants()
    return {a["assistant_id"]: a for a in assistants}

async def save_assistant_async(assistant: Dict):
    await _STORE_INSTANCE.save_assistant(assistant)

async def get_assistant_from_store(assistant_id: str) -> Optional[Dict]:
    return await _STORE_INSTANCE.get_assistant(assistant_id)

async def list_assistants_from_store() -> List[Dict]:
    return await _STORE_INSTANCE.list_assistants()

async def update_assistant_in_store(assistant_id: str, updates: Dict) -> Optional[Dict]:
    # Custom logic: upsert
    current = await get_assistant_from_store(assistant_id)
    if not current: return None
    # Merge
    if "config" in updates: current["config"] = updates["config"]
    if "metadata" in updates: current["metadata"].update(updates["metadata"])
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    await save_assistant_async(current)
    return current

async def delete_assistant_from_store(assistant_id: str) -> bool:
    return await _STORE_INSTANCE.delete_assistant(assistant_id)

async def add_thread(thread: Dict):
    await _STORE_INSTANCE.add_thread(thread)

async def get_thread_from_store(thread_id: str) -> Optional[Dict]:
    return await _STORE_INSTANCE.get_thread(thread_id)

async def list_threads_from_store(limit: int = 100, offset: int = 0, metadata: Optional[Dict] = None) -> List[Dict]:
    return await _STORE_INSTANCE.list_threads(limit, offset, metadata)

async def update_thread_in_store(thread_id: str, updates: Dict) -> Optional[Dict]:
     return await _STORE_INSTANCE.update_thread(thread_id, updates)

async def delete_thread_from_store(thread_id: str) -> bool:
    return await _STORE_INSTANCE.delete_thread(thread_id)
