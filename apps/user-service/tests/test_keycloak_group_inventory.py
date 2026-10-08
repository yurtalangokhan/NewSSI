"""Flat group inventory is complete, bounded, and ordered by ancestry."""

from urllib.parse import parse_qs, urlsplit

import httpx
from error_contract import DependencyResponseError
import pytest

from src.repository.keycloak_group_inventory import read_group_inventory


class FlatAdmin:
    def __init__(self, groups, count=None):
        self.groups = groups
        self.count = len(groups) if count is None else count
        self.calls = []

    async def _keycloak_request(self, method, path):
        self.calls.append(path)
        parsed = urlsplit(path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if parsed.path == "/groups/count":
            assert query == {"top": ["false"]}
            data = {"count": self.count}
        else:
            assert parsed.path == "/groups"
            assert query["search"] == [""]
            assert query["populateHierarchy"] == ["false"]
            assert query["briefRepresentation"] == ["false"]
            first, maximum = int(query["first"][0]), int(query["max"][0])
            data = self.groups[first : first + maximum]
        return httpx.Response(200, json=data, request=httpx.Request(method, "https://kc" + path))


@pytest.mark.asyncio
async def test_ten_thousand_flat_groups_need_eleven_pages_and_one_count():
    rows = [
        {
            "id": str(i),
            "name": str(i),
            "parentId": "root",
            "subGroupCount": 0,
            "attributes": {"kept": [str(i)]},
        }
        for i in range(10050)
    ]
    rows.append({"id": "root", "name": "Root", "subGroupCount": 10050})
    admin = FlatAdmin(rows)
    groups = await read_group_inventory(admin)
    assert len(admin.calls) == 12
    assert len(groups) == 10051 and next(iter(groups)) == "root"
    assert groups["0"]["path"] == "/Root/0"
    assert groups["0"]["attributes"] == {"kept": ["0"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rows,count",
    [
        ([{"id": "root", "name": "Root"}], 2),
        ([{"id": "child", "name": "Child", "parentId": "missing"}], 1),
        ([{"id": "a", "name": "A", "parentId": "b"}, {"id": "b", "name": "B", "parentId": "a"}], 2),
        ([{"id": "root", "name": "Root", "subGroupCount": 1}], 1),
        ([{"id": "same", "name": "A"}, {"id": "same", "name": "B"}], 2),
    ],
)
async def test_incomplete_or_invalid_flat_hierarchy_fails_closed(rows, count):
    with pytest.raises(DependencyResponseError):
        await read_group_inventory(FlatAdmin(rows, count))


@pytest.mark.asyncio
async def test_older_group_representations_can_resolve_parent_from_path():
    groups = await read_group_inventory(
        FlatAdmin(
            [
                {"id": "child", "name": "Child", "path": "/Root/Child"},
                {"id": "root", "name": "Root", "path": "/Root"},
            ]
        )
    )
    assert list(groups) == ["root", "child"]
    assert groups["child"]["parentId"] == "root"
