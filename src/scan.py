"""Daily OHLCV watchlist scanner. Flags are research candidates, not trade advice."""
import argparse
import time
from pathlib import Path
import sys

import pandas as pd
import yaml
import yfinance as yf

try:
    from .indicators import add_indicators
    from .risk import build_trade_plan
except ImportError:  # supports: python src/scan.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.indicators import add_indicators
    from src.risk import build_trade_plan


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def yahoo_symbol(symbol: str, exchange: str) -> str:
    symbol = symbol.strip().upper()
    # Yahoo Finance/NSE symbol changes; also support older local config.yaml files.
    symbol = {"TATAMOTORS": "TMPV", "LTIM": "LTM"}.get(symbol, symbol)
    if "." in symbol:
        return symbol
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    return symbol + suffix


SECTOR_INDEX = {
    "TCS": "NIFTY_IT", "INFY": "NIFTY_IT", "HCLTECH": "NIFTY_IT", "WIPRO": "NIFTY_IT",
    "TECHM": "NIFTY_IT", "LTM": "NIFTY_IT", "PERSISTENT": "NIFTY_IT", "COFORGE": "NIFTY_IT", "MPHASIS": "NIFTY_IT",
    "SUNPHARMA": "NIFTY_PHARMA", "DRREDDY": "NIFTY_PHARMA", "CIPLA": "NIFTY_PHARMA", "DIVISLAB": "NIFTY_PHARMA",
    "APOLLOHOSP": "NIFTY_PHARMA", "ZYDUSLIFE": "NIFTY_PHARMA", "TORNTPHARM": "NIFTY_PHARMA",
    "AUROPHARMA": "NIFTY_PHARMA", "LUPIN": "NIFTY_PHARMA", "ALKEM": "NIFTY_PHARMA",
    "MARUTI": "NIFTY_AUTO", "M&M": "NIFTY_AUTO", "EICHERMOT": "NIFTY_AUTO", "HEROMOTOCO": "NIFTY_AUTO",
    "TVSMOTOR": "NIFTY_AUTO", "BOSCHLTD": "NIFTY_AUTO", "MOTHERSON": "NIFTY_AUTO", "TMPV": "NIFTY_AUTO",
    "ITC": "NIFTY_FMCG", "HINDUNILVR": "NIFTY_FMCG", "NESTLEIND": "NIFTY_FMCG", "TATACONSUM": "NIFTY_FMCG",
    "BRITANNIA": "NIFTY_FMCG", "DABUR": "NIFTY_FMCG", "GODREJCP": "NIFTY_FMCG", "UNITDSPR": "NIFTY_FMCG",
    "MARICO": "NIFTY_FMCG", "COLPAL": "NIFTY_FMCG",
    "TATASTEEL": "NIFTY_METAL", "JSWSTEEL": "NIFTY_METAL", "HINDALCO": "NIFTY_METAL",
    "COALINDIA": "NIFTY_METAL", "NMDC": "NIFTY_METAL", "VEDL": "NIFTY_METAL", "SAIL": "NIFTY_METAL", "JINDALSTEL": "NIFTY_METAL",
    "DLF": "NIFTY_REALTY",
    "HDFCBANK": "NIFTY_BANK", "ICICIBANK": "NIFTY_BANK", "SBIN": "NIFTY_BANK", "KOTAKBANK": "NIFTY_BANK",
    "AXISBANK": "NIFTY_BANK", "INDUSINDBK": "NIFTY_BANK", "BANKBARODA": "NIFTY_BANK", "PNB": "NIFTY_BANK",
    "CANBK": "NIFTY_BANK", "IDFCFIRSTB": "NIFTY_BANK", "FEDERALBNK": "NIFTY_BANK", "BANDHANBNK": "NIFTY_BANK"
}
FILTER_WEIGHTS = {"uptrend": 2.0, "momentum": 1.0, "volume": 1.5, "breakout": 2.0,
                  "price_floor": 0.5, "turnover": 1.0, "volatility": 1.0}


def load_sector_context(path: str = "market_context.csv") -> dict:
    """Read sector index trends from the market-context CSV when available."""
    try:
        frame = pd.read_csv(path)
        if not {"index", "trend"}.issubset(frame.columns):
            return {}
        return dict(zip(frame["index"].astype(str), frame["trend"].astype(str)))
    except (FileNotFoundError, OSError, pd.errors.ParserError):
        return {}


def filter_score(checks: dict) -> float:
    """Weighted filter-pass percentage; this is not a probability of profit."""
    total = sum(FILTER_WEIGHTS.values())
    passed = sum(weight for name, weight in FILTER_WEIGHTS.items() if checks.get(name, False))
    return round(100.0 * passed / total, 1)


def sector_for(symbol: str) -> str:
    base = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    return SECTOR_INDEX.get(base, "UNMAPPED")


def sector_rank_adjustment(trend: str) -> float:
    return 2.0 if trend == "BULLISH" else (-2.0 if trend == "BEARISH" else 0.0)


FILTER_GUIDANCE = {
    "uptrend": "Wait for close > EMA20 > EMA50",
    "momentum": "Wait for RSI to return to the 50–70 range",
    "volume": "Wait for relative volume to reach the configured minimum",
    "breakout": "Wait for a daily close above the prior breakout level",
    "price_floor": "Below the configured minimum price; do not override automatically",
    "turnover": "Wait for average daily traded value to meet the liquidity floor",
    "volatility": "Wait for ATR percentage to fall within the configured maximum",
}


def failed_filter_guidance(failed: list[str]) -> str:
    """Human-readable conditions still missing; never relax a filter automatically."""
    if not failed:
        return "All scanner filters passed; independently verify the setup before paper entry"
    return "; ".join(FILTER_GUIDANCE[name] for name in failed)


def scan_one(symbol: str, cfg: dict, sector_context: dict | None = None) -> dict:
    market, account, strategy = cfg["market"], cfg["account"], cfg["strategy"]
    ticker = yahoo_symbol(symbol, market.get("exchange", "NSE"))
    base_symbol = ticker.rsplit(".", 1)[0]
    sector_index = sector_for(base_symbol)
    sector_trend = (sector_context or {}).get(sector_index, "UNAVAILABLE")
    raw = yf.download(ticker, period=market.get("history_period", "1y"),
                      interval=market.get("interval", "1d"), auto_adjust=True,
                      progress=False, threads=False)
    if raw.empty:
        return {"symbol": ticker, "status": "SKIP", "reason": "No price history returned",
                "sector_index": sector_index, "sector_trend": sector_trend,
                "filter_score_pct": 0.0, "ranking_score": 0.0}
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    data = add_indicators(raw, strategy["ema_fast"], strategy["ema_slow"],
                          strategy["rsi_period"], strategy["atr_period"],
                          strategy["volume_lookback"], strategy["breakout_lookback"])
    row = data.iloc[-1]
    close = float(row["Close"])
    checks = {
        "uptrend": close > float(row["ema_fast"]) > float(row["ema_slow"]),
        "momentum": 50 <= float(row["rsi"]) <= 70,
        "volume": pd.notna(row["relative_volume"]) and float(row["relative_volume"]) >= strategy["min_relative_volume"],
        "breakout": pd.notna(row["prior_high"]) and close > float(row["prior_high"]),
        "price_floor": close >= strategy["min_price_inr"],
        "turnover": pd.notna(row["avg_turnover"]) and float(row["avg_turnover"]) >= strategy["min_avg_daily_turnover_inr"],
        "volatility": pd.notna(row["atr_pct"]) and float(row["atr_pct"]) <= strategy["max_atr_pct"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    score = filter_score(checks)
    rank_score = round(score + sector_rank_adjustment(sector_trend), 1)
    prior_high = float(row["prior_high"]) if pd.notna(row["prior_high"]) else None
    atr = float(row["atr"]) if pd.notna(row["atr"]) else None
    result = {"symbol": ticker, "sector_index": sector_index, "sector_trend": sector_trend,
              "filter_score_pct": score, "ranking_score": rank_score,
              "passed_filters": len(checks) - len(failed), "total_filters": len(checks),
              "failed_filters": ", ".join(failed),
              **{f"filter_{name}": bool(passed) for name, passed in checks.items()},
              "date": str(data.index[-1].date()), "close": round(close, 2),
              "ema_fast": round(float(row["ema_fast"]), 2),
              "ema_slow": round(float(row["ema_slow"]), 2),
              "rsi": round(float(row["rsi"]), 1),
              "relative_volume": round(float(row["relative_volume"]), 2) if pd.notna(row["relative_volume"]) else None,
              "required_relative_volume": float(strategy["min_relative_volume"]),
              "prior_breakout_high": round(prior_high, 2) if prior_high is not None else None,
              "atr": round(atr, 2) if atr is not None else None,
              "atr_pct": round(float(row["atr_pct"]), 2) if pd.notna(row["atr_pct"]) else None,
              "next_action": failed_filter_guidance(failed),
              "status": "RESEARCH_CANDIDATE" if not failed else "WATCH / SKIP",
              "reason": "All screening filters passed" if not failed else "Failed: " + ", ".join(failed)}
    if not failed:
        # ATR-based initial stop proxy. Validate support/structure manually before any trade.
        stop = close - 1.5 * float(row["atr"])
        try:
            plan = build_trade_plan(close, stop, float(account["capital_inr"]),
                                    float(account["risk_per_trade_pct"]),
                                    float(account["max_position_pct"]),
                                    float(strategy["min_reward_risk"]))
            result.update({"entry_reference": round(plan.entry, 2), "stop_reference": round(plan.stop, 2),
                           "target_reference": round(plan.target, 2), "quantity_ceiling": plan.quantity,
                           "planned_risk_inr": round(plan.planned_risk_inr, 2),
                           "position_value_inr": round(plan.position_value_inr, 2),
                           "reward_risk_reference": round(plan.reward_risk, 2),
                           "trade_plan_status": "PAPER_REVIEW_ONLY"})
        except ValueError as exc:
            result["status"] = "NO TRADE"
            result["reason"] = str(exc)
            result["trade_plan_status"] = "NOT_FEASIBLE"
    else:
        result["trade_plan_status"] = "NOT_GENERATED_FILTERS_FAILED"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml", help="Path to local YAML config")
    parser.add_argument("--output", default="scan_results.csv", help="CSV output path")
    args = parser.parse_args()
    cfg = load_config(args.config)
    sector_context = load_sector_context()
    if sector_context:
        print("Loaded sector trends from market_context.csv")
    else:
        print("No usable market_context.csv found; sector adjustment disabled.")
    results = []
    for symbol in cfg.get("watchlist", []):
        try:
            result = scan_one(symbol, cfg, sector_context)
        except Exception as exc:  # keep scanner running if one symbol/data source fails
            result = {"symbol": symbol, "status": "ERROR", "reason": str(exc),
                      "filter_score_pct": 0.0, "ranking_score": 0.0}
        results.append(result)
        print(f"{result['symbol']}: {result['status']} — {result['reason']}")
        # Gentle pacing reduces the chance of throttling on large watchlists.
        time.sleep(max(0.0, float(cfg.get("market", {}).get("scan_delay_seconds", 0.5))))
    if results:
        output = pd.DataFrame(results)
        if "ranking_score" in output.columns:
            output = output.sort_values(["ranking_score", "filter_score_pct"], ascending=False,
                                        na_position="last")
        output.to_csv(args.output, index=False)
        print(f"\nSaved {len(results)} rows to {args.output}")
        ranked = output[output["status"].isin(["RESEARCH_CANDIDATE", "WATCH / SKIP"])].head(15)
        if not ranked.empty:
            print("\nTOP 15 WATCHLIST BY FILTER PROXIMITY (not buy signals):")
            for _, row in ranked.iterrows():
                print(f"{row['symbol']}: {row.get('filter_score_pct', 0)}% filters passed | "
                      f"sector {row.get('sector_trend', 'UNAVAILABLE')} | {row['reason']}")
                if row.get("next_action"):
                    print(f"  Next condition: {row['next_action']}")
                if pd.notna(row.get("prior_breakout_high")):
                    print(f"  Prior breakout reference (not an entry order): {row['prior_breakout_high']}")
        print("Ranking is a research-priority aid, not a probability or order instruction.")


if __name__ == "__main__":
    main()
