"""Architectural fitness tests for service and core modularization.

Validates that:
1. All bounded contexts in `service` and `core` expose canonical exports.
2. No legacy shim files exist in `service/` root or `core/` root.
3. No PEP 562 dynamic `__getattr__` fallback exists on `service`.
4. Legacy core MCP shims are completely removed.
"""

import importlib
import os

import pytest


class TestCoreSecurityMcpModularization:
    """Validates the core.security.mcp bounded context."""

    def test_canonical_mcp_security_imports(self):
        mcp_auth = importlib.import_module("core.security.mcp.mcp_auth")
        assert hasattr(mcp_auth, "_is_internal_mcp_url")

        mcp_enums = importlib.import_module("core.security.mcp.mcp_enums")
        assert hasattr(mcp_enums, "MCPAuthType")
        assert hasattr(mcp_enums, "MCPServerStatus")
        assert hasattr(mcp_enums, "MCPAuthPerformer")
        assert hasattr(mcp_enums, "MCPTransport")

        mcp_ssrf = importlib.import_module("core.security.mcp.mcp_ssrf_guard")
        assert hasattr(mcp_ssrf, "validate_mcp_server_url")
        assert hasattr(mcp_ssrf, "MCPUrlRejected")

        mcp_policy = importlib.import_module("core.security.mcp.mcp_url_policy")
        assert hasattr(mcp_policy, "default_mcp_url")
        assert hasattr(mcp_policy, "resolve_allowed_mcp_url")

    def test_no_legacy_mcp_security_shims(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("core.security.mcp_enums")
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("core.security.mcp_ssrf_guard")
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("core.security.mcp_url_policy")
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("core.security.mcp_auth")


class TestServiceAuthModularization:
    """Validates the service.auth bounded context."""

    def test_canonical_auth_imports(self):
        auth_pkg = importlib.import_module("service.auth")
        assert hasattr(auth_pkg, "AuthService")
        assert hasattr(auth_pkg, "PermissionService")
        assert hasattr(auth_pkg, "MailConfigService")


class TestServiceMcpModularization:
    """Validates the service.mcp bounded context."""

    def test_canonical_mcp_imports(self):
        mcp_pkg = importlib.import_module("service.mcp")
        assert hasattr(mcp_pkg, "MCPToolService")
        assert hasattr(mcp_pkg, "MCPProviderService")
        assert hasattr(mcp_pkg, "MCPOAuthService")
        assert hasattr(mcp_pkg, "MCPCredentialService")


class TestServiceStorageModularization:
    """Validates the service.storage bounded context."""

    def test_canonical_storage_imports(self):
        storage_pkg = importlib.import_module("service.storage")
        assert hasattr(storage_pkg, "file_service")
        assert hasattr(storage_pkg, "minio_service")
        assert hasattr(storage_pkg, "DocumentProgressTracker")


class TestServiceDocumentsModularization:
    """Validates the service.documents bounded context."""

    def test_canonical_documents_imports(self):
        doc_pkg = importlib.import_module("service.documents")
        assert hasattr(doc_pkg, "render_pdf")
        assert hasattr(doc_pkg, "render_docx")
        assert hasattr(doc_pkg, "render_xlsx")
        assert hasattr(doc_pkg, "render_csv")
        assert hasattr(doc_pkg, "render_json")
        assert hasattr(doc_pkg, "render_markdown_text")


class TestServiceIngestModularization:
    """Validates the service.ingest bounded context."""

    def test_canonical_ingest_imports(self):
        ingest_pkg = importlib.import_module("service.ingest")
        assert hasattr(ingest_pkg, "connector_catalog_service")
        assert hasattr(ingest_pkg, "ConnectorRuntime")
        assert hasattr(ingest_pkg, "get_connector_runtime")
        assert hasattr(ingest_pkg, "RagDatasourceDestination")
        assert hasattr(ingest_pkg, "ingestion_service")


class TestServiceRuntimeModularization:
    """Validates the service.runtime bounded context."""

    def test_canonical_runtime_imports(self):
        runtime_pkg = importlib.import_module("service.runtime")
        assert hasattr(runtime_pkg, "register_run")
        assert hasattr(runtime_pkg, "RunService")
        assert hasattr(runtime_pkg, "ScheduleService")
        assert hasattr(runtime_pkg, "get_thread_from_store")
        assert hasattr(runtime_pkg, "get_checkpointer")
        assert hasattr(runtime_pkg, "find_fork_point")
        assert hasattr(runtime_pkg, "PlaygroundRetentionWorker")


class TestServiceChatModularization:
    """Validates the service.chat bounded context."""

    def test_canonical_chat_imports(self):
        chat_pkg = importlib.import_module("service.chat")
        assert hasattr(chat_pkg, "resolve_chat_agent")
        assert hasattr(chat_pkg, "build_effective_llm_override")
        assert hasattr(chat_pkg, "build_file_context")
        assert hasattr(chat_pkg, "reconstruct_messages")
        assert hasattr(chat_pkg, "apply_provider_llm_override")
        assert hasattr(chat_pkg, "parse_chat_request")
        assert hasattr(chat_pkg, "prepare_chat_thread")


class TestServiceOrchestrationModularization:
    """Validates the service.orchestration bounded context."""

    def test_canonical_orchestration_imports(self):
        orch_pkg = importlib.import_module("service.orchestration")
        assert hasattr(orch_pkg, "AssistantAgentService")
        assert hasattr(orch_pkg, "AssistantSchemasService")
        assert hasattr(orch_pkg, "CompositionValidationService")
        assert hasattr(orch_pkg, "ConnectorToolService")
        assert hasattr(orch_pkg, "AgentToolsService")
        assert hasattr(orch_pkg, "message_generator")
        assert hasattr(orch_pkg, "get_graph_and_config")


class TestServicePackageStrictness:
    """Validates that PEP 562 dynamic attribute access is removed and root packages strictly expose modular contexts."""

    def test_service_package_no_getattr_fallback(self):
        import service

        # Per architectural standard: no fallback shims or dynamic getattr
        assert not hasattr(service, "AuthService")
        assert not hasattr(service, "RunService")
        assert not hasattr(service, "FileService")
        assert not hasattr(service, "MCPToolService")

    def test_no_pep562_getattr_shims_in_any_service_module(self):
        import ast

        import service

        service_dir = os.path.dirname(service.__file__)
        files_with_getattr = []
        for root_dir, _, files in os.walk(service_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root_dir, file)
                    with open(full_path, encoding="utf-8") as f:
                        try:
                            tree = ast.parse(f.read())
                        except Exception:
                            continue
                    for node in tree.body:
                        if (
                            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and node.name == "__getattr__"
                        ):
                            rel = os.path.relpath(full_path, service_dir)
                            files_with_getattr.append(rel)

        assert files_with_getattr == [], (
            f"Found PEP 562 __getattr__ shims in service package: {files_with_getattr}"
        )

    def test_no_legacy_shims_in_service_root(self):
        import service

        service_dir = os.path.dirname(service.__file__)
        py_files = [f for f in os.listdir(service_dir) if f.endswith(".py") and f != "__init__.py"]
        assert py_files == [], f"Found unexpected loose files in service root: {py_files}"

    def test_no_legacy_document_generation_shim(self):
        import service

        service_dir = os.path.dirname(service.__file__)
        shim_path = os.path.join(service_dir, "storage", "document_generation_service.py")
        assert not os.path.exists(shim_path), (
            f"Found legacy shim {shim_path} that should have been eliminated"
        )

    def test_no_legacy_shims_in_core_root(self):
        import core

        core_dir = os.path.dirname(core.__file__)
        py_files = [f for f in os.listdir(core_dir) if f.endswith(".py") and f != "__init__.py"]
        assert py_files == [], f"Found unexpected loose files in core root: {py_files}"
