import pytest

from tests.service.chat_runs.event_log_contract import EventLogContract
from tests.service.chat_runs.fakes import InMemoryRunEventLog

pytestmark = pytest.mark.asyncio


class TestInMemoryRunEventLog(EventLogContract):
    @pytest.fixture
    def make_log(self):
        return lambda max_events=50_000: InMemoryRunEventLog(max_events=max_events)
