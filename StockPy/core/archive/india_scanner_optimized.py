#!/usr/bin/env python3
"""
india_scanner_optimized.py

Scanner for NIFTY200 (or any provided universe). Reads CSV (auto-extracts Symbol column)
or a plain text file of tickers. Applies optimized swing parameters and returns ranked_candidates.csv

Usage:
  - default: python india_scanner_optimized.py
    (it will look for $NIFTY200_FILE env var, CLI arg, or fallback to ~/trading-venv/data/nifty200.csv)
  - specify file: python india_scanner_optimized.py /path/to/nifty200.csv
  - or set env var: export NIFTY200_FILE=~/nifty200.txt && python india_scanner_optimized.py
"""

import os
import sys
import time
import math
import traceback
import argparse
from typing import List

import pandas as pd
import numpy as np
import yfinance as yf

# ---------------- Configurable defaults ----------------
DEFAULT_NIFTY_CSV = os.path.expanduser('~/trading-venv/data/nifty200.csv')
DEFAULT_NIFTY_TXT = os.path.expanduser('~/nifty200.txt')

# ====== Parameters (optimized for swing trading) ======
# You can override the tickers file via env var NIFTY200_FILE or provide a CLI argument.
PERIOD = "2y"
INTERVAL = "1d"
PAUSE = 0.12

# Portfolio parameters - OPTIMIZED
PORTFOLIO_VALUE = 1_000_000.0
RISK_PER_TRADE = 0.01
MAX_POSITIONS = 10
MAX_POSITION_PCT = 0.08

# Liquidity parameters - OPTIMIZED
LIQUIDITY_TURNOVER_MIN = 1_000_000.0
LIQUIDITY_VMA_MIN = 50_000.0

# Technical indicator parameters
EMA_SHORT = 21
EMA_MED = 50
EMA_ENTRY = 10
RSI_UPPER = 50.0
RSI_LOWER = 25.0
RSI_PULLBACK_MAX = 50.0
PULLBACK_PERCENT_FOR_SCORE = 0.06
VOLUME_SURGE_MULT = 1.5
VOLUME_SURGE_3DAY = 1.15

# Risk management
K_STOP = 2.0
K_TARGET = 2.5

# Scoring weights
W_TREND = 0.25
W_PULLBACK = 0.30
W_MOMENTUM = 0.20
W_VOLUME = 0.15
W_LIQUIDITY = 0.10

PAUSE_BETWEEN_TICKERS = PAUSE
OUT_CSV = 'ranked_candidates.csv'

# ---------------- Utilities ----------------
def load_tickers(path_or_none: str = None) -> List[str]:
    """
    Load tickers from:
      - env var NIFTY200_FILE
      - CLI argument (path_or_none)
      - default csv path (DEFAULT_NIFTY_CSV)
      - fallback ~/nifty200.txt

    Supports:
      - CSV with a Symbol column (case-insensitive 'Symbol') -> uses that column
      - CSV with tickers in 1st/3rd column (common layouts)
      - plain text file with one ticker per line
    Returns list of tickers in Yahoo format (e.g., 'RELIANCE.NS')
    """
    # Decide file path
    env_path = os.environ.get('NIFTY200_FILE')
    path = path_or_none or env_path or (DEFAULT_NIFTY_CSV if os.path.exists(DEFAULT_NIFTY_CSV) else DEFAULT_NIFTY_TXT)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Tickers file not found: {path}")

    # If CSV
    lower = path.lower()
    tickers = []
    if lower.endswith('.csv'):
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        # try to find a Symbol column
        symbol_col = None
        for candidate in ['symbol', 'Symbol', 'SYMBOL', 'Ticker', 'ticker', 'TICKER']:
            if candidate in df.columns:
                symbol_col = candidate
                break
        if symbol_col is None:
            # fallback: if 3+ columns, assume 3rd column is Symbol (common NSE dump)
            if df.shape[1] >= 3:
                symbol_col = df.columns[2]
            else:
                # fallback: take first column
                symbol_col = df.columns[0]
        raw = df[symbol_col].astype(str).str.strip()
        for s in raw.values:
            if s == '' or s.lower() in ['nan', 'none']:
                continue
            # if symbol contains a dot (e.g., '.NS' already) leave it; else append .NS
            if '.' in s:
                tickers.append(s)
            else:
                tickers.append(s + '.NS')
    else:
        # plain text: one ticker per line
        with open(path, 'r') as f:
            for ln in f:
                s = ln.strip()
                if not s:
                    continue
                if '.' in s:
                    tickers.append(s)
                else:
                    tickers.append(s + '.NS')
    # dedupe while preserving order
    seen = set()
    out = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ['_'.join(map(str, c)).strip() for c in df.columns.values]
    col_map = {}
    for target in ["open", "high", "low", "close", "volume"]:
        found = next((c for c in df.columns if target in c.lower()), None)
        if found:
            col_map[found] = target.capitalize()
    if col_map:
        df = df.rename(columns=col_map)
    return df

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close = df['Close']
    high = df['High']
    low = df['Low']
    vol = df['Volume']

    df['ema10'] = close.ewm(span=10, adjust=False).mean()
    df['ema20'] = close.ewm(span=EMA_SHORT, adjust=False).mean()
    df['ema50'] = close.ewm(span=EMA_MED, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    df['rsi14'] = 100 - (100 / (1 + rs))
    df['rsi14'] = df['rsi14'].bfill()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr14'] = tr.rolling(window=14, min_periods=1).mean()

    df['vma20'] = vol.rolling(window=20, min_periods=1).mean()
    df['avg_price20'] = close.rolling(window=20, min_periods=1).mean()
    df['avg_turnover20'] = df['vma20'] * df['avg_price20']

    return df

def score_candidate(row: dict, universe_median_atr: float) -> dict:
    # Trend score
    trend_score = 1.0 if (row.get('ema20', 0) > row.get('ema50', 0) and row.get('Close', 0) > row.get('ema50', 0)) else (0.5 if row.get('ema20', 0) > row.get('ema50', 0) else 0.0)

    # Pullback RSI score
    rsi = row.get('rsi14', np.nan)
    if pd.notna(rsi):
        pull_rsi_score = max(0.0, min(1.0, (RSI_PULLBACK_MAX - rsi) / (RSI_PULLBACK_MAX - RSI_LOWER)))
    else:
        pull_rsi_score = 0.0

    # Pullback price score
    if pd.notna(row.get('ema10')) and row.get('ema10') != 0:
        d = (row.get('ema10') - row.get('Close')) / row.get('ema10')
        pull_pct_score = max(0.0, min(1.0, d / PULLBACK_PERCENT_FOR_SCORE))
    else:
        pull_pct_score = 0.0

    pullback_score = max(pull_rsi_score, pull_pct_score)

    # Momentum score
    macd_hist = row.get('macd_hist', 0.0)
    macd_hist_prev = row.get('macd_hist_prev', 0.0)
    momentum_score = 0.0
    if pd.notna(macd_hist) and pd.notna(macd_hist_prev):
        if macd_hist > 0 and macd_hist_prev <= 0:
            momentum_score = 1.0
        elif row.get('macd', 0) > row.get('macd_signal', 0):
            momentum_score = 0.8
        else:
            diff = macd_hist - macd_hist_prev
            denom = abs(macd_hist_prev) + 1e-9
            momentum_score = max(0.0, min(1.0, (diff / denom) / 2.0 + 0.5))
    else:
        momentum_score = 0.0

    # Volume score
    vma20 = row.get('vma20', np.nan)
    vol_today = row.get('Volume', 0.0)
    vol_score = 0.0
    if pd.notna(vma20) and vma20 > 0:
        vol_score = min(1.0, vol_today / (VOLUME_SURGE_MULT * vma20))

    # Liquidity score
    avg_turn = row.get('avg_turnover20', 0.0)
    vma = vma20 if pd.notna(vma20) else 0.0
    liq_score = 0.0
    if avg_turn >= LIQUIDITY_TURNOVER_MIN or vma >= LIQUIDITY_VMA_MIN:
        liq_score = 1.0
    else:
        t = avg_turn / (LIQUIDITY_TURNOVER_MIN + 1e-9)
        v = vma / (LIQUIDITY_VMA_MIN + 1e-9)
        liq_score = max(0.0, min(1.0, 0.6 * t + 0.4 * v))

    score = (W_TREND * trend_score + W_PULLBACK * pullback_score +
             W_MOMENTUM * momentum_score + W_VOLUME * vol_score + W_LIQUIDITY * liq_score)

    # Position sizing
    atr = row.get('atr14', np.nan)
    entry = row.get('Close', np.nan)
    if pd.notna(entry) and pd.notna(atr) and atr > 0:
        SL = entry - K_STOP * atr
        PT = entry + K_TARGET * atr
        risk_per_trade_amount = PORTFOLIO_VALUE * RISK_PER_TRADE
        per_share_risk = max(1e-6, (entry - SL))
        shares_by_risk = math.floor(risk_per_trade_amount / per_share_risk) if per_share_risk > 0 else 0
        max_shares_by_value = math.floor((PORTFOLIO_VALUE * MAX_POSITION_PCT) / entry)
        suggested_shares = int(max(0, min(shares_by_risk, max_shares_by_value)))
        position_value = suggested_shares * entry
    else:
        SL = np.nan; PT = np.nan; suggested_shares = 0; position_value = 0.0

    return {
        'score': score,
        'trend_score': trend_score,
        'pullback_score': pullback_score,
        'momentum_score': momentum_score,
        'vol_score': vol_score,
        'liq_score': liq_score,
        'SL': SL,
        'PT': PT,
        'suggested_shares': suggested_shares,
        'position_value': position_value
    }

# ---------------- Filter checks ----------------
def check_filters_by_pos(df: pd.DataFrame, pos: int):
    if pos <= 0 or pos >= len(df):
        return False, False, False, False, False
    row = df.iloc[pos]
    trend = (row['ema20'] > row['ema50']) and (row['Close'] > row['ema50'])
    pull_pct_ok = (row['Close'] < row['ema10']) and (row['Close'] > row['ema50'] * (1 - 0.10))
    rsi_ok = (row['rsi14'] >= RSI_LOWER and row['rsi14'] <= RSI_UPPER)
    pullback = bool(pull_pct_ok or rsi_ok)
    macd_hist = row['macd_hist']
    macd_hist_prev = df['macd_hist'].iloc[pos - 1] if pos - 1 >= 0 else np.nan
    momentum = (macd_hist > 0 and (macd_hist_prev <= 0)) or (row['macd'] > row['macd_signal'])
    vma20 = row.get('vma20', np.nan)
    vol_today = row.get('Volume', 0.0)
    volume_ok = False
    if pd.notna(vma20) and vma20 > 0:
        three_day = df['Volume'].iloc[max(0, pos - 2):pos + 1].mean()
        volume_ok = (vol_today >= VOLUME_SURGE_MULT * vma20) or (three_day >= VOLUME_SURGE_3DAY * vma20)
    liquidity_ok = (row.get('avg_turnover20', 0.0) >= LIQUIDITY_TURNOVER_MIN) or (row.get('vma20', 0.0) >= LIQUIDITY_VMA_MIN)
    return bool(trend), bool(pullback), bool(momentum), bool(volume_ok), bool(liquidity_ok)

# ---------------- Main scanner ----------------
def main():
    parser = argparse.ArgumentParser(description="India scanner (NIFTY200) - optimized")
    parser.add_argument('tickers_file', nargs='?', default=None, help='Path to tickers file (CSV or TXT). If not given, uses NIFTY200_FILE env or default path.')
    args = parser.parse_args()

    try:
        tickers = load_tickers(args.tickers_file)
    except Exception as e:
        print("Error loading tickers:", e)
        sys.exit(1)

    print(f"Loaded {len(tickers)} tickers (first 10): {tickers[:10]}")

    results = []
    atr_list = []

    for sym in tickers:
        try:
            df = yf.download(sym, period=PERIOD, interval=INTERVAL, progress=False, auto_adjust=True)
            if df is None or df.empty:
                print(f"Skipping {sym}: no data")
                continue

            df = normalize_columns(df)
            close_cols = [c for c in df.columns if 'close' in c.lower()]
            if not close_cols:
                print(f"Skipping {sym}: no Close column")
                continue
            df['Close'] = df[close_cols[0]]

            # ensure numeric
            for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')

            df = compute_indicators(df)

            if len(df) < 50:
                print(f"Skipping {sym}: too little history ({len(df)} rows)")
                continue

            last = df.iloc[-1].copy()
            # macd_hist_prev safe assignment
            last['macd_hist_prev'] = df['macd_hist'].iloc[-2] if len(df) >= 2 else np.nan

            if pd.notna(last.get('atr14')):
                atr_list.append(last['atr14'])

            row = last.to_dict()
            sc = score_candidate(row, float(np.median(atr_list)) if atr_list else 0.0)

            out = {
                'symbol': sym,
                'date': last.name,
                'close': float(last['Close']),
                'rsi': float(last.get('rsi14', np.nan)),
                'ema10': float(last.get('ema10', np.nan)),
                'ema20': float(last.get('ema20', np.nan)),
                'ema50': float(last.get('ema50', np.nan)),
                'macd': float(last.get('macd', np.nan)),
                'macd_signal': float(last.get('macd_signal', np.nan)),
                'macd_hist': float(last.get('macd_hist', np.nan)),
                'macd_hist_prev': float(last.get('macd_hist_prev', np.nan)),
                'Volume': int(last.get('Volume', 0)),
                'vma20': float(last.get('vma20', np.nan)),
                'avg_turnover20': float(last.get('avg_turnover20', np.nan)),
            }

            out.update(sc)

            # Filter passes (matching backtest: >=3 of 4, with volume|liquidity combined)
            out['trend_pass'] = (out['ema20'] > out['ema50']) and (out['close'] > out['ema50'])
            pull_percent_ok = (out['close'] < out['ema10']) and (out['close'] > out['ema50'] * (1 - 0.10))
            rsi_ok = (out['rsi'] >= RSI_LOWER and out['rsi'] <= RSI_UPPER)
            out['pullback_pass'] = bool(pull_percent_ok or rsi_ok)
            out['momentum_pass'] = (out['macd_hist'] > 0 and out['macd_hist_prev'] <= 0) or (out['macd'] > out['macd_signal'])
            # volume pass uses last 3 days average
            three_day_vol_avg = float(df['Volume'].iloc[-3:].mean()) if len(df) >= 3 else float(df['Volume'].iloc[-1])
            out['volume_pass'] = (out['Volume'] >= VOLUME_SURGE_MULT * out['vma20']) or (three_day_vol_avg >= VOLUME_SURGE_3DAY * out['vma20'])
            out['liquidity_pass'] = (out['avg_turnover20'] >= LIQUIDITY_TURNOVER_MIN) or (out['vma20'] >= LIQUIDITY_VMA_MIN)

            # append results
            results.append(out)

            print(f"Scanned {sym}: score={out['score']:.3f}, rsi={out['rsi']:.1f}, trend={out['trend_pass']}, pullback={out['pullback_pass']}, mom={out['momentum_pass']}, vol={out['volume_pass']}, liq={out['liquidity_pass']}")

            time.sleep(PAUSE_BETWEEN_TICKERS)

        except Exception as e:
            print(f"Err scanning {sym}: {e}")
            traceback.print_exc()
            continue

    if not results:
        print("No tickers scanned successfully.")
        return

    df_out = pd.DataFrame(results)

    # CRITICAL FIX: New hard_pass logic matches backtest (>=3 of 4 filters)
    df_out['pass_count'] = (
        df_out['trend_pass'].astype(int) +
        df_out['pullback_pass'].astype(int) +
        df_out['momentum_pass'].astype(int) +
        ((df_out['volume_pass'] | df_out['liquidity_pass']).astype(int))
    )
    df_out['hard_pass'] = df_out['pass_count'] >= 3

    df_out = df_out.sort_values('score', ascending=False).reset_index(drop=True)

    # Summary
    print("\n--- Summary of filter passes ---")
    total = len(df_out)
    for col in ['trend_pass', 'pullback_pass', 'momentum_pass', 'volume_pass', 'liquidity_pass', 'hard_pass']:
        print(f"{col}: {int(df_out[col].sum())} / {total}")

    print("\nTop 20 by score (regardless of hard filters):")
    print(df_out.head(20)[['symbol', 'score', 'rsi', 'close', 'trend_pass', 'pullback_pass', 'momentum_pass', 'volume_pass', 'liquidity_pass', 'pass_count']].to_string(index=False))

    df_out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved {OUT_CSV}")

    top = df_out[df_out['hard_pass']].head(MAX_POSITIONS)
    if top.empty:
        print("\nNo candidates passed hard filters (>=3 of 4). Showing top scored tickers:")
        print(df_out.head(10)[['symbol', 'score', 'rsi', 'close', 'trend_pass', 'pullback_pass', 'momentum_pass', 'volume_pass', 'liquidity_pass', 'pass_count']].to_string(index=False))
    else:
        print(f"\nTop candidates (pass hard filters - >=3 of 4):")
        print(top[['symbol', 'score', 'rsi', 'close', 'suggested_shares', 'position_value', 'SL', 'PT', 'pass_count']].to_string(index=False))

    print(f"\n=== OPTIMIZATION SUMMARY ===")
    print(f"Data period: {PERIOD}")
    print(f"Risk per trade: {RISK_PER_TRADE:.1%}")
    print(f"Max positions: {MAX_POSITIONS}")
    print(f"Max position size: {MAX_POSITION_PCT:.1%}")
    print(f"Volume surge requirement: {VOLUME_SURGE_MULT}x")
    print(f"Liquidity requirement: ₹{LIQUIDITY_TURNOVER_MIN:,.0f}")
    print(f"RSI range: {RSI_LOWER}-{RSI_UPPER}")
    print(f"Stop/Target (ATR): {K_STOP}x / {K_TARGET}x")


if __name__ == '__main__':
    main()

