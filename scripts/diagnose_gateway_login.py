#!/usr/bin/env python3
"""Replay the APISIX gateway-auth login steps against Keycloak and report which one fails.

Run inside the apisix container so it uses exactly the settings APISIX uses:
  docker cp scripts/diagnose_gateway_login.py apisix:/tmp/diag.py
  docker exec -it apisix python3 /tmp/diag.py <username>
Tokens and secrets are never printed.
"""

import base64
import getpass
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

env = lambda k, d="": os.environ.get(k, d).strip()
realm_url = env("GATEWAY_KEYCLOAK_REALM_URL") or (
    env("KEYCLOAK_BASE_URL").rstrip("/") + "/realms/" + env("KEYCLOAK_REALM")
)
issuer = env("KEYCLOAK_ISSUER_URL").rstrip("/")
login_id, login_secret = env("KEYCLOAK_CLIENT_ID"), env("KEYCLOAK_CLIENT_SECRET")
gw_id = env("GATEWAY_KEYCLOAK_CLIENT_ID")
gw_secret = env("GATEWAY_KEYCLOAK_CLIENT_SECRET")


def call(endpoint, form=None, bearer=None):
    headers = {"Accept": "application/json"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    data = None
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urlencode(form).encode()
    req = Request(realm_url + "/protocol/openid-connect/" + endpoint, data=data, headers=headers,
                  method="POST" if data else "GET")
    try:
        with urlopen(req, timeout=10) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else {})
    except HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, {"raw": body[:200].decode(errors="replace")}


print(f"realm_url        = {realm_url}")
print(f"issuer (expected)= {issuer}")
print(f"login client     = {login_id} (secret {'set' if login_secret else 'EMPTY -> public client'})")
print(f"gateway client   = {gw_id} (secret {'set' if gw_secret else 'EMPTY!'})")

user = sys.argv[1] if len(sys.argv) > 1 else input("username: ")
password = getpass.getpass("password (not echoed): ")

print("\n[1] password grant with login client")
form = {"grant_type": "password", "username": user, "password": password,
        "scope": "openid profile email", "client_id": login_id}
if login_secret:
    form["client_secret"] = login_secret
status, tokens = call("token", form)
print(f"    HTTP {status}", "" if status == 200 else tokens)
if status != 200:
    sys.exit("    -> FAILS HERE (APISIX returns 401). invalid_grant = wrong user/password or user "
             "not in realm; unauthorized_client/invalid_client = login client config/secret.")
at = tokens.get("access_token", "")
try:
    seg = at.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))
    print(f"    token iss={claims.get('iss')} aud={claims.get('aud')} typ={claims.get('typ')}")
except Exception as exc:  # noqa: BLE001
    print(f"    (could not decode token: {exc})")

print("\n[2] introspection with gateway client")
status, data = call("token/introspect", {"token": at, "token_type_hint": "access_token",
                                         "client_id": gw_id, "client_secret": gw_secret})
print(f"    HTTP {status}")
if status != 200:
    sys.exit(f"    -> FAILS HERE: {data} (gateway client id/secret wrong or client not confidential)")
aud = data.get("aud")
aud = [aud] if isinstance(aud, str) else (aud or [])
checks = {
    "active is true": data.get("active") is True,
    "token_type == Bearer": data.get("token_type") == "Bearer",
    "sub present": bool(data.get("sub")),
    f"iss == {issuer}": data.get("iss") == issuer,
    "exp in future": isinstance(data.get("exp"), (int, float)) and data["exp"] > time.time(),
    f"aud contains {gw_id!r}": gw_id in aud,
}
for name, ok in checks.items():
    print(f"    [{'ok' if ok else 'FAIL'}] {name}")
print(f"    (got active={data.get('active')} token_type={data.get('token_type')!r} "
      f"iss={data.get('iss')!r} aud={aud} sub={'set' if data.get('sub') else None})")
if not all(checks.values()):
    sys.exit("    -> FAILS HERE (APISIX's valid_claims rejects the token -> 401)")

print("\n[3] userinfo")
status, profile = call("userinfo", bearer=at)
print(f"    HTTP {status}", "" if status == 200 else profile)
if status != 200:
    sys.exit("    -> FAILS HERE")
print(f"    sub matches: {profile.get('sub') == data.get('sub')}")
print("\nAll gateway login steps pass against Keycloak.")
