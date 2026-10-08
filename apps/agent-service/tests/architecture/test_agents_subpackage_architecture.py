"""Architecture tests verifying the modular subpackage structure of src/agents/."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
AGENTS_DIR = BASE_DIR / "src" / "agents"


def test_agents_subpackages_exist():
    """Verify that primitives, registry, implementations, and tooling subpackages exist."""
    assert (AGENTS_DIR / "primitives").is_dir(), "src/agents/primitives must exist"
    assert (AGENTS_DIR / "primitives" / "__init__.py").exists(), (
        "src/agents/primitives/__init__.py must exist"
    )
    assert (AGENTS_DIR / "primitives" / "base.py").exists(), (
        "src/agents/primitives/base.py must exist"
    )
    assert (AGENTS_DIR / "primitives" / "constants.py").exists(), (
        "src/agents/primitives/constants.py must exist"
    )
    assert (AGENTS_DIR / "primitives" / "agent_types.py").exists(), (
        "src/agents/primitives/agent_types.py must exist"
    )
    assert not (AGENTS_DIR / "primitives" / "types.py").exists(), (
        "src/agents/primitives/types.py must not exist"
    )

    assert (AGENTS_DIR / "registry").is_dir(), "src/agents/registry must exist"
    assert (AGENTS_DIR / "registry" / "__init__.py").exists(), (
        "src/agents/registry/__init__.py must exist"
    )
    assert (AGENTS_DIR / "registry" / "registry.py").exists(), (
        "src/agents/registry/registry.py must exist"
    )
    assert (AGENTS_DIR / "registry" / "agent_factory.py").exists(), (
        "src/agents/registry/agent_factory.py must exist"
    )

    assert (AGENTS_DIR / "implementations").is_dir(), "src/agents/implementations must exist"
    assert (AGENTS_DIR / "implementations" / "__init__.py").exists(), (
        "src/agents/implementations/__init__.py must exist"
    )
    assert (AGENTS_DIR / "implementations" / "chatbot.py").exists(), (
        "src/agents/implementations/chatbot.py must exist"
    )
    assert (AGENTS_DIR / "implementations" / "configurable_mcp_agent.py").exists(), (
        "src/agents/implementations/configurable_mcp_agent.py must exist"
    )
    assert (AGENTS_DIR / "implementations" / "dynamic_agent.py").exists(), (
        "src/agents/implementations/dynamic_agent.py must exist"
    )
    assert (AGENTS_DIR / "implementations" / "flow_agent.py").exists(), (
        "src/agents/implementations/flow_agent.py must exist"
    )
    assert (AGENTS_DIR / "implementations" / "github_mcp_agent.py").exists(), (
        "src/agents/implementations/github_mcp_agent.py must exist"
    )

    assert (AGENTS_DIR / "tooling").is_dir(), "src/agents/tooling must exist"
    assert (AGENTS_DIR / "tooling" / "__init__.py").exists(), (
        "src/agents/tooling/__init__.py must exist"
    )
    assert (AGENTS_DIR / "tooling" / "document_tools.py").exists(), (
        "src/agents/tooling/document_tools.py must exist"
    )
    assert (AGENTS_DIR / "tooling" / "mail_tooling.py").exists(), (
        "src/agents/tooling/mail_tooling.py must exist"
    )


def test_no_concrete_agents_or_tools_in_root():
    """Verify that concrete agent implementations and tools have moved out of the root."""
    forbidden_root_files = [
        "lazy_agent.py",
        "chatbot.py",
        "configurable_mcp_agent.py",
        "configurable_mcp_agent_helpers.py",
        "dynamic_agent.py",
        "flow_agent.py",
        "github_mcp_agent.py",
        "document_tools.py",
        "mail_tooling.py",
        "connector_call_recovery.py",
        "mcp_loader.py",
        "mcp_external.py",
    ]
    for fname in forbidden_root_files:
        assert not (AGENTS_DIR / fname).exists(), (
            f"src/agents/{fname} should be in its respective subpackage"
        )


def test_agents_canonical_exports():
    """Verify that src/agents/__init__.py exports the essential public interface."""
    from agents import (
        DEFAULT_AGENT,
        Agent,
        AgentGraph,
        AgentGraphLike,
        DynamicAgent,
        FlowAgent,
        LazyLoadingAgent,
        get_agent,
        get_agent_or_lazy,
        get_all_agent_info,
    )

    assert DEFAULT_AGENT is not None
    assert Agent is not None
    assert AgentGraph is not None
    assert AgentGraphLike is not None
    assert DynamicAgent is not None
    assert FlowAgent is not None
    assert LazyLoadingAgent is not None
    assert callable(get_agent)
    assert callable(get_agent_or_lazy)
    assert callable(get_all_agent_info)
