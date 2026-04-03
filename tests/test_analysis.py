from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from ai_financial_intelligence.analysis import AnalysisService, DISCLAIMER, build_report
from ai_financial_intelligence.clients import BinanceMarketClient, DataFetchError
from ai_financial_intelligence.indicators import calculate_market_indicators
from ai_financial_intelligence.settings import AppSettings, ProxyConfig


def build_settings(temp_dir: tempfile.TemporaryDirectory[str], *, mock_mode: bool) -> AppSettings:
    return AppSettings(
        mock_mode=mock_mode,
        proxy=ProxyConfig(enabled=True, url="http://127.0.0.1:4780"),
        database_path=Path(temp_dir.name) / "analysis.db",
        default_asset="BTCUSDT",
        default_timeframe="4h",
        fred_api_key=None,
        event_feed_url=None,
    )


def build_report_intelligence(
    *,
    market: dict[str, float] | None = None,
    macro: dict[str, object] | None = None,
    indicators: dict[str, object] | None = None,
    event_summary: dict[str, object] | None = None,
    source_statuses: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "asset": "BTCUSDT",
        "timeframe": "4h",
        "generated_at": "2026-04-03T10:00:00+00:00",
        "snapshot_summary": "Unit test snapshot",
        "market": {
            "change_pct_24h": 2.5,
            "quote_volume": 1_250_000_000.0,
            "open_interest": 9_200_000_000.0,
            **(market or {}),
        },
        "macro": {
            "name": "Effective Federal Funds Rate",
            "latest_value": 4.25,
            "unit": "%",
            "trend": "lower",
            **(macro or {}),
        },
        "indicators": {
            "trend": "bullish",
            "momentum_pct": 4.8,
            "price_vs_slow_sma_pct": 3.2,
            "average_range_pct": 1.1,
            "sma_slow": 101.5,
            "volatility_regime": "calm",
            **(indicators or {}),
        },
        "event_summary": {
            "bias": "positive",
            "negative_count": 0,
            **(event_summary or {}),
        },
        "source_statuses": source_statuses
        or [
            {"name": "Binance market", "mode": "live", "detail": "Live request succeeded."},
            {"name": "FRED macro", "mode": "live", "detail": "Live request succeeded."},
            {"name": "Event feed", "mode": "live", "detail": "Live request succeeded."},
        ],
    }


class IndicatorTests(unittest.TestCase):
    def test_market_indicators_return_defaults_when_candles_are_missing(self) -> None:
        indicators = calculate_market_indicators({})

        self.assertEqual(0.0, indicators["last_close"])
        self.assertEqual(0.0, indicators["sma_fast"])
        self.assertEqual(0.0, indicators["sma_slow"])
        self.assertEqual(0.0, indicators["momentum_pct"])
        self.assertEqual("neutral", indicators["trend"])
        self.assertEqual("calm", indicators["volatility_regime"])

    def test_market_indicators_are_computed_without_pandas_ta(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            market = BinanceMarketClient(build_settings(temp_dir, mock_mode=True)).fixture(
                "BTCUSDT", "4h"
            )
        finally:
            temp_dir.cleanup()

        indicators = calculate_market_indicators(market)

        self.assertGreater(indicators["sma_fast"], 0)
        self.assertGreater(indicators["sma_slow"], 0)
        self.assertIn(indicators["trend"], {"bullish", "bearish", "neutral"})
        self.assertIn(indicators["volatility_regime"], {"calm", "moderate", "high"})

    def test_market_indicators_compute_expected_values_for_bullish_series(self) -> None:
        market = {
            "candles": [
                {"close": 100.0, "high": 102.0, "low": 98.0},
                {"close": 102.0, "high": 104.04, "low": 99.96},
                {"close": 104.0, "high": 106.08, "low": 101.92},
                {"close": 106.0, "high": 108.12, "low": 103.88},
                {"close": 108.0, "high": 110.16, "low": 105.84},
                {"close": 110.0, "high": 112.2, "low": 107.8},
            ]
        }

        indicators = calculate_market_indicators(market)

        self.assertEqual(110.0, indicators["last_close"])
        self.assertEqual(108.0, indicators["sma_fast"])
        self.assertEqual(105.0, indicators["sma_slow"])
        self.assertEqual(10.0, indicators["momentum_pct"])
        self.assertEqual(4.76, indicators["price_vs_slow_sma_pct"])
        self.assertEqual(4.0, indicators["average_range_pct"])
        self.assertEqual("bullish", indicators["trend"])
        self.assertEqual("high", indicators["volatility_regime"])

    def test_market_indicators_treat_non_positive_price_data_as_neutral(self) -> None:
        market = {
            "candles": [
                {"close": 0.0, "high": 0.0, "low": 0.0},
                {"close": 0.0, "high": 0.0, "low": 0.0},
                {"close": 0.0, "high": 0.0, "low": 0.0},
            ]
        }

        indicators = calculate_market_indicators(market)

        self.assertEqual(0.0, indicators["momentum_pct"])
        self.assertEqual(0.0, indicators["price_vs_slow_sma_pct"])
        self.assertEqual("neutral", indicators["trend"])
        self.assertEqual("calm", indicators["volatility_regime"])


class ReportProbabilityTests(unittest.TestCase):
    def test_build_report_clamps_constructive_inputs_to_bullish_skew(self) -> None:
        report = build_report(build_report_intelligence())
        probabilities = {
            item["scenario"]: item["probability"]
            for item in report["scenario_probabilities"]
        }

        self.assertEqual(100, sum(probabilities.values()))
        self.assertEqual(70, probabilities["bullish continuation"])
        self.assertEqual(15, probabilities["balanced range"])
        self.assertEqual(15, probabilities["bearish reversal"])
        self.assertEqual("bullish", report["peter"]["stance"])
        self.assertEqual("bullish", report["venturus"]["stance"])
        self.assertEqual("bullish", report["pivot"]["stance"])
        self.assertEqual("stable", report["reality_check"]["stance"])

    def test_build_report_shifts_probability_toward_bearish_case_when_risk_rises(self) -> None:
        report = build_report(
            build_report_intelligence(
                market={"change_pct_24h": -3.8},
                macro={"trend": "higher"},
                indicators={
                    "trend": "bearish",
                    "momentum_pct": -5.4,
                    "price_vs_slow_sma_pct": -4.1,
                    "average_range_pct": 3.9,
                    "sma_slow": 99.4,
                    "volatility_regime": "high",
                },
                event_summary={"bias": "negative", "negative_count": 3},
                source_statuses=[
                    {
                        "name": "Binance market",
                        "mode": "fixture-fallback",
                        "detail": "Binance request failed.",
                    },
                    {
                        "name": "FRED macro",
                        "mode": "live",
                        "detail": "Live request succeeded.",
                    },
                    {
                        "name": "Event feed",
                        "mode": "fixture-fallback",
                        "detail": "Event feed request failed.",
                    },
                ],
            )
        )
        probabilities = {
            item["scenario"]: item["probability"]
            for item in report["scenario_probabilities"]
        }

        self.assertEqual(100, sum(probabilities.values()))
        self.assertEqual(20, probabilities["bullish continuation"])
        self.assertEqual(20, probabilities["balanced range"])
        self.assertEqual(60, probabilities["bearish reversal"])
        self.assertEqual("guarded", report["reality_check"]["stance"])
        self.assertTrue(
            any("2 fixture fallback(s)" in note for note in report["risk_notes"])
        )
        self.assertEqual(DISCLAIMER, report["risk_notes"][-1])


class AnalysisServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_run_analysis_builds_report_and_persists_latest_result(self) -> None:
        service = AnalysisService(build_settings(self.temp_dir, mock_mode=True))

        result = await service.run_analysis("BTCUSDT", "4h")
        report = result["report"]
        latest = service.latest_result()

        self.assertEqual("BTCUSDT", report["asset"])
        self.assertEqual("4h", report["timeframe"])
        self.assertEqual(100, sum(item["probability"] for item in report["scenario_probabilities"]))
        self.assertTrue(report["bull_case"])
        self.assertTrue(report["bear_case"])
        self.assertTrue(report["invalidation_conditions"])
        self.assertEqual(DISCLAIMER, report["disclaimer"])
        self.assertIsNotNone(latest)
        self.assertEqual(report["generated_at"], latest["report"]["generated_at"])
        self.assertEqual("fixture", report["source_statuses"][0]["mode"])

    async def test_live_failures_fall_back_to_fixtures_and_emit_warnings(self) -> None:
        service = AnalysisService(build_settings(self.temp_dir, mock_mode=False))
        service.market_client.fetch_live = AsyncMock(
            side_effect=DataFetchError(
                "Binance request failed for BTCUSDT 4h at "
                "https://api.binance.com/api/v3/ticker/24hr via "
                "proxy http://127.0.0.1:4780 (ConnectTimeout): proxy timeout "
                "Check AI_FI_HTTP_PROXY or disable AI_FI_USE_PROXY for direct access."
            )
        )
        service.macro_client.fetch_live = AsyncMock(
            side_effect=DataFetchError("FRED_API_KEY is not configured")
        )
        service.event_client.fetch_live = AsyncMock(
            side_effect=DataFetchError("AI_FI_EVENT_FEED_URL is not configured")
        )

        with self.assertLogs("ai_financial_intelligence.analysis", level="WARNING") as logs:
            result = await service.run_analysis("BTCUSDT", "4h")

        modes = [status["mode"] for status in result["report"]["source_statuses"]]
        self.assertEqual(
            ["fixture-fallback", "fixture-fallback", "fixture-fallback"],
            modes,
        )
        self.assertIn(
            "https://api.binance.com/api/v3/ticker/24hr",
            result["report"]["source_statuses"][0]["detail"],
        )
        self.assertIn(
            "http://127.0.0.1:4780",
            result["report"]["source_statuses"][0]["detail"],
        )
        self.assertTrue(any("proxy timeout" in line for line in logs.output))

    async def test_cached_macro_payload_is_reported_as_cache_mode(self) -> None:
        service = AnalysisService(build_settings(self.temp_dir, mock_mode=False))
        fixture_market = BinanceMarketClient(build_settings(self.temp_dir, mock_mode=True)).fixture(
            "BTCUSDT", "4h"
        )
        service.market_client.fetch_live = AsyncMock(return_value={**fixture_market, "source": "live-binance"})
        service.event_client.fetch_live = AsyncMock(
            return_value=[
                {
                    "headline": "ETF inflows remain steady",
                    "impact": "positive",
                    "confidence": "high",
                }
            ]
        )
        service.macro_client.fetch_live = AsyncMock(
            return_value={
                "series": "DFF",
                "name": "Effective Federal Funds Rate",
                "latest_value": 4.25,
                "previous_value": 4.25,
                "unit": "%",
                "trend": "flat",
                "updated_at": "2026-04-02",
                "source": "cache-fred",
            }
        )

        result = await service.run_analysis("BTCUSDT", "4h")

        self.assertEqual("cache", result["report"]["source_statuses"][1]["mode"])
        self.assertIn("local cache", result["report"]["source_statuses"][1]["detail"].lower())


if __name__ == "__main__":
    unittest.main()
