#!/usr/bin/env python3
"""
signal_generator.py

Generates actionable signals from a NIFTY50 universe according to the ruleset
provided by the user: Market preflight → Universe filters → Indicator calc →
Pullback-to-50EMA detection → Sizing & portfolio checks → Emit JSON signals.

Usage (examples):
  # default: C:\trading-project\data\nifty50.csv
  python signal_generator.py --tickers C:\trading-project\data\nifty50.csv --portfolio 10000 --max-positions 3

Requirements:
  pandas, numpy, yfinance, python-dateutil
  Install in your venv: python -m pip install pandas numpy yfinance python-dateutil
"""

from __future__ import annotations
import argparse
import math
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List

import numpy as np
import pandas as pd
import yfinance as yf

# -------------------------
# DEFAULT PARAMETERS (tunable)
# -------------------------
DEFAULT_PERIOD = "2y"
DEFAULT_INTERVAL = "1d"

# Market preflight
MARKET_EMA_SHORT = 50
MARKET_EMA_LONG = 200

# Stock indicators
EMA_SHORT = 50
EMA_LONG = 200
ATR_LENGTH = 14
ADX_LENGTH = 14
ADX_THRESHOLD = 25

# Pullback / proximity
PULLBACK_THRESHOLD_PCT = 1.5  # percent (<= 1.5%)
PULLBACK_ATR_MULT = 1.0       # within 1 * ATR

# Volume / liquidity
ADTV_DAYS = 20
ADTV_MIN_INR = 500_000_000    # default: ₹50 Crore = 500,000,000 INR
# Note: adjust as needed. If too strict, lower this number (e.g., 50_000_000).

# Entry/exit sizing
ATR_STOP_MULTIPLIER = 1.5
REWARD_R = 2.0
RISK_PER_TRADE_PCT = 0.01     # 1% default
MAX_POSITION_ALLOCATION_PCT = 0.20  # per position (20% of portfolio)
MAX_ACTIVE_POSITIONS = 3

# Other
NO_EVENT_WINDOW_DAYS = 3      # ignore stocks with corporate events in next N days
SECTOR_MAX_SAME = 2
MIN_EXPECTED_RETURN_PCT = 0.03  # required minimum expected return (3%)

OUTPUT_JSON = "recommendations.json"

# -------------------------
# Helper / Indicator functions
# -------------------------


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    # True Range
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=n, min_periods=1).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    # Rough implementation of ADX (classic Wilder smoothing)
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_ = tr.rolling(window=n, min_periods=1).mean()
    # Wilder smoothing for DM
    plus_dm_w = plus_dm.ewm(alpha=1 / n, adjust=False).mean()
    minus_dm_w = minus_dm.ewm(alpha=1 / n, adjust=False).mean()

    plus_di = 100 * (plus_dm_w / atr_)
    minus_di = 100 * (minus_dm_w / atr_)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_ = dx.rolling(window=n, min_periods=1).mean()
    return adx_


def compute_advt_inr(df: pd.DataFrame, window: int = ADTV_DAYS) -> float:
    # ADTV in INR = average of (volume * close) over window days
    if "Volume" not in df.columns or "Close" not in df.columns:
        return 0.0
    return float((df["Volume"] * df["Close"]).rolling(window=window, min_periods=1).mean().iloc[-1])


# -------------------------
# Pipeline steps as functions
# -------------------------


def market_preflight(nifty_symbol: str = "^NSEI") -> bool:
    """
    Market preflight check:
    Nifty close > EMA50 and EMA50 > EMA200
    """
    try:
        df = yf.download(nifty_symbol, period=DEFAULT_PERIOD, interval=DEFAULT_INTERVAL, progress=False, auto_adjust=True)
        if df is None or df.empty:
            print("market_preflight: failed to download index data.")
            return False
        close = df["Close"]
        ema50 = ema(close, MARKET_EMA_SHORT)
        ema200 = ema(close, MARKET_EMA_LONG)
        last = df.iloc[-1]
        cond = (last["Close"] > ema50.iloc[-1]) and (ema50.iloc[-1] > ema200.iloc[-1])
        print(f"[market_preflight] NIFTY last_close={last['Close']:.2f}, EMA50={ema50.iloc[-1]:.2f}, EMA200={ema200.iloc[-1]:.2f}, pass={cond}")
        return bool(cond)
    except Exception as e:
        print("market_preflight error:", e)
        return False


def universe_filter(stock_meta: Dict[str, Any], df: pd.DataFrame) -> bool:
    """
    Apply universe-level filters:
     - is_nifty50_member
     - ADTV(20) >= ADTV_MIN_INR
     - no events in next NO_EVENT_WINDOW_DAYS (simple placeholder using meta)
     - price data completeness
    """
    try:
        # meta keys: 'symbol', 'sector', 'is_nifty50', 'is_fno' (optional)
        if not stock_meta.get("is_nifty50", True):
            return False

        # ADTV check
        advt_inr = compute_advt_inr(df, ADTV_DAYS)
        if advt_inr < ADTV_MIN_INR:
            return False

        # corporate event placeholder: if meta has 'next_event_date', check
        next_ev = stock_meta.get("next_event_date")
        if next_ev:
            # next_ev expected as 'YYYY-MM-DD' or datetime
            if isinstance(next_ev, str):
                ev_date = datetime.fromisoformat(next_ev).date()
            else:
                ev_date = next_ev
            days_to_event = (ev_date - datetime.utcnow().date()).days
            if 0 <= days_to_event <= NO_EVENT_WINDOW_DAYS:
                return False

        # price completeness: at least 60 recent rows
        if df.shape[0] < 60:
            return False

        if df["Close"].isna().tail(60).any():
            return False

        return True
    except Exception as e:
        print("universe_filter error:", e)
        return False


def indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute and return indicators on the df (must include columns Open, High, Low, Close, Volume)
    """
    ind = {}
    close = df["Close"]
    ind["EMA50"] = ema(close, EMA_SHORT).iloc[-1]
    ind["EMA200"] = ema(close, EMA_LONG).iloc[-1]
    ind["ATR14"] = atr(df, ATR_LENGTH).iloc[-1]
    ind["ADX14"] = adx(df, ADX_LENGTH).iloc[-1]
    ind["ADTV20_INR"] = compute_advt_inr(df, ADTV_DAYS)
    ind["close"] = float(close.iloc[-1])
    ind["open"] = float(df["Open"].iloc[-1])
    ind["distance_pct"] = (ind["close"] - ind["EMA50"]) / ind["EMA50"] * 100.0
    # other helpful items
    ind["vma20"] = float(df["Volume"].rolling(window=ADTV_DAYS, min_periods=1).mean().iloc[-1])
    return ind


def detect_pullback(ind: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detect PullbackTo50EMA setup according to rules:
    - Trend filter: close > EMA50 and EMA50 > EMA200 and ADX >= threshold
    - Pullback: abs(distance_pct) <= threshold_pct OR abs(close-EMA50) <= ATR*mult
    - Volume confirmation: volume_today >= vma20 OR close > open and close > prior_high
    """
    res = {"is_setup": False, "setup_type": None, "notes": []}
    try:
        close = ind["close"]
        ema50 = ind["EMA50"]
        ema200 = ind["EMA200"]
        atr14 = ind["ATR14"]
        adx14 = ind["ADX14"]
        vma20 = ind["vma20"]

        # Trend
        trend_ok = (close > ema50) and (ema50 > ema200)
        if not trend_ok:
            res["notes"].append("trend_fail")
            return res

        # ADX must be high enough
        if adx14 < ADX_THRESHOLD:
            res["notes"].append("adx_below_threshold")
            return res

        # Pullback proximity
        dist_pct = abs(ind["distance_pct"])
        prox_ok = (dist_pct <= PULLBACK_THRESHOLD_PCT) or (abs(close - ema50) <= PULLBACK_ATR_MULT * atr14)
        if not prox_ok:
            res["notes"].append("not_close_enough_to_50EMA")
            return res

        # Volume/confirmation: check last candle
        last_open = df["Open"].iloc[-1]
        last_high = df["High"].iloc[-1]
        last_close = df["Close"].iloc[-1]
        prior_high = df["High"].iloc[-2] if len(df) >= 2 else last_high
        vol_today = df["Volume"].iloc[-1]
        vol_ok = (vol_today >= vma20) or (last_close > last_open and last_close > prior_high)

        if not vol_ok:
            res["notes"].append("volume_confirm_fail")
            return res

        # If here, we have a valid pullback setup
        res["is_setup"] = True
        res["setup_type"] = "PullbackTo50EMA"
        res["notes"].append("pullback_ok")
        return res

    except Exception as e:
        print("detect_pullback error:", e)
        return res


def compute_size(ind: Dict[str, Any], portfolio_value: float) -> Dict[str, Any]:
    """
    Deterministic sizing:
      - risk_money = portfolio_value * RISK_PER_TRADE_PCT
      - stop_price = entry_price - ATR_STOP_MULTIPLIER * ATR
      - risk_per_share = entry_price - stop_price
      - raw_shares = floor(risk_money / risk_per_share)
      - max_shares_by_alloc = floor((MAX_POSITION_ALLOCATION_PCT*P)/entry_price)
      - final_shares = min(raw_shares, max_shares_by_alloc)
    Returns sizing dict.
    """
    sizing = {}
    entry_price = ind["close"]
    atr14 = ind["ATR14"]

    stop_price = entry_price - (ATR_STOP_MULTIPLIER * atr14)
    risk_per_share = max(1e-6, entry_price - stop_price)  # avoid division by zero
    risk_money_allowed = portfolio_value * RISK_PER_TRADE_PCT
    raw_shares = math.floor(risk_money_allowed / risk_per_share) if risk_per_share > 0 else 0
    max_shares_by_alloc = math.floor((MAX_POSITION_ALLOCATION_PCT * portfolio_value) / entry_price)

    final_shares = int(max(0, min(raw_shares, max_shares_by_alloc)))
    position_value = final_shares * entry_price
    actual_risk_money = final_shares * risk_per_share
    risk_pct_of_portfolio = actual_risk_money / portfolio_value if portfolio_value > 0 else 0.0

    sizing.update({
        "entry_price": entry_price,
        "stop_price": stop_price,
        "risk_per_share": risk_per_share,
        "raw_shares": raw_shares,
        "max_shares_by_alloc": max_shares_by_alloc,
        "final_shares": final_shares,
        "position_value": position_value,
        "actual_risk_money": actual_risk_money,
        "risk_pct_of_portfolio": risk_pct_of_portfolio,
        "target_price_primary": entry_price + REWARD_R * risk_per_share
    })
    return sizing


def portfolio_checks(candidate: Dict[str, Any], active_positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Basic portfolio checks:
      - max active positions
      - sector exposure
      - worst-case simultaneous stop risk cap (e.g., 6% default)
    Returns dict with booleans and reason list.
    """
    ok = {"ok": True, "reasons": []}
    if len(active_positions) >= MAX_ACTIVE_POSITIONS:
        ok["ok"] = False
        ok["reasons"].append("max_active_positions_reached")
        return ok

    # sector exposure
    sector = candidate.get("meta", {}).get("sector")
    if sector:
        same_sector = sum(1 for p in active_positions if p.get("meta", {}).get("sector") == sector)
        if same_sector >= SECTOR_MAX_SAME:
            ok["ok"] = False
            ok["reasons"].append("sector_limit_reached")
            return ok

    # worst-case simultaneous stop risk
    worst_case_risk = candidate["sizing"]["actual_risk_money"]
    worst_case_total = worst_case_risk + sum(p["sizing"]["actual_risk_money"] for p in active_positions)
    # default cap 6% of portfolio
    cap = 0.06 * candidate["sizing"].get("position_value", 0)  # conservative local cap; user can change later
    # Here we compare to portfolio value using stored field if exists
    port_val = candidate.get("sizing", {}).get("portfolio_value", None)
    if port_val:
        global_cap = 0.06 * port_val
        if worst_case_total > global_cap:
            ok["ok"] = False
            ok["reasons"].append("worst_case_risk_exceeds_cap")
            return ok

    return ok


# -------------------------
# Orchestration
# -------------------------


def load_tickers_from_csv(path: str) -> List[Dict[str, Any]]:
    """
    Expect CSV with columns: Symbol, Sector, is_nifty50 (optional), next_event_date (optional)
    Return list of meta dicts.
    """
    df = pd.read_csv(path)
    # try common column names
    symbol_col = next((c for c in df.columns if c.lower() in ("symbol", "ticker", "code")), None)
    sector_col = next((c for c in df.columns if c.lower() in ("sector", "industry")), None)
    meta = []
    for _, row in df.iterrows():
        meta.append({
            "symbol": (row[symbol_col] if symbol_col else None),
            "sector": (row[sector_col] if sector_col else None),
            "is_nifty50": True  # assume true; user file should contain only Nifty50
            # optionally include 'next_event_date', 'is_fno' etc.
        })
    return meta


def run_pipeline(tickers_csv: str, portfolio_value: float, max_positions: int, min_expected_return: float,
                 index_symbol: str = "^NSEI", verbose: bool = True) -> List[Dict[str, Any]]:
    """
    Main pipeline entry. Returns list of signal dicts (ready to be emitted).
    """
    global MAX_ACTIVE_POSITIONS, MAX_POSITION_ALLOCATION_PCT
    MAX_ACTIVE_POSITIONS = max_positions

    tickers_meta = load_tickers_from_csv(tickers_csv)
    signals: List[Dict[str, Any]] = []

    # 1) Market preflight
    mp_ok = market_preflight(index_symbol)
    if not mp_ok:
        if verbose:
            print("Market preflight FAIL. No new long signals today.")
        return []

    # 2) For each ticker: download data, apply universe_filter, compute indicators, detect setup
    for meta in tickers_meta:
        sym = meta["symbol"]
        if not sym:
            continue
        # ensure proper NSE suffix if not present
        if not sym.upper().endswith(".NS"):
            sym_yf = sym + ".NS"
        else:
            sym_yf = sym

        try:
            df = yf.download(sym_yf, period=DEFAULT_PERIOD, interval=DEFAULT_INTERVAL, progress=False, auto_adjust=True)
            if df is None or df.empty:
                if verbose:
                    print(f"Skipping {sym_yf}: no data")
                continue

            # Normalize expected columns
            if "Close" not in df.columns:
                # try to flatten multiindex columns if any
                df.columns = [c[1] if isinstance(c, tuple) and len(c) > 1 else c for c in df.columns]

            # Ensure numeric, drop rows with NA in key columns
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()

            # Universe filter (liquidity, events, completeness)
            if not universe_filter(meta, df):
                if verbose:
                    print(f"{sym_yf} failed universe filter.")
                continue

            # Indicators
            ind = indicators(df)

            # Detect pullback
            det = detect_pullback(ind, df)
            if not det.get("is_setup"):
                if verbose:
                    print(f"{sym_yf}: no setup (pullback not detected).")
                continue

            # Sizing
            sizing = compute_size(ind, portfolio_value)
            sizing["portfolio_value"] = portfolio_value  # pass through

            if sizing["final_shares"] <= 0:
                if verbose:
                    print(f"{sym_yf}: zero shares (size too small or allocation cap).")
                continue

            # Package candidate
            cand = {
                "symbol": sym_yf,
                "meta": meta,
                "indicators": ind,
                "detection": det,
                "sizing": sizing,
                "score": 0.0  # compute later
            }

            # Simple scoring (ADX + proximity + volume)
            adx_score = max(0.0, min(50.0, (ind.get("ADX14", 0.0) - 20.0) * 2.5))
            prox_score = max(0.0, min(25.0, (25.0 - abs(ind["distance_pct"] * 10.0))))
            vol_score = max(0.0, min(25.0, (ind.get("ADTV20_INR", 0.0) / ADTV_MIN_INR) * 12.5))
            total_score = adx_score + prox_score + vol_score
            cand["score"] = float(total_score)

            # Add expected_return placeholder: here we use naive estimate (R * probability).
            # Real expected_return should be computed from backtest per-signal statistics.
            # For now assume historical win_rate_estimate = 0.45 and avg_win_pct = REWARD_R * risk_pct_of_portfolio (approx)
            # This is conservative placeholder; you should replace with backtest-derived stats later.
            win_est = 0.45
            avg_win_pct = REWARD_R * (sizing["risk_per_share"] / sizing["entry_price"])  # approximate gross percent
            avg_loss_pct = -1.0 * (sizing["risk_per_share"] / sizing["entry_price"])  # negative percent
            expected_return_pct = win_est * avg_win_pct + (1 - win_est) * avg_loss_pct
            cand["expected_return_pct"] = float(expected_return_pct)

            signals.append(cand)

            if verbose:
                print(f"[CAND] {sym_yf}: score={total_score:.2f}, exp_ret={expected_return_pct*100:.2f}%, shares={sizing['final_shares']}")

            # small pause so yfinance doesn't throttle too hard
            time.sleep(0.08)

        except Exception as e:
            if verbose:
                print(f"Error processing {sym_yf}: {e}")
            continue

    # 3) Rank & filter by expected return and select top N considering active positions and sector limits
    if not signals:
        if verbose:
            print("No signals found.")
        return []

    # Sort by score desc
    signals = sorted(signals, key=lambda s: (s["score"], s["expected_return_pct"]), reverse=True)

    selected: List[Dict[str, Any]] = []
    active_positions: List[Dict[str, Any]] = []  # placeholder: if live, read from portfolio
    for cand in signals:
        # skip if expected return below threshold
        if cand["expected_return_pct"] < min_expected_return:
            continue

        # re-check portfolio limits
        chk = portfolio_checks(cand, active_positions)
        if not chk["ok"]:
            continue

        # accept candidate
        selected.append(cand)
        active_positions.append(cand)
        if len(selected) >= max_positions:
            break

    # 4) Emit selected signals as JSON objects
    emitted = []
    for s in selected:
        sizing = s["sizing"]
        ind = s["indicators"]
        det = s["detection"]
        meta = s["meta"]
        entry = {
            "entry_type": "next_open",
            "entry_price": sizing["entry_price"]
        }
        risk = {
            "stop_price": sizing["stop_price"],
            "risk_per_share": sizing["risk_per_share"],
            "target_price_primary": sizing["target_price_primary"]
        }
        sizing_out = {
            "portfolio_value": portfolio_value,
            "risk_per_trade_pct": RISK_PER_TRADE_PCT,
            "raw_shares": sizing["raw_shares"],
            "max_shares_by_alloc": sizing["max_shares_by_alloc"],
            "final_shares": sizing["final_shares"],
            "position_value": sizing["position_value"],
            "actual_risk_money": sizing["actual_risk_money"],
            "risk_pct_of_portfolio": sizing["risk_pct_of_portfolio"],
        }
        checks = {"sector_ok": True, "max_positions_ok": True}
        signal = {
            "symbol": s["symbol"],
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "setup": s["detection"]["setup_type"],
            "market_preflight": "PASS",
            "indicators": {
                "close": ind["close"],
                "EMA50": ind["EMA50"],
                "EMA200": ind["EMA200"],
                "ATR14": ind["ATR14"],
                "ADX14": ind["ADX14"],
                "ADTV20_INR": ind["ADTV20_INR"]
            },
            "entry": entry,
            "risk": risk,
            "sizing": sizing_out,
            "checks": checks,
            "score": s["score"],
            "expected_return_pct": s["expected_return_pct"],
            "notes": s["detection"]["notes"],
            "meta": meta
        }
        emitted.append(signal)

    # Save to JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.utcnow().isoformat() + "Z", "portfolio_value": portfolio_value,
                   "signals": emitted}, f, indent=2, default=str)

    if verbose:
        print(f"\nEmitted {len(emitted)} signal(s). Saved to {OUTPUT_JSON}")

    return emitted


# -------------------------
# CLI Entrypoint
# -------------------------
def main():
    p = argparse.ArgumentParser(description="Signal generator pipeline for PullbackTo50EMA")
    p.add_argument("--tickers", required=True, help="CSV file with tickers (Symbol, Sector optional)")
    p.add_argument("--portfolio", type=float, default=10000.0, help="Portfolio capital in INR")
    p.add_argument("--max-positions", type=int, default=3, help="Max positions to emit")
    p.add_argument("--min-expected-return", type=float, default=MIN_EXPECTED_RETURN_PCT,
                   help="Minimum expected return (fractional, e.g. 0.03 for 3%)")
    p.add_argument("--index-symbol", type=str, default="^NSEI", help="Index symbol for market preflight (yfinance)")
    p.add_argument("--no-save", action="store_true", help="Do not write recommendations.json")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = p.parse_args()

    # sanity checks
    if not os.path.exists(args.tickers):
        print("Tickers file not found:", args.tickers)
        return

    signals = run_pipeline(args.tickers, portfolio_value=args.portfolio,
                           max_positions=args.max_positions,
                           min_expected_return=args.min_expected_return,
                           index_symbol=args.index_symbol,
                           verbose=args.verbose)

    if args.no_save:
        # remove saved file if user didn't want it
        try:
            if os.path.exists(OUTPUT_JSON):
                os.remove(OUTPUT_JSON)
        except Exception:
            pass

    # Print summary
    if signals:
        print("\n=== RECOMMENDATIONS SUMMARY ===")
        for s in signals:
            print(f"{s['symbol']} | entry={s['sizing']['entry_price']:.2f} | shares={s['sizing']['final_shares']} | "
                  f"pos_val={s['sizing']['position_value']:.2f} | stop={s['sizing']['stop_price']:.2f} | "
                  f"target={s['sizing']['target_price_primary']:.2f} | exp_ret={s['expected_return_pct']*100:.2f}%")
    else:
        print("\nNo recommendations at this time.")

if __name__ == "__main__":
    main()
