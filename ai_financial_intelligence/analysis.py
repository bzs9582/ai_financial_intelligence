from __future__ import annotations

from datetime import datetime, UTC
import logging
from typing import Any, Awaitable, Callable

from .clients import (
    BinanceMarketClient,
    DataFetchError,
    FredMacroClient,
    TextEventClient,
)
from .indicators import calculate_market_indicators
from .settings import AppSettings
from .storage import ReportStore


logger = logging.getLogger(__name__)

SUPPORTED_ASSETS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
)
SUPPORTED_TIMEFRAMES = ("4h", "1d")
DISCLAIMER = "仅供研究参考，不构成投资建议。"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _event_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    positive = sum(1 for event in events if event.get("impact") == "positive")
    negative = sum(1 for event in events if event.get("impact") == "negative")
    neutral = len(events) - positive - negative
    high_confidence = sum(1 for event in events if event.get("confidence") == "high")

    if positive > negative:
        bias = "positive"
    elif negative > positive:
        bias = "negative"
    else:
        bias = "balanced"

    top_headlines = [
        str(event.get("headline", "")).strip()
        for event in events[:3]
        if str(event.get("headline", "")).strip()
    ]

    return {
        "positive_count": positive,
        "negative_count": negative,
        "neutral_count": neutral,
        "high_confidence_count": high_confidence,
        "bias": bias,
        "top_headlines": top_headlines,
    }


def _success_status(name: str, payload: Any) -> dict[str, str]:
    if isinstance(payload, dict) and str(payload.get("source", "")).startswith("cache-"):
        return {
            "name": name,
            "mode": "cache",
            "detail": "Served from local cache.",
        }
    return {
        "name": name,
        "mode": "live",
        "detail": "Live request succeeded.",
    }


def build_intelligence(
    *,
    asset: str,
    timeframe: str,
    generated_at: str,
    market: dict[str, Any],
    macro: dict[str, Any],
    events: list[dict[str, Any]],
    source_statuses: list[dict[str, str]],
) -> dict[str, Any]:
    indicators = calculate_market_indicators(market)
    event_summary = _event_summary(events)
    snapshot_summary = (
        f"{asset} {timeframe} price {market['last_price']:.2f}, "
        f"24h {market['change_pct_24h']:+.2f}%, "
        f"{macro['name']} {macro['latest_value']:.2f}{macro['unit']} "
        f"({macro['trend']}), events bias {event_summary['bias']}."
    )

    return {
        "asset": asset,
        "timeframe": timeframe,
        "generated_at": generated_at,
        "snapshot_summary": snapshot_summary,
        "market": market,
        "macro": macro,
        "events": events,
        "source_statuses": source_statuses,
        "indicators": indicators,
        "event_summary": event_summary,
    }


def build_report(intelligence: dict[str, Any]) -> dict[str, Any]:
    market = intelligence["market"]
    macro = intelligence["macro"]
    indicators = intelligence["indicators"]
    event_summary = intelligence["event_summary"]
    source_statuses = intelligence["source_statuses"]

    market_score = 0
    if indicators["trend"] == "bullish":
        market_score += 1
    elif indicators["trend"] == "bearish":
        market_score -= 1
    if indicators["momentum_pct"] > 1:
        market_score += 1
    elif indicators["momentum_pct"] < -1:
        market_score -= 1
    if market["change_pct_24h"] > 0:
        market_score += 1
    elif market["change_pct_24h"] < 0:
        market_score -= 1

    macro_score = 0
    if macro["trend"] == "lower":
        macro_score += 1
    elif macro["trend"] == "higher":
        macro_score -= 1
    if event_summary["bias"] == "positive":
        macro_score += 1
    elif event_summary["bias"] == "negative":
        macro_score -= 1

    structure_score = 0
    if market["open_interest"] > 0 and indicators["price_vs_slow_sma_pct"] > 0:
        structure_score += 1
    elif indicators["price_vs_slow_sma_pct"] < 0:
        structure_score -= 1
    if indicators["volatility_regime"] == "high":
        structure_score -= 1

    fallback_count = sum(
        1 for status in source_statuses if status["mode"] == "fixture-fallback"
    )
    risk_penalty = event_summary["negative_count"] + fallback_count
    net_score = market_score + macro_score + structure_score

    bull_probability = _clamp(45 + net_score * 6 - risk_penalty * 3, 20, 70)
    bear_probability = _clamp(30 - net_score * 5 + risk_penalty * 4, 15, 60)
    base_probability = 100 - bull_probability - bear_probability
    if base_probability < 10:
        bull_probability -= max(0, (10 - base_probability) / 2)
        bear_probability -= max(0, (10 - base_probability) / 2)
        base_probability = 100 - bull_probability - bear_probability

    probabilities = [
        {
            "scenario": "bullish continuation",
            "probability": int(round(bull_probability)),
        },
        {
            "scenario": "balanced range",
            "probability": int(round(base_probability)),
        },
        {
            "scenario": "bearish reversal",
            "probability": int(round(bear_probability)),
        },
    ]

    diff = 100 - sum(item["probability"] for item in probabilities)
    probabilities[1]["probability"] += diff

    bull_case = [
        f"Price is {indicators['price_vs_slow_sma_pct']:+.2f}% versus the slow average, keeping the short-term trend constructive.",
        f"24h change is {market['change_pct_24h']:+.2f}% with quote volume near {market['quote_volume']:.0f}.",
        f"Macro backdrop is {macro['trend']} on {macro['name']} and event bias is {event_summary['bias']}.",
    ]
    bear_case = [
        f"Average trading range is {indicators['average_range_pct']:.2f}%, so a volatility squeeze can break lower quickly.",
        f"Negative events count is {event_summary['negative_count']}, which can override a short-lived technical bounce.",
        f"Any loss of the slow average near {indicators['sma_slow']:.2f} weakens the market structure immediately.",
    ]

    invalidation_conditions = [
        f"4h or 1d closes back below the slow moving average around {indicators['sma_slow']:.2f}.",
        "Event flow turns decisively negative or macro liquidity expectations tighten further.",
        "Open interest rises while spot price stalls, signaling crowded positioning without follow-through.",
    ]

    risk_notes = [
        f"Volatility regime: {indicators['volatility_regime']}.",
        f"Data path used {fallback_count} fixture fallback(s)." if fallback_count else "All sources completed without fixture fallback.",
        DISCLAIMER,
    ]

    peter_stance = "bullish" if market_score > 0 else "bearish" if market_score < 0 else "neutral"
    venturus_stance = "bullish" if macro_score > 0 else "bearish" if macro_score < 0 else "neutral"
    pivot_stance = "bullish" if structure_score > 0 else "bearish" if structure_score < 0 else "neutral"
    reality_stance = "guarded" if risk_penalty > 0 else "stable"

    return {
        "asset": intelligence["asset"],
        "timeframe": intelligence["timeframe"],
        "generated_at": intelligence["generated_at"],
        "snapshot_summary": intelligence["snapshot_summary"],
        "key_signals": [
            f"Trend: {indicators['trend']}",
            f"Momentum: {indicators['momentum_pct']:+.2f}%",
            f"Macro: {macro['trend']}",
            f"Events: {event_summary['bias']}",
            f"Funding: {market['funding_rate']:+.4f}%",
            f"Basis: {market['basis_pct']:+.3f}%",
        ],
        "peter": {
            "stance": peter_stance,
            "summary": (
                f"Peter sees {peter_stance} price action with momentum "
                f"{indicators['momentum_pct']:+.2f}% and a slow average at {indicators['sma_slow']:.2f}."
            ),
        },
        "venturus": {
            "stance": venturus_stance,
            "summary": (
                f"Venturus reads the macro tape as {venturus_stance}; "
                f"{macro['name']} is {macro['latest_value']:.2f}{macro['unit']} and trending {macro['trend']}."
            ),
        },
        "pivot": {
            "stance": pivot_stance,
            "summary": (
                f"Pivot flags {pivot_stance} structure with open interest at {market['open_interest']:.0f} "
                f"while mark/index basis sits at {market['basis_pct']:+.3f}% and "
                f"funding runs {market['funding_rate']:+.4f}% into the next reset at "
                f"{market['next_funding_time'] or 'n/a'}."
            ),
        },
        "reality_check": {
            "stance": reality_stance,
            "summary": (
                f"Reality Check stays {reality_stance}; negative-event count is "
                f"{event_summary['negative_count']} and fallback count is {fallback_count}."
            ),
        },
        "bull_case": bull_case,
        "bear_case": bear_case,
        "scenario_probabilities": probabilities,
        "invalidation_conditions": invalidation_conditions,
        "risk_notes": risk_notes,
        "source_statuses": source_statuses,
        "disclaimer": DISCLAIMER,
    }


class AnalysisService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        *,
        store: ReportStore | None = None,
        market_client: BinanceMarketClient | None = None,
        macro_client: FredMacroClient | None = None,
        event_client: TextEventClient | None = None,
    ) -> None:
        self.settings = settings or AppSettings.from_env()
        self.store = store or ReportStore(self.settings.database_path)
        self.market_client = market_client or BinanceMarketClient(self.settings)
        self.macro_client = macro_client or FredMacroClient(
            self.settings,
            store=self.store,
        )
        self.event_client = event_client or TextEventClient(self.settings)

    def latest_result(self) -> dict[str, Any] | None:
        return self.store.latest()

    async def run_analysis(self, asset: str, timeframe: str) -> dict[str, Any]:
        asset = asset.strip().upper()
        timeframe = timeframe.strip().lower()
        if asset not in SUPPORTED_ASSETS:
            raise ValueError(f"Unsupported asset: {asset}")
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        market, market_status = await self._collect_source(
            "Binance market",
            lambda: self.market_client.fetch_live(asset, timeframe),
            lambda: self.market_client.fixture(asset, timeframe),
        )
        macro, macro_status = await self._collect_source(
            "FRED macro",
            self.macro_client.fetch_live,
            self.macro_client.fixture,
        )
        events, event_status = await self._collect_source(
            "Event feed",
            self.event_client.fetch_live,
            self.event_client.fixture,
        )

        intelligence = build_intelligence(
            asset=asset,
            timeframe=timeframe,
            generated_at=generated_at,
            market=market,
            macro=macro,
            events=events,
            source_statuses=[market_status, macro_status, event_status],
        )
        report = build_report(intelligence)
        self.store.save(intelligence, report)
        return {"intelligence": intelligence, "report": report}

    async def _collect_source(
        self,
        name: str,
        live_fetcher: Callable[[], Awaitable[Any]],
        fixture_fetcher: Callable[[], Any],
    ) -> tuple[Any, dict[str, str]]:
        if self.settings.mock_mode:
            return fixture_fetcher(), {
                "name": name,
                "mode": "fixture",
                "detail": "Mock mode enabled; using local fixture data.",
            }

        try:
            payload = await live_fetcher()
            return payload, _success_status(name, payload)
        except DataFetchError as exc:
            logger.warning("%s fallback to fixture: %s", name, exc)
            return fixture_fetcher(), {
                "name": name,
                "mode": "fixture-fallback",
                "detail": str(exc),
            }
