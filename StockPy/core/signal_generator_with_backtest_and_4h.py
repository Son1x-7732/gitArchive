#!/usr/bin/env python3
"""
signal_generator_with_backtest_and_4h.py

Updated pipeline:
 - loads backtest CSV (--backtest-csv) and computes per-symbol stats (win_rate, avg_win_pct, avg_loss_pct)
 - optional 4H confirmation (--confirm-4h)
 - CLI args: --tickers, --backtest-csv, --confirm-4h, etc.

Usage example:
  python signal_generator_with_backtest_and_4h.py --tickers C:\trading-project\data\nifty50.csv \
    --portfolio 10000 --max-positions 3 --backtest-csv C:\trading-project\core\backtest_trades_with_costs_optimized.csv \
    --confirm-4h --verbose
"""

from __future__ import annotations
import argparse
import math
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# -------------------------
# Parameters (same defaults as before — adjust if needed)
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
PULLBACK_THRESHOLD_PCT = 1.5  # percent
PULLBACK_ATR_MULT = 1.0

# Volume / liquidity
ADTV_DAYS = 20
ADTV_MIN_INR = 500_000_000    # ₹50 Crore

# Entry/exit sizing
ATR_STOP_MULTIPLIER = 1.5
REWARD_R = 2.0
RISK_PER_TRADE_PCT = 0.01     # 1% default
MAX_POSITION_ALLOCATION_PCT = 0.20  # per position
MAX_ACTIVE_POSITIONS = 3

NO_EVENT_WINDOW_DAYS = 3
SECTOR_MAX_SAME = 2

MIN_EXPECTED_RETURN_PCT = 0.03

OUTPUT_JSON = "recommendations.json"

# -------------------------
# Helper functions (EMA, ATR, ADX, ADTV)
# -------------------------
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
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
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_ = tr.rolling(window=n, min_periods=1).mean()

    plus_dm_w = plus_dm.ewm(alpha=1/n, adjust=False).mean()
    minus_dm_w = minus_dm.ewm(alpha=1/n, adjust=False).mean()

    plus_di = 100 * (plus_dm_w / atr_)
    minus_di = 100 * (minus_dm_w / atr_)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_ = dx.rolling(window=n, min_periods=1).mean()
    return adx_

def compute_advt_inr(df: pd.DataFrame, window: int = ADTV_DAYS) -> float:
    if "Volume" not in df.columns or "Close" not in df.columns:
        return 0.0
    return float((df["Volume"] * df["Close"]).rolling(window=window, min_periods=1).mean().iloc[-1])

# -------------------------
# Backtest stats integration
# -------------------------
def compute_backtest_stats(backtest_csv: str, min_trades_for_symbol: int = 5
                           ) -> Tuple[Dict[str, Dict[str, float]], Dict[str, float]]:
    """
    Read backtest CSV and compute per-symbol stats:
      - win_rate
      - avg_win_pct (mean of gross_pct for winning trades)
      - avg_loss_pct (mean of gross_pct for losing trades)
    Also return global fallback stats.
    Assumes backtest CSV has columns: symbol, entry_price, shares (optional), gross_pnl
    """
    if not backtest_csv or not os.path.exists(backtest_csv):
        return {}, {"win_rate": 0.45, "avg_win_pct": REWARD_R * 0.01, "avg_loss_pct": -0.01}  # conservative defaults

    df = pd.read_csv(backtest_csv)
    # ensure needed columns
    if "symbol" not in df.columns or "gross_pnl" not in df.columns:
        return {}, {"win_rate": 0.45, "avg_win_pct": REWARD_R * 0.01, "avg_loss_pct": -0.01}

    # compute gross_pct per trade: gross_pnl / (entry_price * shares) if shares present else gross_pnl / entry_price
    def gross_pct(row):
        try:
            if "shares" in row and not pd.isna(row["shares"]) and row["shares"] > 0 and "entry_price" in row and row["entry_price"] > 0:
                return row["gross_pnl"] / (row["entry_price"] * row["shares"])
            elif "entry_price" in row and row["entry_price"] > 0:
                return row["gross_pnl"] / row["entry_price"]
        except Exception:
            pass
        return np.nan

    df["gross_pct"] = df.apply(gross_pct, axis=1)

    stats = {}
    global_wins = df[df["gross_pnl"] > 0]
    global_losses = df[df["gross_pnl"] <= 0]

    # global stats fallback
    if not df.empty:
        global_win_rate = float((df["gross_pnl"] > 0).mean())
        global_avg_win_pct = float(global_wins["gross_pct"].dropna().mean()) if not global_wins.empty else 0.03
        global_avg_loss_pct = float(global_losses["gross_pct"].dropna().mean()) if not global_losses.empty else -0.02
    else:
        global_win_rate, global_avg_win_pct, global_avg_loss_pct = 0.45, REWARD_R*0.01, -0.01

    for sym, g in df.groupby("symbol"):
        total = len(g)
        wins = (g["gross_pnl"] > 0).sum()
        win_rate = float(wins / total) if total > 0 else global_win_rate
        win_gross_pct = g[g["gross_pnl"] > 0]["gross_pct"].dropna()
        loss_gross_pct = g[g["gross_pnl"] <= 0]["gross_pct"].dropna()

        avg_win_pct = float(win_gross_pct.mean()) if len(win_gross_pct) > 0 else global_avg_win_pct
        avg_loss_pct = float(loss_gross_pct.mean()) if len(loss_gross_pct) > 0 else global_avg_loss_pct

        # If too few trades, mark for fallback
        if total < min_trades_for_symbol:
            avg_win_pct = global_avg_win_pct
            avg_loss_pct = global_avg_loss_pct
            win_rate = global_win_rate

        stats[sym if sym.endswith(".NS") else (str(sym) + ".NS")] = {
            "win_rate": win_rate,
            "avg_win_pct": avg_win_pct,
            "avg_loss_pct": avg_loss_pct,
            "trades": total
        }

    global_stats = {"win_rate": global_win_rate, "avg_win_pct": global_avg_win_pct, "avg_loss_pct": global_avg_loss_pct}
    return stats, global_stats

# -------------------------
# detection, sizing, portfolio checks (unchanged)
# -------------------------
def market_preflight(nifty_symbol: str = "^NSEI") -> bool:
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
    try:
        if not stock_meta.get("is_nifty50", True):
            return False
        advt_inr = compute_advt_inr(df, ADTV_DAYS)
        if advt_inr < ADTV_MIN_INR:
            return False
        next_ev = stock_meta.get("next_event_date")
        if next_ev:
            if isinstance(next_ev, str):
                ev_date = datetime.fromisoformat(next_ev).date()
            else:
                ev_date = next_ev
            days_to_event = (ev_date - datetime.utcnow().date()).days
            if 0 <= days_to_event <= NO_EVENT_WINDOW_DAYS:
                return False
        if df.shape[0] < 60:
            return False
        if df["Close"].isna().tail(60).any():
            return False
        return True
    except Exception as e:
        print("universe_filter error:", e)
        return False

def indicators(df: pd.DataFrame) -> Dict[str, Any]:
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
    ind["vma20"] = float(df["Volume"].rolling(window=ADTV_DAYS, min_periods=1).mean().iloc[-1])
    return ind

def detect_pullback(ind: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
    res = {"is_setup": False, "setup_type": None, "notes": []}
    try:
        close = ind["close"]
        ema50 = ind["EMA50"]
        ema200 = ind["EMA200"]
        atr14 = ind["ATR14"]
        adx14 = ind["ADX14"]
        vma20 = ind["vma20"]
        trend_ok = (close > ema50) and (ema50 > ema200)
        if not trend_ok:
            res["notes"].append("trend_fail")
            return res
        if adx14 < ADX_THRESHOLD:
            res["notes"].append("adx_below_threshold")
            return res
        dist_pct = abs(ind["distance_pct"])
        prox_ok = (dist_pct <= PULLBACK_THRESHOLD_PCT) or (abs(close - ema50) <= PULLBACK_ATR_MULT * atr14)
        if not prox_ok:
            res["notes"].append("not_close_enough_to_50EMA")
            return res
        last_open = df["Open"].iloc[-1]
        last_high = df["High"].iloc[-1]
        last_close = df["Close"].iloc[-1]
        prior_high = df["High"].iloc[-2] if len(df) >= 2 else last_high
        vol_today = df["Volume"].iloc[-1]
        vol_ok = (vol_today >= vma20) or (last_close > last_open and last_close > prior_high)
        if not vol_ok:
            res["notes"].append("volume_confirm_fail")
            return res
        res["is_setup"] = True
        res["setup_type"] = "PullbackTo50EMA"
        res["notes"].append("pullback_ok")
        return res
    except Exception as e:
        print("detect_pullback error:", e)
        return res

def compute_size(ind: Dict[str, Any], portfolio_value: float) -> Dict[str, Any]:
    sizing = {}
    entry_price = ind["close"]
    atr14 = ind["ATR14"]
    stop_price = entry_price - (ATR_STOP_MULTIPLIER * atr14)
    risk_per_share = max(1e-6, entry_price - stop_price)
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

def portfolio_checks(candidate: Dict[str, Any], active_positions: List[Dict[str, Any]], portfolio_value: float) -> Dict[str, Any]:
    ok = {"ok": True, "reasons": []}
    if len(active_positions) >= MAX_ACTIVE_POSITIONS:
        ok["ok"] = False
        ok["reasons"].append("max_active_positions_reached")
        return ok
    sector = candidate.get("meta", {}).get("sector")
    if sector:
        same_sector = sum(1 for p in active_positions if p.get("meta", {}).get("sector") == sector)
        if same_sector >= SECTOR_MAX_SAME:
            ok["ok"] = False
            ok["reasons"].append("sector_limit_reached")
            return ok
    worst_case_risk = candidate["sizing"]["actual_risk_money"]
    worst_case_total = worst_case_risk + sum(p["sizing"]["actual_risk_money"] for p in active_positions)
    global_cap = 0.06 * portfolio_value
    if worst_case_total > global_cap:
        ok["ok"] = False
        ok["reasons"].append("worst_case_risk_exceeds_cap")
        return ok
    return ok

# -------------------------
# 4H Confirmation helper
# -------------------------
def confirm_4h(symbol_yf: str) -> bool:
    """
    Fetch recent 4h candles and require latest close > prior candle high.
    Returns True if confirmation passes; False on failure or missing data.
    """
    try:
        # small window is sufficient: last 10 4h candles (~40h)
        df4 = yf.download(symbol_yf, period="10d", interval="4h", progress=False, auto_adjust=True)
        if df4 is None or df4.empty or len(df4) < 2:
            return False
        last = df4.iloc[-1]
        prev = df4.iloc[-2]
        return last["Close"] > prev["High"]
    except Exception:
        return False

# -------------------------
# Orchestration: run_pipeline (integrates backtest stats and optional 4H)
# -------------------------
def load_tickers_from_csv(path: str) -> List[Dict[str, Any]]:
    df = pd.read_csv(path)
    symbol_col = next((c for c in df.columns if c.lower() in ("symbol", "ticker", "code")), None)
    sector_col = next((c for c in df.columns if c.lower() in ("sector", "industry")), None)
    meta = []
    for _, row in df.iterrows():
        meta.append({
            "symbol": (row[symbol_col] if symbol_col else None),
            "sector": (row[sector_col] if sector_col else None),
            "is_nifty50": True
        })
    return meta

def run_pipeline(tickers_csv: str, portfolio_value: float, max_positions: int, min_expected_return: float,
                 backtest_csv: str = None, confirm_4h_flag: bool = False, index_symbol: str = "^NSEI", verbose: bool = True) -> List[Dict[str, Any]]:
    global MAX_ACTIVE_POSITIONS
    MAX_ACTIVE_POSITIONS = max_positions

    tickers_meta = load_tickers_from_csv(tickers_csv)
    signals: List[Dict[str, Any]] = []

    # Load backtest stats if provided
    per_symbol_stats, global_stats = compute_backtest_stats(backtest_csv) if backtest_csv else ({}, {"win_rate": 0.45, "avg_win_pct": REWARD_R*0.01, "avg_loss_pct": -0.01})

    # 1) Market preflight
    if not market_preflight(index_symbol):
        if verbose:
            print("Market preflight FAIL. No new long signals today.")
        return []

    # 2) Loop through tickers
    for meta in tickers_meta:
        sym = meta["symbol"]
        if not sym:
            continue
        sym_yf = sym if sym.upper().endswith(".NS") else sym + ".NS"
        try:
            df = yf.download(sym_yf, period=DEFAULT_PERIOD, interval=DEFAULT_INTERVAL, progress=False, auto_adjust=True)
            if df is None or df.empty:
                if verbose: print(f"Skipping {sym_yf}: no data"); continue
            if "Close" not in df.columns:
                df.columns = [c[1] if isinstance(c, tuple) and len(c) > 1 else c for c in df.columns]
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if not universe_filter(meta, df):
                if verbose: print(f"{sym_yf} failed universe filter."); continue
            ind = indicators(df)
            det = detect_pullback(ind, df)
            if not det.get("is_setup"):
                if verbose: print(f"{sym_yf}: no setup"); continue
            # optional 4H confirmation
            if confirm_4h_flag:
                ok4 = confirm_4h(sym_yf)
                if not ok4:
                    if verbose: print(f"{sym_yf}: 4H confirmation failed or unavailable"); continue
            sizing = compute_size(ind, portfolio_value)
            sizing["portfolio_value"] = portfolio_value
            if sizing["final_shares"] <= 0:
                if verbose: print(f"{sym_yf}: zero shares, skipping"); continue
            cand = {"symbol": sym_yf, "meta": meta, "indicators": ind, "detection": det, "sizing": sizing, "score": 0.0}
            # scoring
            adx_score = max(0.0, min(50.0, (ind.get("ADX14", 0.0) - 20.0) * 2.5))
            prox_score = max(0.0, min(25.0, (25.0 - abs(ind["distance_pct"] * 10.0))))
            vol_score = max(0.0, min(25.0, (ind.get("ADTV20_INR", 0.0) / ADTV_MIN_INR) * 12.5))
            total_score = adx_score + prox_score + vol_score
            cand["score"] = float(total_score)
            # Expected return using backtest stats if available
            stats = per_symbol_stats.get(sym_yf)
            if stats:
                win_rate = stats["win_rate"]
                avg_win_pct = stats["avg_win_pct"]
                avg_loss_pct = stats["avg_loss_pct"]
            else:
                win_rate = global_stats["win_rate"]
                avg_win_pct = global_stats["avg_win_pct"]
                avg_loss_pct = global_stats["avg_loss_pct"]
            expected_return_pct = win_rate * avg_win_pct + (1 - win_rate) * avg_loss_pct
            cand["expected_return_pct"] = float(expected_return_pct)
            signals.append(cand)
            if verbose:
                print(f"[CAND] {sym_yf}: score={total_score:.2f}, exp_ret={expected_return_pct*100:.2f}%, shares={sizing['final_shares']}")
            time.sleep(0.08)
        except Exception as e:
            if verbose: print(f"Error processing {sym_yf}: {e}")
            continue

    if not signals:
        if verbose: print("No signals found."); return []

    # Rank & select
    signals = sorted(signals, key=lambda s: (s["score"], s["expected_return_pct"]), reverse=True)
    selected = []
    active_positions = []
    for cand in signals:
        if cand["expected_return_pct"] < min_expected_return:
            continue
        chk = portfolio_checks(cand, active_positions, portfolio_value)
        if not chk["ok"]:
            continue
        selected.append(cand)
        active_positions.append(cand)
        if len(selected) >= max_positions:
            break

    # Emit JSON
    emitted = []
    for s in selected:
        sizing = s["sizing"]
        ind = s["indicators"]
        det = s["detection"]
        entry = {"entry_type": "next_open", "entry_price": sizing["entry_price"]}
        risk = {"stop_price": sizing["stop_price"], "risk_per_share": sizing["risk_per_share"], "target_price_primary": sizing["target_price_primary"]}
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
        signal = {
            "symbol": s["symbol"],
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "setup": det["setup_type"],
            "market_preflight": "PASS",
            "indicators": {"close": ind["close"], "EMA50": ind["EMA50"], "EMA200": ind["EMA200"], "ATR14": ind["ATR14"], "ADX14": ind["ADX14"], "ADTV20_INR": ind["ADTV20_INR"]},
            "entry": entry,
            "risk": risk,
            "sizing": sizing_out,
            "checks": {"sector_ok": True, "max_positions_ok": True},
            "score": s["score"],
            "expected_return_pct": s["expected_return_pct"],
            "notes": det["notes"],
            "meta": s["meta"]
        }
        emitted.append(signal)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.utcnow().isoformat() + "Z", "portfolio_value": portfolio_value, "signals": emitted}, f, indent=2, default=str)

    if verbose:
        print(f"\nEmitted {len(emitted)} signal(s). Saved to {OUTPUT_JSON}")

    return emitted

# -------------------------
# CLI entrypoint
# -------------------------
def main():
    p = argparse.ArgumentParser(description="Signal generator with backtest stats and optional 4H confirm")
    p.add_argument("--tickers", required=True, help="Tickers CSV file (Symbol, Sector optional)")
    p.add_argument("--portfolio", type=float, default=10000.0, help="Portfolio capital in INR")
    p.add_argument("--max-positions", type=int, default=3, help="Max positions to emit")
    p.add_argument("--min-expected-return", type=float, default=MIN_EXPECTED_RETURN_PCT, help="Min expected return (fraction)")
    p.add_argument("--backtest-csv", default=None, help="Backtest trades CSV to compute per-symbol stats")
    p.add_argument("--confirm-4h", action="store_true", help="Require 4H confirmation for setups")
    p.add_argument("--index-symbol", default="^NSEI", help="Index symbol for market preflight")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = p.parse_args()

    if not os.path.exists(args.tickers):
        print("Tickers file not found", args.tickers)
        return

    signals = run_pipeline(args.tickers, portfolio_value=args.portfolio, max_positions=args.max_positions,
                           min_expected_return=args.min_expected_return, backtest_csv=args.backtest_csv,
                           confirm_4h_flag=args.confirm_4h, index_symbol=args.index_symbol, verbose=args.verbose)

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
