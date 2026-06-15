"""Controller for user settings and LLM provider endpoints."""

import base64
import csv
import io
import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, UploadFile, status

from controller.base import BaseController
from controller.session_controller import SessionController, get_session_controller
from core.db.repositories.project_repo import ProjectRepository
from core.env import env
from service.StoreService import list_threads_from_store
from service.UserServiceClient import (
    create_prompt_shortcut,
    delete_prompt_shortcut,
    get_user_settings,
    update_prompt_shortcut,
    update_user_settings,
)

logger = logging.getLogger(__name__)


class UserController(BaseController):
    """Owns user preferences and model/provider endpoints."""

    def __init__(self, session_controller: SessionController | None = None):
        self._session_controller = session_controller or get_session_controller()
        self._supported_roles = ["admin", "global_curator", "curator", "limited", "basic"]
        self._project_repo = ProjectRepository()
        # Minimal in-memory file store for project/recent file APIs.
        self._recent_files_by_user: dict[str, list[dict[str, Any]]] = {}
        self._project_files_by_user: dict[str, dict[int, list[dict[str, Any]]]] = {}
        self._file_payloads_by_user: dict[str, dict[str, dict[str, str]]] = {}

    async def _update_user_settings(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        try:
            return await update_user_settings(user_id, updates)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to persist user settings: {exc}",
            ) from exc

    async def resolve_projects_user_id(self, user_id: str | None) -> str | None:
        if user_id:
            if env.get("MODE", "").lower() == "dev" and str(user_id).startswith(
                ("user-", "dev-user")
            ):
                fallback_user = await self._project_repo.get_latest_user_id()
                if fallback_user:
                    return fallback_user
            return user_id

        if env.get("MODE", "").lower() == "dev":
            fallback_user = await self._project_repo.get_latest_user_id()
            if fallback_user:
                return fallback_user
            return "dev-user"

        return None

    def _is_keycloak_enabled(self) -> bool:
        return env.get("KEYCLOAK_ENABLED", "false").lower() == "true"

    def _get_keycloak_base_url(self) -> str:
        base_url = env.get("KEYCLOAK_BASE_URL")
        if base_url:
            return str(base_url).rstrip("/")

        issuer = env.get("KEYCLOAK_ISSUER_URL", "")
        if issuer and "/realms/" in issuer:
            return issuer.split("/realms/")[0].rstrip("/")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Keycloak base URL is not configured",
        )

    def _get_keycloak_realm(self) -> str:
        realm = env.get("KEYCLOAK_REALM")
        if realm:
            return str(realm)

        issuer = env.get("KEYCLOAK_ISSUER_URL", "")
        if issuer and "/realms/" in issuer:
            return issuer.split("/realms/")[-1].split("/")[0]

        return "agenticai"

    async def _get_keycloak_admin_token(self) -> str:
        base_url = self._get_keycloak_base_url()
        admin_realm = env.get("KEYCLOAK_ADMIN_REALM", "master")
        admin_user = env.get("KEYCLOAK_ADMIN") or env.get("KEYCLOAK_ADMIN_USERNAME", "admin")
        admin_password = env.get("KEYCLOAK_ADMIN_PASSWORD", "admin123")

        token_url = f"{base_url}/realms/{admin_realm}/protocol/openid-connect/token"
        data = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": admin_user,
            "password": admin_password,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(token_url, data=data)

        if not resp.is_success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Keycloak admin login failed: {resp.text}",
            )

        token = resp.json().get("access_token")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Keycloak admin token not returned",
            )
        return token

    async def _keycloak_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | list[Any] | None = None,
    ) -> httpx.Response:
        token = await self._get_keycloak_admin_token()
        base_url = self._get_keycloak_base_url()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(
                method,
                f"{base_url}{path}",
                headers=headers,
                params=params,
                json=json,
            )
        return response

    @staticmethod
    def _first_attr(user: dict[str, Any], key: str, default: str | None = None) -> str | None:
        attrs = user.get("attributes") or {}
        value = attrs.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str):
            return value
        return default

    def _normalize_user(self, user: dict[str, Any], role_override: str | None = None) -> dict[str, Any]:
        role = role_override or self._first_attr(user, "agentic_role", "basic") or "basic"
        password_configured = (self._first_attr(user, "password_configured", "true") or "true").lower() == "true"
        first_name = user.get("firstName")
        last_name = user.get("lastName")
        full_name = (
            f"{first_name} {last_name}".strip()
            if first_name and last_name
            else first_name or last_name
        )

        return {
            "id": str(user.get("id", "")),
            "email": user.get("email") or user.get("username") or "",
            "is_active": bool(user.get("enabled", True)),
            "is_superuser": role == "admin",
            "is_verified": bool(user.get("emailVerified", True)),
            "role": role,
            "preferences": {
                "chosen_assistants": None,
                "visible_assistants": [],
                "hidden_assistants": [],
                "default_model": None,
                "recent_assistants": [],
                "auto_scroll": True,
                "shortcut_enabled": True,
                "temperature_override_enabled": False,
                "theme_preference": None,
                "chat_background": None,
                "default_app_mode": "AUTO",
            },
            "team_name": None,
            "is_anonymous_user": False,
            "password_configured": password_configured,
            "first_name": first_name,
            "full_name": full_name,
            "personalization": {
                "name": full_name or first_name or (user.get("email") or user.get("username") or "user"),
                "role": "",
                "memories": [],
                "use_memories": False,
                "enable_memory_tool": False,
                "user_preferences": "",
            },
        }

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _file_chat_type(content_type: str | None, filename: str) -> str:
        mime = (content_type or "").lower()
        lower_name = filename.lower()
        if mime.startswith("image/"):
            return "image"
        if mime in {"text/csv", "application/csv"} or lower_name.endswith(".csv"):
            return "csv"
        if mime.startswith("text/") or lower_name.endswith((".txt", ".md")):
            return "plain_text"
        return "document"

    async def _resolve_or_raise_user_id(self, user_id: str | None) -> str:
        effective_user_id = await self.resolve_projects_user_id(user_id)
        if not effective_user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return effective_user_id

    def _project_files(self, user_id: str, project_id: int) -> list[dict[str, Any]]:
        return self._project_files_by_user.setdefault(user_id, {}).setdefault(project_id, [])

    def _recent_files(self, user_id: str) -> list[dict[str, Any]]:
        return self._recent_files_by_user.setdefault(user_id, [])

    def _file_payloads(self, user_id: str) -> dict[str, dict[str, str]]:
        return self._file_payloads_by_user.setdefault(user_id, {})

    async def _ensure_realm_role_exists(self, role_name: str) -> None:
        realm = self._get_keycloak_realm()
        role_resp = await self._keycloak_request(
            "GET",
            f"/admin/realms/{realm}/roles/{role_name}",
        )
        if role_resp.status_code == 404:
            create_resp = await self._keycloak_request(
                "POST",
                f"/admin/realms/{realm}/roles",
                json={"name": role_name},
            )
            if create_resp.status_code not in (201, 204, 409):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to create realm role {role_name}: {create_resp.text}",
                )
            return
        if role_resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to query realm role {role_name}: {role_resp.text}",
            )

    async def _get_realm_role_representation(self, role_name: str) -> dict[str, Any]:
        realm = self._get_keycloak_realm()
        await self._ensure_realm_role_exists(role_name)
        resp = await self._keycloak_request(
            "GET",
            f"/admin/realms/{realm}/roles/{role_name}",
        )
        if not resp.is_success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch realm role {role_name}: {resp.text}",
            )
        role = resp.json()
        if not isinstance(role, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Invalid role representation for {role_name}",
            )
        return role

    async def _get_user_realm_roles(self, user_id: str) -> list[str]:
        realm = self._get_keycloak_realm()
        resp = await self._keycloak_request(
            "GET",
            f"/admin/realms/{realm}/users/{user_id}/role-mappings/realm",
        )
        if resp.status_code == 404:
            return []
        if not resp.is_success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to get user realm roles: {resp.text}",
            )
        roles = resp.json()
        if not isinstance(roles, list):
            return []
        return [str(role.get("name", "")) for role in roles if isinstance(role, dict)]

    async def _set_user_realm_role(self, user_id: str, role_name: str) -> None:
        realm = self._get_keycloak_realm()
        existing_role_names = await self._get_user_realm_roles(user_id)
        roles_to_remove = [r for r in existing_role_names if r in self._supported_roles and r != role_name]

        if roles_to_remove:
            role_reprs_to_remove: list[dict[str, Any]] = []
            for role in roles_to_remove:
                role_reprs_to_remove.append(await self._get_realm_role_representation(role))

            remove_resp = await self._keycloak_request(
                "DELETE",
                f"/admin/realms/{realm}/users/{user_id}/role-mappings/realm",
                json=role_reprs_to_remove,
            )
            if remove_resp.status_code not in (200, 204):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to remove old user roles: {remove_resp.text}",
                )

        if role_name in self._supported_roles and role_name not in existing_role_names:
            role_repr = await self._get_realm_role_representation(role_name)
            add_resp = await self._keycloak_request(
                "POST",
                f"/admin/realms/{realm}/users/{user_id}/role-mappings/realm",
                json=[role_repr],
            )
            if add_resp.status_code not in (200, 201, 204, 409):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to add user role: {add_resp.text}",
                )

    async def _resolve_user_role(self, user: dict[str, Any]) -> str:
        user_id = str(user.get("id", ""))
        if user_id:
            realm_roles = await self._get_user_realm_roles(user_id)
            for candidate in ["admin", "global_curator", "curator", "limited", "basic"]:
                if candidate in realm_roles:
                    return candidate

        return self._first_attr(user, "agentic_role", "basic") or "basic"

    async def _normalize_user_async(self, user: dict[str, Any]) -> dict[str, Any]:
        role = await self._resolve_user_role(user)
        return self._normalize_user(user, role_override=role)

    async def _list_keycloak_users(self) -> list[dict[str, Any]]:
        if not self._is_keycloak_enabled():
            return []

        realm = self._get_keycloak_realm()
        resp = await self._keycloak_request(
            "GET",
            f"/admin/realms/{realm}/users",
            params={"first": 0, "max": 1000},
        )
        if not resp.is_success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to list Keycloak users: {resp.text}",
            )
        return resp.json()

    async def _find_user_by_email(self, email: str) -> dict[str, Any] | None:
        realm = self._get_keycloak_realm()
        resp = await self._keycloak_request(
            "GET",
            f"/admin/realms/{realm}/users",
            params={"email": email, "exact": "true"},
        )
        if not resp.is_success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to query Keycloak user: {resp.text}",
            )

        users = resp.json()
        return users[0] if users else None

    async def _find_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        realm = self._get_keycloak_realm()
        resp = await self._keycloak_request(
            "GET",
            f"/admin/realms/{realm}/users/{user_id}",
        )
        if resp.status_code == 404:
            return None
        if not resp.is_success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to query Keycloak user by id: {resp.text}",
            )
        data = resp.json()
        return data if isinstance(data, dict) else None

    @staticmethod
    def _thread_project_id(thread: dict[str, Any]) -> int | None:
        project_id = thread.get("project_id")
        if project_id is None:
            metadata = thread.get("metadata", {}) or {}
            project_id = metadata.get("project_id")
        if project_id is None:
            return None
        try:
            return int(project_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_owner_ids(user_id: str, owner_ids: list[str] | None = None) -> list[str]:
        normalized: list[str] = []
        for candidate in [user_id, *(owner_ids or [])]:
            if not candidate:
                continue
            candidate_id = str(candidate)
            if candidate_id not in normalized:
                normalized.append(candidate_id)
        return normalized

    def _thread_belongs_to_owner_ids(
        self,
        thread: dict[str, Any],
        owner_ids: list[str],
    ) -> bool:
        metadata = thread.get("metadata", {}) or {}
        owner = metadata.get("user_id")
        if owner and str(owner) in owner_ids:
            return True

        legacy_owner_ids = metadata.get("legacy_user_ids") or []
        if isinstance(legacy_owner_ids, list):
            return any(str(candidate) in owner_ids for candidate in legacy_owner_ids)

        return False

    @staticmethod
    def _serialize_chat_session(thread: dict[str, Any]) -> dict[str, Any]:
        metadata = thread.get("metadata", {}) or {}
        session_name = metadata.get("name") or "New Chat"
        return {
            "id": thread.get("thread_id", ""),
            "name": session_name,
            "description": session_name,
            "persona_id": metadata.get("persona_id", 0),
            "time_created": thread.get("created_at"),
            "time_updated": thread.get("updated_at"),
            "shared_status": "private",
            "project_id": UserController._thread_project_id(thread),
            "current_alternate_model": metadata.get("current_alternate_model", ""),
            "current_temperature_override": metadata.get("current_temperature_override"),
        }

    async def get_user_assistant_preferences(self) -> dict[str, Any]:
        return {}

    async def get_recent_files(self, user_id: str | None) -> list[Any]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)
        recent = self._recent_files(effective_user_id)
        if recent:
            return recent

        from core.db.repositories.document_repo import DocumentRepository

        docs = await DocumentRepository().list_by_user(effective_user_id, limit=50)
        now = self._now_iso()
        hydrated = []
        for doc in docs:
            hydrated.append({
                "id": doc["file_id"],
                "name": doc["filename"],
                "project_id": doc["project_id"],
                "user_id": doc["user_id"],
                "file_id": doc["file_id"],
                "created_at": doc["created_at"] or now,
                "status": "COMPLETED",
                "file_type": doc["mime_type"],
                "last_accessed_at": doc["created_at"] or now,
                "chat_file_type": doc["chat_file_type"],
                "token_count": 0,
                "chunk_count": 0,
                "temp_id": None,
                "minio_object_key": doc["minio_object_key"],
            })
        self._recent_files_by_user[effective_user_id] = hydrated
        return hydrated

    async def upload_user_project_files(
        self,
        user_id: str | None,
        files: list[UploadFile],
        project_id: int | None,
        temp_id_map_raw: str | None,
        owner_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)
        effective_owner_ids = self._normalize_owner_ids(effective_user_id, owner_ids)

        if project_id is not None:
            project = await self._project_repo.get_for_user_ids(effective_owner_ids, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

        temp_id_map: dict[str, str] = {}
        if temp_id_map_raw:
            try:
                parsed = json.loads(temp_id_map_raw)
                if isinstance(parsed, dict):
                    temp_id_map = {str(k): str(v) for k, v in parsed.items()}
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid temp_id_map")

        uploaded: list[dict[str, Any]] = []
        now = self._now_iso()
        recent = self._recent_files(effective_user_id)

        for upload in files:
            file_id = secrets.token_hex(16)
            file_name = upload.filename or file_id
            content_type = upload.content_type or "application/octet-stream"
            raw = await upload.read()
            encoded = base64.b64encode(raw).decode("ascii")
            temp_id = temp_id_map.get(file_name)
            chat_file_type = self._file_chat_type(content_type, file_name)
            file_obj = {
                "id": file_id,
                "name": file_name,
                "project_id": project_id,
                "user_id": effective_user_id,
                "file_id": file_id,
                "created_at": now,
                "status": "COMPLETED",
                "file_type": content_type,
                "last_accessed_at": now,
                "chat_file_type": chat_file_type,
                "token_count": max(1, len(raw) // 4),
                "chunk_count": 0,
                "temp_id": temp_id,
            }
            self._file_payloads(effective_user_id)[file_id] = {
                "data": encoded,
                "mime_type": content_type,
                "name": file_name,
                "chat_file_type": chat_file_type,
            }
            try:
                from service.FileService import store_file

                store_file(file_id, raw, content_type, file_name)
            except Exception:
                # The base64 payload above is enough for chat context extraction.
                pass

            # Persist to MinIO + DB for durable storage
            try:
                from core.db.repositories.document_repo import DocumentRepository
                from service.MinioService import upload_file as minio_upload

                object_key = minio_upload(
                    user_id=effective_user_id,
                    file_id=file_id,
                    filename=file_name,
                    data=raw,
                    mime_type=content_type,
                )
                await DocumentRepository().create(
                    file_id=file_id,
                    user_id=effective_user_id,
                    filename=file_name,
                    mime_type=content_type,
                    chat_file_type=chat_file_type,
                    size_bytes=len(raw),
                    minio_object_key=object_key,
                    project_id=project_id,
                )
                # Enrich payload with minio key so ChatRoute can fetch without base64
                self._file_payloads(effective_user_id)[file_id]["minio_object_key"] = object_key
                file_obj["minio_object_key"] = object_key
            except Exception as minio_err:
                logger.warning("MinIO/DB persist failed for file %s: %s", file_id, minio_err)

            uploaded.append(file_obj)

        # Newest first in recent files.
        self._recent_files_by_user[effective_user_id] = [*uploaded, *recent]

        if project_id is not None:
            project_files = self._project_files(effective_user_id, project_id)
            self._project_files_by_user[effective_user_id][project_id] = [
                *uploaded,
                *project_files,
            ]

        return {"user_files": uploaded, "rejected_files": []}

    async def get_files_in_project(
        self,
        user_id: str | None,
        project_id: int,
        owner_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)
        project = await self._project_repo.get_for_user_ids(
            self._normalize_owner_ids(effective_user_id, owner_ids),
            project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        return await self._hydrate_project_files(effective_user_id, project_id)

    async def link_file_to_project(
        self,
        user_id: str | None,
        project_id: int,
        file_id: str,
        owner_ids: list[str] | None = None,
    ) -> dict[str, bool]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)
        project = await self._project_repo.get_for_user_ids(
            self._normalize_owner_ids(effective_user_id, owner_ids),
            project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        from core.db.repositories.document_repo import DocumentRepository

        doc_repo = DocumentRepository()
        await doc_repo.update_project_id(file_id, project_id)

        file_obj = next(
            (f for f in self._recent_files(effective_user_id) if f.get("id") == file_id),
            None,
        )
        if not file_obj:
            doc = await doc_repo.get_by_file_id(file_id)
            if doc:
                file_obj = {
                    "id": doc["file_id"],
                    "name": doc["filename"],
                    "project_id": project_id,
                    "user_id": doc["user_id"],
                    "file_id": doc["file_id"],
                    "created_at": doc["created_at"] or self._now_iso(),
                    "status": "COMPLETED",
                    "file_type": doc["mime_type"],
                    "last_accessed_at": doc["created_at"] or self._now_iso(),
                    "chat_file_type": doc["chat_file_type"],
                    "token_count": 0,
                    "chunk_count": 0,
                    "temp_id": None,
                    "minio_object_key": doc["minio_object_key"],
                }

        if file_obj:
            project_files = self._project_files(effective_user_id, project_id)
            if not any(f.get("id") == file_id for f in project_files):
                linked = {**file_obj, "project_id": project_id}
                self._project_files_by_user[effective_user_id][project_id] = [linked, *project_files]

        return {"success": True}

    async def unlink_file_from_project(
        self,
        user_id: str | None,
        project_id: int,
        file_id: str,
    ) -> dict[str, bool]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)

        from core.db.repositories.document_repo import DocumentRepository

        await DocumentRepository().update_project_id(file_id, None)

        project_files = self._project_files(effective_user_id, project_id)
        self._project_files_by_user[effective_user_id][project_id] = [
            f for f in project_files if f.get("id") != file_id
        ]
        return {"success": True}

    async def get_user_file(self, user_id: str | None, file_id: str) -> dict[str, Any]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)
        file_obj = next(
            (f for f in self._recent_files(effective_user_id) if f.get("id") == file_id),
            None,
        )
        if file_obj:
            return file_obj

        from core.db.repositories.document_repo import DocumentRepository

        doc = await DocumentRepository().get_by_file_id(file_id)
        if not doc:
            raise HTTPException(status_code=404, detail="File not found")
        return {
            "id": doc["file_id"],
            "name": doc["filename"],
            "project_id": doc["project_id"],
            "user_id": doc["user_id"],
            "file_id": doc["file_id"],
            "created_at": doc["created_at"] or self._now_iso(),
            "status": "COMPLETED",
            "file_type": doc["mime_type"],
            "last_accessed_at": doc["created_at"] or self._now_iso(),
            "chat_file_type": doc["chat_file_type"],
            "token_count": 0,
            "chunk_count": 0,
            "temp_id": None,
            "minio_object_key": doc["minio_object_key"],
        }

    async def get_user_file_statuses(
        self,
        user_id: str | None,
        file_ids: list[str],
    ) -> list[dict[str, Any]]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)
        by_id = {f.get("id"): f for f in self._recent_files(effective_user_id)}
        found = [by_id[file_id] for file_id in file_ids if file_id in by_id]

        missing = [fid for fid in file_ids if fid not in by_id]
        if missing:
            from core.db.repositories.document_repo import DocumentRepository

            for file_id in missing:
                doc = await DocumentRepository().get_by_file_id(file_id)
                if doc:
                    found.append({
                        "id": doc["file_id"],
                        "name": doc["filename"],
                        "project_id": doc["project_id"],
                        "user_id": doc["user_id"],
                        "file_id": doc["file_id"],
                        "created_at": doc["created_at"] or self._now_iso(),
                        "status": "COMPLETED",
                        "file_type": doc["mime_type"],
                        "last_accessed_at": doc["created_at"] or self._now_iso(),
                        "chat_file_type": doc["chat_file_type"],
                        "token_count": 0,
                        "chunk_count": 0,
                        "temp_id": None,
                        "minio_object_key": doc["minio_object_key"],
                    })

        return found

    async def delete_user_file(self, user_id: str | None, file_id: str) -> dict[str, Any]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)

        from core.db.repositories.document_repo import DocumentRepository

        doc_repo = DocumentRepository()
        doc = await doc_repo.get_by_file_id(file_id)

        in_memory = self._recent_files(effective_user_id)
        self._recent_files_by_user[effective_user_id] = [
            f for f in in_memory if f.get("id") != file_id
        ]
        self._file_payloads(effective_user_id).pop(file_id, None)

        project_map = self._project_files_by_user.get(effective_user_id, {})
        for pid, files in list(project_map.items()):
            project_map[pid] = [f for f in files if f.get("id") != file_id]

        if doc:
            try:
                from service.MinioService import delete_file as minio_delete

                minio_delete(doc["minio_object_key"])
            except Exception:
                logger.warning("Failed to delete MinIO object for file %s", file_id)
            await doc_repo.delete_by_file_id(file_id)

        return {
            "has_associations": False,
            "project_names": [],
            "assistant_names": [],
        }

    async def update_pinned_assistants(self, ordered_assistant_ids: list[int]) -> dict[str, Any]:
        return {"success": True, "pinned_assistants": ordered_assistant_ids}

    async def get_pinned_assistants(self) -> dict[str, list[int]]:
        return {"pinned_assistants": []}

    async def get_llm_provider(self) -> dict[str, Any]:
        return await self._session_controller.get_llm_providers()

    async def get_llm_built_in_options(self) -> list[dict[str, Any]]:
        return await self._session_controller.get_llm_built_in_options()

    async def test_llm_default(self) -> dict[str, bool]:
        return {"success": True}

    async def get_default_assistant(self) -> None:
        return None

    async def get_user_projects(
        self,
        user_id: str,
        owner_ids: list[str] | None = None,
    ) -> list[Any]:
        effective_owner_ids = self._normalize_owner_ids(user_id, owner_ids)
        projects = await self._project_repo.list_by_user_ids(effective_owner_ids)
        project_ids = {project["id"] for project in projects}
        threads = await list_threads_from_store(
            limit=1000,
            offset=0,
        )

        sessions_by_project: dict[int, list[dict[str, Any]]] = {}
        for thread in threads:
            project_id = self._thread_project_id(thread)
            if project_id is None or project_id not in project_ids:
                continue
            if not self._thread_belongs_to_owner_ids(thread, effective_owner_ids):
                continue
            sessions_by_project.setdefault(project_id, []).append(
                self._serialize_chat_session(thread)
            )

        for project in projects:
            project_id = project["id"]
            project_sessions = sessions_by_project.get(project_id, [])
            project_sessions.sort(key=lambda s: s.get("time_updated") or "", reverse=True)
            project["chat_sessions"] = project_sessions

        return projects

    async def create_user_project(self, user_id: str, name: str) -> dict[str, Any]:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise HTTPException(status_code=400, detail="Project name is required")
        project = await self._project_repo.create_for_user(user_id=user_id, name=cleaned_name)
        project["chat_sessions"] = []
        return project

    async def get_user_project(
        self,
        user_id: str,
        project_id: int,
        owner_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        effective_owner_ids = self._normalize_owner_ids(user_id, owner_ids)
        project = await self._project_repo.get_for_user_ids(effective_owner_ids, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        threads = await list_threads_from_store(
            limit=1000,
            offset=0,
        )
        chat_sessions = [
            self._serialize_chat_session(thread)
            for thread in threads
            if self._thread_project_id(thread) == project_id
            and self._thread_belongs_to_owner_ids(thread, effective_owner_ids)
        ]
        chat_sessions.sort(key=lambda s: s.get("time_updated") or "", reverse=True)
        project["chat_sessions"] = chat_sessions
        return project

    async def rename_user_project(
        self,
        user_id: str,
        project_id: int,
        name: str,
        owner_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise HTTPException(status_code=400, detail="Project name is required")
        project = await self._project_repo.rename_for_user_ids(
            user_ids=self._normalize_owner_ids(user_id, owner_ids),
            project_id=project_id,
            name=cleaned_name,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        project["chat_sessions"] = []
        return project

    async def delete_user_project(
        self,
        user_id: str,
        project_id: int,
        owner_ids: list[str] | None = None,
    ) -> dict[str, bool]:
        deleted = await self._project_repo.delete_for_user_ids(
            user_ids=self._normalize_owner_ids(user_id, owner_ids),
            project_id=project_id,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"success": True}

    async def _hydrate_project_files(
        self, user_id: str, project_id: int
    ) -> list[dict[str, Any]]:
        from core.db.repositories.document_repo import DocumentRepository

        cache = self._project_files(user_id, project_id)
        cache_ids = {f.get("id") for f in cache}

        now = self._now_iso()
        merged = list(cache)

        for doc in await DocumentRepository().list_by_project(project_id):
            if doc["file_id"] in cache_ids:
                continue
            cache_ids.add(doc["file_id"])
            merged.append({
                "id": doc["file_id"],
                "name": doc["filename"],
                "project_id": doc["project_id"],
                "user_id": doc["user_id"],
                "file_id": doc["file_id"],
                "created_at": doc["created_at"] or now,
                "status": "COMPLETED",
                "file_type": doc["mime_type"],
                "last_accessed_at": doc["created_at"] or now,
                "chat_file_type": doc["chat_file_type"],
                "token_count": 0,
                "chunk_count": 0,
                "temp_id": None,
                "minio_object_key": doc["minio_object_key"],
            })

        self._project_files_by_user.setdefault(user_id, {})[project_id] = merged
        return merged

    async def get_user_project_details(
        self,
        user_id: str,
        project_id: int,
        owner_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        project = await self.get_user_project(user_id, project_id, owner_ids)
        return {
            "project": project,
            "files": await self._hydrate_project_files(user_id, project_id),
            "persona_id_to_featured": {},
        }

    async def get_user_project_instructions(
        self,
        user_id: str,
        project_id: int,
        owner_ids: list[str] | None = None,
    ) -> dict[str, str | None]:
        project = await self._project_repo.get_for_user_ids(
            self._normalize_owner_ids(user_id, owner_ids),
            project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"instructions": project.get("instructions")}

    async def upsert_user_project_instructions(
        self,
        user_id: str,
        project_id: int,
        instructions: str,
        owner_ids: list[str] | None = None,
    ) -> dict[str, str | None]:
        project = await self._project_repo.upsert_instructions_for_user_ids(
            user_ids=self._normalize_owner_ids(user_id, owner_ids),
            project_id=project_id,
            instructions=instructions,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"instructions": project.get("instructions")}

    async def get_project_token_count(self, user_id: str, project_id: int) -> dict[str, int]:
        project_files = self._project_files(user_id, project_id)
        total_tokens = sum(int(file.get("token_count") or 0) for file in project_files)
        return {"total_tokens": total_tokens}

    async def get_project_file_descriptors_for_chat(
        self,
        user_id: str | list[str],
        project_id: int | None,
        file_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if project_id is None:
            return []

        descriptors: list[dict[str, Any]] = []
        seen_file_ids: set[str] = set()
        user_ids = user_id if isinstance(user_id, list) else [user_id]

        for candidate_user_id in user_ids:
            if not candidate_user_id:
                continue

            project_files = await self._hydrate_project_files(str(candidate_user_id), project_id)
            payloads = self._file_payloads(str(candidate_user_id))

            for file_obj in project_files:
                file_id = str(file_obj.get("file_id") or file_obj.get("id") or "")
                if not file_id or file_id in seen_file_ids:
                    continue
                if file_ids is not None and file_id not in file_ids:
                    continue
                payload = payloads.get(file_id)

                if not payload:
                    object_key = file_obj.get("minio_object_key")
                    if object_key:
                        try:
                            from service.MinioService import download_file

                            raw = download_file(object_key)
                            encoded = base64.b64encode(raw).decode("ascii")
                            payload = {
                                "data": encoded,
                                "mime_type": file_obj.get("file_type") or "application/octet-stream",
                                "name": file_obj.get("name") or file_id,
                                "chat_file_type": file_obj.get("chat_file_type") or "document",
                            }
                            payloads[file_id] = payload
                        except Exception:
                            logger.warning("Failed to download file %s from MinIO", file_id)
                            continue

                seen_file_ids.add(file_id)
                descriptors.append(
                    {
                        "id": file_id,
                        "type": payload.get("chat_file_type") or file_obj.get("chat_file_type") or "document",
                        "name": payload.get("name") or file_obj.get("name") or file_id,
                        "user_file_id": file_obj.get("id"),
                        "data": payload.get("data"),
                        "mime_type": payload.get("mime_type") or file_obj.get("file_type"),
                        "source": "project",
                    }
                )
        return descriptors

    async def move_chat_session_to_project(
        self,
        *,
        user_id: str,
        project_id: int,
        chat_session_id: str,
        owner_ids: list[str] | None = None,
    ) -> dict[str, bool]:
        moved = await self._project_repo.move_chat_session_to_project_for_user_ids(
            primary_user_id=user_id,
            owner_ids=self._normalize_owner_ids(user_id, owner_ids),
            project_id=project_id,
            chat_session_id=chat_session_id,
        )
        if not moved:
            raise HTTPException(status_code=404, detail="Project or chat session not found")
        return {"success": True}

    async def remove_chat_session_from_project(
        self,
        *,
        user_id: str,
        chat_session_id: str,
        owner_ids: list[str] | None = None,
    ) -> dict[str, bool]:
        removed = await self._project_repo.remove_chat_session_from_project_for_user_ids(
            primary_user_id=user_id,
            owner_ids=self._normalize_owner_ids(user_id, owner_ids),
            chat_session_id=chat_session_id,
        )
        if not removed:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return {"success": True}

    async def get_notifications(self) -> list[Any]:
        return []

    async def get_input_prompts(self, user_id: str) -> list[Any]:
        if not user_id:
            return []
        settings = await get_user_settings(user_id)
        prompts = settings.get("prompt_shortcuts") or []
        return prompts if isinstance(prompts, list) else []

    async def create_input_prompt(self, *, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return await create_prompt_shortcut(user_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def update_input_prompt(
        self,
        *,
        user_id: str,
        prompt_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            updated = await update_prompt_shortcut(user_id, prompt_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if updated is None:
            raise HTTPException(status_code=404, detail="Input prompt not found")
        return updated

    async def delete_input_prompt(self, *, user_id: str, prompt_id: int) -> dict[str, bool]:
        deleted = await delete_prompt_shortcut(user_id, prompt_id)
        if isinstance(deleted, dict) and deleted.get("message") == "Shortcut deleted":
            return {"success": True}
        return {"success": True}

    async def get_connector_status(self) -> list[Any]:
        return []

    async def get_federated_oauth_status(self) -> dict[str, bool]:
        return {"enabled": env.get("KEYCLOAK_ENABLED", "false").lower() == "true"}

    async def get_valid_domains(self) -> list[str]:
        return ["*"]

    async def list_accepted_users_paginated(
        self,
        *,
        page_num: int,
        page_size: int,
        query: str | None,
        is_active: bool | None,
        roles: list[str] | None,
    ) -> dict[str, Any]:
        users = await self._list_keycloak_users()

        accepted: list[dict[str, Any]] = []
        for user in users:
            invited = (self._first_attr(user, "invited", "false") or "false").lower() == "true"
            if invited:
                continue
            normalized = await self._normalize_user_async(user)
            accepted.append(normalized)

        if query:
            q = query.lower()
            accepted = [u for u in accepted if q in u["email"].lower()]

        if is_active is not None:
            accepted = [u for u in accepted if u["is_active"] == is_active]

        if roles:
            role_set = {r for r in roles}
            accepted = [u for u in accepted if u["role"] in role_set]

        total_items = len(accepted)
        start = page_num * page_size
        end = start + page_size
        return {
            "items": accepted[start:end],
            "total_items": total_items,
        }

    async def get_invited_users(self) -> list[dict[str, str]]:
        users = await self._list_keycloak_users()
        invited_users: list[dict[str, str]] = []
        for user in users:
            invited = (self._first_attr(user, "invited", "false") or "false").lower() == "true"
            if invited:
                email = user.get("email") or user.get("username")
                if email:
                    invited_users.append({"email": email})
        return invited_users

    async def get_all_users(self, include_api_keys: bool) -> dict[str, Any]:
        _ = include_api_keys
        users = await self._list_keycloak_users()
        accepted = []
        invited = []
        for user in users:
            invited_flag = (self._first_attr(user, "invited", "false") or "false").lower() == "true"
            if invited_flag:
                email = user.get("email") or user.get("username")
                if email:
                    invited.append({"email": email})
            else:
                accepted.append(await self._normalize_user_async(user))

        return {
            "accepted": accepted,
            "invited": invited,
            "slack_users": [],
            "accepted_pages": 1,
            "invited_pages": 1,
            "slack_users_pages": 0,
        }

    async def invite_users(self, emails: list[str]) -> dict[str, Any]:
        realm = self._get_keycloak_realm()
        for raw_email in emails:
            email = raw_email.lower().strip()
            if not email:
                continue

            existing = await self._find_user_by_email(email)
            if existing:
                user_id = existing.get("id")
                if user_id:
                    attrs = existing.get("attributes") or {}
                    attrs.update({"invited": ["true"], "password_configured": ["false"]})
                    payload = {
                        "email": email,
                        "username": existing.get("username") or email,
                        "enabled": bool(existing.get("enabled", True)),
                        "emailVerified": bool(existing.get("emailVerified", True)),
                        "attributes": attrs,
                    }
                    await self._keycloak_request(
                        "PUT",
                        f"/admin/realms/{realm}/users/{user_id}",
                        json=payload,
                    )
                continue

            payload = {
                "username": email,
                "email": email,
                "enabled": True,
                "emailVerified": True,
                "attributes": {
                    "invited": ["true"],
                    "agentic_role": ["basic"],
                    "password_configured": ["false"],
                },
            }
            resp = await self._keycloak_request(
                "POST",
                f"/admin/realms/{realm}/users",
                json=payload,
            )
            if resp.status_code not in (201, 204, 409):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to create invited user {email}: {resp.text}",
                )

        return {"success": True, "email_invite_status": "SENT"}

    async def create_user(
        self,
        *,
        email: str,
        role: str,
        first_name: str | None,
        last_name: str | None,
        password: str | None,
    ) -> dict[str, Any]:
        realm = self._get_keycloak_realm()
        normalized_email = email.lower().strip()
        if not normalized_email:
            raise HTTPException(status_code=400, detail="Email is required")

        existing = await self._find_user_by_email(normalized_email)
        if existing:
            raise HTTPException(status_code=409, detail="User already exists")

        payload = {
            "username": normalized_email,
            "email": normalized_email,
            "enabled": True,
            "emailVerified": True,
            "firstName": (first_name or "").strip() or None,
            "lastName": (last_name or "").strip() or None,
            "attributes": {
                "invited": ["false"],
                "agentic_role": [role or "basic"],
                "password_configured": ["true" if password else "false"],
            },
        }

        resp = await self._keycloak_request(
            "POST",
            f"/admin/realms/{realm}/users",
            json=payload,
        )
        if resp.status_code not in (201, 204):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to create user: {resp.text}",
            )

        created = await self._find_user_by_email(normalized_email)
        if not created:
            return {"success": True}

        if password:
            await self._keycloak_request(
                "PUT",
                f"/admin/realms/{realm}/users/{created.get('id')}/reset-password",
                json={
                    "type": "password",
                    "temporary": False,
                    "value": password,
                },
            )

        created_user_id = str(created.get("id", ""))
        if created_user_id:
            await self._set_user_realm_role(created_user_id, role or "basic")
            await self._update_user_settings(created_user_id, {})

        return {
            "success": True,
            "user": await self._normalize_user_async(created),
        }

    async def update_user_profile(
        self,
        *,
        user_email: str,
        first_name: str | None,
        last_name: str | None,
    ) -> dict[str, Any]:
        user = await self._find_user_by_email(user_email.lower().strip())
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        realm = self._get_keycloak_realm()
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")

        payload = {
            "email": user.get("email") or user_email,
            # Username is intentionally immutable because Keycloak login identity depends on it.
            "username": user.get("username") or user_email,
            "enabled": bool(user.get("enabled", True)),
            "emailVerified": bool(user.get("emailVerified", True)),
            "firstName": (first_name or "").strip() or None,
            "lastName": (last_name or "").strip() or None,
            "attributes": user.get("attributes") or {},
        }
        resp = await self._keycloak_request(
            "PUT",
            f"/admin/realms/{realm}/users/{user_id}",
            json=payload,
        )
        if resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to update user profile: {resp.text}",
            )

        return {"success": True}

    async def set_user_password(
        self,
        *,
        user_email: str,
        password: str,
        temporary: bool = False,
    ) -> dict[str, Any]:
        user = await self._find_user_by_email(user_email.lower().strip())
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        clean_password = (password or "").strip()
        if len(clean_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

        realm = self._get_keycloak_realm()
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")

        payload = {
            "type": "password",
            "temporary": bool(temporary),
            "value": clean_password,
        }
        resp = await self._keycloak_request(
            "PUT",
            f"/admin/realms/{realm}/users/{user_id}/reset-password",
            json=payload,
        )
        if resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to set user password: {resp.text}",
            )

        attrs = user.get("attributes") or {}
        attrs["password_configured"] = ["true"]
        attrs["invited"] = ["false"]

        user_payload = {
            "email": user.get("email") or user_email,
            "username": user.get("username") or user_email,
            "enabled": bool(user.get("enabled", True)),
            "emailVerified": bool(user.get("emailVerified", True)),
            "firstName": user.get("firstName"),
            "lastName": user.get("lastName"),
            "attributes": attrs,
        }
        update_resp = await self._keycloak_request(
            "PUT",
            f"/admin/realms/{realm}/users/{user_id}",
            json=user_payload,
        )
        if update_resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to persist password flags: {update_resp.text}",
            )

        return {"success": True}

    async def remove_invited_user(self, user_email: str) -> dict[str, Any]:
        user = await self._find_user_by_email(user_email.lower().strip())
        if not user:
            return {"success": True}

        user_id = user.get("id")
        realm = self._get_keycloak_realm()
        resp = await self._keycloak_request("DELETE", f"/admin/realms/{realm}/users/{user_id}")
        if resp.status_code not in (204, 404):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to remove invited user: {resp.text}",
            )
        return {"success": True}

    async def set_user_role(self, user_email: str, new_role: str) -> dict[str, Any]:
        user = await self._find_user_by_email(user_email.lower().strip())
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        realm = self._get_keycloak_realm()
        user_id = user.get("id")
        attrs = user.get("attributes") or {}
        attrs["agentic_role"] = [new_role]
        attrs["invited"] = ["false"]
        payload: dict[str, Any] = {
            "email": user.get("email") or user_email,
            "username": user.get("username") or user_email,
            "enabled": bool(user.get("enabled", True)),
            "emailVerified": bool(user.get("emailVerified", True)),
            "attributes": attrs,
        }
        # Preserve existing name fields so they are not wiped by the PUT
        if user.get("firstName"):
            payload["firstName"] = user["firstName"]
        if user.get("lastName"):
            payload["lastName"] = user["lastName"]
        resp = await self._keycloak_request(
            "PUT",
            f"/admin/realms/{realm}/users/{user_id}",
            json=payload,
        )
        if resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to set user role: {resp.text}",
            )

        await self._set_user_realm_role(str(user_id), new_role)
        return {"success": True}

    async def set_user_active(self, user_email: str, active: bool) -> dict[str, Any]:
        user = await self._find_user_by_email(user_email.lower().strip())
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        realm = self._get_keycloak_realm()
        user_id = user.get("id")
        payload = {
            "email": user.get("email") or user_email,
            "username": user.get("username") or user_email,
            "enabled": active,
            "emailVerified": bool(user.get("emailVerified", True)),
            "attributes": user.get("attributes") or {},
        }
        resp = await self._keycloak_request(
            "PUT",
            f"/admin/realms/{realm}/users/{user_id}",
            json=payload,
        )
        if resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to update user status: {resp.text}",
            )
        return {"success": True}

    async def delete_user(self, user_email: str) -> dict[str, Any]:
        user = await self._find_user_by_email(user_email.lower().strip())
        if not user:
            return {"success": True}

        realm = self._get_keycloak_realm()
        resp = await self._keycloak_request("DELETE", f"/admin/realms/{realm}/users/{user.get('id')}")
        if resp.status_code not in (204, 404):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to delete user: {resp.text}",
            )
        return {"success": True}

    async def reset_user_password(self, user_email: str) -> dict[str, Any]:
        user = await self._find_user_by_email(user_email.lower().strip())
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        new_password = secrets.token_urlsafe(10)
        realm = self._get_keycloak_realm()
        user_id = user.get("id")

        payload = {
            "type": "password",
            "temporary": False,
            "value": new_password,
        }
        resp = await self._keycloak_request(
            "PUT",
            f"/admin/realms/{realm}/users/{user_id}/reset-password",
            json=payload,
        )
        if resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to reset password: {resp.text}",
            )

        attrs = user.get("attributes") or {}
        attrs["password_configured"] = ["true"]
        attrs["invited"] = ["false"]
        user_payload = {
            "email": user.get("email") or user_email,
            "username": user.get("username") or user_email,
            "enabled": bool(user.get("enabled", True)),
            "emailVerified": bool(user.get("emailVerified", True)),
            "attributes": attrs,
        }
        await self._keycloak_request(
            "PUT",
            f"/admin/realms/{realm}/users/{user_id}",
            json=user_payload,
        )

        return {"success": True, "new_password": new_password}

    async def download_users_csv(self) -> tuple[str, str]:
        users = await self._list_keycloak_users()
        normalized = [await self._normalize_user_async(u) for u in users]

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["email", "role", "is_active", "is_verified"])
        for user in normalized:
            writer.writerow([
                user["email"],
                user["role"],
                str(user["is_active"]),
                str(user["is_verified"]),
            ])

        return output.getvalue(), "users.csv"

    async def update_user_personalization(
        self,
        *,
        user_id: str,
        personalization: dict[str, Any],
    ) -> dict[str, Any]:
        user = await self._find_user_by_id(user_id)
        if not user and "@" in user_id:
            user = await self._find_user_by_email(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        realm = self._get_keycloak_realm()
        user_keycloak_id = user.get("id")
        if not user_keycloak_id:
            raise HTTPException(status_code=404, detail="User not found")

        name = str(personalization.get("name", "")).strip()
        work_role = str(personalization.get("role", "")).strip()

        first_name = user.get("firstName")
        last_name = user.get("lastName")
        if name:
            parts = name.split()
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        attrs = user.get("attributes") or {}
        if work_role:
            attrs["work_role"] = [work_role]

        payload = {
            "email": user.get("email") or user.get("username"),
            "username": user.get("username") or user.get("email"),
            "enabled": bool(user.get("enabled", True)),
            "emailVerified": bool(user.get("emailVerified", True)),
            "firstName": first_name,
            "lastName": last_name,
            "attributes": attrs,
        }

        resp = await self._keycloak_request(
            "PUT",
            f"/admin/realms/{realm}/users/{user_keycloak_id}",
            json=payload,
        )
        if resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to update user personalization: {resp.text}",
            )

        settings_updates: dict[str, Any] = {}
        if "memories" in personalization:
            settings_updates["memories"] = personalization.get("memories") or []
        if "long_term_memory_enabled" in personalization:
            settings_updates["long_term_memory_enabled"] = bool(
                personalization.get("long_term_memory_enabled")
            )
        if "extract_memory" in personalization:
            settings_updates["extract_memory"] = bool(
                personalization.get("extract_memory")
            )
        if "user_preferences" in personalization:
            settings_updates["user_preferences"] = str(
                personalization.get("user_preferences") or ""
            )
        if settings_updates:
            await self._update_user_settings(user_id, settings_updates)

        return {"success": True}

    async def update_user_theme_preference(
        self,
        *,
        user_id: str,
        theme_preference: str,
    ) -> dict[str, Any]:
        normalized = theme_preference.lower().strip()
        if normalized not in {"light", "dark", "system"}:
            raise HTTPException(status_code=400, detail="Invalid theme preference")
        await self._update_user_settings(user_id, {"theme_preference": normalized})
        return {"success": True}

    async def update_user_chat_background(
        self,
        *,
        user_id: str,
        chat_background: str | None,
    ) -> dict[str, Any]:
        value = chat_background.strip() if isinstance(chat_background, str) else None
        await self._update_user_settings(user_id, {"chat_background": value or None})
        return {"success": True}

    async def update_user_default_model(
        self,
        *,
        user_id: str,
        default_model: str | None,
        default_provider_id: str | None = None,
    ) -> dict[str, Any]:
        value = default_model.strip() if isinstance(default_model, str) else None
        await self._update_user_settings(user_id, {"default_model": value or None})
        if default_provider_id is not None:
            provider_id = (
                default_provider_id.strip()
                if isinstance(default_provider_id, str)
                else None
            )
            await self._update_user_settings(
                user_id, {"default_provider_id": provider_id or None}
            )
        return {"success": True}

    async def update_user_auto_scroll(
        self,
        *,
        user_id: str,
        auto_scroll: bool,
    ) -> dict[str, Any]:
        await self._update_user_settings(user_id, {"auto_scroll": bool(auto_scroll)})
        return {"success": True}

    async def update_user_shortcut_enabled(
        self,
        *,
        user_id: str,
        shortcut_enabled: bool,
    ) -> dict[str, Any]:
        await self._update_user_settings(user_id, {"shortcut_enabled": bool(shortcut_enabled)})
        return {"success": True}

    async def update_user_default_app_mode(
        self,
        *,
        user_id: str,
        default_app_mode: str,
    ) -> dict[str, Any]:
        normalized = default_app_mode.upper().strip()
        if normalized not in {"AUTO", "CHAT", "SEARCH"}:
            raise HTTPException(status_code=400, detail="Invalid default app mode")
        await self._update_user_settings(user_id, {"default_app_mode": normalized})
        return {"success": True}

    async def get_federated(self) -> list[Any]:
        return []

    async def get_valid_tags(self) -> list[Any]:
        return []

    async def get_document_sets(self) -> list[Any]:
        return []

    async def get_admin_llm_provider(self) -> dict[str, Any]:
        llm_provider = await self.get_llm_provider()
        providers = llm_provider.get("providers", [])

        admin_providers = []
        for provider in providers:
            admin_providers.append(
                {
                    "id": provider.get("id"),
                    "name": provider.get("name"),
                    "provider": provider.get("provider"),
                    "provider_display_name": provider.get("provider_display_name"),
                    "api_key": None,
                    "api_base": None,
                    "api_version": None,
                    "custom_config": {},
                    "is_public": True,
                    "is_auto_mode": False,
                    "groups": [],
                    "personas": [],
                    "deployment_name": None,
                    "model_configurations": provider.get("model_configurations", []),
                }
            )

        default_model = env.DEFAULT_MODEL or llm_provider.get("default_text")
        return {
            "providers": admin_providers,
            "selected_provider": admin_providers[0]["name"] if admin_providers else None,
            "default_model": default_model,
        }

    async def test_llm(self) -> dict[str, bool]:
        return {"success": True}

    async def set_default_llm(self) -> dict[str, bool]:
        return {"success": True}

    async def get_ollama_models(self) -> list[dict[str, Any]]:
        return await self._session_controller.get_ollama_models()

    async def save_llm_provider(self) -> dict[str, bool]:
        return {"success": True}

    async def create_llm_provider(self) -> dict[str, bool]:
        return {"success": True}

    async def get_persona_providers(self, persona_id: int) -> dict[str, Any]:
        _ = persona_id
        llm_provider = await self.get_llm_provider()
        return {
            "providers": llm_provider.get("providers", []),
            "selected_provider": llm_provider.get("selected_provider"),
            "default_model": llm_provider.get("default_text"),
        }


_user_controller: UserController | None = None


def get_user_controller() -> UserController:
    """Get singleton UserController."""
    global _user_controller
    if _user_controller is None:
        _user_controller = UserController()
    return _user_controller
