from fakeredis.model._stream import StreamEntryKey, XStream
import fakeredis
import pytest
import pytest_asyncio

_original_xstream_add = XStream.add


def _xstream_add_with_strict_ordering(
    self, fields, entry_key="*", producer_id=None, idempotent_id=None
):
    if producer_id is None and self._ids:
        key = entry_key.decode() if isinstance(entry_key, bytes) else entry_key
        if isinstance(key, str) and key != "*" and not key.endswith("*"):
            if self._ids[-1] >= StreamEntryKey.parse_str(key):
                return None
    return _original_xstream_add(
        self, fields, entry_key=entry_key, producer_id=producer_id, idempotent_id=idempotent_id
    )


@pytest_asyncio.fixture
async def redis_client(monkeypatch: pytest.MonkeyPatch):
    # fakeredis 2.38.0's XStream.add only rejects an explicit XADD id that is
    # strictly smaller than the stream's last id (`self._ids[-1] > ts_seq`); real
    # Redis also rejects an id that is *equal* to the last one. RedisRunEventLog
    # relies on that equal-id rejection to fence a re-appended/duplicate seq via
    # EventSequenceError, so we patch the comparison to `>=` for this test double
    # rather than adding an app-level pre-check to the adapter, which would
    # reintroduce the race the atomic Redis-side check exists to prevent.
    #
    # Applied through `monkeypatch` (not a module-level reassignment) so pytest
    # undoes it automatically when this fixture tears down: the patch is scoped
    # to tests that request `redis_client`, and cannot leak into some other
    # test file's own `fakeredis.FakeAsyncRedis`/`FakeStrictRedis` instance.
    monkeypatch.setattr(XStream, "add", _xstream_add_with_strict_ordering)

    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()
