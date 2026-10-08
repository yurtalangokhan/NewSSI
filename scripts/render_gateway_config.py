"""Render Gateway configuration without interpolating secrets into shell or YAML."""

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml


def render(template, environ):
    """Fill the APISIX standalone template from ``environ``; ``ValueError`` on a bad setting."""
    environ = dict(environ)
    values = {}
    for service in ("USER", "AGENT", "RAG", "TOOLS"):
        name = f"{service}_SERVICE_UPSTREAM_ADDR"
        address = environ.get(name, "").strip()
        parsed = urlsplit("http://" + address)
        try:
            valid = (
                parsed.hostname
                and parsed.port
                and not (
                    parsed.username
                    or parsed.password
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                )
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(f"Invalid APISIX upstream address: {name}; expected host:port")
        values[name] = address
    required = (
        "KEYCLOAK_ISSUER_URL",
        "KEYCLOAK_BASE_URL",
        "KEYCLOAK_REALM",
        "KEYCLOAK_CLIENT_ID",
        "GATEWAY_KEYCLOAK_CLIENT_ID",
        "GATEWAY_KEYCLOAK_CLIENT_SECRET",
        "INTERNAL_SERVICE_TOKEN",
        "REDIS_HOST",
        "REDIS_PORT",
        "GATEWAY_ALLOWED_REDIRECT_URIS",
    )
    for name in required:
        value = environ.get(name, "").strip()
        if not value:
            raise ValueError(f"Required Gateway setting is missing: {name}")
        values[name] = value
    try:
        redirects = json.loads(values["GATEWAY_ALLOWED_REDIRECT_URIS"])
    except (TypeError, ValueError) as error:
        raise ValueError("Gateway redirect URIs must be a JSON array") from error
    if not isinstance(redirects, list) or not redirects:
        raise ValueError("Gateway redirect URIs must be a nonempty JSON array")
    for uri in redirects:
        if not isinstance(uri, str):
            raise ValueError("Gateway redirect URI must be a string")  # noqa: TRY004 -- invalid JSON configuration value
        parsed = urlsplit(uri)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.fragment
            or "*" in uri
        ):
            raise ValueError("Gateway redirect URI must be an exact HTTP(S) URL")
    try:
        rewrites = json.loads(environ.get("GATEWAY_BROKER_URL_REWRITES", "").strip() or "{}")
    except ValueError as error:
        raise ValueError("Gateway broker URL rewrites must be a JSON object") from error
    if not isinstance(rewrites, dict):
        raise ValueError("Gateway broker URL rewrites must be a JSON object")
    for public, backend in rewrites.items():
        for value in (public, backend):
            parsed = urlsplit(value) if isinstance(value, str) else None
            if (
                parsed is None
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Gateway broker URL rewrite must map HTTP(S) URL prefixes")
    secure = environ.get("GATEWAY_COOKIE_SECURE", "true").lower()
    if secure not in {"true", "false"}:
        raise ValueError("GATEWAY_COOKIE_SECURE must be true or false")
    external_alias = environ.get("GATEWAY_EXTERNAL_IDP_ALIAS", "").strip()
    if not external_alias and environ.get("EXTERNAL_KEYCLOAK", "false").strip().lower() in {
        "true",
        "1",
        "yes",
        "on",
    }:
        external_alias = environ.get("EXTERNAL_KEYCLOAK_ALIAS", "").strip() or "external-keycloak"
    values.update(
        {
            "KEYCLOAK_CLIENT_SECRET": environ.get("KEYCLOAK_CLIENT_SECRET", ""),
            "GATEWAY_KEYCLOAK_REALM_URL": environ.get("GATEWAY_KEYCLOAK_REALM_URL")
            or (values["KEYCLOAK_BASE_URL"].rstrip("/") + "/realms/" + values["KEYCLOAK_REALM"]),
            "GATEWAY_ALLOWED_REDIRECT_URIS": redirects,
            "GATEWAY_COOKIE_SECURE": secure == "true",
            "GATEWAY_EXTERNAL_IDP_ALIAS": external_alias,
            "GATEWAY_BROKER_URL_REWRITES": rewrites,
            "REDIS_PASSWORD": environ.get("REDIS_PASSWORD", ""),
            "REDIS_PORT": int(values["REDIS_PORT"]),
            "GATEWAY_REDIS_DB": int(environ.get("GATEWAY_REDIS_DB", "0")),
        }
    )
    for name, value in values.items():
        if name.endswith("_URL"):
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(f"Invalid Gateway URL setting: {name}")
            values[name] = value.rstrip("/")

    def substitute(value):
        if isinstance(value, dict):
            return {substitute(key): substitute(item) for key, item in value.items()}
        if isinstance(value, list):
            return [substitute(item) for item in value]
        if not isinstance(value, str):
            return value
        match = re.fullmatch(r"__([A-Z_]+)__", value)
        if match:
            return values[match[1]]
        return re.sub(r"__([A-Z_]+)__", lambda match: str(values[match[1]]), value)

    return substitute(template)


def main():
    if len(sys.argv) != 3:
        raise ValueError("Usage: render_gateway_config.py TEMPLATE OUTPUT")
    config = render(yaml.safe_load(Path(sys.argv[1]).read_text()), os.environ)
    output = Path(sys.argv[2])
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)
        stream.write("#END\n")  # APISIX standalone mode reads the file only with this trailer.


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError) as error:
        print(f"Gateway configuration failed: {error}", file=sys.stderr)
        sys.exit(1)
