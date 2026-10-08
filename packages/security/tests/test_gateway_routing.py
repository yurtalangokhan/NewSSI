"""Startup guard: service URLs must route through Gateway.

Services no longer authenticate callers themselves, so a URL pointing straight
at a service host does not merely bypass route authorization — it 401s on every
request. Catching that at boot with a clear message is the point.
"""

import pytest

from security import (
    GATEWAY_ROUTE_PREFIXES,
    GatewayRoutingError,
    assert_gateway_routed,
    is_gateway_routed,
)

PUBLIC = "http://apisix:8000/user-service"
INTERNAL = "http://apisix:8000/internal/tools-service"


@pytest.mark.parametrize(
    "url",
    [PUBLIC, INTERNAL, PUBLIC + "/", PUBLIC + "/health", f"  {PUBLIC}  "],
)
def test_recognises_a_gateway_route_prefix(url):
    assert is_gateway_routed(url) is True


@pytest.mark.parametrize("url", [None, "", "   "])
def test_unset_is_not_routed(url):
    assert is_gateway_routed(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "http://user-service:8090",
        "http://agent-service:8001",
        "http://apisix:8000/some-other-service",
        "https://example.com/user-service-like",
    ],
)
def test_a_bare_service_origin_is_not_routed(url):
    """A path that merely *contains* a prefix is not a route through Gateway."""
    assert is_gateway_routed(url) is False


def test_every_prefix_is_covered_for_both_traffic_classes():
    for service in ("agent-service", "user-service", "rag-service", "tools-service"):
        assert f"/{service}" in GATEWAY_ROUTE_PREFIXES
        assert f"/internal/{service}" in GATEWAY_ROUTE_PREFIXES


def test_a_clean_mapping_passes():
    assert_gateway_routed({"USER_SERVICE_URL": PUBLIC, "TOOLS_SERVICE_URL": INTERNAL})


def test_a_direct_service_url_is_rejected_with_the_offending_name():
    with pytest.raises(GatewayRoutingError) as exc:
        assert_gateway_routed({"USER_SERVICE_URL": "http://user-service:8090"})
    assert "USER_SERVICE_URL" in str(exc.value)
    assert "apisix:8000" in str(exc.value)


def test_every_offender_is_named_in_one_error():
    with pytest.raises(GatewayRoutingError) as exc:
        assert_gateway_routed({"A_URL": "http://a:1", "B_URL": "http://b:2"})
    assert "A_URL" in str(exc.value)
    assert "B_URL" in str(exc.value)


def test_a_required_unset_url_is_reported_as_not_set():
    with pytest.raises(GatewayRoutingError, match="is not set"):
        assert_gateway_routed({"USER_SERVICE_URL": None})


def test_optional_unset_urls_are_tolerated():
    assert_gateway_routed({"USER_SERVICE_URL": PUBLIC, "OPTIONAL_URL": None}, required=False)


def test_optional_but_set_urls_must_still_be_routed():
    """`required=False` relaxes presence, not correctness."""
    with pytest.raises(GatewayRoutingError, match="does not route through Gateway"):
        assert_gateway_routed({"OPTIONAL_URL": "http://optional:1"}, required=False)


def test_the_error_is_a_value_error():
    assert issubclass(GatewayRoutingError, ValueError)
