"""Salesforce source: one stream per configured sObject, read with SOQL.

The field list of every object comes from ``describe`` (compound address /
location fields are skipped because SOQL cannot select them together with their
components). Incremental sync filters on ``SystemModstamp``.

Auth: OAuth2 *client credentials* (connected app with a run-as user; use your My
Domain URL as ``login_url``) or the *username-password* flow. The token
response carries the ``instance_url`` that all API calls must use.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field, model_validator

from ..base import secret_field
from ..common.declarative import (
    DeclarativeRestSource,
    NextUrlPagination,
    PageRequest,
    StreamSpec,
    as_iso_z,
)
from ..common.oauth2 import OAuth2BearerMixin, OAuth2Token
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

DEFAULT_OBJECTS = ["Account", "Contact", "Lead", "Opportunity", "Case"]
_SKIP_TYPES = {"address", "location", "base64"}
CURSOR = "SystemModstamp"


class SalesforceConfig(BaseModel):
    login_url: str = Field(
        default="https://login.salesforce.com",
        description="My Domain URL for client credentials; test.salesforce.com for sandboxes.",
    )
    client_id: str = Field(description="Connected app consumer key.")
    client_secret: str = secret_field(description="Connected app consumer secret.")
    username: str | None = Field(default=None, description="Only for the username-password flow.")
    password: str | None = secret_field(default=None, description="Password + security token.")
    objects: list[str] = Field(default_factory=lambda: list(DEFAULT_OBJECTS))
    api_version: str = "v60.0"
    timeout_seconds: float = 120.0

    @model_validator(mode="after")
    def _password_pair(self) -> SalesforceConfig:
        if bool(self.username) != bool(self.password):
            raise ValueError("username and password must be given together")
        return self


class SalesforceSource(OAuth2BearerMixin, DeclarativeRestSource[SalesforceConfig]):
    definition = ConnectorDefinition(
        name="salesforce",
        display_name="Salesforce",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.SALES,
        documentation_url="https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/",
        icon="salesforce.svg",
        tags=frozenset({"saas", "crm"}),
    )
    Config = SalesforceConfig
    _fields: dict[str, list[str]] | None = None

    def base_url(self) -> str:
        return self.config.login_url

    # ---- auth ---------------------------------------------------------------------

    def oauth2_token(self) -> OAuth2Token:
        c = self.config
        form: dict[str, Any] = {"client_id": c.client_id, "client_secret": c.client_secret}
        if c.username:
            form.update(grant_type="password", username=c.username, password=c.password)
        else:
            form["grant_type"] = "client_credentials"
        return OAuth2Token(
            f"{c.login_url.rstrip('/')}/services/oauth2/token", form, default_ttl=3600
        )

    async def _instance_url(self) -> str:
        await self.access_token()
        instance = self.token_source().last_response.get("instance_url")
        return str(instance or self.config.login_url).rstrip("/")

    async def _fetch_page(
        self, spec: StreamSpec, req: PageRequest
    ) -> tuple[httpx.Response, Any, list[Any]]:
        if req.url.startswith("/"):
            req.url = await self._instance_url() + req.url
        return await super()._fetch_page(spec, req)

    # ---- streams --------------------------------------------------------------------

    def streams(self) -> list[StreamSpec]:
        return [self._spec(obj, ["Id", CURSOR]) for obj in self.config.objects]

    async def stream_specs(self) -> list[StreamSpec]:
        if self._fields is None:
            self._fields = {}
            root = f"{await self._instance_url()}/services/data/{self.config.api_version}"
            for obj in self.config.objects:
                meta = await self.get_json(f"{root}/sobjects/{obj}/describe")
                self._fields[obj] = [
                    f["name"] for f in meta.get("fields", []) if f.get("type") not in _SKIP_TYPES
                ]
        return [self._spec(obj, fields) for obj, fields in self._fields.items()]

    def _spec(self, obj: str, fields: list[str]) -> StreamSpec:
        select = f"SELECT {', '.join(fields)} FROM {obj}"
        has_cursor = CURSOR in fields

        def with_soql(req: PageRequest, cursor: Any) -> None:
            where = (
                f" WHERE {CURSOR} > {as_iso_z(cursor)}" if cursor is not None and has_cursor else ""
            )
            order = f" ORDER BY {CURSOR} ASC" if has_cursor else ""
            req.params["q"] = select + where + order

        return StreamSpec(
            name=obj.lower(),
            path=f"/services/data/{self.config.api_version}/query",
            records_path="records",
            paginator=NextUrlPagination(next_url_path="nextRecordsUrl"),
            primary_key=("Id",),
            cursor_field=CURSOR if has_cursor else None,
            on_request=with_soql,
            transform=_drop_attributes,
        )


def _drop_attributes(rec: dict[str, Any]) -> dict[str, Any]:
    rec.pop("attributes", None)
    return rec
