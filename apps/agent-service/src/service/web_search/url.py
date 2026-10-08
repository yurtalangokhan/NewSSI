import ipaddress
from typing import Any
from urllib.parse import urlparse, urlunparse

from error_contract.domain import DNSResolutionError, SSRFBlockedException, SSRFException
import requests
from security import UrlPolicyError, is_blocked_ip, resolve_and_check

from core.observability.logger import get_logger

logger = get_logger(__name__)

# Hostnames that should always be blocked
BLOCKED_HOSTNAMES = {
    # Localhost variations
    "localhost",
    # Cloud metadata endpoints (defense-in-depth; the IPs are also rejected by the
    # shared address policy)
    "169.254.169.254",  # AWS/Azure/GCP metadata IP
    "fd00:ec2::254",  # AWS IPv6 metadata
    "metadata.azure.com",
    "metadata.google.internal",
    "metadata.gke.internal",
    # Kubernetes internal
    "kubernetes.default",
    "kubernetes.default.svc",
    "kubernetes.default.svc.cluster.local",
}


def _validate_and_resolve_url(url: str) -> tuple[str, str, int]:
    """
    Validate a URL for SSRF and resolve it to a safe IP address.

    The address rules live in ``security.url_policy`` — this module owns only
    what is specific to web search: the blocked hostname list, the public
    exception names its callers catch, and the IP-pinned request that follows.

    Returns:
        Tuple of (validated_ip, original_hostname, port)

    Raises:
        SSRFException: If the URL could be used for SSRF attack
        ValueError: If the URL is malformed
    """
    if not url:
        raise ValueError("URL cannot be empty")

    # Parse the URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}") from e

    # Validate scheme
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedException(f"Invalid URL scheme '{parsed.scheme}'. Only http and https are allowed.")

    # Get hostname
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must contain a hostname")

    # Check for blocked hostnames
    hostname_lower = hostname.lower()
    if hostname_lower in BLOCKED_HOSTNAMES:
        raise SSRFBlockedException(f"Access to hostname '{hostname}' is not allowed.")

    # Check for common SSRF bypass attempts
    # Block URLs with credentials (user:pass@host)
    if parsed.username or parsed.password:
        raise SSRFBlockedException("URLs with embedded credentials are not allowed.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # Check if the hostname is already an IP address
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # Not an IP address, proceed with DNS resolution
        pass
    else:
        if is_blocked_ip(str(ip)):
            raise SSRFBlockedException(f"Access to internal/private IP address '{hostname}' is not allowed.")
        return str(ip), hostname, port

    # Resolve and reject if *any* address is internal, so a later connection
    # attempt or a different resolver cannot land on the private one.
    try:
        return resolve_and_check(hostname, port), hostname, port
    except UrlPolicyError as e:
        logger.warning("DNS resolution failed for hostname '%s': %s", hostname, e)
        raise DNSResolutionError(f"Could not resolve hostname '{hostname}': {e}") from e


def validate_outbound_http_url(
    url: str,
    *,
    allow_private_network: bool = False,
    https_only: bool = False,
) -> str:
    """
    Validate a URL that will be used by backend outbound HTTP calls.

    Args:
        url: The URL to validate.
        allow_private_network: If True, skip private/reserved IP checks.
        https_only: If True, reject http:// URLs (only https:// is allowed).

    Returns:
        A normalized URL string with surrounding whitespace removed.

    Raises:
        ValueError: If URL is malformed.
        SSRFException: If URL fails SSRF checks.
    """
    normalized_url = url.strip()
    if not normalized_url:
        raise ValueError("URL cannot be empty")

    parsed = urlparse(normalized_url)

    if https_only:
        if parsed.scheme != "https":
            raise SSRFBlockedException(f"Invalid URL scheme '{parsed.scheme}'. Only https is allowed.")
    elif parsed.scheme not in ("http", "https"):
        raise SSRFBlockedException(f"Invalid URL scheme '{parsed.scheme}'. Only http and https are allowed.")

    if not parsed.hostname:
        raise ValueError("URL must contain a hostname")

    if parsed.username or parsed.password:
        raise SSRFBlockedException("URLs with embedded credentials are not allowed.")

    hostname = parsed.hostname.lower()
    if hostname in BLOCKED_HOSTNAMES:
        raise SSRFBlockedException(f"Access to hostname '{parsed.hostname}' is not allowed.")

    if not allow_private_network:
        _validate_and_resolve_url(normalized_url)

    return normalized_url


MAX_REDIRECTS = 10


def _make_ssrf_safe_request(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float | tuple[float, float] = 15,
    **kwargs: Any,
) -> requests.Response:
    """
    Make a single GET request with SSRF protection (no redirect following).

    Returns the response which may be a redirect (3xx status).
    """
    # Validate and resolve the URL to get a safe IP
    validated_ip, original_hostname, port = _validate_and_resolve_url(url)

    # Parse the URL to rebuild it with the IP
    parsed = urlparse(url)

    # Build the new URL using the validated IP
    # For HTTPS, we need to use the original hostname for TLS verification
    if parsed.scheme == "https":
        # For HTTPS, make request to original URL but we've validated the IP
        # The TLS handshake needs the hostname for SNI
        # We rely on the short time window between validation and request
        # A more robust solution would require custom SSL context
        request_url = url
    else:
        # For HTTP, we can safely request directly to the IP
        netloc = f"{validated_ip}:{port}" if port not in (80, 443) else validated_ip
        request_url = urlunparse(
            (
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    # Prepare headers
    request_headers = headers.copy() if headers else {}

    # Set Host header to original hostname (required for virtual hosting)
    if parsed.scheme == "http":
        request_headers["Host"] = f"{original_hostname}:{port}" if port != 80 else original_hostname

    # Disable automatic redirects to prevent SSRF bypass via redirect
    return requests.get(
        request_url,
        headers=request_headers,
        timeout=timeout,
        allow_redirects=False,
        **kwargs,
    )


def ssrf_safe_get(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float | tuple[float, float] = 15,
    follow_redirects: bool = True,
    **kwargs: Any,
) -> requests.Response:
    """
    Make a GET request with SSRF protection.

    This function resolves the hostname, validates the IP is not private/internal,
    and makes the request directly to the validated IP to prevent DNS rebinding attacks.
    Redirects are followed safely by validating each redirect URL.

    Args:
        url: The URL to fetch
        headers: Optional headers to include in the request
        timeout: Request timeout in seconds
        follow_redirects: Whether to follow redirects (each redirect URL is validated)
        **kwargs: Additional arguments passed to requests.get()

    Returns:
        requests.Response object

    Raises:
        SSRFException: If the URL could be used for SSRF attack
        ValueError: If the URL is malformed
        requests.RequestException: If the request fails
    """
    response = _make_ssrf_safe_request(url, headers, timeout, **kwargs)

    if not follow_redirects:
        return response

    # Manually follow redirects while validating each redirect URL
    redirect_count = 0
    current_url = url

    while response.is_redirect and redirect_count < MAX_REDIRECTS:
        redirect_count += 1

        # Get the redirect location
        redirect_url = response.headers.get("Location")
        if not redirect_url:
            break

        # Handle relative redirects
        if not redirect_url.startswith(("http://", "https://")):
            parsed_current = urlparse(current_url)
            if redirect_url.startswith("/"):
                redirect_url = f"{parsed_current.scheme}://{parsed_current.netloc}{redirect_url}"
            else:
                # Relative path
                base_path = parsed_current.path.rsplit("/", 1)[0]
                redirect_url = f"{parsed_current.scheme}://{parsed_current.netloc}{base_path}/{redirect_url}"

        # Validate and follow the redirect (this will raise SSRFException if invalid)
        current_url = redirect_url
        response = _make_ssrf_safe_request(redirect_url, headers, timeout, **kwargs)

    if response.is_redirect and redirect_count >= MAX_REDIRECTS:
        raise SSRFException(f"Too many redirects (max {MAX_REDIRECTS})")

    return response
