from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_EVENT_FEED_URL = (
    "https://api.rss2json.com/v1/api.json"
    "?rss_url=https://www.coindesk.com/arc/outboundfeeds/rss/"
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class ProxyConfig:
    enabled: bool
    url: str | None

    @classmethod
    def from_env(cls) -> "ProxyConfig":
        enabled = env_flag("AI_FI_USE_PROXY", True)
        raw_url = os.getenv("AI_FI_HTTP_PROXY", "http://127.0.0.1:4780").strip()
        url = raw_url if enabled and raw_url else None
        return cls(enabled=enabled, url=url)

    def httpx_kwargs(self) -> dict[str, str]:
        if not self.enabled or not self.url:
            return {}
        return {"proxy": self.url}

    def label(self) -> str:
        if not self.enabled or not self.url:
            return "disabled"
        return self.url


@dataclass(slots=True)
class AppSettings:
    mock_mode: bool
    proxy: ProxyConfig
    database_path: Path
    default_asset: str
    default_timeframe: str
    fred_api_key: str | None
    event_feed_url: str | None

    @classmethod
    def from_env(cls) -> "AppSettings":
        raw_event_feed_url = os.getenv(
            "AI_FI_EVENT_FEED_URL",
            DEFAULT_EVENT_FEED_URL,
        ).strip()
        return cls(
            mock_mode=env_flag("AI_FI_MOCK_MODE", True),
            proxy=ProxyConfig.from_env(),
            database_path=Path(
                os.getenv(
                    "AI_FI_DATABASE_PATH",
                    str(repo_root() / "data" / "analysis.db"),
                )
            ),
            default_asset=os.getenv("AI_FI_DEFAULT_ASSET", "BTCUSDT").strip().upper(),
            default_timeframe=os.getenv("AI_FI_DEFAULT_TIMEFRAME", "4h")
            .strip()
            .lower(),
            fred_api_key=os.getenv("FRED_API_KEY"),
            event_feed_url=raw_event_feed_url or None,
        )
