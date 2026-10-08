"""Spec: the shared psycopg pool backing the checkpointer/store must be
closed during app shutdown, like every other startup resource (Redis, the
SQLAlchemy engine, background workers) already is. Before this, `app.py`'s
lifespan shutdown path closed all of those but never called
`close_shared_pool()`, so the pool was only ever reclaimed by process exit.
"""

import inspect

import app as app_module


def test_lifespan_calls_close_shared_pool():
    source = inspect.getsource(app_module)
    assert "close_shared_pool" in source


def test_close_shared_pool_runs_in_the_shutdown_section_after_yield():
    source = inspect.getsource(app_module.lifespan)
    yield_index = source.index("yield")
    close_index = source.index("close_shared_pool")
    assert close_index > yield_index
