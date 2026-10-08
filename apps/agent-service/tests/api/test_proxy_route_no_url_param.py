"""The proxy must never send the internal service token to a
caller-supplied URL. Spec T2/C3.

ProxyService._mcp_connection attaches Authorization: Bearer
INTERNAL_SERVICE_TOKEN to whatever url it is given; get_mcp_tools and
execute_mcp_tool used to accept that url from a request query parameter.
"""

import inspect

from api.routes import proxy_route


def test_get_mcp_tools_has_no_url_parameter():
    params = inspect.signature(proxy_route.get_mcp_tools).parameters
    assert "url" not in params


def test_execute_mcp_tool_has_no_url_parameter():
    params = inspect.signature(proxy_route.execute_mcp_tool).parameters
    assert "url" not in params


def test_module_no_longer_imports_query():
    source = inspect.getsource(proxy_route)
    assert "Query" not in source
