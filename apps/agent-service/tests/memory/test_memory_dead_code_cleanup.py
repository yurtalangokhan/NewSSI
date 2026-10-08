"""Spec: memory/long_term.py must not export constants nothing reads.

MAX_FACTS, FACTS_KEY and MEMORY_NAMESPACE_PREFIX were defined here "for any
code that imports them directly", but nothing does -- the actual recall cap
lives in user-service's UserMemoryService.MAX_FACTS, and the cache module
(domain/user_memory/cache.py) keeps its own independent copies of the
namespace prefix and key. Two independent copies of the same constant is a
maintenance trap: changing one doesn't change the enforced behavior.
"""

import memory.long_term as lt


def test_unused_recall_cap_constant_is_removed():
    assert not hasattr(lt, "MAX_FACTS")


def test_unused_namespace_constants_are_removed():
    assert not hasattr(lt, "FACTS_KEY")
    assert not hasattr(lt, "MEMORY_NAMESPACE_PREFIX")


def test_store_parameter_is_dropped_from_recall_memories():
    import inspect

    sig = inspect.signature(lt.recall_memories)
    assert "store" not in sig.parameters
    assert list(sig.parameters)[0] == "user_id"


def test_store_parameter_is_dropped_from_save_memories():
    import inspect

    sig = inspect.signature(lt.save_memories)
    assert "store" not in sig.parameters
    assert list(sig.parameters)[0] == "user_id"


def test_store_parameter_is_dropped_from_extract_and_save_memories():
    import inspect

    sig = inspect.signature(lt.extract_and_save_memories)
    assert "store" not in sig.parameters
    assert list(sig.parameters)[0] == "user_id"
