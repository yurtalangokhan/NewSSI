# Shared i18n Package (`i18n-py`)

Provides backend internationalization (i18n) capabilities for Python services (`agent-service`, `rag-service`, `tools-service`, `user-service`).

## Features
- Thread-safe async context scoping via `ContextVar`.
- `Accept-Language` header, `X-Language` header, and `?lang=` query param parsing.
- Dynamic key lookup with template interpolation (`t("key", param="val")`).
- Automatic fallback: requested locale -> default locale (`en`) -> key.
- ASGI / FastAPI middleware (`I18nMiddleware`).
- Translation checker utility for validating key parity and code usage.
