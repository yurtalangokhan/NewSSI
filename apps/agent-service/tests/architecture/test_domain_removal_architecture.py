"""Architectural test: Verify that src/domain is completely removed and integrated
into service-repository-controller architecture (service and schemas).
Also verifies that schemas are flat and entities subfolder is removed.
"""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
TESTS_DIR = Path(__file__).resolve().parent.parent.parent / "tests"


def test_domain_folder_does_not_exist():
    """Verify that neither src/domain nor tests/domain exists."""
    domain_src = SRC_DIR / "domain"
    domain_tests = TESTS_DIR / "domain"
    assert not domain_src.exists(), f"src/domain must be removed, but found at {domain_src}"
    assert not domain_tests.exists(), f"tests/domain must be removed, but found at {domain_tests}"


def test_schemas_entities_folder_does_not_exist():
    """Verify that src/schemas/entities does not exist and schemas are flat."""
    entities_dir = SRC_DIR / "schemas" / "entities"
    assert not entities_dir.exists(), (
        f"src/schemas/entities must be removed, but found at {entities_dir}"
    )
    assert (SRC_DIR / "schemas" / "base.py").exists()


def test_service_and_schemas_subpackages_exist():
    """Verify all integrated subpackages exist under src/service and src/schemas."""
    assert (SRC_DIR / "service" / "flows" / "__init__.py").exists()
    assert (SRC_DIR / "service" / "agent_definitions" / "__init__.py").exists()
    assert (SRC_DIR / "service" / "model_providers" / "__init__.py").exists()
    assert (SRC_DIR / "service" / "threads" / "__init__.py").exists()
    assert (SRC_DIR / "service" / "user_memory" / "__init__.py").exists()
    assert (SRC_DIR / "service" / "ollama" / "__init__.py").exists()
    assert (SRC_DIR / "service" / "chat" / "message_conversion.py").exists()


def test_canonical_exports():
    """Verify that canonical symbols can be imported from their new locations."""
    # Base Schema Model & Aliases
    from schemas.base import BaseDomainEntity, BaseSchemaModel

    assert BaseSchemaModel is not None
    assert BaseDomainEntity is BaseSchemaModel

    # Personas Schema Model & Aliases
    from schemas.personas import Persona, PersonaEntity

    assert Persona is not None
    assert PersonaEntity is Persona

    # Mail Config Schema Model & Aliases
    from schemas.mail_configs import MailConfig, MailConfigEntity

    assert MailConfig is not None
    assert MailConfigEntity is MailConfig

    # Threads Schema Model & Aliases
    from schemas.threads import Thread, ThreadEntity

    assert Thread is not None
    assert ThreadEntity is Thread

    # MCP Schema Models & Aliases
    from schemas.mcp_admin import MCPProvider, MCPProviderEntity, MCPTool, MCPToolEntity

    assert MCPProvider is not None
    assert MCPTool is not None
    assert MCPProviderEntity is MCPProvider
    assert MCPToolEntity is MCPTool

    # Flows
    from service.flows import FlowService

    assert FlowService is not None

    # Agent Definitions
    from service.agent_definitions import AgentDefinitionService, AgentService

    assert AgentDefinitionService is not None
    assert AgentService is not None

    # Providers
    from service.model_providers import ModelProviderService, ProviderService, known_model_providers

    assert ModelProviderService is not None
    assert ProviderService is not None
    assert known_model_providers is not None

    # Threads
    from service.threads import ThreadService

    assert ThreadService is not None

    # User Memory
    from service.user_memory import UserMemoryService

    assert UserMemoryService is not None

    # Ollama
    from service.ollama import OllamaRepository, OllamaService

    assert OllamaService is not None
    assert OllamaRepository is not None

    # Chat Message Conversion
    from service.chat.message_conversion import (
        convert_input_messages,
        langchain_to_chat_message,
    )

    assert convert_input_messages is not None
    assert langchain_to_chat_message is not None
