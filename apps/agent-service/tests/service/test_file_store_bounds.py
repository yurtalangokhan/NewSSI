"""FileService._STORE was an unbounded dict: TTL only expired an entry on
the read path (get_file), so a file stored but never read again lingered
in memory until process restart. Spec T4/T6 bounds it as an LRU with item
and byte budgets."""

import pytest

from service.storage import file_service as FileService


@pytest.fixture(autouse=True)
def clear_store():
    FileService._STORE.clear()
    FileService._STORE_BYTES = 0
    yield
    FileService._STORE.clear()
    FileService._STORE_BYTES = 0


def test_store_evicts_oldest_when_item_limit_is_reached():
    for i in range(FileService.MAX_STORE_ITEMS + 10):
        FileService.store_file(f"f{i}", b"x" * 100, "text/plain", f"f{i}.txt")
    assert len(FileService._STORE) <= FileService.MAX_STORE_ITEMS


def test_store_evicts_when_byte_budget_is_exceeded():
    # Each file must stay under MAX_FILE_SIZE_BYTES (50 MB) on its own, but
    # several of them together must exceed MAX_STORE_BYTES (256 MB).
    payload = b"x" * (FileService.MAX_STORE_BYTES // 8)
    for i in range(10):
        FileService.store_file(f"f{i}", payload, "text/plain", f"f{i}.bin")
    assert FileService.store_stats()["bytes"] <= FileService.MAX_STORE_BYTES


def test_evicted_files_are_no_longer_retrievable():
    for i in range(FileService.MAX_STORE_ITEMS + 5):
        FileService.store_file(f"f{i}", b"x", "text/plain", f"f{i}.txt")
    # The very first file stored must have been evicted (oldest-first).
    assert FileService.get_file("f0") is None


def test_re_storing_the_same_file_id_accounts_for_the_size_change():
    FileService.store_file("f1", b"x" * 100, "text/plain", "f1.txt")
    FileService.store_file("f1", b"x" * 10, "text/plain", "f1.txt")
    assert FileService.store_stats()["bytes"] == 10


def test_store_stats_reports_items_and_bytes():
    FileService.store_file("f1", b"hello", "text/plain", "f1.txt")
    stats = FileService.store_stats()
    assert stats["items"] == 1
    assert stats["bytes"] == len(b"hello")
