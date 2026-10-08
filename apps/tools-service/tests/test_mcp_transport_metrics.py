"""The MCP transport must show up in metrics once, under its own route label.

Two regressions this guards against: counting ``/mcp`` twice (a metrics
middleware on both the FastAPI app and the embedded transport) and labelling
it ``__unmatched__`` (a plain Starlette ``Route`` does not publish itself in
``scope["route"]`` the way FastAPI's ``APIRoute`` does).
"""

import re


def _counter(body: str, **labels: str) -> float | None:
    for line in body.splitlines():
        if not line.startswith("http_requests_total{"):
            continue
        if all(f'{key}="{value}"' in line for key, value in labels.items()):
            return float(line.rsplit(" ", 1)[1])
    return None


def test_mcp_request_is_counted_once_under_its_route(http_client) -> None:
    body_before = http_client.get("/metrics").text
    before = _counter(body_before, method="POST", route="/mcp") or 0.0

    http_client.post("/mcp", follow_redirects=False)

    body = http_client.get("/metrics").text
    assert _counter(body, method="POST", route="/mcp") == before + 1.0
    assert not re.search(r'http_requests_total\{[^}]*method="POST"[^}]*route="__unmatched__"', body)
