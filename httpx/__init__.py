from __future__ import annotations

import asyncio
import json
import socket
from typing import Any
from urllib.error import HTTPError as UrllibHTTPError
from urllib.error import URLError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import ProxyHandler, Request as UrllibRequest, build_opener


class HTTPError(Exception):
    """Base HTTP client exception used by the bootstrap shim."""


class ConnectTimeout(HTTPError):
    """Raised when the client cannot connect before the timeout."""


class HTTPStatusError(HTTPError):
    def __init__(self, message: str, response: "Response") -> None:
        super().__init__(message)
        self.response = response


class Response:
    def __init__(
        self,
        *,
        status_code: int,
        content: bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPStatusError(
                f"HTTP request failed with status {self.status_code}",
                response=self,
            )


class ASGITransport:
    def __init__(self, *, app) -> None:
        self.app = app

    async def handle_async_request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        content: bytes = b"",
    ) -> Response:
        parsed = urlsplit(url)
        response_status = 500
        response_headers: list[tuple[bytes, bytes]] = []
        response_body = bytearray()
        request_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal request_sent
            if request_sent:
                return {"type": "http.disconnect"}
            request_sent = True
            return {
                "type": "http.request",
                "body": content,
                "more_body": False,
            }

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_status, response_headers
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
                response_headers = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": parsed.scheme or "http",
            "path": parsed.path or "/",
            "raw_path": (parsed.path or "/").encode("utf-8"),
            "query_string": parsed.query.encode("utf-8"),
            "headers": [
                (key.lower().encode("latin-1"), value.encode("latin-1"))
                for key, value in (headers or {}).items()
            ],
            "client": ("127.0.0.1", 0),
            "server": (parsed.hostname or "testserver", parsed.port or 80),
            "root_path": "",
        }

        await self.app(scope, receive, send)

        return Response(
            status_code=response_status,
            content=bytes(response_body),
            headers={
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in response_headers
            },
        )


class AsyncClient:
    def __init__(
        self,
        *,
        transport: ASGITransport | None = None,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        proxy: str | None = None,
    ) -> None:
        self.transport = transport
        self.base_url = base_url
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.proxy = proxy

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Response:
        return await self.request("GET", url, params=params)

    async def post(
        self,
        url: str,
        *,
        data: dict[str, Any] | str | bytes | None = None,
    ) -> Response:
        return await self.request("POST", url, data=data)

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | str | bytes | None = None,
    ) -> Response:
        full_url = self._build_url(url, params=params)
        headers = dict(self.headers)
        content = self._encode_body(data, headers=headers)

        if self.transport is not None:
            return await self.transport.handle_async_request(
                method,
                full_url,
                headers=headers,
                content=content,
            )

        return await asyncio.to_thread(
            self._request_via_urllib,
            method,
            full_url,
            headers,
            content,
        )

    def _build_url(self, url: str, *, params: dict[str, Any] | None = None) -> str:
        if self.base_url and not urlsplit(url).scheme:
            base = self.base_url if self.base_url.endswith("/") else f"{self.base_url}/"
            target = url.lstrip("/")
            url = urljoin(base, target)

        if not params:
            return url

        parsed = urlsplit(url)
        query_items: list[tuple[str, Any]] = []
        if parsed.query:
            for pair in parsed.query.split("&"):
                if not pair:
                    continue
                key, _, value = pair.partition("=")
                query_items.append((key, value))
        query_items.extend(params.items())
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query_items, doseq=True),
                parsed.fragment,
            )
        )

    def _encode_body(
        self,
        data: dict[str, Any] | str | bytes | None,
        *,
        headers: dict[str, str],
    ) -> bytes:
        if data is None:
            return b""
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            if not any(key.lower() == "content-type" for key in headers):
                headers["Content-Type"] = "text/plain; charset=utf-8"
            return data.encode("utf-8")

        if not any(key.lower() == "content-type" for key in headers):
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        return urlencode(data, doseq=True).encode("utf-8")

    def _request_via_urllib(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        content: bytes,
    ) -> Response:
        request = UrllibRequest(
            url=url,
            data=content if method.upper() != "GET" else None,
            headers=headers,
            method=method.upper(),
        )
        handlers = [ProxyHandler({"http": self.proxy, "https": self.proxy})] if self.proxy else []
        opener = build_opener(*handlers)
        timeout = self.timeout if self.timeout is not None else None

        try:
            with opener.open(request, timeout=timeout) as remote_response:
                return Response(
                    status_code=int(remote_response.status),
                    content=remote_response.read(),
                    headers=dict(remote_response.headers.items()),
                )
        except UrllibHTTPError as exc:
            return Response(
                status_code=int(exc.code),
                content=exc.read(),
                headers=dict(exc.headers.items()),
            )
        except URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise ConnectTimeout(str(exc.reason)) from exc
            raise HTTPError(str(exc.reason)) from exc
        except TimeoutError as exc:
            raise ConnectTimeout(str(exc)) from exc


__all__ = [
    "ASGITransport",
    "AsyncClient",
    "ConnectTimeout",
    "HTTPError",
    "HTTPStatusError",
    "Response",
]
