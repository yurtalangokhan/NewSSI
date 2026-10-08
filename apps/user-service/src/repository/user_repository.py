import asyncio
from collections import Counter
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
import inspect
import json
import time
from typing import Any
import unicodedata
from urllib.parse import quote
import uuid

from error_contract import DependencyResponseError, raise_for_httpx_response
import httpx

from src.core.permissions.roles import display_role_name


def _scoped_directory_reads(method):
    """Opt into pooling when the injected admin client explicitly supports it."""

    @wraps(method)
    async def scoped(self, *args, **kwargs):
        scope = getattr(type(self.keycloak), "admin_request_scope", None)
        if scope is None:
            return await method(self, *args, **kwargs)
        from src.service.keycloak_service import DIRECTORY_TIMEOUT

        try:
            pooled = scope(self.keycloak, DIRECTORY_TIMEOUT)
        except TypeError:  # a scope that predates the timeout argument
            pooled = scope(self.keycloak)
        async with pooled:
            return await method(self, *args, **kwargs)

    return scoped


# Keycloak search operators: "*" for infix, '"' for exact, and a backslash may escape.
_SEARCH_OPERATORS = frozenset('*"\\')


@dataclass
class KeycloakUser:
    id: uuid.UUID
    keycloak_id: str
    email: str = ""
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_active: bool = True
    is_verified: bool = False
    role: str = ""
    groups: list[str] = field(default_factory=list)
    invited: bool = False
    password_configured: bool = False
    is_external_keycloak_user: bool = False
    team_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserRepository:
    """Identity facade backed exclusively by the Keycloak Admin API."""

    # Building the role index walks every role, client role, composite, role
    # membership and group membership in the realm. That is far too expensive to
    # repeat per request, and on a large directory it starves interactive calls
    # of Keycloak capacity. Hold it briefly and rebuild once, not per caller.
    ROLE_INDEX_TTL = 600.0
    # A searched role filter resolves membership per candidate rather than by
    # inverting the realm. That is the cheaper side only while the candidates
    # stay few, so past this many the cached index is built and used instead.
    ROLE_LOOKUP_BUDGET = 50
    _role_index_cache: tuple[float, object, dict] | None = None
    _role_index_lock: asyncio.Lock | None = None

    @classmethod
    def invalidate_role_index(cls) -> None:
        """Drop the cached index after anything that changes role membership."""
        UserRepository._role_index_cache = None

    def _directory_identity(self):
        """Realm and runtime generation, so a repointed Keycloak never reads stale."""
        try:
            realm = self.keycloak.get_realm()
        except Exception:
            realm = None
        if not isinstance(realm, str):
            # A test double may hand back an awaitable; close it rather than leak it.
            close = getattr(realm, "close", None)
            if inspect.isawaitable(realm) and callable(close):
                close()
            realm = None
        generation = getattr(type(self.keycloak), "_runtime_generation", None)
        return (realm, generation if isinstance(generation, int) else None)

    def __init__(self, keycloak=None):
        if keycloak is None:
            from src.service.keycloak_service import get_keycloak_service

            keycloak = get_keycloak_service()
        self.keycloak = keycloak

    async def _profile(self, user_id):
        response = await self.keycloak._keycloak_request("GET", f"/users/{quote(str(user_id), safe='')}")
        if response.status_code == 404:
            return None
        raise_for_httpx_response(response)
        return response.json()

    async def _roles(self, user_id):
        response = await self.keycloak._keycloak_request("GET", f"/users/{user_id}/role-mappings/realm/composite")
        raise_for_httpx_response(response)
        return [
            r["name"]
            for r in response.json()
            if r["name"] not in {"offline_access", "uma_authorization", "agentic-permission-catalog"}
            and not r["name"].startswith("default-roles-")
        ]

    async def _group_paths(self, user_id):
        groups = []
        first = 0
        while True:
            response = await self.keycloak._keycloak_request(
                "GET", f"/users/{user_id}/groups", params={"first": first, "max": 100}
            )
            raise_for_httpx_response(response)
            page = response.json()
            groups.extend(group["path"] for group in page if group.get("path"))
            if len(page) < 100:
                return groups
            first += len(page)

    async def _to_user(self, profile, role_names=None):
        attrs = profile.get("attributes") or {}

        def attr(name, default=None):
            values = attrs.get(f"agentic.{name}") or []
            return values[0] if values else default

        roles = await self._roles(profile["id"]) if role_names is None else role_names
        from .keycloak_role_client import primary_role_name

        primary = primary_role_name(roles, attr("primary_role"))
        created = profile.get("createdTimestamp")
        return KeycloakUser(
            id=uuid.UUID(profile["id"]),
            keycloak_id=profile["id"],
            email=profile.get("email") or "",
            username=profile.get("username"),
            first_name=profile.get("firstName"),
            last_name=profile.get("lastName"),
            is_active=profile.get("enabled", True),
            is_verified=profile.get("emailVerified", False),
            role=primary,
            groups=await self._group_paths(profile["id"]),
            invited=attr("invited", "false") == "true",
            password_configured=attr("password_configured", "false") == "true",
            is_external_keycloak_user=bool(profile.get("federatedIdentities"))
            or attr("is_external_keycloak_user", "false") == "true",
            team_name=attr("team_name"),
            created_at=datetime.fromtimestamp(created / 1000, UTC) if created else None,
        )

    @_scoped_directory_reads
    async def get_by_id(self, user_id):
        profile = await self._profile(user_id)
        return await self._to_user(profile) if profile else None

    @_scoped_directory_reads
    async def get_by_ids(self, user_ids):
        result = []
        for user_id in dict.fromkeys(user_ids):
            user = await self.get_by_id(user_id)
            if user:
                result.append(user)
        return result

    @_scoped_directory_reads
    async def _find(self, field, value):
        response = await self.keycloak._keycloak_request("GET", "/users", params={field: value, "exact": "true"})
        raise_for_httpx_response(response)
        matches = [row for row in response.json() if str(row.get(field, "")).lower() == value.lower()]
        return await self._to_user(matches[0]) if matches else None

    async def get_by_email(self, email):
        return await self._find("email", email)

    async def _pages(self, path, *, brief=False, retries=2, **filters):
        """Stream bounded admin pages without hydrating individual identities.

        ``brief`` asks Keycloak to leave out attributes and credentials, which is
        the bulk of a user representation. Use it wherever only identifiers are
        read: it is the difference between a page that returns and one that
        times out on a large directory.
        """

        async def fetch(first):
            params = {
                **filters,
                "first": first,
                "max": 1000,
                "briefRepresentation": "true" if brief else "false",
            }
            for attempt in range(retries + 1):
                try:
                    response = await self.keycloak._keycloak_request("GET", path, params=params)
                    raise_for_httpx_response(response)
                    break
                except (httpx.TimeoutException, httpx.TransportError):
                    # One slow page should not discard the whole walk.
                    if attempt == retries:
                        raise
                    await asyncio.sleep(0.5 * 2**attempt)
            page = response.json()
            if not isinstance(page, list):
                raise DependencyResponseError()
            return page

        pages = [await fetch(0)]
        first = 1000
        concurrency = 8 if path.endswith("/users") else 1
        while True:
            for page in pages:
                for row in page:
                    yield row
                if len(page) < 1000:
                    return
            # Release the preceding batch before allocating the next eight pages.
            pages = None
            page = None
            results = await asyncio.gather(
                *(fetch(offset) for offset in range(first, first + concurrency * 1000, 1000)),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            pages = results
            results = None
            result = None
            first += concurrency * 1000

    async def _hydrate(self, profiles, role_index=None):
        semaphore = asyncio.Semaphore(8)

        async def hydrate(profile):
            async with semaphore:
                roles = None if role_index is None else role_index.get(profile["id"], set())
                return await self._to_user(profile, roles)

        return list(await asyncio.gather(*(hydrate(profile) for profile in profiles)))

    @_scoped_directory_reads
    async def get_all(self):
        return [await self._to_user(row) async for row in self._pages("/users")]

    @staticmethod
    def _attribute(profile, name, default=None):
        values = (profile.get("attributes") or {}).get(f"agentic.{name}") or []
        return values[0] if values else default

    @classmethod
    def _primary(cls, profile, role_index):
        from .keycloak_role_client import primary_role_name

        return primary_role_name(role_index.get(profile["id"], set()), cls._attribute(profile, "primary_role"))

    async def _role_index(self, *, refresh=False):
        """Cached view of :meth:`_build_role_index`, rebuilt at most once at a time."""
        identity = self._directory_identity()

        def fresh():
            cached = UserRepository._role_index_cache
            if refresh or cached is None or cached[1] != identity:
                return None
            return cached if (time.monotonic() - cached[0]) < UserRepository.ROLE_INDEX_TTL else None

        hit = fresh()
        if hit is not None:
            return hit[2]

        lock = UserRepository._role_index_lock
        if lock is None:
            lock = UserRepository._role_index_lock = asyncio.Lock()
        async with lock:
            # A concurrent caller may have rebuilt it while we waited for the lock.
            hit = fresh()
            if hit is not None:
                return hit[2]
            index = await self._build_role_index()
            UserRepository._role_index_cache = (time.monotonic(), identity, index)
            return index

    async def _role_graph(self):
        """Every realm and client role keyed by ID, with its composite children's IDs."""
        from .keycloak_role_client import segment

        definitions = {role["id"]: role async for role in self._pages("/roles")}
        async for client in self._pages("/clients"):
            async for role in self._pages(f"/clients/{segment(client['id'])}/roles"):
                definitions[role["id"]] = {**role, "clientRole": True, "containerId": client["id"]}
        edges = {}
        pending = list(definitions.values())
        while pending:
            role = pending.pop()
            if role["id"] in edges:
                continue
            children = []
            if role.get("composite"):
                children = [child async for child in self._pages(f"/roles-by-id/{segment(role['id'])}/composites")]
            edges[role["id"]] = [child["id"] for child in children]
            for child in children:
                definitions.setdefault(child["id"], child)
                pending.append(child)
        return definitions, edges

    @staticmethod
    def _role_source(role):
        from .keycloak_role_client import segment

        if role.get("clientRole"):
            return f"/clients/{segment(role['containerId'])}/roles/{segment(role['name'])}"
        return f"/roles/{segment(role['name'])}"

    async def effective_role_holders(self, role_name):
        """IDs of users holding one realm role directly, via composites, or via groups.

        Only the roles whose composite closure contains the target are read, so a
        rarely held role costs a handful of requests instead of a directory scan.
        """
        from .keycloak_role_client import segment

        definitions, edges = await self._role_graph()
        target = next(
            (
                role_id
                for role_id, role in definitions.items()
                if not role.get("clientRole") and role["name"] == role_name
            ),
            None,
        )
        if target is None:
            return set()
        parents = {}
        for parent, children in edges.items():
            for child in children:
                parents.setdefault(child, set()).add(parent)
        ancestors, stack = set(), [target]
        while stack:
            role_id = stack.pop()
            if role_id not in ancestors:
                ancestors.add(role_id)
                stack.extend(parents.get(role_id, ()))

        holders, groups = set(), set()
        for role_id in ancestors:
            source = self._role_source(definitions[role_id])
            holders.update([user["id"] async for user in self._pages(f"{source}/users", brief=True)])
            groups.update([group["id"] async for group in self._pages(f"{source}/groups")])
        # Subgroups inherit their parent's role mappings.
        pending = list(groups)
        while pending:
            group_id = pending.pop()
            async for child in self._pages(f"/groups/{segment(group_id)}/children"):
                if child["id"] not in groups:
                    groups.add(child["id"])
                    pending.append(child["id"])
        for group_id in groups:
            holders.update(
                [user["id"] async for user in self._pages(f"/groups/{segment(group_id)}/members", brief=True)]
            )
        return holders

    async def _build_role_index(self, *, role_name: str | None = None):
        """Bulk effective realm assignments, including client composites and groups.

        Invert role membership endpoints rather than issuing one effective-role
        request for every user. A role filter skips unrelated memberships while
        retaining every path through realm/client composites and descendant groups.
        """
        from .keycloak_role_client import manageable, segment

        definitions, edges = await self._role_graph()

        index: dict[str, set[str]] = {}
        group_roles: dict[str, set[str]] = {}
        for role in definitions.values():
            reachable, stack, names = set(), [role["id"]], set()
            while stack:
                role_id = stack.pop()
                if role_id in reachable:
                    continue
                reachable.add(role_id)
                current = definitions[role_id]
                if not current.get("clientRole") and manageable(current["name"]):
                    names.add(current["name"])
                stack.extend(edges.get(role_id, []))
            if role_name is not None:
                names.intersection_update({role_name})
            if not names:
                continue
            source = self._role_source(role)
            async for user in self._pages(f"{source}/users", brief=True):
                index.setdefault(user["id"], set()).update(names)
            async for group in self._pages(f"{source}/groups"):
                group_roles.setdefault(group["id"], set()).update(names)

        pending = list(group_roles)
        children_by_group = {}
        while pending:
            group_id = pending.pop()
            if group_id not in children_by_group:
                children_by_group[group_id] = [
                    group["id"] async for group in self._pages(f"/groups/{segment(group_id)}/children")
                ]
            for child_id in children_by_group[group_id]:
                inherited = group_roles[group_id] - group_roles.get(child_id, set())
                if inherited:
                    group_roles.setdefault(child_id, set()).update(inherited)
                    pending.append(child_id)
        for group_id, names in group_roles.items():
            async for user in self._pages(f"/groups/{segment(group_id)}/members", brief=True):
                index.setdefault(user["id"], set()).update(names)
        return index

    async def _count_profiles(self, filters):
        response = await self.keycloak._keycloak_request("GET", "/users/count", params=filters)
        raise_for_httpx_response(response)
        count = response.json()
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise DependencyResponseError()
        return count

    async def _non_invited_page(self, filters, skip, limit):
        total, invited = await asyncio.gather(
            self._count_profiles(filters),
            self._count_profiles({**filters, "q": "agentic.invited:true"}),
        )
        if invited > total:
            raise DependencyResponseError()
        total -= invited
        if not limit or skip >= total:
            return [], total

        # Missing invitation attributes also mean false. With no invitations,
        # native offsets are exact. Otherwise count exclusions only in the
        # prefix needed for this page, not throughout the entire directory.
        first, visible = (skip, skip) if invited == 0 else (0, 0)
        selected = []
        while len(selected) < limit:
            size = min(1000, skip + limit - visible + invited)
            response = await self.keycloak._keycloak_request(
                "GET",
                "/users",
                params={**filters, "first": first, "max": size, "briefRepresentation": "false"},
            )
            raise_for_httpx_response(response)
            rows = response.json()
            for profile in rows:
                if self._attribute(profile, "invited") == "true":
                    invited = max(0, invited - 1)
                    continue
                if visible >= skip:
                    selected.append(profile)
                    if len(selected) == limit:
                        break
                visible += 1
            if len(rows) < size:
                break
            first += len(rows)
        return await self._hydrate(selected), total

    _SEARCHABLE_FIELDS = ("email", "username", "firstName", "lastName")

    @staticmethod
    def _search_terms(query):
        """Split a search box entry into the words that must all match."""
        return (query or "").split()

    @staticmethod
    def _term_predicate(term):
        """Match one word the way Keycloak's own user search matches it.

        Its admin console and REST API are prefix-based by default; ``*word*``
        asks for an infix match and ``"word"`` for an exact one. Mirroring that
        keeps this fallback and the directory's native filter interchangeable,
        and keeps a one-letter query cheap instead of matching the whole realm.
        """
        word = term.casefold()
        if len(word) > 1 and word.startswith('"') and word.endswith('"'):
            exact = word[1:-1]
            return lambda value: value == exact
        if len(word) > 1 and word.startswith("*") and word.endswith("*"):
            infix = word[1:-1]
            return lambda value: infix in value
        prefix = word[:-1] if word.endswith("*") else word
        return lambda value: value.startswith(prefix)

    @staticmethod
    def _fold_stable(char):
        """Whether Keycloak and Python fold this character to the same single character.

        Keycloak lowers the query in Java and the stored fields in PostgreSQL. Those
        agree with ``str.casefold`` for ASCII and letters such as ``ş ı ö ü ç ğ``,
        but not for ``İ`` (PostgreSQL gives ``i``, Python ``i̇``) or expanding folds
        such as ``ß``; a native search containing those could hide a real match.
        """
        folded = char.casefold()
        return (
            char not in _SEARCH_OPERATORS
            and not char.isspace()
            and not unicodedata.combining(char)
            and len(folded) == 1
            and folded == char.lower()
        )

    @classmethod
    def _native_search_term(cls, term):
        """A Keycloak ``search`` value matching a superset of ``_term_predicate(term)``.

        The native search only narrows the read; ``_matches_terms`` decides. A term
        that folds identically everywhere is sent as typed. Otherwise its longest
        fold-stable run is sent, as a prefix when it starts a prefix search and as
        an infix otherwise. ``None`` means the term can only be matched in process.
        """
        if len(term) > 1 and term[0] == term[-1] and term[0] in '"*':
            word, prefix = term[1:-1], False
        else:
            word, prefix = (term[:-1] if term.endswith("*") else term), True
        if word and all(cls._fold_stable(char) for char in word):
            return term
        best, best_start, start = "", 0, None
        for index, char in enumerate([*word, None]):
            if char is not None and cls._fold_stable(char):
                start = index if start is None else start
                continue
            if start is not None and index - start > len(best):
                best, best_start = word[start:index], start
            start = None
        if not best:
            return None
        return best if prefix and best_start == 0 else f"*{best}*"

    @classmethod
    def _native_search(cls, terms):
        """The most selective native filter among the terms, which all must match."""
        natives = [native for native in map(cls._native_search_term, terms) if native]
        if not natives:
            return None
        return max(natives, key=lambda native: (len(native.strip('*"')), native[0] != "*"))

    @classmethod
    def _matches_terms(cls, profile, terms):
        """Every word must match a searchable field, not all of them one field."""
        values = [(profile.get(field) or "").casefold() for field in cls._SEARCHABLE_FIELDS]
        return all(any(matches(value) for value in values) for matches in map(cls._term_predicate, terms))

    def _passes(self, profile, terms, is_active, invited, include_external_keycloak_users):
        """Every filter that a profile answers on its own, without its roles."""
        if terms and not self._matches_terms(profile, terms):
            return False
        if is_active is not None and profile.get("enabled", True) != is_active:
            return False
        if invited is not None and (self._attribute(profile, "invited") == "true") != invited:
            return False
        return not (
            not include_external_keycloak_users
            and (profile.get("federatedIdentities") or self._attribute(profile, "is_external_keycloak_user") == "true")
        )

    @staticmethod
    async def _take_window(profiles, skip, limit, keep):
        """Fill one page from a stream, reading no further than it has to.

        Without a total to compute there is nothing to read past the window:
        one extra surviving row is enough to know another page exists, which
        is what the directory's own console settles for.
        """
        window, position, more = [], 0, False
        async with aclosing(profiles) as rows:
            async for profile in rows:
                if not keep(profile):
                    continue
                if position >= skip + limit:
                    more = True
                    break
                if position >= skip:
                    window.append(profile)
                position += 1
        return window, position, more

    async def _invited_ids(self):
        """Invitations, resolved natively so membership reads can stay brief."""
        return {profile["id"] async for profile in self._pages("/users", brief=True, q="agentic.invited:true")}

    @staticmethod
    async def _passing(profiles, predicate):
        """Drop the rows a profile answers on its own, before anything is read for it."""
        async with aclosing(profiles) as rows:
            async for profile in rows:
                if predicate(profile):
                    yield profile

    async def _holding_roles(self, profiles, wanted, into=None):
        """Yield the candidates that hold one of ``wanted``.

        Membership is resolved per candidate while they are few, which is the
        whole point of arriving here: a searched page has already been narrowed
        by the directory, so a handful of effective-role reads beats inverting
        every role in the realm. Past ``ROLE_LOOKUP_BUDGET`` the balance tips
        and the cached index -- one expensive build, shared by every caller --
        is used for the remainder.
        """
        index = None
        spent = 0
        chunk = []

        async def memberships(rows):
            nonlocal index, spent
            if index is None and spent + len(rows) <= self.ROLE_LOOKUP_BUDGET:
                spent += len(rows)
                reads = await asyncio.gather(*(self._roles(row["id"]) for row in rows))
                return [set(names) for names in reads]
            if index is None:
                index = await self._role_index()
            return [index.get(row["id"], set()) for row in rows]

        async def drain(rows):
            for row, names in zip(rows, await memberships(rows), strict=True):
                if names & wanted:
                    # Hand the caller what was just read, so hydrating the page
                    # does not ask the directory for it a second time.
                    if into is not None:
                        into[row["id"]] = names
                    yield row

        async with aclosing(profiles) as candidates:
            async for profile in candidates:
                chunk.append(profile)
                if len(chunk) < 8:
                    continue
                async for row in drain(chunk):
                    yield row
                chunk = []
        if chunk:
            async for row in drain(chunk):
                yield row

    async def _role_member_page(self, names, skip, limit, terms, is_active, invited, include_external_keycloak_users):
        """Page a role's membership, the way Keycloak's own role tab lists it.

        Membership is the only role view the directory paginates, so a filtered
        page is read from the selected roles rather than by scanning the realm
        and inverting every role in it. Brief rows carry everything the other
        filters need except the invitation and external-identity markers; the
        first is resolved with one native query, and only the second -- which is
        off by default -- has to fall back to full representations.
        """
        from .keycloak_role_client import segment

        brief = include_external_keycloak_users
        invitations = await self._invited_ids() if brief and invited is not None else set()
        seen = set()

        def keep(profile):
            if profile["id"] in seen:  # a member of two selected roles is one row
                return False
            seen.add(profile["id"])
            if not brief:
                return self._passes(profile, terms, is_active, invited, include_external_keycloak_users)
            if invited is not None and (profile["id"] in invitations) != invited:
                return False
            if terms and not self._matches_terms(profile, terms):
                return False
            return is_active is None or profile.get("enabled", True) == is_active

        # With nothing dropped in process, the directory's own offsets are the
        # page's offsets, so any page is a single read of its own window.
        if (
            len(names) == 1
            and brief
            and not terms
            and is_active is None
            and (invited is None or (invited is False and not invitations))
        ):
            response = await self.keycloak._keycloak_request(
                "GET",
                f"/roles/{segment(names[0])}/users",
                params={"first": skip, "max": limit + 1, "briefRepresentation": "true"},
            )
            raise_for_httpx_response(response)
            rows = response.json()
            window, more = rows[:limit], len(rows) > limit
            return await self._hydrate(window), skip + len(window) + (1 if more else 0), False

        async def members():
            for name in names:
                async with aclosing(self._pages(f"/roles/{segment(name)}/users", brief=brief)) as rows:
                    async for profile in rows:
                        yield profile

        window, position, more = await self._take_window(members(), skip, limit, keep)
        return await self._hydrate(window), position + (1 if more else 0), False

    @_scoped_directory_reads
    async def list_paginated(
        self,
        skip=0,
        limit=20,
        query=None,
        role=None,
        roles=None,
        is_active=None,
        invited=None,
        include_external_keycloak_users=True,
    ):
        """Use native directory order and hydrate only the selected page.

        Returns the page, a total, and whether that total is exact. Only the
        reads the directory can count natively carry an exact one; a filtered
        page reports how far it read plus a probe row, which is what tells the
        caller another page exists without counting the rest of the realm.
        """
        skip, limit = max(0, skip), max(0, limit)
        filters = {}
        if is_active is not None:
            filters["enabled"] = str(is_active).lower()
        # A multi-word query ("first last") spans two profile fields, so it can
        # only be resolved by matching each word separately; the directory's own
        # search cannot be trusted to fold non-ASCII case the way Python does.
        terms = self._search_terms(query)
        native_search = self._native_search(terms)
        if native_search:
            # Every profile matching all terms also matches any single term, so
            # the most selective one narrows the read without hiding a match.
            filters["search"] = native_search
        if invited is True:
            filters["q"] = "agentic.invited:true"
        # A searched page can never be sized by the directory's own counter:
        # Keycloak answers a "search" on its own and drops both "q" and
        # "enabled" (UsersResource#getUsersCount), so the invitation
        # subtraction below would cancel out to zero and hide every match.
        # Matches are counted while they are walked instead; the native search
        # filter keeps that walk proportional to the matches, not the realm.
        residual = bool(terms) or bool(role or roles) or not include_external_keycloak_users
        if invited is False and not residual:
            users, total = await self._non_invited_page(filters, skip, limit)
            return users, total, True
        if not residual:
            total = await self._count_profiles(filters)
            if not limit or skip >= total:
                return [], total, True
            response = await self.keycloak._keycloak_request(
                "GET",
                "/users",
                params={**filters, "first": skip, "max": limit, "briefRepresentation": "false"},
            )
            raise_for_httpx_response(response)
            return await self._hydrate(response.json()), total, True

        names = list(dict.fromkeys([*([role] if role else []), *(roles or [])]))
        if names:
            if native_search:
                # /roles/{name}/users takes no search, so with a term the
                # membership side is the wrong one to page: it would walk the
                # whole role to keep the few rows that match. The users side
                # does take one, so read that and keep the members instead.
                candidates = self._passing(
                    self._pages("/users", **filters),
                    lambda profile: self._passes(profile, terms, is_active, invited, include_external_keycloak_users),
                )
                memberships = {}
                window, position, more = await self._take_window(
                    self._holding_roles(candidates, set(names), memberships),
                    skip,
                    limit,
                    lambda _profile: True,
                )
                return (
                    await self._hydrate(window, memberships),
                    position + (1 if more else 0),
                    False,
                )
            return await self._role_member_page(
                names, skip, limit, terms, is_active, invited, include_external_keycloak_users
            )

        window, position, more = await self._take_window(
            self._pages("/users", **filters),
            skip,
            limit,
            lambda profile: self._passes(profile, terms, is_active, invited, include_external_keycloak_users),
        )
        return await self._hydrate(window), position + (1 if more else 0), False

    @_scoped_directory_reads
    async def count_by_role(self):
        index = await self._role_index()
        counts = Counter()
        async for profile in self._pages("/users"):
            counts[display_role_name(self._primary(profile, index))] += 1
        return [{"role": role, "count": count} for role, count in counts.most_common()]

    async def exists_by_id(self, user_id: uuid.UUID) -> bool:
        return await self._profile(user_id) is not None

    async def exists_by_email(self, email):
        return await self.get_by_email(email) is not None

    async def upsert_by_keycloak_id(self, keycloak_id, **_kwargs):
        # Compatibility endpoint: token/profile claims never mutate the identity provider.
        user = await self.get_by_id(keycloak_id)
        if user is None:
            raise DependencyResponseError()
        return user

    @staticmethod
    def _updates(profile: dict[str, Any], updates):
        payload = {
            k: profile[k]
            for k in (
                "username",
                "email",
                "firstName",
                "lastName",
                "enabled",
                "emailVerified",
                "requiredActions",
            )
            if k in profile
        }
        attrs = dict(profile.get("attributes") or {})
        fields = {
            "email": "email",
            "username": "username",
            "first_name": "firstName",
            "last_name": "lastName",
            "is_active": "enabled",
            "is_verified": "emailVerified",
        }
        for key, value in updates.items():
            if value is None:
                continue
            if key in fields:
                payload[fields[key]] = value
            elif key in {
                "team_name",
                "invited",
                "password_configured",
                "is_external_keycloak_user",
            }:
                attrs[f"agentic.{key}"] = [str(value).lower() if isinstance(value, bool) else str(value)]
        payload["attributes"] = attrs
        return payload

    async def update(self, user_id, **kwargs):
        profile = await self._profile(user_id)
        if profile is None:
            return None
        response = await self.keycloak._keycloak_request(
            "PUT", f"/users/{user_id}", json=self._updates(profile, kwargs)
        )
        raise_for_httpx_response(response)
        return await self.get_by_id(user_id)

    async def create(self, **kwargs):
        keycloak_id = kwargs.get("keycloak_id")
        if keycloak_id:
            user = await self.update(keycloak_id, **kwargs)
            if not user:
                raise DependencyResponseError()
            return user
        response = await self.keycloak._keycloak_request("POST", "/users", json=self._updates({}, kwargs))
        raise_for_httpx_response(response)
        keycloak_id = response.headers.get("Location", "").rsplit("/", 1)[-1]
        if not keycloak_id:
            raise DependencyResponseError()
        return await self.get_by_id(keycloak_id)

    async def delete(self, user_id):
        response = await self.keycloak._keycloak_request("DELETE", f"/users/{user_id}")
        if response.status_code == 404:
            return False
        raise_for_httpx_response(response)
        return True

    @_scoped_directory_reads
    async def list_assignable(self, organization_id, *, root_ids, query="", limit=20, user_id=None):
        """Return lightweight assignee rows from bulk group memberships.

        This endpoint only exposes names and IDs, so resolving every candidate's
        roles/groups is unnecessary. Scoped requests read one hierarchy snapshot
        and the relevant groups' member pages; global search uses native search.
        """
        from .keycloak_group_inventory import read_group_inventory
        from .keycloak_role_client import segment

        if root_ids is not None and not root_ids:
            return [], 0
        target = str(organization_id)
        groups = None
        if root_ids is not None:
            groups = await read_group_inventory(self.keycloak)
            target_group = groups.get(target)
        else:
            response = await self.keycloak._keycloak_request("GET", f"/groups/{segment(target)}")
            if response.status_code == 404:
                target_group = None
            else:
                raise_for_httpx_response(response)
                target_group = response.json()

        def active(group):
            if not group:
                return False
            values = (group.get("attributes") or {}).get("agenticai.organization.is_active")
            return bool(json.loads(values[0])) if values else True

        scoped_groups = None
        if root_ids is not None:
            roots = set(map(str, root_ids))
            scoped_groups = set()
            for group_id, group in groups.items():
                if not active(group):
                    continue
                ancestors, cursor = set(), group_id
                while cursor and cursor not in ancestors:
                    ancestors.add(cursor)
                    cursor = (groups.get(cursor) or {}).get("parentId")
                if roots.intersection(ancestors):
                    scoped_groups.add(group_id)

        terms = self._search_terms(query)
        if user_id is not None:
            profile = await self._profile(user_id)
            if profile is None:
                return [], 0
            memberships = {group["id"] async for group in self._pages(f"/users/{segment(user_id)}/groups")}
            if active(target_group) and target in memberships:
                return [], 0
            if scoped_groups is not None and not scoped_groups.intersection(memberships):
                return [], 0
            candidates = [profile]
            excluded = set()
        else:
            excluded = (
                {profile["id"] async for profile in self._pages(f"/groups/{segment(target)}/members")}
                if active(target_group)
                else set()
            )
            if scoped_groups is not None:
                candidates_by_id = {}
                for group_id in scoped_groups - {target}:
                    async for profile in self._pages(f"/groups/{segment(group_id)}/members"):
                        candidates_by_id[profile["id"]] = profile
                candidates = candidates_by_id.values()
            else:
                filters = {}
                native_search = self._native_search(terms)
                if native_search:
                    filters["search"] = native_search
                candidates = [profile async for profile in self._pages("/users", **filters)]
        matches = []
        for profile in candidates:
            if profile["id"] in excluded:
                continue
            if terms and not self._matches_terms(profile, terms):
                continue
            matches.append(
                {
                    "id": uuid.UUID(profile["id"]),
                    "email": profile.get("email") or "",
                    "username": profile.get("username"),
                    "first_name": profile.get("firstName"),
                    "last_name": profile.get("lastName"),
                }
            )
        matches.sort(key=lambda row: (row["email"], str(row["id"])))
        return matches[: max(1, min(limit, 100))], len(matches)
