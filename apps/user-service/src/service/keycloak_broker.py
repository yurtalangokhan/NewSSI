import html
import secrets
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx


class _KeycloakLoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_form = False
        self.form_action: str | None = None
        self.form_inputs: dict[str, str] = {}
        self._current_inputs: dict[str, str] = {}
        self._current_action: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        if tag == "form" and self.form_action is None:
            self.in_form = True
            self._current_action = attr_map.get("action")
            self._current_inputs = {}
            return

        if tag != "input" or not self.in_form:
            return

        name = attr_map.get("name")
        if name:
            self._current_inputs[name] = attr_map.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag != "form" or not self.in_form:
            return

        self.in_form = False
        if self._current_action and self.form_action is None:
            self.form_action = self._current_action
            self.form_inputs = dict(self._current_inputs)


class KeycloakBrokerMixin:
    def _default_oidc_redirect_uri(self) -> str:
        redirect_uris = self._login_client_redirect_uris()
        for redirect_uri in redirect_uris:
            if "*" not in redirect_uri:
                return redirect_uri
        return "http://localhost:3000/auth/oidc/callback"

    def _rewrite_keycloak_url_for_backend(self, url: str) -> str:
        rewritten = html.unescape(url)
        external_issuer = self._external_issuer_url()
        external_backend_issuer = self._external_backend_issuer_url()
        if external_backend_issuer != external_issuer and rewritten.startswith(external_issuer):
            return external_backend_issuer + rewritten[len(external_issuer) :]
        return rewritten

    @staticmethod
    def _extract_authorization_code(
        redirect_url: str,
        expected_state: str,
    ) -> tuple[str | None, str | None]:
        parsed = urlparse(redirect_url)
        query = parse_qs(parsed.query)
        error = query.get("error", [None])[0]
        if error:
            description = query.get("error_description", [error])[0]
            return None, description

        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]
        if code and state != expected_state:
            return None, "Invalid OIDC state returned from Keycloak"
        return code, None

    @staticmethod
    def _extract_login_form(response: httpx.Response) -> tuple[str, dict[str, str]]:
        parser = _KeycloakLoginFormParser()
        parser.feed(response.text)
        if not parser.form_action:
            raise ValueError("External IdP login form was not found")

        action = urljoin(str(response.url), html.unescape(parser.form_action))
        return action, dict(parser.form_inputs)

    def _external_redirect_uri_error(self, response: httpx.Response) -> str | None:
        if response.status_code != 400:
            return None

        parsed = urlparse(str(response.url))
        if not str(response.url).startswith(self.get_external_issuer_url()):
            return None

        query = parse_qs(parsed.query)
        rejected_redirect_uri = query.get("redirect_uri", [None])[0]
        if not rejected_redirect_uri:
            return None

        return (
            "External IdP rejected redirect_uri. Add this Valid Redirect URI to "
            f"external Keycloak client '{query.get('client_id', [''])[0]}': "
            f"{rejected_redirect_uri}"
        )

    @staticmethod
    def _response_error_detail(response: httpx.Response) -> str:
        detail = f"status={response.status_code}, url={response.url}"
        location = response.headers.get("location")
        if location:
            detail = f"{detail}, location={location}"

        body = response.text.strip()
        if body:
            compact_body = " ".join(body.split())
            detail = f"{detail}, body={compact_body[:300]}"
        return detail

    async def _follow_broker_redirects(
        self,
        client: httpx.AsyncClient,
        response: httpx.Response,
        redirect_uri: str,
        expected_state: str,
    ) -> tuple[str | None, httpx.Response]:
        current = response
        for _ in range(20):
            if current.status_code in (301, 302, 303, 307, 308):
                location = current.headers.get("location")
                if not location:
                    break

                absolute_location = urljoin(str(current.url), html.unescape(location))
                if absolute_location.startswith(redirect_uri):
                    code, error = self._extract_authorization_code(
                        absolute_location,
                        expected_state,
                    )
                    if error:
                        raise ValueError(error)
                    if code:
                        return code, current

                if absolute_location.startswith(("http://localhost", "https://localhost")):
                    return None, current

                current = await client.get(
                    self._rewrite_keycloak_url_for_backend(absolute_location),
                    follow_redirects=False,
                )
                continue

            if str(current.url).startswith(redirect_uri):
                code, error = self._extract_authorization_code(
                    str(current.url),
                    expected_state,
                )
                if error:
                    raise ValueError(error)
                if code:
                    return code, current

            if current.status_code == 200:
                return None, current

            redirect_uri_error = self._external_redirect_uri_error(current)
            if redirect_uri_error:
                raise ValueError(redirect_uri_error)

            break

        detail = self._response_error_detail(current)
        raise ValueError(f"External IdP login flow did not complete ({detail})")

    async def external_broker_password_login(
        self,
        username: str,
        password: str,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        """Authenticate on the configured IdP through the SP broker."""
        if not self.is_external_keycloak():
            raise ValueError("External Keycloak is not configured")

        callback_uri = redirect_uri or self._default_oidc_redirect_uri()
        state = secrets.token_urlsafe(24)
        authorize_url = await self.get_oidc_authorize_url(
            callback_uri,
            state=state,
            idp_hint=self.get_external_keycloak_alias(),
        )

        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": "AgenticAI-UserService/1.0"},
        ) as client:
            response = await client.get(
                self._rewrite_keycloak_url_for_backend(authorize_url),
                follow_redirects=False,
            )
            code, login_response = await self._follow_broker_redirects(
                client,
                response,
                callback_uri,
                state,
            )
            if code:
                return await self.handle_oidc_callback(code, callback_uri)

            form_action, form_data = self._extract_login_form(login_response)
            form_data.update({"username": username, "password": password})

            response = await client.post(
                self._rewrite_keycloak_url_for_backend(form_action),
                data=form_data,
                follow_redirects=False,
            )
            code, final_response = await self._follow_broker_redirects(
                client,
                response,
                callback_uri,
                state,
            )
            if not code:
                if final_response.status_code in (400, 401, 403):
                    raise ValueError("External authentication failed")
                raise ValueError("External IdP credentials were rejected")

        assert code is not None
        return await self.handle_oidc_callback(code, callback_uri)
