import importlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

import error_contract
from error_contract import ApplicationError, render_error_code_message, render_error_message


@pytest.mark.parametrize("locale", ["en", "tr"])
def test_every_exported_static_code_renders_without_calling_domain_constructors(locale):
    for name in error_contract.__all__:
        exported = getattr(error_contract, name)
        if inspect.isclass(exported) and issubclass(exported, ApplicationError):
            message = render_error_code_message(exported.code, locale)
            assert message and "{" not in message and not message.startswith("errors.")


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("validation.failed", "Request validation failed."),
        ("auth.forbidden", "You do not have permission to perform this action."),
        ("request.payload_too_large", "The request payload is too large."),
        ("dependency.timeout", "A required dependency timed out."),
        ("dependency.startup_failed", "A required dependency is unavailable."),
        ("unknown_component_key", "Request validation failed."),
        ("agent.component_duplicate", "This flow component is already registered."),
    ],
)
def test_code_rendering_uses_canonical_safe_metadata(code, expected):
    assert (
        render_error_code_message(code, "en", message_params={"message": "secret password"})
        == expected
    )


@pytest.mark.parametrize(
    "category",
    [
        "authorization",
        "configuration",
        "validation",
        "connection",
        "timeout",
        "authentication",
        "unsupported",
        "response",
    ],
)
def test_connector_categories_are_registered_with_safe_defaults(category):
    code = f"connector.{category}"
    assert render_error_code_message(code, "en") != "An unexpected error occurred."
    assert render_error_code_message(code, "tr") != "Beklenmeyen bir hata oluştu."
    assert "{" not in render_error_code_message(code, "en")


@pytest.mark.parametrize(
    "name",
    [
        "CompositionValidationError",
        "CircularDependencyError",
        "SchemaMismatchError",
        "MaxDepthExceededError",
        "MissingAgentError",
    ],
)
def test_composition_defaults_and_diagnostics_are_localized(name):
    error_type = getattr(error_contract, name)
    assert render_error_message(error_type(), "tr") == "İstek doğrulaması başarısız oldu."
    assert (
        render_error_message(error_type("private schema diagnostic"), "tr")
        == "İstek doğrulaması başarısız oldu."
    )


def test_dependency_startup_diagnostic_is_localized():
    error = error_contract.DependencyStartupError(
        dependency="private-db", operation_name="connect", remediation="password=secret"
    )
    assert render_error_message(error, "tr") == "Gerekli bir bağımlılık kullanılamıyor."


def test_core_import_does_not_load_transport_adapters():
    script = """
import sys
from error_contract import BadRequestError
assert not any(name in sys.modules for name in (
    'error_contract.fastapi', 'error_contract.openapi', 'error_contract.starlette',
    'fastapi', 'starlette'))
from error_contract import (register_error_handlers, ERROR_RESPONSES,
                              ErrorContractMiddleware, ApiError)
assert callable(register_error_handlers)
assert isinstance(ERROR_RESPONSES, dict)
assert ErrorContractMiddleware and ApiError
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_registered_metadata_keys_exist_in_both_locales():
    localization = importlib.import_module("error_contract.localization")
    for locale in ("en", "tr"):
        catalog = json.loads(
            (Path(localization.__file__).with_name("locales") / f"{locale}.json").read_text()
        )
        for error_type in localization._ERROR_TYPES:
            if error_type.message_key:
                value = catalog
                for segment in error_type.message_key.split("."):
                    value = value[segment]
                assert isinstance(value, str)
            assert error_type.code in localization._ERROR_BY_CODE


def test_connector_instance_keeps_english_diagnostic_and_turkish_category_message():
    error = error_contract.ConnectorAccessError(
        "Access denied to the selected database.", category="authorization"
    )
    assert render_error_message(error, "en") == "Access denied to the selected database."
    assert render_error_message(error, "tr") != error.message
    assert error.code == "connector.authorization"


def test_missing_code_translation_uses_safe_metadata_not_diagnostic(monkeypatch):
    localization = importlib.import_module("error_contract.localization")
    monkeypatch.setattr(localization, "t", lambda key, **kwargs: key)
    assert (
        render_error_code_message(
            "connector.connection", "tr", message_params={"message": "private database password"}
        )
        == "The connector could not be reached."
    )


def test_required_field_code_retains_localized_default_and_explicit_field():
    assert render_error_code_message("validation.field_required", "tr") == "value alanı boş olamaz."
    assert (
        render_error_code_message(
            "validation.field_required", "tr", message_params={"field": "email"}
        )
        == "email alanı boş olamaz."
    )
