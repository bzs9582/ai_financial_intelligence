from __future__ import annotations

from typing import Any


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _percent_change(base: float, current: float) -> float:
    if base == 0:
        return 0.0
    return ((current - base) / base) * 100


def calculate_market_indicators(market: dict[str, Any]) -> dict[str, Any]:
    candles = market.get("candles", [])
    closes = [float(candle.get("close", 0.0)) for candle in candles]
    if not closes:
        return {
            "last_close": 0.0,
            "sma_fast": 0.0,
            "sma_slow": 0.0,
            "momentum_pct": 0.0,
            "price_vs_slow_sma_pct": 0.0,
            "average_range_pct": 0.0,
            "trend": "neutral",
            "volatility_regime": "calm",
        }

    fast_window = closes[-3:]
    slow_window = closes[-6:] if len(closes) >= 6 else closes
    last_close = closes[-1]
    sma_fast = _average(fast_window)
    sma_slow = _average(slow_window)

    range_samples: list[float] = []
    for candle in candles[-6:]:
        close = float(candle.get("close", 0.0)) or 1.0
        high = float(candle.get("high", close))
        low = float(candle.get("low", close))
        range_samples.append(max(high - low, 0.0) / close * 100)

    average_range_pct = _average(range_samples)
    momentum_pct = _percent_change(closes[0], last_close)
    price_vs_slow_sma_pct = _percent_change(sma_slow or last_close, last_close)

    if last_close <= 0 or sma_fast <= 0 or sma_slow <= 0:
        trend = "neutral"
    elif last_close >= sma_fast >= sma_slow:
        trend = "bullish"
    elif last_close <= sma_fast <= sma_slow:
        trend = "bearish"
    else:
        trend = "neutral"

    if average_range_pct >= 2.5:
        volatility_regime = "high"
    elif average_range_pct >= 1.2:
        volatility_regime = "moderate"
    else:
        volatility_regime = "calm"

    return {
        "last_close": round(last_close, 4),
        "sma_fast": round(sma_fast, 4),
        "sma_slow": round(sma_slow, 4),
        "momentum_pct": round(momentum_pct, 2),
        "price_vs_slow_sma_pct": round(price_vs_slow_sma_pct, 2),
        "average_range_pct": round(average_range_pct, 2),
        "trend": trend,
        "volatility_regime": volatility_regime,
    }
