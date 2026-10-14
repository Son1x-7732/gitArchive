#!/usr/bin/env python3
"""
backtest_with_costs.py

Per-trade backtester (trade-level CSV) aligned to india_scanner_optimized.py logic.

- Reads tickers from CSV (auto-detect Symbol column) or a TXT file (one ticker per line).
- Uses same indicators and filter logic: >=3 of 4 checks where 4th = (volume OR liquidity).
- Position sizing: RISK_PER_TRADE and MAX_POSITION_PCT (uses PORTFOLIO_VALUE for sizing).
- Transaction cost model: conservative per-side costs + STT on sell.
- Outputs a CSV of trades and prints a short summary.

Usage:
    python backtest_with_costs.py [tickers_file]
    Or set env var NIFTY200_FILE to choose tickers file.
"""

import os
import sys
import time
import math
import argparse
from typing import List

import pandas as pd
import numpy as np
import yfinance as yf

# ---------------- Config / defaults (keep in sync with scanner) ----------------
DEFAULT_NIFTY_CSV = os.path.expanduser('~/trading-venv/data/nifty200.csv')
DEFAULT_NIFTY_TXT = os.path.expanduser('~/nifty200.txt')

PERIOD = "2y"
INTERVAL = "1d"
PAUSE = 0.06  # polite pause between yfinance calls

# Indicator params (same as scanner)
EMA_SHORT = 21
EMA_MED = 50
EMA_ENTRY = 10
RSI_LOWER = 25.0
RSI_UPPER = 50.0
VOLUME_SURGE_MULT = 1.5
VOLUME_SURGE_3DAY = 1.15
LIQUIDITY_TURNOVER_MIN = 1_000_000.0
LIQUIDITY_VMA_MIN = 50_000.0

# Backtest sizing & risk (same as scanner)
PORTFOLIO_VALUE = 1_000_000.0
RISK_PER_TRADE = 0.01        # 1% risk
MAX_POSITION_PCT = 0.08      # 8% max per position (value)

# Trade rules
K_STOP = 2.0
K_TARGET = 2.5
MAX_HOLD = 15   # days to hold before forced exit

# Transaction cost model (conservative)
BROKERAGE_PCT_PER_SIDE = 0.0002
OTHER_PCT_PER_SIDE = 0.00025
SLIPPAGE_PCT_PER_SIDE = 0.0005
STT_ON_SELL = 0.001

OUTFILE = 'backtest_trades_with_costs_optimized.csv'

# ---------------- Helpers ----------------
def load_tickers(path_or_none: str = None) -> List[str]:
    env_path = os.environ.get('NIFTY200_FILE')
    path = path_or_none or env_path or (DEFAULT_NIFTY_CSV if os.path.exists(DEFAULT_NIFTY_CSV) else DEFAULT_NIFTY_TXT)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Tickers file not found: {path}")

    tickers = []
    if path.lower().endswith('.csv'):
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        # find Symbol column (case-insensitive)
        symbol_col = None
        for c in df.columns:
            if c.strip().lower() == 'symbol' or 'symbol' in c.strip().lower():
                symbol_col = c
                break
        if symbol_col is None:
            # fallback heuristics
            if df.shape[1] >= 3:
                symbol_col = df.columns[2]
            else:
                symbol_col = df.columns[0]
        raw = df[symbol_col].astype(str).str.strip()
        for s in raw.values:
            if not s or s.lower() in ['nan', 'none']:
                continue
            tickers.append(s if '.' in s else s + '.NS')
    else:
        with open(path, 'r') as f:
            for ln in f:
                s = ln.strip()
                if not s:
                    continue
                tickers.append(s if '.' in s else s + '.NS')

    # dedupe
    seen = set(); out=[]
    for t in tickers:
        if t not in seen:
            seen.add(t); out.append(t)
    return out

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ['_'.join(map(str, c)).strip() for c in df.columns.values]
    col_map = {}
    for t in ['open','high','low','close','volume']:
        found = next((c for c in df.columns if t in c.lower()), None)
        if found:
            col_map[found] = t.capitalize()
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

def compute_costs(entry_price: float, exit_price: float, shares: int):
    tv_entry = entry_price * shares
    tv_exit = exit_price * shares
    entry_pct = BROKERAGE_PCT_PER_SIDE + OTHER_PCT_PER_SIDE + SLIPPAGE_PCT_PER_SIDE
    exit_pct = BROKERAGE_PCT_PER_SIDE + OTHER_PCT_PER_SIDE + SLIPPAGE_PCT_PER_SIDE + STT_ON_SELL
    entry_cost = tv_entry * entry_pct
    exit_cost = tv_exit * exit_pct
    total_cost = entry_cost + exit_cost
    return float(total_cost), float(entry_cost), float(exit_cost)

def check_filters_by_pos(df: pd.DataFrame, pos: int):
    if pos <= 0 or pos >= len(df):
        return False, False, False, False, False
    row = df.iloc[pos]
    trend = (row['ema20'] > row['ema50']) and (row['Close'] > row['ema50'])
    pull_pct_ok = (row['Close'] < row['ema10']) and (row['Close'] > row['ema50'] * (1 - 0.10))
    rsi_ok = (row['rsi14'] >= RSI_LOWER and row['rsi14'] <= RSI_UPPER)
    pullback = bool(pull_pct_ok or rsi_ok)
    macd_hist = row['macd_hist']
    macd_hist_prev = df['macd_hist'].iloc[pos-1] if pos-1 >= 0 else np.nan
    momentum = (macd_hist > 0 and (macd_hist_prev <= 0)) or (row['macd'] > row['macd_signal'])
    vma20 = row.get('vma20', np.nan)
    vol_today = row.get('Volume', 0.0)
    vol_ok = False
    if pd.notna(vma20) and vma20 > 0:
        three_day = df['Volume'].iloc[max(0, pos-2):pos+1].mean()
        vol_ok = (vol_today >= VOLUME_SURGE_MULT * vma20) or (three_day >= VOLUME_SURGE_3DAY * vma20)
    liq_ok = (row.get('avg_turnover20', 0.0) >= LIQUIDITY_TURNOVER_MIN) or (row.get('vma20', 0.0) >= LIQUIDITY_VMA_MIN)
    return bool(trend), bool(pullback), bool(momentum), bool(vol_ok), bool(liq_ok)

# ---------------- Single-ticker backtest (per-trade) ----------------
def simulate_one_ticker(sym: str):
    df = yf.download(sym, period=PERIOD, interval=INTERVAL, progress=False, auto_adjust=True)
    if df is None or df.empty:
        return None
    df = normalize_columns(df)
    close_cols = [c for c in df.columns if 'close' in c.lower()]
    if not close_cols:
        return None
    df['Close'] = df[close_cols[0]]
    for c in ['Open','High','Low','Close','Volume']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    df = compute_indicators(df)
    df = df.dropna(subset=['Close']).copy()
    if len(df) < 50:
        return None

    trades = []
    start_pos = max(60, 30)
    for pos in range(start_pos, len(df)-2):
        trend, pullback, momentum, volume_pass, liquidity_pass = check_filters_by_pos(df, pos)
        pass_count = int(trend) + int(pullback) + int(momentum) + int((volume_pass or liquidity_pass))
        if pass_count < 3:
            continue

        entry_pos = pos + 1
        if entry_pos >= len(df):
            break
        entry_open = df['Open'].iloc[entry_pos]
        if np.isnan(entry_open):
            continue
        atr = df['atr14'].iloc[entry_pos] if 'atr14' in df.columns else np.nan
        if pd.isna(atr) or atr <= 0:
            continue

        SL = entry_open - K_STOP * atr
        PT = entry_open + K_TARGET * atr

        risk_amount = PORTFOLIO_VALUE * RISK_PER_TRADE
        per_share_risk = entry_open - SL
        if per_share_risk <= 0:
            continue
        shares_by_risk = math.floor(risk_amount / per_share_risk)
        max_shares_by_value = math.floor((PORTFOLIO_VALUE * MAX_POSITION_PCT) / entry_open)
        shares = int(max(0, min(shares_by_risk, max_shares_by_value)))
        if shares <= 0:
            continue

        # simulate exit up to MAX_HOLD
        exit_price = None; exit_date = None; exit_type = None
        for j in range(entry_pos, min(entry_pos + MAX_HOLD + 1, len(df))):
            high = df['High'].iloc[j]; low = df['Low'].iloc[j]; close = df['Close'].iloc[j]
            if high >= PT:
                exit_price = PT; exit_date = df.index[j]; exit_type = 'target'; break
            if low <= SL:
                exit_price = SL; exit_date = df.index[j]; exit_type = 'stop'; break
        if exit_price is None:
            last_j = min(len(df)-1, entry_pos + MAX_HOLD)
            exit_price = df['Close'].iloc[last_j]; exit_date = df.index[last_j]; exit_type = 'times'

        gross_pnl = (exit_price - entry_open) * shares
        total_cost, entry_cost, exit_cost = compute_costs(entry_open, exit_price, shares)
        net_pnl = gross_pnl - total_cost

        trades.append({
            'symbol': sym,
            'entry_date': str(df.index[entry_pos]),
            'entry_price': float(entry_open),
            'exit_date': str(exit_date),
            'exit_price': float(exit_price),
            'exit_type': exit_type,
            'shares': shares,
            'gross_pnl': float(gross_pnl),
            'total_cost': float(total_cost),
            'net_pnl': float(net_pnl),
            'pass_count': pass_count
        })

    return trades if trades else None

# ---------------- Main ----------------
def main():
    parser = argparse.ArgumentParser(description='Backtest with costs (optimized)')
    parser.add_argument('tickers_file', nargs='?', default=None, help='CSV or TXT of tickers (optional)')
    parser.add_argument('--outfile', default=OUTFILE, help='output trades CSV name')
    args = parser.parse_args()

    try:
        tickers = load_tickers(args.tickers_file)
    except Exception as e:
        print("Failed to load tickers:", e); sys.exit(1)

    print(f"Backtesting {len(tickers)} tickers (period={PERIOD}) ...")
    all_trades = []
    for s in tickers:
        try:
            t = simulate_one_ticker(s)
            if t:
                all_trades += t
            time.sleep(PAUSE)
        except Exception as e:
            print("Err", s, e)
            continue

    if not all_trades:
        print("No trades generated.")
        return

    df_tr = pd.DataFrame(all_trades)
    df_tr.to_csv(args.outfile, index=False)

    total_trades = len(df_tr)
    wins = (df_tr['net_pnl'] > 0).sum()
    total_gross = df_tr['gross_pnl'].sum()
    total_net = df_tr['net_pnl'].sum()
    avg_net = df_tr['net_pnl'].mean()

    print(f"Trades: {total_trades} Wins (net): {wins} Win rate (net): {round(wins/total_trades,3)}")
    print(f"Total Gross PnL (INR): {round(total_gross,2)}")
    print(f"Total Net PnL after costs (INR): {round(total_net,2)} Avg net per trade: {round(avg_net,2)}")
    print("Saved", args.outfile)

if __name__ == '__main__':
    main()

