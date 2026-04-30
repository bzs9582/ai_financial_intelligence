from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from ai_financial_intelligence.clients import (
    BinanceMarketClient,
    DataFetchError,
    EVENT_FEED_SCHEMA_VERSION,
    FredMacroClient,
    TextEventClient,
)
from ai_financial_intelligence.settings import (
    AppSettings,
    DEFAULT_EVENT_FEED_URL,
    ProxyConfig,
)
from ai_financial_intelligence.storage import ReportStore


def build_settings(
    temp_dir: tempfile.TemporaryDirectory[str],
    *,
    event_feed_url: str = "https://example.com/events.json",
) -> AppSettings:
    return AppSettings(
        mock_mode=False,
        proxy=ProxyConfig(enabled=True, url="http://127.0.0.1:4780"),
        database_path=Path(temp_dir.name) / "analysis.db",
        default_asset="BTCUSDT",
        default_timeframe="4h",
        fred_api_key="demo",
        event_feed_url=event_feed_url,
    )


class ProxyConfigTests(unittest.TestCase):
    def test_proxy_kwargs_are_populated_when_enabled(self) -> None:
        config = ProxyConfig(enabled=True, url="http://127.0.0.1:4780")

        self.assertEqual({"proxy": "http://127.0.0.1:4780"}, config.httpx_kwargs())
        self.assertEqual("http://127.0.0.1:4780", config.label())

    def test_proxy_kwargs_are_empty_when_disabled(self) -> None:
        config = ProxyConfig(enabled=False, url="http://127.0.0.1:4780")

        self.assertEqual({}, config.httpx_kwargs())
        self.assertEqual("disabled", config.label())


class DummyResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class RecordingAsyncClient:
    last_kwargs: dict[str, object] | None = None
    calls: list[tuple[str, dict[str, object] | None]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        type(self).last_kwargs = dict(kwargs)
        type(self).calls = []

    async def __aenter__(self) -> "RecordingAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, params: dict[str, object] | None = None) -> DummyResponse:
        type(self).calls.append((url, params))
        if "ticker/24hr" in url:
            return DummyResponse(
                {
                    "lastPrice": "68420.5",
                    "priceChangePercent": "2.84",
                    "quoteVolume": "1658400000",
                    "highPrice": "68950",
                    "lowPrice": "66320",
                }
            )
        if "klines" in url:
            return DummyResponse(
                [
                    [1, "68000", "68600", "67880", "68350", "1200"],
                    [2, "68350", "68950", "68220", "68420.5", "1399"],
                ]
            )
        if "premiumIndex" in url:
            return DummyResponse(
                {
                    "markPrice": "68428.0",
                    "indexPrice": "68420.5",
                    "lastFundingRate": "0.000125",
                    "nextFundingTime": "1712116800000",
                }
            )
        return DummyResponse({"openInterest": "9215000000"})


class FailingAsyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        return None

    async def __aenter__(self) -> "FailingAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, params: dict[str, object] | None = None) -> DummyResponse:
        raise httpx.ConnectTimeout("proxy timeout")


class RecordingFredAsyncClient:
    last_kwargs: dict[str, object] | None = None
    calls: list[tuple[str, dict[str, object] | None]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        type(self).last_kwargs = dict(kwargs)
        type(self).calls = []

    async def __aenter__(self) -> "RecordingFredAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, params: dict[str, object] | None = None) -> DummyResponse:
        type(self).calls.append((url, params))
        return DummyResponse(
            {
                "observations": [
                    {"date": "2026-04-02", "value": "4.33"},
                    {"date": "2026-04-01", "value": "4.31"},
                ]
            }
        )


class UnexpectedCallAsyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        return None

    async def __aenter__(self) -> "UnexpectedCallAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, params: dict[str, object] | None = None) -> DummyResponse:
        raise AssertionError("network call should not happen when cache is fresh")


class RecordingEventAsyncClient:
    payload: object = {}
    last_kwargs: dict[str, object] | None = None
    calls: list[tuple[str, dict[str, object] | None]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        type(self).last_kwargs = dict(kwargs)
        type(self).calls = []

    async def __aenter__(self) -> "RecordingEventAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, params: dict[str, object] | None = None) -> DummyResponse:
        type(self).calls.append((url, params))
        return DummyResponse(type(self).payload)


class BinanceClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_live_uses_proxy_and_normalizes_response(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            client = BinanceMarketClient(build_settings(temp_dir))
            with patch(
                "ai_financial_intelligence.clients.httpx.AsyncClient",
                RecordingAsyncClient,
            ):
                payload = await client.fetch_live("BTCUSDT", "4h")
        finally:
            temp_dir.cleanup()

        self.assertEqual("http://127.0.0.1:4780", RecordingAsyncClient.last_kwargs["proxy"])
        self.assertEqual("live-binance", payload["source"])
        self.assertEqual("BTCUSDT", payload["symbol"])
        self.assertEqual("4h", payload["timeframe"])
        self.assertEqual(2, len(payload["candles"]))
        self.assertEqual(68420.5, payload["last_price"])
        self.assertEqual(68428.0, payload["mark_price"])
        self.assertEqual(68420.5, payload["index_price"])
        self.assertEqual(0.0125, payload["funding_rate"])
        self.assertAlmostEqual(0.01096, payload["basis_pct"], places=5)
        self.assertEqual("1712116800000", payload["next_funding_time"])
        self.assertEqual(
            "https://fapi.binance.com/fapi/v1/premiumIndex",
            RecordingAsyncClient.calls[3][0],
        )

    async def test_fetch_live_failure_includes_proxy_and_endpoint_context(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            client = BinanceMarketClient(build_settings(temp_dir))
            with patch(
                "ai_financial_intelligence.clients.httpx.AsyncClient",
                FailingAsyncClient,
            ):
                with self.assertRaises(DataFetchError) as exc_info:
                    await client.fetch_live("BTCUSDT", "4h")
        finally:
            temp_dir.cleanup()

        message = str(exc_info.exception)
        self.assertIn("BTCUSDT 4h", message)
        self.assertIn("https://api.binance.com/api/v3/ticker/24hr", message)
        self.assertIn("proxy http://127.0.0.1:4780", message)
        self.assertIn("ConnectTimeout", message)
        self.assertIn("AI_FI_HTTP_PROXY", message)


class FredClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_live_requests_fred_endpoint_and_populates_cache(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            settings = build_settings(temp_dir)
            store = ReportStore(settings.database_path)
            client = FredMacroClient(settings, store=store)
            with patch(
                "ai_financial_intelligence.clients.httpx.AsyncClient",
                RecordingFredAsyncClient,
            ):
                payload = await client.fetch_live()
            cached = store.load_macro_cache("DFF")
        finally:
            temp_dir.cleanup()

        self.assertEqual("http://127.0.0.1:4780", RecordingFredAsyncClient.last_kwargs["proxy"])
        self.assertEqual(1, len(RecordingFredAsyncClient.calls))
        self.assertEqual(
            "https://api.stlouisfed.org/fred/series/observations",
            RecordingFredAsyncClient.calls[0][0],
        )
        self.assertEqual("DFF", RecordingFredAsyncClient.calls[0][1]["series_id"])
        self.assertEqual("demo", RecordingFredAsyncClient.calls[0][1]["api_key"])
        self.assertEqual("live-fred", payload["source"])
        self.assertEqual("higher", payload["trend"])
        self.assertEqual("2026-04-02", payload["updated_at"])
        self.assertIsNotNone(cached)
        self.assertEqual(4.33, cached["payload"]["latest_value"])

    async def test_fetch_live_uses_fresh_cache_before_hitting_network(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            settings = build_settings(temp_dir)
            store = ReportStore(settings.database_path)
            store.save_macro_cache(
                series="DFF",
                cached_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
                payload={
                    "series": "DFF",
                    "name": "Effective Federal Funds Rate",
                    "latest_value": 4.25,
                    "previous_value": 4.25,
                    "unit": "%",
                    "trend": "flat",
                    "updated_at": "2026-04-02",
                    "source": "live-fred",
                },
            )
            client = FredMacroClient(settings, store=store)
            with patch(
                "ai_financial_intelligence.clients.httpx.AsyncClient",
                UnexpectedCallAsyncClient,
            ):
                payload = await client.fetch_live()
        finally:
            temp_dir.cleanup()

        self.assertEqual("cache-fred", payload["source"])
        self.assertEqual(4.25, payload["latest_value"])


class TextEventClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_live_accepts_ai_fi_event_feed_v1_payload(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            settings = build_settings(temp_dir)
            client = TextEventClient(settings)
            RecordingEventAsyncClient.payload = {
                "schema_version": EVENT_FEED_SCHEMA_VERSION,
                "generated_at": "2026-04-03T10:00:00Z",
                "source": {
                    "name": "Unit Test Feed",
                    "url": "https://example.com/events.json",
                },
                "events": [
                    {
                        "headline": "ETF inflows remain strong",
                        "impact": "positive",
                        "confidence": "high",
                        "published_at": "2026-04-03T09:45:00Z",
                        "url": "https://example.com/etf",
                        "symbols": ["btcusdt", "ethusdt"],
                    }
                ],
            }
            with patch(
                "ai_financial_intelligence.clients.httpx.AsyncClient",
                RecordingEventAsyncClient,
            ):
                payload = await client.fetch_live()
        finally:
            temp_dir.cleanup()

        self.assertEqual("http://127.0.0.1:4780", RecordingEventAsyncClient.last_kwargs["proxy"])
        self.assertEqual(
            "ai-financial-intelligence-platform/0.1",
            RecordingEventAsyncClient.last_kwargs["headers"]["User-Agent"],
        )
        self.assertEqual("ETF inflows remain strong", payload[0]["headline"])
        self.assertEqual("positive", payload[0]["impact"])
        self.assertEqual("high", payload[0]["confidence"])
        self.assertEqual("Unit Test Feed", payload[0]["source"])
        self.assertEqual(["BTCUSDT", "ETHUSDT"], payload[0]["symbols"])

    async def test_fetch_live_normalizes_rss_to_json_payload_from_default_feed(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            settings = build_settings(temp_dir, event_feed_url=DEFAULT_EVENT_FEED_URL)
            client = TextEventClient(settings)
            RecordingEventAsyncClient.payload = {
                "status": "ok",
                "feed": {
                    "title": "CoinDesk: Bitcoin, Ethereum, Crypto News and Price Data",
                    "link": "https://www.coindesk.com/",
                },
                "items": [
                    {
                        "title": "ETF inflows spark fresh bitcoin rally",
                        "pubDate": "2026-04-03 13:18:50",
                        "link": "https://www.coindesk.com/example-story",
                        "description": "<p>Spot ETF inflows accelerated again.</p>",
                        "categories": ["Markets", "News"],
                    }
                ],
            }
            with patch(
                "ai_financial_intelligence.clients.httpx.AsyncClient",
                RecordingEventAsyncClient,
            ):
                payload = await client.fetch_live()
        finally:
            temp_dir.cleanup()

        self.assertEqual(DEFAULT_EVENT_FEED_URL, RecordingEventAsyncClient.calls[0][0])
        self.assertEqual("positive", payload[0]["impact"])
        self.assertEqual("low", payload[0]["confidence"])
        self.assertEqual(
            "CoinDesk: Bitcoin, Ethereum, Crypto News and Price Data",
            payload[0]["source"],
        )
        self.assertEqual("2026-04-03 13:18:50", payload[0]["published_at"])
        self.assertEqual("https://www.coindesk.com/example-story", payload[0]["url"])


class AppSettingsTests(unittest.TestCase):
    def test_from_env_uses_default_live_event_feed_url(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AI_FI_MOCK_MODE": "0",
                "FRED_API_KEY": "demo",
            },
            clear=True,
        ):
            settings = AppSettings.from_env()

        self.assertEqual(DEFAULT_EVENT_FEED_URL, settings.event_feed_url)


if __name__ == "__main__":
    unittest.main()
