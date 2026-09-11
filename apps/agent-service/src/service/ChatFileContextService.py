"""A chat turn's attachments, from request descriptors to LLM content blocks.

Split out of ``api/routes/ChatRoute.send_chat_message``, which had grown to
445 lines doing identity resolution, provider selection, thread
reconciliation, agent routing and this. Storing bytes, mirroring them to
MinIO/DB and normalising images is service work, not route work
(docs/coding-standards.md).

Behaviour is unchanged from the extracted original.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FileContext:
    """What a turn's attachments contribute to the model call.

    These three lists were separate locals threaded through 140 lines of the
    route, always built together and always consumed together — one result
    with one lifetime.
    """

    content_blocks: list[dict] = field(default_factory=list)
    files_metadata: list[dict] = field(default_factory=list)
    mail_attachments: list[dict[str, Any]] = field(default_factory=list)


def _merge_file_descriptors(
    request_descriptors: list[dict[str, Any]],
    project_descriptors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for descriptor in [*request_descriptors, *project_descriptors]:
        descriptor_id = descriptor.get("id") or descriptor.get("file_id")
        if not descriptor_id:
            descriptor_id = str(uuid.uuid4())
            descriptor = {**descriptor, "id": descriptor_id}

        existing = merged.get(str(descriptor_id))
        if existing is None:
            merged[str(descriptor_id)] = descriptor
            continue

        if not existing.get("data") and descriptor.get("data"):
            merged[str(descriptor_id)] = {**existing, **descriptor}

    return list(merged.values())


async def _resolve_project_file_descriptors(
    user_controller: Any,
    known_user_ids: set[str],
    project_id: Any,
) -> list[dict[str, Any]]:
    """The project's own files, or none if they cannot be read.

    A project whose files are unreachable still gets a working chat turn —
    the attachments are context, not a precondition.
    """
    if project_id is None:
        return []
    try:
        return await user_controller.get_project_file_descriptors_for_chat(
            list(known_user_ids),
            project_id,
        )
    except Exception as exc:
        logger.warning(
            "Could not resolve project files for chat context (project_id=%s): %s",
            project_id,
            exc,
        )
        return []


async def build_file_context(
    request_file_descriptors: list[dict[str, Any]],
    *,
    user_controller: Any,
    known_user_ids: set[str],
    effective_user_id: str,
    session_id: str,
    resolved_project_id: Any | None,
) -> FileContext:
    """Merge the request's attachments with the project's and materialise them.

    Each descriptor's bytes are stored in FileService so
    ``GET /api/chat/file/{id}`` can serve them later, and mirrored to MinIO/DB
    best-effort. A descriptor that arrives without data is recovered from
    MinIO when possible and skipped otherwise: one unusable attachment must
    not fail the turn.
    """
    project_file_descriptors = await _resolve_project_file_descriptors(
        user_controller, known_user_ids, resolved_project_id
    )
    file_descriptors = _merge_file_descriptors(
        request_file_descriptors,
        project_file_descriptors,
    )
    file_content_blocks: list[dict] = []
    files_metadata: list[dict] = []
    mail_attachments: list[dict[str, Any]] = []

    if file_descriptors:
        import base64 as _base64

        from service.FileService import IMAGE_MIMES, normalize_image_for_llm
        from service.FileService import store_file as _store_file
        from service.message_conversion import _extract_file_blocks

        for fd in file_descriptors:
            fd_id: str = fd.get("id") or str(uuid.uuid4())
            fd_name: str = fd.get("name") or "file"
            fd_mime: str = fd.get("mime_type") or "application/octet-stream"
            fd_data: str | None = fd.get("data")  # base64 string or None
            fd_type: str = fd.get("type") or "document"

            logger.debug(
                "Processing file descriptor: id=%s, name=%s, mime=%s, has_data=%s, type=%s",
                fd_id,
                fd_name,
                fd_mime,
                bool(fd_data),
                fd_type,
            )
            files_metadata.append({"id": fd_id, "type": fd_type, "name": fd_name})

            if not fd_data:
                # Try to recover file bytes from MinIO (e.g. after service restart)
                try:
                    from core.db.repositories.document_repo import DocumentRepository
                    from service.MinioService import download_file as minio_download

                    db_doc = await DocumentRepository().get_by_file_id(fd_id)
                    if db_doc and db_doc.get("minio_object_key"):
                        raw_bytes = minio_download(db_doc["minio_object_key"])
                        import base64 as _b64_inner

                        fd_data = _b64_inner.b64encode(raw_bytes).decode("ascii")
                        fd_mime = db_doc.get("mime_type") or fd_mime
                        fd_name = db_doc.get("filename") or fd_name
                        logger.debug(
                            "Recovered file %s from MinIO (%d bytes)", fd_id, len(raw_bytes)
                        )
                except Exception as _minio_err:
                    logger.warning("Could not recover file %s from MinIO: %s", fd_id, _minio_err)

            if not fd_data:
                logger.warning("File descriptor %s has no data, skipping", fd_id)
                continue

            m = fd_mime.lower().split(";")[0].strip()

            # Store raw bytes so the file-serve endpoint can return them
            try:
                raw = _base64.b64decode(fd_data)
                logger.debug("Storing file %s (%s): %d bytes", fd_id, m, len(raw))
                _store_file(fd_id, raw, fd_mime, fd_name)
                mail_attachments.append(
                    {
                        "id": fd_id,
                        "filename": fd_name,
                        "mime_type": fd_mime,
                        "content_base64": fd_data,
                    }
                )
            except Exception as store_err:
                logger.error(
                    "Could not store file %s in FileService: %s", fd_id, store_err, exc_info=True
                )

            # Persist to MinIO + DB (best-effort, only if not already saved)
            try:
                from core.db.repositories.document_repo import DocumentRepository
                from service.FileService import mime_to_chat_file_type
                from service.MinioService import upload_file as minio_upload

                doc_repo = DocumentRepository()
                existing = await doc_repo.get_by_file_id(fd_id)
                if existing is None:
                    object_key = minio_upload(
                        user_id=effective_user_id,
                        file_id=fd_id,
                        filename=fd_name,
                        data=raw,
                        mime_type=fd_mime,
                    )
                    await doc_repo.create(
                        file_id=fd_id,
                        user_id=effective_user_id,
                        filename=fd_name,
                        mime_type=fd_mime,
                        chat_file_type=mime_to_chat_file_type(fd_mime),
                        size_bytes=len(raw),
                        minio_object_key=object_key,
                        thread_id=session_id,
                        project_id=resolved_project_id,
                    )
            except Exception as _persist_err:
                logger.warning(
                    "MinIO/DB persist for inline file %s failed: %s", fd_id, _persist_err
                )

            if m in IMAGE_MIMES:
                norm_data, norm_mime = normalize_image_for_llm(fd_data, m)
                file_content_blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{norm_mime};base64,{norm_data}"},
                    }
                )
            else:
                blocks = _extract_file_blocks(fd_data, fd_mime, fd_name)
                file_content_blocks.extend(blocks)
    return FileContext(
        content_blocks=file_content_blocks,
        files_metadata=files_metadata,
        mail_attachments=mail_attachments,
    )
