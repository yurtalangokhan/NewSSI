"""Startup migrations must be serialised across concurrently starting replicas.

Spec 5/T7: two replicas starting together previously ran CREATE DATABASE
and alembic upgrade concurrently with no coordination, which blocked
horizontal scaling and could corrupt the schema. A Postgres session
advisory lock, held on the always-present ``postgres`` maintenance
database, now serialises the whole startup migration sequence.
"""

import inspect
import threading
import time

from src.core.database import startup


def test_startup_uses_an_advisory_lock():
    assert "pg_advisory_lock" in inspect.getsource(startup)


def test_migration_lock_serialises_concurrent_holders():
    order: list[tuple[str, str]] = []
    lock = threading.Lock()

    def hold_lock(label: str) -> None:
        with startup._migration_lock():
            with lock:
                order.append(("start", label))
            time.sleep(0.2)
            with lock:
                order.append(("end", label))

    t1 = threading.Thread(target=hold_lock, args=("a",))
    t2 = threading.Thread(target=hold_lock, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not t1.is_alive()
    assert not t2.is_alive()
    # Whichever thread wins the race, the lock must fully serialise them:
    # one thread's (start, end) pair always completes before the other's
    # starts — never interleaved.
    assert order in (
        [("start", "a"), ("end", "a"), ("start", "b"), ("end", "b")],
        [("start", "b"), ("end", "b"), ("start", "a"), ("end", "a")],
    )
