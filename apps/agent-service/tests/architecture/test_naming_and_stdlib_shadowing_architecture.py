"""Architectural test: Verify stdlib shadowing elimination and helper disambiguation.

Ensures that:
1. agents.primitives uses agent_types.py and NO types.py shim exists (preventing stdlib shadowing).
2. core/utils/pdf_utils.py is the single source of truth and NO service/web_search/pdf_utils.py shim exists.
3. chat_helpers.py is disambiguated into chat_title_service.py and chat_route_helpers.py, and NO chat_helpers.py shim exists.
4. user_helpers.py is disambiguated into user_controller_helpers.py and user_route_helpers.py, and NO user_helpers.py shim exists.
5. Legacy shims in service/threads, service/ollama, service/user_memory, service/providers are completely removed.
"""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"


def test_agent_types_exists_and_no_stdlib_shadowing():
    """Verify that agent_types.py exists and NO types.py shim exists."""
    agent_types_file = SRC_DIR / "agents" / "primitives" / "agent_types.py"
    legacy_types_file = SRC_DIR / "agents" / "primitives" / "types.py"

    assert agent_types_file.exists(), f"Expected {agent_types_file} to exist"
    assert not legacy_types_file.exists(), f"Legacy shim {legacy_types_file} must not exist"

    from agents.primitives.agent_types import AgentGraph, AgentGraphLike

    assert AgentGraph is not None
    assert AgentGraphLike is not None


def test_pdf_utils_unified_in_core():
    """Verify core.utils.pdf_utils is the SSOT and NO web_search/pdf_utils.py shim exists."""
    pdf_utils_file = SRC_DIR / "core" / "utils" / "pdf_utils.py"
    legacy_web_pdf = SRC_DIR / "service" / "web_search" / "pdf_utils.py"

    assert pdf_utils_file.exists(), f"Expected {pdf_utils_file} to exist"
    assert not legacy_web_pdf.exists(), f"Legacy shim {legacy_web_pdf} must not exist"

    from core.utils.pdf_utils import (
        MAX_EMBEDDED_IMAGES_PER_FILE,
        TEXT_SECTION_SEPARATOR,
        extract_text_from_pdf,
        extract_text_from_pdf_bytes,
        is_garbage_text,
        read_pdf_file,
    )

    assert is_garbage_text is not None
    assert extract_text_from_pdf_bytes is not None
    assert extract_text_from_pdf is not None
    assert read_pdf_file is not None
    assert TEXT_SECTION_SEPARATOR == "\n\n"
    assert MAX_EMBEDDED_IMAGES_PER_FILE == 10


def test_chat_helpers_disambiguated():
    """Verify chat helper modules are clearly named and NO chat_helpers.py shim exists."""
    title_service = SRC_DIR / "service" / "chat" / "chat_title_service.py"
    route_helpers = SRC_DIR / "api" / "helpers" / "chat_route_helpers.py"
    legacy_ctrl_chat = SRC_DIR / "controller" / "chat_helpers.py"
    legacy_api_chat = SRC_DIR / "api" / "helpers" / "chat_helpers.py"

    assert title_service.exists(), f"Expected {title_service} to exist"
    assert route_helpers.exists(), f"Expected {route_helpers} to exist"
    assert not legacy_ctrl_chat.exists(), f"Legacy shim {legacy_ctrl_chat} must not exist"
    assert not legacy_api_chat.exists(), f"Legacy shim {legacy_api_chat} must not exist"

    # The title helpers became a service: naming a session now goes through
    # one object that asks the model for the language itself, instead of a
    # bag of functions each guessing at it. The disambiguation this test
    # guards is unchanged -- the module is still clearly named and there is
    # still no chat_helpers.py shim.
    from service.chat.chat_title_service import (
        ChatTitleService,
        TitleResult,
        TitleSource,
        get_chat_title_service,
        resolve_display_name,
    )

    assert ChatTitleService is not None
    assert TitleSource is not None
    assert TitleResult is not None
    assert get_chat_title_service is not None
    assert resolve_display_name is not None

    from api.helpers.chat_route_helpers import (
        coerce_project_id,
        merge_file_descriptors,
        resolve_effective_chat_user_id,
        resolve_project_id_from_chat_context,
        truncate_name,
    )

    assert truncate_name is not None
    assert coerce_project_id is not None
    assert resolve_project_id_from_chat_context is not None
    assert merge_file_descriptors is not None
    assert resolve_effective_chat_user_id is not None


def test_user_helpers_disambiguated():
    """Verify user helper modules are clearly named and NO user_helpers.py shim exists."""
    ctrl_helpers = SRC_DIR / "service" / "users" / "user_helpers.py"
    route_helpers = SRC_DIR / "api" / "helpers" / "user_route_helpers.py"
    legacy_ctrl_user = SRC_DIR / "controller" / "user_helpers.py"
    legacy_api_user = SRC_DIR / "api" / "helpers" / "user_helpers.py"

    assert ctrl_helpers.exists(), f"Expected {ctrl_helpers} to exist"
    assert route_helpers.exists(), f"Expected {route_helpers} to exist"
    assert not legacy_ctrl_user.exists(), f"Legacy shim {legacy_ctrl_user} must not exist"
    assert not legacy_api_user.exists(), f"Legacy shim {legacy_api_user} must not exist"

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

    assert now_iso is not None
    assert file_chat_type is not None
    assert thread_project_id is not None
    assert normalize_owner_ids is not None
    assert thread_belongs_to_owner_ids is not None
    assert chat_session_activity_time is not None
    assert serialize_chat_session is not None
    assert serialize_admin_provider is not None

    from api.helpers.user_route_helpers import resolve_project_identity

    assert resolve_project_identity is not None


def test_no_legacy_service_shims():
    """Verify that no legacy service.py or repository.py re-export shims exist."""
    forbidden = [
        SRC_DIR / "service" / "threads" / "service.py",
        SRC_DIR / "service" / "ollama" / "service.py",
        SRC_DIR / "service" / "ollama" / "repository.py",
        SRC_DIR / "service" / "user_memory" / "service.py",
        SRC_DIR / "service" / "providers" / "provider_service.py",
    ]
    for p in forbidden:
        assert not p.exists(), f"Legacy service shim {p} must not exist"
