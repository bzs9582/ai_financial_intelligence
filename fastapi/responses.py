from __future__ import annotations

from typing import Iterable


HeaderIterable = Iterable[tuple[bytes, bytes]]


class Response:
    media_type = "text/plain; charset=utf-8"

    def __init__(
        self,
        content: str | bytes = b"",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        if isinstance(content, bytes):
            body = content
        else:
            body = str(content).encode("utf-8")

        self.body = body
        self.status_code = status_code
        self.headers = {
            "content-length": str(len(body)),
            "content-type": media_type or self.media_type,
        }
        if headers:
            for key, value in headers.items():
                self.headers[key.lower()] = value

    @property
    def raw_headers(self) -> HeaderIterable:
        return [
            (key.encode("latin-1"), value.encode("latin-1"))
            for key, value in self.headers.items()
        ]

    async def __call__(self, scope, receive, send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": list(self.raw_headers),
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": self.body,
                "more_body": False,
            }
        )


class HTMLResponse(Response):
    media_type = "text/html; charset=utf-8"
