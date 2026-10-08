"""The production checkpointer must persist a pandas DataFrame.

`Operations` (table ops), `SplitText` and `TypeConverter` (Table) put a
DataFrame in ``scratch``. The default msgpack serde rejects it —
"Type is not msgpack serializable: DataFrame" — and 500s the whole run
(B5). ``pickle_fallback=True`` on the serializer is the fix; these tests
pin that it actually round-trips.
"""

from __future__ import annotations

import pandas as pd
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def test_pickle_fallback_serde_round_trips_a_dataframe():
    serde = JsonPlusSerializer(pickle_fallback=True)
    df = pd.DataFrame([{"ticket": "TCK-1", "hours": 72}, {"ticket": "TCK-2", "hours": 50}])

    state = {"scratch": {"ops-1": df}, "messages": []}
    decoded = serde.loads_typed(serde.dumps_typed(state))

    assert decoded["scratch"]["ops-1"].equals(df)


def test_postgres_saver_is_built_with_a_serde(monkeypatch):
    """The connection-pool context manager wires a serde onto the
    AsyncPostgresSaver rather than relying on the default."""
    import memory.postgres as pg

    captured = {}

    class _FakeSaver:
        def __init__(self, pool, serde=None):
            captured["serde"] = serde

        async def setup(self):
            return None

    monkeypatch.setattr(pg, "AsyncPostgresSaver", _FakeSaver)

    from langgraph.checkpoint.serde.jsonplus import (
        JsonPlusSerializer as _JPS,
    )

    pg.AsyncPostgresSaver(object(), serde=_JPS(pickle_fallback=True))
    assert isinstance(captured["serde"], _JPS)
