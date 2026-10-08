"""Naming a chat session exactly once, whoever asks first: the run hook or the client."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import StrEnum
import time
from typing import Any, Protocol
import uuid

from core.observability.logger import get_logger
from infrastructure.runtime.checkpointer import get_checkpointer
from service.chat.chat_llm_override_service import resolve_provider_llm
from service.chat.chat_title_service import DEFAULT_SESSION_NAME, TitleResult, TitleSource

logger = get_logger(__name__)


class NameSource(StrEnum):
    """Who chose a session's name, as stored in the thread metadata."""

    SEED = "seed"
    AUTO = "auto"
    USER = "user"


class NamingLock(Protocol):
    async def acquire(self, thread_id: str) -> str | None: ...
    async def release(self, thread_id: str, token: str) -> None: ...
    async def is_held(self, thread_id: str) -> bool: ...


class LocalNamingLock:
    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._held: dict[str, tuple[str, float]] = {}

    async def acquire(self, thread_id: str) -> str | None:
        if await self.is_held(thread_id):
            return None
        token = uuid.uuid4().hex
        self._held[thread_id] = (token, time.monotonic() + self._ttl)
        return token

    async def release(self, thread_id: str, token: str) -> None:
        if self._held.get(thread_id, ("", 0.0))[0] == token:
            del self._held[thread_id]

    async def is_held(self, thread_id: str) -> bool:
        held = self._held.get(thread_id)
        return held is not None and held[1] > time.monotonic()


_configured_lock: NamingLock | None = None
_local_lock = LocalNamingLock()


def configure_naming_lock(lock: NamingLock | None) -> None:
    global _configured_lock
    _configured_lock = lock


def get_naming_lock() -> NamingLock:
    return _configured_lock or _local_lock


class NamingOutcome(StrEnum):
    NAMED = "named"
    ALREADY_NAMED = "already_named"
    WAITED = "waited"
    MISSING = "missing"


def is_settled(metadata: dict[str, Any], *, respect_legacy: bool) -> bool:
    source = metadata.get("name_source")
    provisional = bool(metadata.get("name_provisional"))
    if source == NameSource.USER:
        return True
    if source == NameSource.AUTO:
        return not provisional
    if source is None and respect_legacy:
        return metadata.get("name") not in (None, "", DEFAULT_SESSION_NAME) and not provisional
    return False


def apply_user_name(metadata: dict[str, Any], name: str) -> None:
    metadata["name"] = name
    metadata["name_source"] = NameSource.USER.value
    metadata.pop("name_provisional", None)


def apply_auto_name(metadata: dict[str, Any], result: TitleResult) -> None:
    metadata["name"] = result.title
    metadata["name_source"] = NameSource.AUTO.value
    if result.provisional:
        metadata["name_provisional"] = True
    else:
        metadata.pop("name_provisional", None)


def _message_text(msg: Any) -> str:
    """Flatten one stored message to a single line of text."""
    content = getattr(msg, "content", None)
    if content is None and isinstance(msg, dict):
        content = msg.get("content", "")

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if text:
                    parts.append(str(text))
            elif isinstance(item, str):
                parts.append(item)
        content = " ".join(parts)

    if not isinstance(content, str):
        content = str(content or "")
    return " ".join(content.split())


def _message_role(msg: Any) -> str:
    return getattr(msg, "type", None) or (msg.get("type", "") if isinstance(msg, dict) else "")


class SessionNamingService:
    def __init__(
        self,
        *,
        thread_service: Any,
        title_service: Any,
        lock: NamingLock,
        wait_seconds: float = 10.0,
        poll_seconds: float = 0.1,
        checkpointer_provider: Callable[[], Any] | None = None,
        default_user_id: str | None = None,
    ) -> None:
        self._thread_service = thread_service
        self._title_service = title_service
        self._lock = lock
        self._wait_seconds = wait_seconds
        self._poll_seconds = poll_seconds
        # Late-bound so a caller that patches its own module binding (as the
        # regression suite does for ChatManagementService) still reaches it.
        self._get_checkpointer = checkpointer_provider or get_checkpointer
        self._default_user_id = default_user_id

    async def extract_first_exchange(self, session_id: str) -> TitleSource:
        """Return the session's opening question and the reply it drew.

        The reply matters: a first message of "merhaba" or "şuna bir bakar
        mısın" carries no topic at all, and naming from the question alone is
        why those sessions ended up with the question as their own title.
        """
        state = await self._thread_service.get_thread_state(session_id)
        messages = state.get("values", {}).get("messages", [])

        user_message = ""
        for msg in messages:
            role = _message_role(msg)
            text = _message_text(msg)
            if not text:
                continue
            if not user_message:
                if role in ("human", "user"):
                    user_message = text
                continue
            if role in ("ai", "assistant"):
                return TitleSource(user_message=user_message, assistant_message=text)

        return TitleSource(user_message=user_message)

    async def derive_name(
        self,
        session_id: str,
        *,
        default_name: str = DEFAULT_SESSION_NAME,
        model_name: str | None = None,
        llm: Any | None = None,
    ) -> TitleResult:
        """Name *session_id* from its first exchange.

        Returns the default as a provisional result whenever the transcript
        cannot be read, so a session named before its history was persisted is
        retried rather than left with a placeholder forever.
        """
        if not self._get_checkpointer():
            return TitleResult(default_name, provisional=True, reason="no_checkpointer")

        try:
            source = await self.extract_first_exchange(session_id)
        except Exception as exc:
            logger.warning("[ChatTitle] Could not read session %s transcript: %s", session_id, exc)
            return TitleResult(default_name, provisional=True, reason="transcript_unavailable")

        return await self._title_service.generate(source, model_name=model_name, llm=llm, default_title=default_name)

    async def resolve_title_model(self, metadata: dict[str, Any]) -> tuple[str | None, Any | None]:
        """The model that should name this thread: the one the chat used.

        A provider-backed model is rebuilt as its owner (the API key is theirs),
        exactly as the chat request did. When that cannot be done the name is
        dropped rather than forwarded: a provider model name reaching the local
        fallback is a guaranteed 404.
        """
        model_name = metadata.get("current_alternate_model")
        provider_id = metadata.get("current_alternate_provider_id")
        provider_type = metadata.get("current_alternate_provider_type")
        if not (model_name and provider_id and provider_type):
            return model_name, None

        try:
            llm = await resolve_provider_llm(
                model_name=model_name,
                provider_id=str(provider_id),
                provider_type=str(provider_type),
                user_id=str(metadata.get("user_id") or self._default_user_id),
            )
        except Exception as exc:
            logger.warning("[ChatTitle] Could not rebuild %s for naming: %s", model_name, exc)
            return None, None
        return (model_name, llm) if llm is not None else (None, None)

    async def ensure_named(self, session_id: str, *, respect_legacy: bool = True) -> NamingOutcome:
        token = await self._lock.acquire(session_id)
        if token is None:
            await self._wait_for_release(session_id)
            return NamingOutcome.WAITED
        try:
            thread = await self._thread_service.get_thread(session_id)
            if not thread:
                return NamingOutcome.MISSING
            metadata = dict(thread.get("metadata") or {})
            if is_settled(metadata, respect_legacy=respect_legacy):
                return NamingOutcome.ALREADY_NAMED
            model_name, llm = await self.resolve_title_model(metadata)
            result = await self.derive_name(
                session_id,
                default_name=metadata.get("name") or DEFAULT_SESSION_NAME,
                model_name=model_name,
                llm=llm,
            )
            # A manual rename may have landed while the model was thinking.
            latest = await self._thread_service.get_thread(session_id)
            latest_metadata = dict((latest or {}).get("metadata") or {})
            if latest_metadata.get("name_source") == NameSource.USER:
                return NamingOutcome.ALREADY_NAMED
            apply_auto_name(latest_metadata, result)
            await self._thread_service.update_thread(session_id, latest_metadata, update_timestamp=False)
            return NamingOutcome.NAMED
        finally:
            await self._lock.release(session_id, token)

    async def _wait_for_release(self, session_id: str) -> None:
        deadline = time.monotonic() + self._wait_seconds
        # The lock lives in Redis and may be held by another instance, so there is
        # no in-process event to await: polling with a deadline is the only option.
        while await self._lock.is_held(session_id) and time.monotonic() < deadline:  # noqa: ASYNC110
            await asyncio.sleep(self._poll_seconds)
