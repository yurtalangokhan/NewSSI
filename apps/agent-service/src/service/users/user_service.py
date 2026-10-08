"""User settings and LLM provider service."""

import asyncio
import base64
from collections import OrderedDict
from collections.abc import Sequence
import functools
import json
import secrets
from typing import Any

from config_manager import env
from error_contract import RejectedUploadError, UnauthorizedError, render_error_message

from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import document_repository, project_repository
from service.common.base import BaseService
from service.common.uploads import UploadedFile
from service.runtime.store_service import list_chat_sessions_by_activity_from_store
from service.storage.file_service import validate_upload
from service.threads.session_service import SessionService, get_session_service
from service.users.user_helpers import (
    chat_session_activity_time,
    file_chat_type,
    normalize_owner_ids,
    now_iso,
    serialize_admin_provider,
    serialize_chat_session,
    thread_belongs_to_owner_ids,
    thread_project_id,
)

logger = get_logger(__name__)


# How many base64 upload payloads one user's in-memory store keeps.
MAX_PAYLOADS_PER_USER = 40


class UserService(BaseService):
    """Owns user preferences and model/provider endpoints."""

    def __init__(
        self,
        session_service: SessionService | None = None,
    ):
        self._session_service = session_service or get_session_service()
        self._project_repo = project_repository()
        # Minimal in-memory file store for project/recent file APIs.
        self._recent_files_by_user: dict[str, list[dict[str, Any]]] = {}
        self._project_files_by_user: dict[str, dict[int, list[dict[str, Any]]]] = {}
        self._file_payloads_by_user: dict[str, OrderedDict[str, dict[str, str]]] = {}

    async def resolve_project_identity(self, token: str | None, user: Any) -> tuple[str, list[str]]:
        """The user id projects are filed under, and every id that may own them.

        The identity lookup can map a Keycloak subject to a canonical user-service
        id; ownership checks must accept every id the same person is known by.
        """
        from service.auth.auth_service import get_auth_service

        identity = await get_auth_service().resolve_user_identity(token=token, user_id=user.user_id, user=user)
        primary_user_id = str(identity.get("primary_user_id") or user.user_id)
        effective_user_id = await self.resolve_projects_user_id(primary_user_id)
        if not effective_user_id:
            raise UnauthorizedError()
        owner_ids = list(
            dict.fromkeys(
                str(value)
                for value in [effective_user_id, *(identity.get("known_user_ids") or []), user.user_id]
                if value
            )
        )
        return effective_user_id, owner_ids

    async def resolve_projects_user_id(self, user_id: str | None) -> str | None:
        if user_id:
            if (env.MODE or "").lower() == "dev" and str(user_id).startswith(("user-", "dev-user")):
                fallback_user = await self._project_repo.get_latest_user_id()
                if fallback_user:
                    return fallback_user
            return user_id

        if (env.MODE or "").lower() == "dev":
            fallback_user = await self._project_repo.get_latest_user_id()
            if fallback_user:
                return fallback_user
            return "dev-user"

        return None

    async def _resolve_or_raise_user_id(self, user_id: str | None) -> str:
        effective_user_id = await self.resolve_projects_user_id(user_id)
        if not effective_user_id:
            self._raise_unauthorized("auth.not_authenticated")
        return effective_user_id

    def _project_files(self, user_id: str, project_id: int) -> list[dict[str, Any]]:
        return self._project_files_by_user.setdefault(user_id, {}).setdefault(project_id, [])

    def _recent_files(self, user_id: str) -> list[dict[str, Any]]:
        return self._recent_files_by_user.setdefault(user_id, [])

    def _file_payloads(self, user_id: str) -> "OrderedDict[str, dict[str, str]]":
        return self._file_payloads_by_user.setdefault(user_id, OrderedDict())

    def _remember_payload(self, user_id: str, file_id: str, payload: dict[str, str]) -> None:
        """Store one base64 payload, oldest-first evicted.

        This is a second copy of every upload, alongside FileService's own
        bounded store, and nothing evicted it — only an explicit delete removed
        an entry, so a session that uploaded steadily grew it without limit.
        """
        payloads = self._file_payloads(user_id)
        payloads[file_id] = payload
        payloads.move_to_end(file_id)
        while len(payloads) > MAX_PAYLOADS_PER_USER:
            payloads.popitem(last=False)

    async def _list_project_threads_for_owner_ids(
        self,
        owner_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Iterate activity pages until all owner-matching project threads are collected."""
        matching_threads: list[dict[str, Any]] = []
        before_activity: str | None = None
        before_id: str | None = None
        batch_size = 100

        while True:
            batch = await list_chat_sessions_by_activity_from_store(
                page_size=batch_size,
                before_activity=before_activity,
                before_id=before_id,
            )
            if not batch:
                break

            matching_threads.extend(
                thread
                for thread in batch
                if thread_project_id(thread) is not None and thread_belongs_to_owner_ids(thread, owner_ids)
            )

            if len(batch) < batch_size:
                break

            last_thread = batch[-1]
            before_activity = chat_session_activity_time(last_thread)
            before_id = last_thread.get("thread_id") or ""
            if not before_activity or not before_id:
                break

        return matching_threads

    async def get_recent_files(self, user_id: str | None) -> list[Any]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)
        recent = self._recent_files(effective_user_id)
        if recent:
            return recent

        docs = await document_repository().list_by_user(effective_user_id, limit=50)
        now = now_iso()
        hydrated = [
            {
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
            }
            for doc in docs
        ]
        self._recent_files_by_user[effective_user_id] = hydrated
        return hydrated

    async def upload_user_project_files(
        self,
        user_id: str | None,
        files: Sequence[UploadedFile],
        project_id: int | None,
        temp_id_map_raw: str | None,
        owner_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)
        effective_owner_ids = normalize_owner_ids(effective_user_id, owner_ids)

        if project_id is not None:
            project = await self._project_repo.get_for_user_ids(effective_owner_ids, project_id)
            if not project:
                self._raise_not_found("project.not_found")

        temp_id_map: dict[str, str] = {}
        if temp_id_map_raw:
            try:
                parsed = json.loads(temp_id_map_raw)
                if isinstance(parsed, dict):
                    temp_id_map = {str(k): str(v) for k, v in parsed.items()}
            except json.JSONDecodeError:
                self._raise_bad_request("project.invalid_temp_id_map")

        uploaded: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        now = now_iso()
        recent = self._recent_files(effective_user_id)

        for upload in files:
            file_id = secrets.token_hex(16)
            file_name = upload.filename or file_id
            content_type = upload.content_type or "application/octet-stream"
            raw = await upload.read()

            try:
                content_type = validate_upload(file_name, raw, content_type)
            except RejectedUploadError as exc:
                rejected.append({"name": file_name, "reason": render_error_message(exc)})
                continue

            temp_id = temp_id_map.get(file_name)
            chat_file_type = file_chat_type(content_type, file_name)
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
            try:
                from service.storage.file_service import store_file

                store_file(file_id, raw, content_type, file_name, owner_id=effective_user_id)
            except Exception:
                # FileService.store_file already holds these exact bytes, so
                # chat context reads them from there instead of a second copy
                # kept here (see get_project_file_descriptors_for_chat). This
                # base64 copy exists only for the case that write failed.
                self._remember_payload(
                    effective_user_id,
                    file_id,
                    {
                        "data": base64.b64encode(raw).decode("ascii"),
                        "mime_type": content_type,
                        "name": file_name,
                        "chat_file_type": chat_file_type,
                    },
                )

            # Persist to MinIO + DB for durable storage
            try:
                from service.storage.minio_service import upload_file as minio_upload

                # MinIO's client is synchronous; keep it off the event loop.
                object_key = await asyncio.to_thread(
                    functools.partial(
                        minio_upload,
                        user_id=effective_user_id,
                        file_id=file_id,
                        filename=file_name,
                        data=raw,
                        mime_type=content_type,
                    )
                )
                await document_repository().create(
                    file_id=file_id,
                    user_id=effective_user_id,
                    filename=file_name,
                    mime_type=content_type,
                    chat_file_type=chat_file_type,
                    size_bytes=len(raw),
                    minio_object_key=object_key,
                    project_id=project_id,
                )
                # Enrich payload with minio key so chat_route can fetch without base64
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

        return {"user_files": uploaded, "rejected_files": rejected}

    async def get_files_in_project(
        self,
        user_id: str | None,
        project_id: int,
        owner_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)
        project = await self._project_repo.get_for_user_ids(
            normalize_owner_ids(effective_user_id, owner_ids),
            project_id,
        )
        if not project:
            self._raise_not_found("project.not_found")

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
            normalize_owner_ids(effective_user_id, owner_ids),
            project_id,
        )
        if not project:
            self._raise_not_found("project.not_found")

        doc_repo = document_repository()
        await doc_repo.update_project_id(file_id, project_id)

        file_obj = next(
            (f for f in self._recent_files(effective_user_id) if f.get("id") == file_id),
            None,
        )
        if not file_obj:
            doc = await doc_repo.get_by_file_id(file_id, effective_user_id)
            if doc:
                file_obj = {
                    "id": doc["file_id"],
                    "name": doc["filename"],
                    "project_id": project_id,
                    "user_id": doc["user_id"],
                    "file_id": doc["file_id"],
                    "created_at": doc["created_at"] or now_iso(),
                    "status": "COMPLETED",
                    "file_type": doc["mime_type"],
                    "last_accessed_at": doc["created_at"] or now_iso(),
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
                self._project_files_by_user[effective_user_id][project_id] = [
                    linked,
                    *project_files,
                ]

        return {"success": True}

    async def unlink_file_from_project(
        self,
        user_id: str | None,
        project_id: int,
        file_id: str,
    ) -> dict[str, bool]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)

        await document_repository().update_project_id(file_id, None)

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

        doc = await document_repository().get_by_file_id(file_id, effective_user_id)
        if not doc:
            self._raise_not_found("file.not_found")
        return {
            "id": doc["file_id"],
            "name": doc["filename"],
            "project_id": doc["project_id"],
            "user_id": doc["user_id"],
            "file_id": doc["file_id"],
            "created_at": doc["created_at"] or now_iso(),
            "status": "COMPLETED",
            "file_type": doc["mime_type"],
            "last_accessed_at": doc["created_at"] or now_iso(),
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
            for file_id in missing:
                doc = await document_repository().get_by_file_id(file_id, effective_user_id)
                if doc:
                    found.append(
                        {
                            "id": doc["file_id"],
                            "name": doc["filename"],
                            "project_id": doc["project_id"],
                            "user_id": doc["user_id"],
                            "file_id": doc["file_id"],
                            "created_at": doc["created_at"] or now_iso(),
                            "status": "COMPLETED",
                            "file_type": doc["mime_type"],
                            "last_accessed_at": doc["created_at"] or now_iso(),
                            "chat_file_type": doc["chat_file_type"],
                            "token_count": 0,
                            "chunk_count": 0,
                            "temp_id": None,
                            "minio_object_key": doc["minio_object_key"],
                        }
                    )

        return found

    async def delete_user_file(self, user_id: str | None, file_id: str) -> dict[str, Any]:
        effective_user_id = await self._resolve_or_raise_user_id(user_id)

        doc_repo = document_repository()
        doc = await doc_repo.get_by_file_id(file_id, effective_user_id)

        in_memory = self._recent_files(effective_user_id)
        self._recent_files_by_user[effective_user_id] = [f for f in in_memory if f.get("id") != file_id]
        self._file_payloads(effective_user_id).pop(file_id, None)

        project_map = self._project_files_by_user.get(effective_user_id, {})
        for pid, files in list(project_map.items()):
            project_map[pid] = [f for f in files if f.get("id") != file_id]

        if doc:
            try:
                from service.storage.minio_service import delete_file as minio_delete

                minio_delete(doc["minio_object_key"])
            except Exception:
                logger.warning("Failed to delete MinIO object for file %s", file_id)
            await doc_repo.delete_by_file_id(file_id)

        return {
            "has_associations": False,
            "project_names": [],
            "assistant_names": [],
        }

    async def get_llm_provider(self) -> dict[str, Any]:
        return await self._session_service.get_llm_providers()

    async def get_llm_built_in_options(self) -> list[dict[str, Any]]:
        return await self._session_service.get_llm_built_in_options()

    async def test_llm_default(self) -> dict[str, bool]:
        return {"success": True}

    async def get_default_assistant(self) -> None:
        return None

    async def get_user_projects(
        self,
        user_id: str,
        owner_ids: list[str] | None = None,
    ) -> list[Any]:
        effective_owner_ids = normalize_owner_ids(user_id, owner_ids)
        projects = await self._project_repo.list_by_user_ids(effective_owner_ids)
        project_ids = {project["id"] for project in projects}
        threads = await self._list_project_threads_for_owner_ids(effective_owner_ids)

        sessions_by_project: dict[int, list[dict[str, Any]]] = {}
        for thread in threads:
            project_id = thread_project_id(thread)
            if project_id is None or project_id not in project_ids:
                continue
            sessions_by_project.setdefault(project_id, []).append(serialize_chat_session(thread))

        for project in projects:
            project_id = project["id"]
            project_sessions = sessions_by_project.get(project_id, [])
            project_sessions.sort(
                key=lambda session: (
                    chat_session_activity_time(session),
                    session.get("id") or "",
                ),
                reverse=True,
            )
            project["chat_sessions"] = project_sessions

        return projects

    async def create_user_project(self, user_id: str, name: str) -> dict[str, Any]:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            self._raise_bad_request("project.name_required")
        project = await self._project_repo.create_for_user(user_id=user_id, name=cleaned_name)
        project["chat_sessions"] = []
        return project

    async def get_user_project(
        self,
        user_id: str,
        project_id: int,
        owner_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        effective_owner_ids = normalize_owner_ids(user_id, owner_ids)
        project = await self._project_repo.get_for_user_ids(effective_owner_ids, project_id)
        if not project:
            self._raise_not_found("project.not_found")

        threads = await self._list_project_threads_for_owner_ids(effective_owner_ids)
        chat_sessions = [
            serialize_chat_session(thread) for thread in threads if thread_project_id(thread) == project_id
        ]
        chat_sessions.sort(
            key=lambda session: (
                chat_session_activity_time(session),
                session.get("id") or "",
            ),
            reverse=True,
        )
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
            self._raise_bad_request("project.name_required")
        project = await self._project_repo.rename_for_user_ids(
            user_ids=normalize_owner_ids(user_id, owner_ids),
            project_id=project_id,
            name=cleaned_name,
        )
        if not project:
            self._raise_not_found("project.not_found")
        project["chat_sessions"] = []
        return project

    async def delete_user_project(
        self,
        user_id: str,
        project_id: int,
        owner_ids: list[str] | None = None,
    ) -> dict[str, bool]:
        deleted = await self._project_repo.delete_for_user_ids(
            user_ids=normalize_owner_ids(user_id, owner_ids),
            project_id=project_id,
        )
        if not deleted:
            self._raise_not_found("project.not_found")
        return {"success": True}

    async def _hydrate_project_files(self, user_id: str, project_id: int) -> list[dict[str, Any]]:
        cache = self._project_files(user_id, project_id)
        cache_ids = {f.get("id") for f in cache}

        now = now_iso()
        merged = list(cache)

        for doc in await document_repository().list_by_project(project_id):
            if doc["file_id"] in cache_ids:
                continue
            cache_ids.add(doc["file_id"])
            merged.append(
                {
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
                }
            )

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
            normalize_owner_ids(user_id, owner_ids),
            project_id,
        )
        if not project:
            self._raise_not_found("project.not_found")
        return {"instructions": project.get("instructions")}

    async def upsert_user_project_instructions(
        self,
        user_id: str,
        project_id: int,
        instructions: str,
        owner_ids: list[str] | None = None,
    ) -> dict[str, str | None]:
        project = await self._project_repo.upsert_instructions_for_user_ids(
            user_ids=normalize_owner_ids(user_id, owner_ids),
            project_id=project_id,
            instructions=instructions,
        )
        if not project:
            self._raise_not_found("project.not_found")
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
                    # The same bytes this upload stored, read from
                    # FileService's own bounded cache rather than kept a
                    # second time here. Not written into `payloads`: doing so
                    # would recreate the copy this path exists to avoid, and
                    # FileService's own store is exactly as cheap to read
                    # again next time.
                    from service.storage.file_service import get_file as get_cached_file

                    cached_file = get_cached_file(file_id)
                    if cached_file is not None:
                        payload = {
                            "data": base64.b64encode(cached_file.data).decode("ascii"),
                            "mime_type": cached_file.mime_type,
                            "name": cached_file.filename,
                            "chat_file_type": cached_file.chat_file_type,
                        }

                if not payload:
                    object_key = file_obj.get("minio_object_key")
                    if object_key:
                        try:
                            from service.storage.minio_service import download_file

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
            owner_ids=normalize_owner_ids(user_id, owner_ids),
            project_id=project_id,
            chat_session_id=chat_session_id,
        )
        if not moved:
            self._raise_not_found("project.or_chat_session_not_found")
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
            owner_ids=normalize_owner_ids(user_id, owner_ids),
            chat_session_id=chat_session_id,
        )
        if not removed:
            self._raise_not_found("chat.chat_session_not_found")
        return {"success": True}

    async def get_admin_llm_provider(self) -> dict[str, Any]:
        llm_provider = await self.get_llm_provider()
        providers = llm_provider.get("providers", [])

        admin_providers = [serialize_admin_provider(p) for p in providers]

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
        return await self._session_service.get_ollama_models()

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


_user_service: UserService | None = None


def get_user_service() -> UserService:
    """Get singleton UserService."""
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
