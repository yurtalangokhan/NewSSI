"""Directory pagination must not hydrate identities outside the returned page."""

import asyncio
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from src.repository.user_repository import UserRepository


def profile(number, **updates):
    return {"id": str(uuid.UUID(int=number)), "username": f"user{number}", **updates}


def response(payload):
    return httpx.Response(200, json=payload, request=httpx.Request("GET", "https://kc.test/users"))


def repository(handler):
    kc = AsyncMock()
    kc._keycloak_request.side_effect = handler
    repo = UserRepository(kc)
    repo._roles = AsyncMock(return_value=["enduser"])
    repo._group_paths = AsyncMock(return_value=[])
    return repo, kc


async def test_native_page_and_count_only_hydrate_requested_users():
    async def handler(method, path, **kwargs):
        if path == "/users/count":
            assert kwargs["params"] == {"enabled": "true"}
            return response(100003)
        assert kwargs["params"] == {
            "enabled": "true",
            "first": 40,
            "max": 2,
            "briefRepresentation": "false",
        }
        return response([profile(41), profile(42)])

    repo, kc = repository(handler)
    users, total, _ = await repo.list_paginated(skip=40, limit=2, is_active=True)
    assert [str(user.id) for user in users] == [profile(41)["id"], profile(42)["id"]]
    assert total == 100003
    assert kc._keycloak_request.await_count == 2
    assert repo._roles.await_count == repo._group_paths.await_count == 2


@pytest.mark.parametrize("invitations", [0, 3, 1500])
async def test_non_invited_page_does_not_scan_large_directory(invitations):
    fetched = []

    async def handler(method, path, **kwargs):
        params = kwargs["params"]
        assert params["enabled"] == "true"
        if path == "/users/count":
            return response(invitations if params.get("q") else 100017)
        first, size = params["first"], params["max"]
        fetched.extend(range(first, first + size))
        assert len(fetched) <= 100 + invitations, "A small page must not read the directory"
        return response(
            [
                profile(i + 1, attributes={"agentic.invited": ["true"]})
                if i < invitations
                else profile(i + 1)
                for i in range(first, first + size)
            ]
        )

    repo, _ = repository(handler)
    users, total, _ = await repo.list_paginated(skip=80, limit=20, invited=False, is_active=True)
    assert total == 100017 - invitations
    assert [str(user.id) for user in users] == [
        profile(i + 1)["id"] for i in range(80 + invitations, 100 + invitations)
    ]
    assert repo._roles.await_count == repo._group_paths.await_count == 20


@pytest.mark.parametrize("skip,limit", [(100017, 20), (0, 0)])
async def test_non_invited_empty_page_only_reads_counts(skip, limit):
    async def handler(method, path, **kwargs):
        assert path == "/users/count"
        return response(3 if kwargs["params"].get("q") else 100017)

    repo, _ = repository(handler)
    assert await repo.list_paginated(skip=skip, limit=limit, invited=False) == ([], 100014, True)


async def test_external_exclusion_counts_missing_markers_without_hydrating_inventory():
    rows = [profile(i) for i in range(1, 2002)]
    rows[0]["attributes"] = {"agentic.is_external_keycloak_user": ["true"]}
    rows[1]["federatedIdentities"] = [{"identityProvider": "external"}]

    async def handler(method, path, **kwargs):
        assert path == "/users"
        params = kwargs["params"]
        assert params["max"] == 1000
        return response(rows[params["first"] : params["first"] + params["max"]])

    repo, kc = repository(handler)
    users, total, exact = await repo.list_paginated(
        skip=1, limit=2, include_external_keycloak_users=False
    )
    assert [str(user.id) for user in users] == [profile(4)["id"], profile(5)["id"]]
    # A filtered page is never counted: it reports what it read plus one probe
    # row, which is only a marker that a further page exists.
    assert (total, exact) == (4, False)
    # The window is filled from the first page; the realm behind it is not read.
    assert kc._keycloak_request.await_count == 1
    assert repo._roles.await_count == repo._group_paths.await_count == 2


@pytest.mark.parametrize(
    "path", ["/users", "/roles/enduser/users", "/clients/client/roles/role/users"]
)
async def test_user_pages_prefetch_eight_at_most_and_preserve_order_and_filters(path):
    inflight = maximum = 0
    offsets = []

    async def handler(method, actual_path, **kwargs):
        nonlocal inflight, maximum
        assert actual_path == path
        params = kwargs["params"]
        assert params["search"] == "*alex*" and params["enabled"] == "true"
        first = params["first"]
        offsets.append(first)
        inflight += 1
        maximum = max(maximum, inflight)
        try:
            await asyncio.sleep(0)
            return response([{"id": str(i)} for i in range(first, min(first + 1000, 10001))])
        finally:
            inflight -= 1

    repo, _ = repository(handler)
    rows = [row async for row in repo._pages(path, search="*alex*", enabled="true")]
    assert [row["id"] for row in rows] == [str(i) for i in range(10001)]
    assert maximum == 8 and inflight == 0
    assert offsets == list(range(0, 17000, 1000))


async def test_prefetched_user_page_failure_is_propagated_after_tasks_finish():
    inflight = 0

    async def handler(method, path, **kwargs):
        nonlocal inflight
        first = kwargs["params"]["first"]
        inflight += 1
        try:
            await asyncio.sleep(0)
            if first == 2000:
                raise RuntimeError("directory unavailable")
            return response([{"id": str(i)} for i in range(first, first + 1000)])
        finally:
            inflight -= 1

    repo, _ = repository(handler)
    with pytest.raises(RuntimeError, match="directory unavailable"):
        _ = [row async for row in repo._pages("/users")]
    assert inflight == 0


async def test_non_user_directory_pages_remain_sequential():
    offsets = []

    async def handler(method, path, **kwargs):
        first = kwargs["params"]["first"]
        offsets.append(first)
        return response([{"id": str(i)} for i in range(first, min(first + 1000, 1001))])

    repo, _ = repository(handler)
    assert len([row async for row in repo._pages("/roles")]) == 1001
    assert offsets == [0, 1000]


async def test_role_filter_pages_membership_instead_of_scanning_the_realm():
    """Membership is the one role view Keycloak paginates, so a filtered page
    reads the role rather than the directory, and never inverts every role."""
    members = [profile(number) for number in range(1, 26)]

    async def handler(method, path, **kwargs):
        assert path == "/roles/analyst/users", "The realm must not be scanned"
        assert kwargs["params"]["briefRepresentation"] == "true"
        first, size = kwargs["params"]["first"], kwargs["params"]["max"]
        return response(members[first : first + size])

    repo, _ = repository(handler)
    repo._role_index = AsyncMock()

    users, total, exact = await repo.list_paginated(skip=10, limit=5, roles=["analyst"])
    assert (total, exact) == (16, False)
    assert [str(user.id) for user in users] == [row["id"] for row in members[10:15]]
    repo._role_index.assert_not_awaited()


async def test_role_filter_counts_a_shared_member_once():
    shared = profile(1)
    membership = {"analyst": [shared, profile(2)], "reviewer": [shared, profile(3)]}

    async def handler(method, path, **kwargs):
        return response(membership[path.split("/")[2]] if kwargs["params"]["first"] == 0 else [])

    repo, _ = repository(handler)
    users, total, _ = await repo.list_paginated(roles=["analyst", "reviewer"])
    assert total == 3
    assert [str(user.id) for user in users] == [shared["id"], profile(2)["id"], profile(3)["id"]]


async def test_role_filter_excludes_invitations_without_reading_attributes():
    """Brief membership rows carry no attributes, so invitations are resolved
    with one native attribute query rather than by re-reading every member."""
    invited = profile(2)
    members = [profile(1), invited, profile(3)]

    async def handler(method, path, **kwargs):
        if path == "/users":
            assert kwargs["params"]["q"] == "agentic.invited:true"
            return response([invited] if kwargs["params"]["first"] == 0 else [])
        return response(members if kwargs["params"]["first"] == 0 else [])

    repo, _ = repository(handler)
    users, total, _ = await repo.list_paginated(roles=["analyst"], invited=False)
    assert total == 2
    assert [str(user.id) for user in users] == [profile(1)["id"], profile(3)["id"]]


async def test_native_search_narrows_the_read_but_never_sizes_the_page():
    """Keycloak answers /users/count from "search" alone, dropping both "q" and
    "enabled" (UsersResource#getUsersCount), so the invitation subtraction would
    cancel out to zero. A searched page counts the matches it walks instead."""

    async def handler(method, path, **kwargs):
        assert path == "/users", "a searched page cannot be sized by a native count"
        assert kwargs["params"]["search"] == "search-me"
        return response([profile(1, email="search-me@test")])

    repo, kc = repository(handler)
    users, total, _ = await repo.list_paginated(query="search-me", invited=False)
    assert total == len(users) == 1
    assert kc._keycloak_request.await_count == 1


async def test_multi_word_search_matches_a_name_split_across_two_fields():
    """ "First Last" lives in two fields, so no single field contains the query."""
    rows = [
        profile(1, firstName="Yusuf", lastName="Demir", email="y.demir@test"),
        profile(2, firstName="Yusuf", lastName="Kaya", email="y.kaya@test"),
    ]

    async def handler(method, path, **kwargs):
        # One native term still narrows the directory read; it cannot hide a match.
        assert kwargs["params"]["search"] == "Yusuf"
        return response(rows)

    repo, _ = repository(handler)
    users, total, _ = await repo.list_paginated(query="Yusuf Demir", invited=False)
    assert total == 1
    assert [str(user.id) for user in users] == [rows[0]["id"]]


async def test_turkish_search_narrows_the_read_with_a_native_filter():
    rows = [profile(1, firstName="Ali Burak", lastName="Pek\u0131\u015f\u0131k")]

    async def handler(method, path, **kwargs):
        assert kwargs["params"]["search"] == "Pek\u0131\u015f\u0131k"
        return response(rows)

    repo, _ = repository(handler)
    users, total, _ = await repo.list_paginated(query="Pek\u0131\u015f\u0131k", invited=False)
    assert total == 1 and str(users[0].id) == rows[0]["id"]


@pytest.mark.parametrize(
    ("term", "native"),
    [
        ("Pek\u0131\u015f\u0131k", "Pek\u0131\u015f\u0131k"),  # ı ş fold alike everywhere
        ("g\u00f6khan", "g\u00f6khan"),
        ("\u015fule", "\u015fule"),
        ("*k\u0131\u015f\u0131k*", "*k\u0131\u015f\u0131k*"),
        ('"G\u00f6khan"', '"G\u00f6khan"'),
        ("O'Brien", "O'Brien"),
        ("ali@test.com", "ali@test.com"),
        # PostgreSQL folds İ to "i" but Python and Java to "i̇": search around it.
        ("\u0130smail", "*smail*"),
        ("Stra\u00dfe", "Stra"),  # ß expands under casefold: keep the stable prefix
        ("\u0130", None),
    ],
)
def test_native_search_term_is_the_most_selective_fold_safe_filter(term, native):
    assert UserRepository._native_search_term(term) == native


def _pg_lower(value):
    """PostgreSQL lower() under en_US.utf8, as measured: İ becomes a single i."""
    return "".join("i" if char == "\u0130" else char.lower() for char in value)


def _keycloak_matches(search, value):
    """Keycloak's user search: Java-lowered term against PostgreSQL-lowered fields."""
    field = _pg_lower(value)
    if len(search) > 1 and search.startswith('"') and search.endswith('"'):
        return field == search[1:-1].lower()
    if len(search) > 1 and search.startswith("*") and search.endswith("*"):
        return search[1:-1].lower() in field
    return field.startswith(search.rstrip("*").lower())


NAMES = [
    "Pek\u0131\u015f\u0131k",
    "PEKI\u015eIK",
    "G\u00f6khan",
    "G\u00d6KHAN",
    "\u0130smail",
    "\u0130SMA\u0130L",
    "Ismail",
    "\u0131\u015f\u0131k",
    "I\u015eIK",
    "\u00c7a\u011fla",
    "\u00dczeyir",
    "\u015eahin",
    "STRASSE",
    "O'Brien",
    "Yi\u011fit",
    "\u00d6mer",
]


def test_stored_expanding_folds_are_the_one_native_search_limit():
    """A stored "Straße" folds to "strasse" in Python but stays "straße" in PostgreSQL.

    An ASCII "strasse" search therefore cannot reach it natively. That was already
    true before non-ASCII terms went native, and matches Keycloak's own console;
    closing it would give up the native filter for every ASCII search.
    """
    assert UserRepository._native_search_term("strasse") == "strasse"
    assert not _keycloak_matches("strasse", "Stra\u00dfe")
    assert _keycloak_matches(UserRepository._native_search_term("Stra\u00dfe"), "Stra\u00dfe")


def test_native_narrowing_never_hides_a_match_the_directory_would_show():
    queries = set()
    for name in NAMES:
        for end in range(1, len(name) + 1):
            queries.update({name[:end], name[:end].lower(), name[:end].upper()})
            queries.update({f"*{name[1:end]}*", f'"{name}"'})
    missed = []
    for query in sorted(queries):
        native = UserRepository._native_search_term(query)
        if native is None:
            continue
        predicate = UserRepository._term_predicate(query)
        for name in NAMES:
            if predicate(name.casefold()) and not _keycloak_matches(native, name):
                missed.append((query, native, name))
    assert missed == []


@pytest.mark.parametrize(
    "query,expected",
    [
        ("ali", ["ali.veli"]),  # prefix, the way the Keycloak console searches
        ("li", []),  # a prefix search does not match mid-word
        ("*li*", ["ali.veli", "veli.ahmet"]),  # infix is opted into, as in Keycloak
        ('"Ali"', ["ali.veli"]),  # quoted terms are exact
        ("veli ali", ["ali.veli"]),  # every word must match some field
    ],
)
async def test_search_terms_follow_keycloak_matching_rules(query, expected):
    rows = [
        profile(1, username="ali.veli", firstName="Ali", lastName="Veli", email="ali@test"),
        profile(2, username="veli.ahmet", firstName="Veli", lastName="Ahmet", email="veli@test"),
        profile(3, username="ahmet.can", firstName="Ahmet", lastName="Can", email="ahmet@test"),
    ]

    async def handler(method, path, **kwargs):
        return response(rows)

    repo, _ = repository(handler)
    users, total, _ = await repo.list_paginated(query=query, invited=False)
    assert [user.username for user in users] == expected
    assert total == len(expected)


async def test_zero_limit_fetches_count_without_profiles():
    repo, kc = repository(AsyncMock(return_value=response(100003)))
    users, total, _ = await repo.list_paginated(limit=0)
    assert users == [] and total == 100003
    assert kc._keycloak_request.call_args.args[1] == "/users/count"
    repo._roles.assert_not_awaited()


async def test_bulk_role_index_expands_composites_and_group_descendants():
    enduser = {"id": "end", "name": "enduser"}
    analyst = {"id": "analyst", "name": "analyst"}
    parent = {"id": "parent", "name": "reviewer", "composite": True}
    client_role = {
        "id": "client-role",
        "name": "feature",
        "clientRole": True,
        "containerId": "client",
        "composite": True,
    }
    routes = {
        "/roles": [enduser, analyst, parent],
        "/clients": [{"id": "client", "clientId": "agent-service"}],
        "/clients/client/roles": [client_role],
        "/roles-by-id/parent/composites": [analyst],
        "/roles-by-id/client-role/composites": [parent],
        "/roles/enduser/users": [profile(1)],
        "/roles/reviewer/users": [profile(2)],
        "/roles/analyst/groups": [{"id": "team"}],
        "/groups/team/members": [profile(3)],
        "/groups/team/children": [{"id": "child"}],
        "/groups/child/members": [profile(4)],
        "/clients/client/roles/feature/users": [profile(5)],
    }

    async def handler(method, path, **kwargs):
        return response(routes.get(path.split("?", 1)[0], []))

    repo, kc = repository(handler)
    index = await repo._role_index()
    assert index == {
        profile(1)["id"]: {"enduser"},
        profile(2)["id"]: {"reviewer", "analyst"},
        profile(3)["id"]: {"analyst"},
        profile(4)["id"]: {"analyst"},
        profile(5)["id"]: {"reviewer", "analyst"},
    }
    assert not any("/users/" in call.args[1] for call in kc._keycloak_request.call_args_list)


async def test_role_statistics_do_not_hydrate_users_or_memberships():
    rows = [profile(1), profile(2), profile(3)]
    repo, _ = repository(AsyncMock(return_value=response(rows)))
    repo._role_index = AsyncMock(
        return_value={
            rows[0]["id"]: {"enduser"},
            rows[1]["id"]: {"enduser", "analyst"},
            rows[2]["id"]: {"analyst"},
        }
    )
    assert await repo.count_by_role() == [
        {"role": "enduser", "count": 2},
        {"role": "analyst", "count": 1},
    ]
    repo._roles.assert_not_awaited()
    repo._group_paths.assert_not_awaited()


async def test_page_hydration_overlaps_requests_with_bounded_concurrency():
    import asyncio

    rows = [profile(i) for i in range(1, 21)]
    repo, _ = repository(AsyncMock())
    active = peak = 0

    async def hydrate(row, role_names=None):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return row["id"]

    repo._to_user = hydrate
    assert await repo._hydrate(rows) == [row["id"] for row in rows]
    assert 1 < peak <= 8


async def test_assignable_search_uses_bulk_scope_and_does_not_hydrate_users(monkeypatch):
    from src.repository.user_organization_repository import UserOrganizationRepository

    monkeypatch.setattr(
        UserOrganizationRepository,
        "get_user_organizations",
        AsyncMock(side_effect=AssertionError("Per-user membership scan")),
    )
    root, child, destination = [str(uuid.UUID(int=i)) for i in (100, 101, 102)]
    rows = [profile(i, email=f"alex{i}@example.com", firstName="Alex") for i in range(1, 5)]
    tree = [
        {
            "id": root,
            "name": "Root",
            "subGroupCount": 2,
            "subGroups": [
                {"id": child, "name": "Team", "subGroupCount": 0, "parentId": root},
                {"id": destination, "name": "Destination", "subGroupCount": 0, "parentId": root},
            ],
        }
    ]
    routes = {
        "/groups": tree + tree[0]["subGroups"],
        "/groups/count": {"count": 3},
        f"/groups/{root}/members": [rows[0]],
        f"/groups/{child}/members": [rows[0], rows[1], rows[2]],
        f"/groups/{destination}/members": [rows[1]],
        "/users": rows,
    }

    async def handler(method, path, **kwargs):
        assert not path.startswith("/users/")
        return response(routes.get(path.split("?", 1)[0], []))

    repo, kc = repository(handler)
    users, total = await repo.list_assignable(
        uuid.UUID(destination), root_ids=[uuid.UUID(root)], query="alex", limit=1
    )
    assert total == 2 and users[0]["id"] == uuid.UUID(rows[0]["id"])
    repo._roles.assert_not_awaited()
    repo._group_paths.assert_not_awaited()
    child_reads = [
        call.args[1].split("?", 1)[0]
        for call in kc._keycloak_request.call_args_list
        if "/children" in call.args[1]
    ]
    assert child_reads == []


async def test_searched_role_filter_reads_the_native_search_not_role_membership():
    """A term plus a role must not walk the role: /roles/{name}/users takes no
    search, so the realm side is the only one that can be narrowed."""
    matches = [profile(7, username="yusuf.demir"), profile(9, username="yusufcan")]

    async def handler(method, path, **kwargs):
        assert path == "/users", "Role membership must not be paged for a searched filter"
        assert kwargs["params"]["search"] == "yusuf", "The term must narrow the directory read"
        return response(matches)

    repo, kc = repository(handler)
    repo._roles = AsyncMock(side_effect=lambda user_id: ["enduser"])
    repo._role_index = AsyncMock(side_effect=AssertionError("index must not be built"))

    users, total, exact = await repo.list_paginated(query="yusuf", roles=["enduser"])

    assert [user.username for user in users] == ["yusuf.demir", "yusufcan"]
    assert (total, exact) == (2, False)
    # One directory read, then one effective-role read per candidate.
    assert kc._keycloak_request.await_count == 1
    assert repo._roles.await_count == 2


async def test_searched_role_filter_keeps_only_members_of_the_selected_roles():
    rows = [profile(number, username=f"yusuf{number}") for number in range(1, 5)]
    memberships = {
        rows[0]["id"]: ["enduser"],
        rows[1]["id"]: ["system-admin"],
        rows[2]["id"]: ["enduser", "system-admin"],
        rows[3]["id"]: [],
    }

    repo, _ = repository(AsyncMock(return_value=response(rows)))
    repo._roles = AsyncMock(side_effect=lambda user_id: memberships[str(user_id)])
    repo._role_index = AsyncMock(side_effect=AssertionError("index must not be built"))

    users, _, _ = await repo.list_paginated(query="yusuf", roles=["enduser"])

    assert [user.username for user in users] == ["yusuf1", "yusuf3"]


async def test_searched_role_filter_falls_back_to_the_index_past_the_lookup_budget():
    """Per-candidate reads win while candidates are few; a broad term tips the
    balance back to the one shared index build."""
    rows = [profile(number, username=f"yusuf{number}") for number in range(1, 61)]
    index = {row["id"]: {"enduser"} for row in rows[::2]}

    repo, _ = repository(AsyncMock(return_value=response(rows)))
    repo._roles = AsyncMock(return_value=["enduser"])
    repo._role_index = AsyncMock(return_value=index)

    users, _, _ = await repo.list_paginated(skip=0, limit=60, query="yusuf", roles=["enduser"])

    # Candidates are resolved in batches, so the switch lands on a batch edge
    # at or below the budget -- never past it.
    switched = repo._roles.await_count
    assert 0 < switched <= UserRepository.ROLE_LOOKUP_BUDGET
    repo._role_index.assert_awaited_once()
    # Everything up to the switch was resolved individually (all members here);
    # past it the index decides, and it holds only every other row.
    expected = [f"yusuf{number}" for number in range(1, switched + 1)]
    expected += [f"yusuf{number}" for number in range(switched + 1, 61) if number % 2]
    assert [user.username for user in users] == expected


async def test_searched_role_filter_stops_at_the_window():
    """A page must not read the whole match set, only far enough to fill itself."""
    rows = [profile(number, username=f"yusuf{number}") for number in range(1, 2002)]
    resolved = []

    async def handler(method, path, **kwargs):
        params = kwargs["params"]
        return response(rows[params["first"] : params["first"] + params["max"]])

    repo, _ = repository(handler)

    async def roles(user_id):
        resolved.append(str(user_id))
        return ["enduser"]

    repo._roles = roles
    repo._role_index = AsyncMock(side_effect=AssertionError("index must not be built"))

    users, total, exact = await repo.list_paginated(
        skip=2, limit=3, query="yusuf", roles=["enduser"]
    )

    assert [user.username for user in users] == ["yusuf3", "yusuf4", "yusuf5"]
    assert (total, exact) == (6, False)
    assert len(resolved) <= 8, "Membership must not be resolved beyond the window"


async def test_unsearched_role_filter_still_pages_membership():
    """The fast single-read path must survive: no term means no realm scan."""

    async def handler(method, path, **kwargs):
        assert path == "/roles/enduser/users"
        first, size = kwargs["params"]["first"], kwargs["params"]["max"]
        return response([profile(number) for number in range(1, 26)][first : first + size])

    repo, kc = repository(handler)
    repo._role_index = AsyncMock(side_effect=AssertionError("index must not be built"))

    users, _, _ = await repo.list_paginated(skip=0, limit=5, roles=["enduser"])

    assert len(users) == 5
    assert kc._keycloak_request.await_count == 1


@pytest.mark.parametrize("target", ["analyst", "missing"])
async def test_filtered_role_index_skips_unrelated_memberships(target):
    enduser = {"id": "end", "name": "enduser"}
    analyst = {"id": "analyst", "name": "analyst"}
    parent = {"id": "parent", "name": "reviewer", "composite": True}
    client_role = {
        "id": "client-role",
        "name": "feature",
        "clientRole": True,
        "containerId": "client",
        "composite": True,
    }
    routes = {
        "/roles": [enduser, analyst, parent],
        "/clients": [{"id": "client", "clientId": "agent-service"}],
        "/clients/client/roles": [client_role],
        "/roles-by-id/parent/composites": [analyst],
        "/roles-by-id/client-role/composites": [parent],
        "/roles/enduser/users": [profile(1)],
        "/roles/reviewer/users": [profile(2)],
        "/roles/analyst/users": [profile(6), profile(3)],
        "/roles/analyst/groups": [{"id": "team"}],
        "/groups/team/members": [profile(3)],
        "/groups/team/children": [{"id": "child"}],
        "/groups/child/members": [profile(4)],
        "/clients/client/roles/feature/users": [profile(5)],
    }

    async def handler(method, path, **kwargs):
        assert path not in {"/roles/enduser/users", "/roles/enduser/groups"}
        return response(routes.get(path.split("?", 1)[0], []))

    repo, kc = repository(handler)
    index = await repo._build_role_index(role_name=target)
    expected = {
        profile(2)["id"]: {"analyst"},
        profile(3)["id"]: {"analyst"},
        profile(4)["id"]: {"analyst"},
        profile(5)["id"]: {"analyst"},
        profile(6)["id"]: {"analyst"},
    }
    assert index == (expected if target == "analyst" else {})
    assert not any("/users/" in call.args[1] for call in kc._keycloak_request.call_args_list)
