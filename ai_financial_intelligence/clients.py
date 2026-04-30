from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import unescape
import json
from pathlib import Path
import re
from typing import Any

import httpx

from .settings import AppSettings, DEFAULT_EVENT_FEED_URL
from .storage import ReportStore


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
FRED_SERIES_ID = "DFF"
FRED_CACHE_TTL = timedelta(hours=12)
EVENT_FEED_SCHEMA_VERSION = "ai-fi-event-feed/v1"
EVENT_FEED_USER_AGENT = "ai-financial-intelligence-platform/0.1"
EVENT_IMPACTS = {"positive", "negative", "neutral"}
EVENT_CONFIDENCE_LEVELS = {"low", "medium", "high"}
POSITIVE_EVENT_KEYWORDS = (
    "approval",
    "approves",
    "approved",
    "bullish",
    "gain",
    "gains",
    "inflow",
    "launch",
    "rally",
    "rebound",
    "surge",
)
NEGATIVE_EVENT_KEYWORDS = (
    "ban",
    "bearish",
    "decline",
    "drop",
    "exploit",
    "hack",
    "liquidation",
    "lawsuit",
    "outflow",
    "sell-off",
    "slump",
)


class DataFetchError(RuntimeError):
    """Raised when live data collection fails."""


def load_json_fixture(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(unescape(text).split())


def _normalize_event_source_name(
    value: Any,
    *,
    default: Any = None,
) -> str | None:
    for candidate in (value, default):
        if isinstance(candidate, dict):
            name = str(
                candidate.get("name")
                or candidate.get("title")
                or candidate.get("author")
                or ""
            ).strip()
            if name:
                return name
        elif candidate is not None:
            name = str(candidate).strip()
            if name:
                return name
    return None


def _normalize_event_symbols(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    symbols: list[str] = []
    for item in value:
        normalized = str(item).strip().upper()
        if normalized:
            symbols.append(normalized)
    return symbols


def _infer_event_impact(*texts: str) -> str:
    haystack = " ".join(texts).lower()
    positive = any(keyword in haystack for keyword in POSITIVE_EVENT_KEYWORDS)
    negative = any(keyword in haystack for keyword in NEGATIVE_EVENT_KEYWORDS)
    if positive == negative:
        return "neutral"
    return "positive" if positive else "negative"


def _normalize_event_impact(
    value: Any,
    *,
    heuristic_texts: tuple[str, ...] = (),
) -> tuple[str, bool]:
    raw = str(value or "").strip().lower()
    if raw in {"positive", "bullish"}:
        return "positive", False
    if raw in {"negative", "bearish"}:
        return "negative", False
    if raw in {"neutral", "balanced", "mixed"}:
        return "neutral", False
    if heuristic_texts:
        return _infer_event_impact(*heuristic_texts), True
    return "neutral", False


def _normalize_event_confidence(value: Any, *, inferred: bool) -> str:
    raw = str(value or "").strip().lower()
    if raw in EVENT_CONFIDENCE_LEVELS:
        return raw
    return "low" if inferred else "medium"


def _normalize_event_item(
    item: dict[str, Any],
    *,
    default_source: Any = None,
    use_heuristic_impact: bool = False,
) -> dict[str, Any] | None:
    headline = _clean_text(item.get("headline") or item.get("title"))
    if not headline:
        return None

    categories = [
        _clean_text(category)
        for category in item.get("categories", [])
        if _clean_text(category)
    ]
    impact, inferred = _normalize_event_impact(
        item.get("impact"),
        heuristic_texts=(headline, *categories) if use_heuristic_impact else (),
    )
    if impact not in EVENT_IMPACTS:
        impact = "neutral"

    normalized: dict[str, Any] = {
        "headline": headline,
        "impact": impact,
        "confidence": _normalize_event_confidence(
            item.get("confidence"),
            inferred=inferred,
        ),
    }

    published_at = _clean_text(
        item.get("published_at") or item.get("pubDate") or item.get("published")
    )
    if published_at:
        normalized["published_at"] = published_at

    url = _clean_text(item.get("url") or item.get("link"))
    if url:
        normalized["url"] = url

    summary = _clean_text(item.get("summary") or item.get("description"))
    if summary:
        normalized["summary"] = summary

    source_name = _normalize_event_source_name(item.get("source"), default=default_source)
    if source_name:
        normalized["source"] = source_name

    symbols = _normalize_event_symbols(item.get("symbols"))
    if symbols:
        normalized["symbols"] = symbols

    return normalized


def _normalize_event_list(
    payload: Any,
    *,
    default_source: Any = None,
    use_heuristic_impact: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise DataFetchError("event feed events must be a list")

    events: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_event_item(
            item,
            default_source=default_source,
            use_heuristic_impact=use_heuristic_impact,
        )
        if normalized:
            events.append(normalized)
    if not events:
        raise DataFetchError("event feed did not return any usable events")
    return events


def _normalize_event_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return _normalize_event_list(payload)

    if not isinstance(payload, dict):
        raise DataFetchError(
            "event feed payload must match ai-fi-event-feed/v1 or rss2json format"
        )

    schema_version = str(payload.get("schema_version", "")).strip()
    if schema_version:
        if schema_version != EVENT_FEED_SCHEMA_VERSION:
            raise DataFetchError(
                f"event feed schema_version must be {EVENT_FEED_SCHEMA_VERSION}"
            )
        return _normalize_event_list(
            payload.get("events"),
            default_source=payload.get("source"),
        )

    if "feed" in payload and "items" in payload:
        return _normalize_event_list(
            payload.get("items"),
            default_source=payload.get("feed"),
            use_heuristic_impact=True,
        )

    if "events" in payload:
        return _normalize_event_list(
            payload.get("events"),
            default_source=payload.get("source"),
        )

    raise DataFetchError(
        "event feed payload must match ai-fi-event-feed/v1 or rss2json format"
    )


class BinanceMarketClient:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def _connection_target(self) -> str:
        proxy_label = self.settings.proxy.label()
        if proxy_label == "disabled":
            return "direct network path"
        return f"proxy {proxy_label}"

    def _build_request_error(
        self,
        *,
        exc: httpx.HTTPError,
        asset: str,
        timeframe: str,
        url: str,
    ) -> DataFetchError:
        detail = (
            f"Binance request failed for {asset} {timeframe} at {url} via "
            f"{self._connection_target()} ({exc.__class__.__name__}): {exc}"
        )
        if self.settings.proxy.enabled and self.settings.proxy.url:
            detail += " Check AI_FI_HTTP_PROXY or disable AI_FI_USE_PROXY for direct access."
        return DataFetchError(detail)

    def fixture(self, asset: str, timeframe: str) -> dict[str, Any]:
        payload = load_json_fixture("market_snapshot.json")
        payload["symbol"] = asset
        payload["timeframe"] = timeframe
        payload["source"] = "fixture-binance"
        return payload

    async def fetch_live(self, asset: str, timeframe: str) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=10.0, **self.settings.proxy.httpx_kwargs()
        ) as client:
            try:
                ticker_response = await client.get(
                    "https://api.binance.com/api/v3/ticker/24hr",
                    params={"symbol": asset},
                )
                ticker_response.raise_for_status()
            except httpx.HTTPError as exc:
                raise self._build_request_error(
                    exc=exc,
                    asset=asset,
                    timeframe=timeframe,
                    url="https://api.binance.com/api/v3/ticker/24hr",
                ) from exc

            try:
                candles_response = await client.get(
                    "https://api.binance.com/api/v3/klines",
                    params={"symbol": asset, "interval": timeframe, "limit": 12},
                )
                candles_response.raise_for_status()
            except httpx.HTTPError as exc:
                raise self._build_request_error(
                    exc=exc,
                    asset=asset,
                    timeframe=timeframe,
                    url="https://api.binance.com/api/v3/klines",
                ) from exc

            try:
                open_interest_response = await client.get(
                    "https://fapi.binance.com/fapi/v1/openInterest",
                    params={"symbol": asset},
                )
                open_interest_response.raise_for_status()
            except httpx.HTTPError as exc:
                raise self._build_request_error(
                    exc=exc,
                    asset=asset,
                    timeframe=timeframe,
                    url="https://fapi.binance.com/fapi/v1/openInterest",
                ) from exc

            try:
                premium_index_response = await client.get(
                    "https://fapi.binance.com/fapi/v1/premiumIndex",
                    params={"symbol": asset},
                )
                premium_index_response.raise_for_status()
            except httpx.HTTPError as exc:
                raise self._build_request_error(
                    exc=exc,
                    asset=asset,
                    timeframe=timeframe,
                    url="https://fapi.binance.com/fapi/v1/premiumIndex",
                ) from exc

        ticker = ticker_response.json()
        candles = candles_response.json()
        open_interest = open_interest_response.json()
        premium_index = premium_index_response.json()

        normalized_candles: list[dict[str, Any]] = []
        for candle in candles:
            normalized_candles.append(
                {
                    "open_time": candle[0],
                    "open": _to_float(candle[1]),
                    "high": _to_float(candle[2]),
                    "low": _to_float(candle[3]),
                    "close": _to_float(candle[4]),
                    "volume": _to_float(candle[5]),
                }
            )

        mark_price = _to_float(premium_index.get("markPrice"))
        index_price = _to_float(premium_index.get("indexPrice"))

        return {
            "symbol": asset,
            "timeframe": timeframe,
            "last_price": _to_float(ticker.get("lastPrice")),
            "change_pct_24h": _to_float(ticker.get("priceChangePercent")),
            "quote_volume": _to_float(ticker.get("quoteVolume")),
            "high_price": _to_float(ticker.get("highPrice")),
            "low_price": _to_float(ticker.get("lowPrice")),
            "open_interest": _to_float(open_interest.get("openInterest")),
            "mark_price": mark_price,
            "index_price": index_price,
            "basis_pct": _to_float(
                ((mark_price - index_price) / index_price) * 100 if index_price else 0.0
            ),
            "funding_rate": _to_float(premium_index.get("lastFundingRate")) * 100,
            "next_funding_time": str(premium_index.get("nextFundingTime") or ""),
            "candles": normalized_candles,
            "source": "live-binance",
        }


class FredMacroClient:
    def __init__(
        self,
        settings: AppSettings,
        *,
        store: ReportStore | None = None,
        cache_ttl: timedelta = FRED_CACHE_TTL,
    ) -> None:
        self.settings = settings
        self.store = store
        self.cache_ttl = cache_ttl

    def fixture(self) -> dict[str, Any]:
        payload = load_json_fixture("macro_snapshot.json")
        payload["source"] = "fixture-fred"
        return payload

    def _load_fresh_cache(self) -> dict[str, Any] | None:
        if self.store is None:
            return None

        cached = self.store.load_macro_cache(FRED_SERIES_ID)
        if cached is None:
            return None

        try:
            cached_at = datetime.fromisoformat(str(cached["cached_at"]))
        except ValueError:
            return None

        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=UTC)

        if datetime.now(UTC) - cached_at > self.cache_ttl:
            return None

        payload = dict(cached["payload"])
        payload["source"] = "cache-fred"
        return payload

    def _save_cache(self, payload: dict[str, Any]) -> None:
        if self.store is None:
            return
        self.store.save_macro_cache(
            series=FRED_SERIES_ID,
            cached_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            payload=payload,
        )

    async def fetch_live(self) -> dict[str, Any]:
        cached_payload = self._load_fresh_cache()
        if cached_payload is not None:
            return cached_payload

        if not self.settings.fred_api_key:
            raise DataFetchError("FRED_API_KEY is not configured")

        try:
            async with httpx.AsyncClient(
                timeout=10.0, **self.settings.proxy.httpx_kwargs()
            ) as client:
                response = await client.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": FRED_SERIES_ID,
                        "api_key": self.settings.fred_api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 2,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DataFetchError(f"FRED request failed: {exc}") from exc

        observations = [
            item
            for item in response.json().get("observations", [])
            if item.get("value") not in {"", "."}
        ]
        if len(observations) < 2:
            raise DataFetchError("FRED returned insufficient observations")

        latest, previous = observations[0], observations[1]
        latest_value = _to_float(latest.get("value"))
        previous_value = _to_float(previous.get("value"))
        trend = (
            "higher"
            if latest_value > previous_value
            else "lower"
            if latest_value < previous_value
            else "flat"
        )

        payload = {
            "series": FRED_SERIES_ID,
            "name": "Effective Federal Funds Rate",
            "latest_value": latest_value,
            "previous_value": previous_value,
            "unit": "%",
            "trend": trend,
            "updated_at": latest.get("date"),
            "source": "live-fred",
        }
        self._save_cache(payload)
        return payload


class TextEventClient:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def fixture(self) -> list[dict[str, Any]]:
        payload = load_json_fixture("events_snapshot.json")
        normalized: list[dict[str, Any]] = []
        for item in payload:
            normalized.append(
                {
                    "headline": str(item.get("headline", "")).strip(),
                    "impact": str(item.get("impact", "neutral")).strip().lower(),
                    "confidence": str(item.get("confidence", "medium"))
                    .strip()
                    .lower(),
                }
            )
        return normalized

    async def fetch_live(self) -> list[dict[str, Any]]:
        if not self.settings.event_feed_url:
            raise DataFetchError("AI_FI_EVENT_FEED_URL is not configured")

        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": EVENT_FEED_USER_AGENT},
                **self.settings.proxy.httpx_kwargs(),
            ) as client:
                response = await client.get(self.settings.event_feed_url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            endpoint_label = self.settings.event_feed_url or DEFAULT_EVENT_FEED_URL
            raise DataFetchError(
                f"event feed request failed for {endpoint_label}: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise DataFetchError(
                f"event feed returned invalid JSON from {self.settings.event_feed_url}"
            ) from exc
        return _normalize_event_payload(payload)
