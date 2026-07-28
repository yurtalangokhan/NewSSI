import pytest

from domain.ollama.service import OllamaService


class _FakeOllamaRepository:
    def __init__(self) -> None:
        self.base_url = "http://ollama:11434"
        self.deleted_models: list[str] = []

    async def get_version(self) -> str:
        return "0.6.8"

    async def list_models(self) -> list[dict]:
        return [
            {"name": "llama3.1:8b", "size": 4_900_000_000},
            {"name": "nomic-embed-text:latest", "size": 274_000_000},
        ]

    async def show_model(self, model_name: str) -> dict:
        if model_name == "llama3.1:8b":
            return {
                "capabilities": ["completion", "tools", "thinking"],
                "model_info": {"llama.context_length": 131072},
            }
        return {"capabilities": ["embedding"], "model_info": {"bert.context_length": 8192}}

    async def delete_model(self, model_name: str) -> bool:
        self.deleted_models.append(model_name)
        return True


class _OfflineOllamaRepository(_FakeOllamaRepository):
    async def get_version(self) -> str:
        raise ConnectionError("cannot connect")

    async def list_models(self) -> list[dict]:
        raise ConnectionError("cannot connect")


@pytest.mark.asyncio
async def test_status_reports_online_builtin_ollama_with_model_count():
    service = OllamaService(_FakeOllamaRepository())

    status = await service.get_status()

    assert status == {
        "base_url": "http://ollama:11434",
        "online": True,
        "version": "0.6.8",
        "model_count": 2,
        "error": None,
    }


@pytest.mark.asyncio
async def test_status_reports_offline_without_raising():
    service = OllamaService(_OfflineOllamaRepository())

    status = await service.get_status()

    assert status["base_url"] == "http://ollama:11434"
    assert status["online"] is False
    assert status["version"] is None
    assert status["model_count"] == 0
    assert status["error"] == "cannot connect"


@pytest.mark.asyncio
async def test_list_models_enriches_capabilities_from_show_payloads():
    service = OllamaService(_FakeOllamaRepository())

    models = await service.list_models()

    assert models == [
        {
            "name": "llama3.1:8b",
            "display_name": "llama3.1:8b",
            "size": 4_900_000_000,
            "max_input_tokens": 131072,
            "supports_image_input": False,
            "supports_reasoning": True,
            "is_remote": False,
        },
        {
            "name": "nomic-embed-text:latest",
            "display_name": "nomic-embed-text:latest",
            "size": 274_000_000,
            "max_input_tokens": 8192,
            "supports_image_input": False,
            "supports_reasoning": False,
            "is_remote": False,
        },
    ]


@pytest.mark.asyncio
async def test_delete_model_passes_name_to_repository():
    repo = _FakeOllamaRepository()
    service = OllamaService(repo)

    result = await service.delete_model("llama3.1:8b")

    assert result == {"success": True}
    assert repo.deleted_models == ["llama3.1:8b"]
