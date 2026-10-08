#!/usr/bin/env python3
"""Assert the API and observability contract for one service.

Run with the service's own interpreter so its dependencies resolve:

    apps/agent-service/.venv/bin/python scripts/governance/check_service_contract.py \
        --root apps/agent-service --src src --app app:app

Covers the runtime governance rules that were previously only ever checked by
hand: API-001..006, SVC-002, SVC-003, OBS-001..004, plus operationId uniqueness,
which the rules do not state but the OpenAPI specification requires.
"""

from __future__ import annotations

import argparse
import collections
import importlib
import os
import sys
from pathlib import Path

HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head"}
FASTAPI_DEFAULT_TITLE = "FastAPI"
REQUIRED_METRICS = {
    "OBS-002": "http_requests_total",
    "OBS-003": "http_request_duration_seconds",
    "OBS-004": "http_request_errors_total",
    "OBS-005": "idempotency_decisions_total",
    "OBS-006": "idempotency_lock_wait_seconds",
}


def _load_app(spec: str):
    """Load ``module:attr``; a trailing ``()`` calls the attribute as a factory."""
    module_name, _, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    if attr.endswith("()"):
        return getattr(module, attr[:-2])()
    return getattr(module, attr)


def _iter_refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_refs(item)


def _operations(spec):
    return [
        (path, method, operation)
        for path, item in (spec.get("paths") or {}).items()
        for method, operation in item.items()
        if method in HTTP_METHODS and isinstance(operation, dict)
    ]


def check(spec, metrics_body, metrics_content_type, metrics_status):
    """Return {rule: (ok, detail)} for every rule this script covers."""
    results: dict[str, tuple[bool, str]] = {}
    info = spec.get("info", {})
    operations = _operations(spec)

    missing_meta = [
        field
        for field in ("title", "description", "version")
        if not info.get(field)
    ]
    if info.get("title") == FASTAPI_DEFAULT_TITLE:
        missing_meta.append("title is the framework default")
    results["API-001 info metadata"] = (not missing_meta, ", ".join(missing_meta))

    no_id = [f"{m} {p}" for p, m, o in operations if not o.get("operationId")]
    results["API-002 operationId present"] = (not no_id, f"{len(no_id)}: {no_id[:3]}")

    ids = [o["operationId"] for _, _, o in operations if o.get("operationId")]
    dupes = {i: n for i, n in collections.Counter(ids).items() if n > 1}
    results["API-002 operationId unique"] = (not dupes, f"{len(dupes)}: {list(dupes)[:3]}")

    no_2xx = [
        f"{m} {p}" for p, m, o in operations
        if not any(str(c).startswith("2") for c in (o.get("responses") or {}))
    ]
    results["API-003 success response"] = (not no_2xx, f"{len(no_2xx)}: {no_2xx[:3]}")

    no_err = [
        f"{m} {p}" for p, m, o in operations
        if not any(str(c)[:1] in {"4", "5"} for c in (o.get("responses") or {}))
    ]
    results["API-004 error response"] = (not no_err, f"{len(no_err)}: {no_err[:3]}")

    no_schema = []
    for path, method, operation in operations:
        body = operation.get("requestBody")
        if body and not any("schema" in c for c in (body.get("content") or {}).values()):
            no_schema.append(f"{method} {path} requestBody")
        for code, response in (operation.get("responses") or {}).items():
            if isinstance(response, dict) and response.get("content") and not any(
                "schema" in c for c in response["content"].values()
            ):
                no_schema.append(f"{method} {path} -> {code}")
    results["API-005 operation schemas"] = (not no_schema, f"{len(no_schema)}: {no_schema[:3]}")

    schemes = list((spec.get("components") or {}).get("securitySchemes") or {})
    results["API-006 security scheme"] = (bool(schemes), str(schemes))

    dangling = []
    for ref in _iter_refs(spec):
        if not ref.startswith("#/"):
            dangling.append(ref)
            continue
        node = spec
        for part in ref.removeprefix("#/").split("/"):
            if not isinstance(node, dict) or part not in node:
                dangling.append(ref)
                break
            node = node[part]
    results["SVC-002 references resolve"] = (not dangling, f"{len(dangling)}: {dangling[:3]}")

    results["SVC-003 metrics endpoint"] = (metrics_status == 200, f"status {metrics_status}")
    results["OBS-001 prometheus format"] = (
        metrics_content_type.startswith("text/plain"), metrics_content_type
    )
    for rule, metric in REQUIRED_METRICS.items():
        results[f"{rule} {metric}"] = (metric in metrics_body, metric)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="service directory to run from")
    parser.add_argument("--src", default=None, help="path added to sys.path, relative to --root")
    parser.add_argument("--app", required=True, help="module:attr, or module:factory()")
    parser.add_argument("--warmup", default="/", help="path requested before reading /metrics")
    parser.add_argument("--label", default=None)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    os.chdir(root)
    sys.path.insert(0, str(root))
    if args.src:
        sys.path.insert(0, str(root / args.src))

    from fastapi.testclient import TestClient

    app = _load_app(args.app)
    # The lifespan must run: services start their metrics and transport there.
    with TestClient(app) as client:
        client.get(args.warmup)
        response = client.get("/metrics")
        results = check(
            app.openapi(), response.text, response.headers.get("content-type", ""),
            response.status_code,
        )

    label = args.label or root.name
    print(f"--- {label} ({len(_operations(app.openapi()))} operations) ---")
    failed = False
    for rule, (ok, detail) in results.items():
        if ok:
            print(f"  PASS   {rule}")
        else:
            failed = True
            print(f"  FAIL   {rule}  [{detail}]")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
