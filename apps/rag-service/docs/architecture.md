# RAG service architecture

RAG service has a flatter architecture than agent-service and user-service. API
routers call service modules directly, and services coordinate Postgres,
Milvus, and Neo4j access through the database package.

## Data flow

```text
langconnect/api -> langconnect/services -> langconnect/database
```

Document upload and ingestion write vector chunks to Milvus and metadata to
Postgres. Graph build operations extract entities and relationships, then write
graph data to Neo4j.

## Retrieval boundary

Agent-facing retrieval is exposed through tools-service. Tools-service calls
rag-service `POST /api/v1/retrieval` with trusted user and tenant context. Keep
new reusable agent tools in tools-service, and keep retrieval implementation in
rag-service.
