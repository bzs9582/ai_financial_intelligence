from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from .responses import HTMLResponse, Response


Handler = Callable[["Request"], Awaitable[Any]]


@dataclass(slots=True)
class _Route:
    method: str
    path: str
    handler: Handler
    response_class: type[Response] | None


class Request:
    def __init__(self, app: "FastAPI", scope: dict[str, Any], body: bytes) -> None:
        self.app = app
        self.scope = scope
        self._body = body

    async def body(self) -> bytes:
        return self._body


class FastAPI:
    def __init__(self, *, title: str = "") -> None:
        self.title = title
        self.state = SimpleNamespace()
        self._routes: dict[tuple[str, str], _Route] = {}

    def get(
        self,
        path: str,
        *,
        response_class: type[Response] | None = None,
    ) -> Callable[[Handler], Handler]:
        return self._register("GET", path, response_class)

    def post(
        self,
        path: str,
        *,
        response_class: type[Response] | None = None,
    ) -> Callable[[Handler], Handler]:
        return self._register("POST", path, response_class)

    def _register(
        self,
        method: str,
        path: str,
        response_class: type[Response] | None,
    ) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self._routes[(method, path)] = _Route(
                method=method,
                path=path,
                handler=handler,
                response_class=response_class,
            )
            return handler

        return decorator

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            raise RuntimeError("Only HTTP scopes are supported by the bootstrap shim.")

        route = self._routes.get((str(scope.get("method", "")).upper(), scope.get("path", "")))
        if route is None:
            response = HTMLResponse("Not Found", status_code=404)
            await response(scope, receive, send)
            return

        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            more_body = bool(message.get("more_body", False))

        request = Request(self, scope, body)
        result = await route.handler(request)

        if isinstance(result, Response):
            response = result
        elif route.response_class is not None:
            response = route.response_class(result)
        else:
            response = HTMLResponse(result)

        await response(scope, receive, send)


__all__ = ["FastAPI", "HTMLResponse", "Request", "Response"]
