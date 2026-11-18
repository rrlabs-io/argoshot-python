from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Sequence, TypedDict, Union

DEFAULT_BASE_URL = "https://api.argoshot.com"
_VERSION = "0.1.0"
_CLIENT_OWN = ("access_key", "signature")

OptionValue = Union[str, int, float, bool, None, Sequence[Union[str, int, float, bool]]]


class TakeOptions(TypedDict, total=False):
    """The common options, typed. Any other option of https://argoshot.com/docs/options is accepted by name."""

    url: str
    html: str
    markdown: str
    format: str
    viewport_width: int
    viewport_height: int
    viewport_device: str
    device_scale_factor: float
    full_page: bool
    block_cookie_banners: bool
    block_ads: bool
    dark_mode: bool
    selector: str
    cache: bool
    cache_ttl: int
    image_quality: int
    delay: int
    timeout: int
    wait_until: List[str]
    hide_selectors: List[str]
    response_type: str
    webhook_url: str


class ArgoshotError(Exception):
    """An error the API answered (its error_code and error_message), or a response that was not the API's."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 0,
        documentation_url: Optional[str] = None,
        upgrade_url: Optional[str] = None,
        returned_status_code: Optional[int] = None,
        matched_string: Optional[str] = None,
        retry_after: Optional[int] = None,
        body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.documentation_url = documentation_url
        self.upgrade_url = upgrade_url
        self.returned_status_code = returned_status_code
        self.matched_string = matched_string
        self.retry_after = retry_after
        self.body = body

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class Argoshot:
    """A client for the Argoshot API.

    >>> client = Argoshot("ACCESS_KEY", secret_key="SECRET_KEY")
    >>> png = client.take(url="https://example.com", format="png")
    >>> og_image = client.url(url="https://example.com", viewport_width=1200, viewport_height=630)
    """

    def __init__(
        self,
        access_key: str,
        secret_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
    ) -> None:
        if not access_key:
            raise ValueError("Argoshot: an access key is required")
        self.access_key = access_key
        self.secret_key = secret_key or None
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    def url(self, options: Optional[Mapping[str, OptionValue]] = None, /, **kwargs: OptionValue) -> str:
        """A GET /take URL for these options (for <img src> or og:image), signed when a secret key is set.

        The access key is in the URL: for public pages, use a key set to "signed requests only".
        """
        query = build_query(_merge(options, kwargs))
        unsigned = (query + "&" if query else "") + "access_key=" + _encode(self.access_key)
        if self.secret_key:
            unsigned += "&signature=" + sign(self.secret_key, unsigned)
        return self.base_url + "/take?" + unsigned

    def take(self, options: Optional[Mapping[str, OptionValue]] = None, /, **kwargs: OptionValue) -> bytes:
        """Render and return the file's bytes. Raises ArgoshotError on failure.

        GET for url captures (signed when a secret key is set); a JSON POST when html or markdown is given.
        Options are the API's names; pass ones that are Python keywords (async) in the dict.
        """
        opts = _clean(_merge(options, kwargs))
        headers = {"X-Access-Key": self.access_key, "User-Agent": "argoshot-python/" + _VERSION}
        if "html" in opts or "markdown" in opts:
            headers["Content-Type"] = "application/json"
            body = json.dumps(opts).encode("utf-8")
            request = urllib.request.Request(self.base_url + "/take", data=body, headers=headers, method="POST")
        else:
            query = build_query(opts)
            if self.secret_key:
                query += "&signature=" + sign(self.secret_key, query)
            request = urllib.request.Request(self.base_url + "/take?" + query, headers=headers, method="GET")
        return self._send(request)

    def usage(self) -> Dict[str, Any]:
        """GET /usage: renders total, available and used, and the plan's limits. Costs nothing."""
        headers = {"X-Access-Key": self.access_key, "User-Agent": "argoshot-python/" + _VERSION}
        request = urllib.request.Request(self.base_url + "/usage", headers=headers, method="GET")
        return json.loads(self._send(request).decode("utf-8"))

    def _send(self, request: urllib.request.Request) -> bytes:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise parse_error(e.code, body, e.headers.get("Retry-After") if e.headers else None) from None


def parse_error(status: int, body: str, retry_after: Optional[str] = None) -> ArgoshotError:
    """An ArgoshotError from an error response's status and body."""
    retry: Optional[int] = None
    if retry_after and str(retry_after).strip().isdigit():
        retry = int(retry_after)
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict) and isinstance(data.get("error_code"), str):
        return ArgoshotError(
            code=data["error_code"],
            message=data.get("error_message") or data["error_code"],
            status=status,
            documentation_url=data.get("documentation_url"),
            upgrade_url=data.get("upgrade_url"),
            returned_status_code=data.get("returned_status_code"),
            matched_string=data.get("matched_string"),
            retry_after=retry,
            body=body,
        )
    snippet = (body or "")[:200]
    return ArgoshotError("http_error", f"HTTP {status}" + (f": {snippet}" if snippet else ""), status, retry_after=retry, body=body)


def build_query(options: Optional[Mapping[str, OptionValue]]) -> str:
    """The query string of these options: names sorted, lists repeated, None left out (no access key)."""
    opts = _clean(options)
    parts = []
    for name in sorted(opts):
        value = opts[name]
        values = value if isinstance(value, (list, tuple)) else [value]
        for v in values:
            if v is None:
                continue
            parts.append(_encode(name) + "=" + _encode(_text(v)))
    return "&".join(parts)


def sign(secret_key: str, query: str) -> str:
    """The signature the API checks: lowercase hex HMAC-SHA256 of the query string, under the secret key."""
    return hmac.new(secret_key.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


def _merge(options: Optional[Mapping[str, OptionValue]], kwargs: Mapping[str, OptionValue]) -> Dict[str, OptionValue]:
    merged: Dict[str, OptionValue] = dict(options or {})
    merged.update(kwargs)
    return merged


def _clean(options: Optional[Mapping[str, OptionValue]]) -> Dict[str, OptionValue]:
    return {k: v for k, v in (options or {}).items() if v is not None and k not in _CLIENT_OWN}


def _text(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _encode(s: str) -> str:
    # RFC 3986: everything but A-Z a-z 0-9 - . _ ~ is percent-encoded (a space is %20, a + is %2B).
    return urllib.parse.quote(s, safe="-._~")
