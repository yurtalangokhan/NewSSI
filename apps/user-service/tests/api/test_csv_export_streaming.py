"""GET /users/download/csv built the entire CSV (up to 10,000 rows) as one
in-memory string before ever writing a response byte. Spec T4:
stream_users_csv yields rows batch by batch instead."""

from unittest.mock import AsyncMock

import pytest

from src.controller.user_controller import UserController


def _make_controller(users_by_batch: list[list[dict]]) -> UserController:
    """The real controller advances skip by however many rows the previous
    call actually returned, not by the fixed batch size it requested -- so
    this fake tracks "which call is this" directly rather than trying to
    recompute a batch index from skip/limit."""
    controller = UserController.__new__(UserController)
    controller.user_service = AsyncMock()
    total = sum(len(b) for b in users_by_batch)
    call_count = {"n": 0}

    async def fake_list_users(skip, limit, query=None, *_args, **_kwargs):
        index = call_count["n"]
        call_count["n"] += 1
        if index >= len(users_by_batch):
            return [], total, {}
        return users_by_batch[index], total, {}

    controller.user_service.list_users = AsyncMock(side_effect=fake_list_users)
    return controller


@pytest.mark.asyncio
async def test_stream_yields_a_header_row_first():
    from src.controller.user_controller import CSV_COLUMNS

    controller = _make_controller([[{"id": "1", "email": "a@example.com"}]])
    rows = [chunk async for chunk in controller.stream_users_csv(None)]
    assert rows[0].strip() == ",".join(CSV_COLUMNS)


@pytest.mark.asyncio
async def test_stream_yields_every_user_across_multiple_batches():
    batch1 = [{"id": str(i), "email": f"u{i}@example.com"} for i in range(3)]
    batch2 = [{"id": str(i), "email": f"u{i}@example.com"} for i in range(3, 5)]
    controller = _make_controller([batch1, batch2])

    output = "".join([chunk async for chunk in controller.stream_users_csv(None)])

    for i in range(5):
        assert f"u{i}@example.com" in output


@pytest.mark.asyncio
async def test_stream_requests_bounded_batches_not_one_giant_page():
    controller = _make_controller([[{"id": "1", "email": "a@example.com"}]])
    async for _ in controller.stream_users_csv(None):
        pass
    _skip, limit = controller.user_service.list_users.call_args_list[0].args[:2]
    assert limit <= 1000


@pytest.mark.asyncio
async def test_stream_with_no_users_yields_only_the_header():
    from src.controller.user_controller import CSV_COLUMNS

    controller = _make_controller([[]])
    rows = [chunk async for chunk in controller.stream_users_csv(None)]
    assert len(rows) == 1
    assert rows[0].strip() == ",".join(CSV_COLUMNS)
