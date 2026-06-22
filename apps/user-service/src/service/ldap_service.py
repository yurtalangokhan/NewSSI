import asyncio
import contextlib
import json
import logging
from typing import Any

import ldap3  # type: ignore[import-untyped]
from ldap3 import ALL, SUBTREE, Connection, Server  # type: ignore[import-untyped]
from ldap3.core.exceptions import LDAPBindError, LDAPException  # type: ignore[import-untyped]

from src.config import get_settings
from src.core.env import get_env

logger = logging.getLogger(__name__)

_env = get_env()
_settings = get_settings()


class LdapService:
    def is_enabled(self) -> bool:
        return _env.LDAP_ENABLED or _settings.LDAP_ENABLED

    def _get_server(self) -> Server:
        host = _env.LDAP_HOST or _settings.LDAP_HOST
        port = _env.LDAP_PORT or _settings.LDAP_PORT
        use_tls = _env.LDAP_USE_TLS or _settings.LDAP_USE_TLS
        return Server(host, port=port, use_ssl=use_tls, get_info=ALL)

    def _get_bind_credentials(self) -> tuple[str | None, str | None]:
        bind_dn = _env.LDAP_BIND_DN or _settings.LDAP_BIND_DN or None
        bind_password = _env.LDAP_BIND_PASSWORD or _settings.LDAP_BIND_PASSWORD or None
        return bind_dn, bind_password

    def _get_base_dn(self) -> str:
        return _env.LDAP_BASE_DN or _settings.LDAP_BASE_DN

    def _get_search_base(self) -> str:
        return _env.LDAP_USER_SEARCH_BASE or _settings.LDAP_USER_SEARCH_BASE or self._get_base_dn()

    def _get_search_filter(self, username: str) -> str:
        raw = _env.LDAP_USER_SEARCH_FILTER or _settings.LDAP_USER_SEARCH_FILTER
        return raw.replace("{{username}}", ldap3.utils.conv.escape_filter_chars(username))

    def _get_attribute_map(self) -> dict[str, str]:
        raw = _env.LDAP_ATTRIBUTE_MAP or _settings.LDAP_ATTRIBUTE_MAP
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {
                "username": "uid",
                "email": "mail",
                "first_name": "givenName",
                "last_name": "sn",
            }

    async def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        server = self._get_server()
        bind_dn, bind_password = self._get_bind_credentials()
        search_base = self._get_search_base()
        search_filter = self._get_search_filter(username)

        def _do_auth() -> dict[str, Any] | None:
            service_conn = Connection(
                server,
                user=bind_dn,
                password=bind_password,
                auto_bind=True,
                raise_exceptions=True,
            )
            try:
                if not service_conn.search(
                    search_base=search_base,
                    search_filter=search_filter,
                    search_scope=SUBTREE,
                    attributes=["*"],
                ):
                    logger.warning("LDAP search returned no results for %s", username)
                    return None

                if not service_conn.entries:
                    return None

                entry = service_conn.entries[0]
                user_dn = entry.entry_dn

                user_conn = Connection(
                    server,
                    user=user_dn,
                    password=password,
                    auto_bind=True,
                    raise_exceptions=True,
                )
                user_conn.unbind()

                attrs: dict[str, Any] = {"dn": user_dn}
                for attr_name in entry.entry_attributes:
                    values = entry[attr_name].values
                    if len(values) == 1:
                        attrs[attr_name] = str(values[0])
                    elif len(values) > 1:
                        attrs[attr_name] = [str(v) for v in values]

                return attrs

            except LDAPBindError:
                logger.warning("LDAP bind failed for %s", username)
                return None
            except LDAPException as e:
                logger.error("LDAP error during authentication: %s", e)
                return None
            finally:
                with contextlib.suppress(Exception):
                    service_conn.unbind()

        return await asyncio.to_thread(_do_auth)

    def _map_ldap_entry(self, ldap_attrs: dict[str, Any]) -> dict[str, Any]:
        attr_map = self._get_attribute_map()
        result: dict[str, Any] = {}
        for user_field, ldap_attr in attr_map.items():
            value = ldap_attrs.get(ldap_attr)
            if value is not None:
                if isinstance(value, list):
                    value = value[0] if value else None
                result[user_field] = str(value) if value is not None else None
            else:
                result[user_field] = None
        result["dn"] = ldap_attrs.get("dn", "")
        return result

    async def search_users(
        self,
        filter_str: str = "(objectClass=person)",
        attributes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        attrs = attributes or ["dn", "cn", "mail", "uid"]
        server = self._get_server()
        bind_dn, bind_password = self._get_bind_credentials()
        search_base = self._get_search_base()

        def _do_search() -> list[dict[str, Any]]:
            conn = Connection(
                server,
                user=bind_dn,
                password=bind_password,
                auto_bind=True,
                raise_exceptions=True,
            )
            try:
                if not conn.search(
                    search_base=search_base,
                    search_filter=filter_str,
                    search_scope=SUBTREE,
                    attributes=attrs,
                ):
                    return []

                results: list[dict[str, Any]] = []
                for entry in conn.entries:
                    entry_dict: dict[str, Any] = {"dn": entry.entry_dn}
                    for attr_name in attrs:
                        if attr_name == "dn":
                            continue
                        if hasattr(entry, attr_name):
                            values = entry[attr_name].values
                            if len(values) == 1:
                                entry_dict[attr_name] = str(values[0])
                            elif len(values) > 1:
                                entry_dict[attr_name] = [str(v) for v in values]
                        else:
                            entry_dict[attr_name] = None
                    results.append(entry_dict)
                return results

            except LDAPException as e:
                logger.error("LDAP search error: %s", e)
                return []
            finally:
                with contextlib.suppress(Exception):
                    conn.unbind()

        return await asyncio.to_thread(_do_search)

    async def validate_user(self, username: str) -> bool:
        server = self._get_server()
        bind_dn, bind_password = self._get_bind_credentials()
        search_base = self._get_search_base()
        search_filter = self._get_search_filter(username)

        def _do_validate() -> bool:
            conn = Connection(
                server,
                user=bind_dn,
                password=bind_password,
                auto_bind=True,
                raise_exceptions=True,
            )
            try:
                return conn.search(
                    search_base=search_base,
                    search_filter=search_filter,
                    search_scope=SUBTREE,
                    attributes=["dn"],
                    size_limit=1,
                )
            except LDAPException as e:
                logger.error("LDAP validation error for %s: %s", username, e)
                return False
            finally:
                with contextlib.suppress(Exception):
                    conn.unbind()

        return await asyncio.to_thread(_do_validate)


_ldap_service: LdapService | None = None


def get_ldap_service() -> LdapService:
    global _ldap_service
    if _ldap_service is None:
        _ldap_service = LdapService()
    return _ldap_service
