import pytest

from tests.service.chat_runs.fakes import InMemoryRunRegistry
from tests.service.chat_runs.run_registry_contract import RunRegistryContract

pytestmark = pytest.mark.asyncio


class TestInMemoryRunRegistry(RunRegistryContract):
    @pytest.fixture
    def registry(self):
        return InMemoryRunRegistry()
