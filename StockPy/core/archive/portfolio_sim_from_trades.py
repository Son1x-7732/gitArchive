#!/usr/bin/env python3
"""
portfolio_sim_from_trades.py

Portfolio-level simulator that consumes a trade-level backtest CSV and simulates
realistic portfolio execution with capital, concurrency and per-position caps.

Behavior & features:
 - Input CSV: accepts command-line argument or BACKTEST_FILE env var. If not provided,
   will try to find a backtest_*.csv in the current directory and use the newest one.
 - Exits processed before entries on the same date.
 - If a trade's nominal position_value exceeds the dynamic MAX_POS_PCT * current_equity,
   the simulator will attempt to scale the trade down (floor shares) and accept scaled
   position if it is >= 50% of original size (configurable acceptance threshold).
   Otherwise the trade is skipped.
 - Produces:
     - portfolio_equity.csv  (date, equity, cash, reserved, open_positions)
     - executed_trades_portfolio.csv (details of executed trades, scaled shares, realized pnl)
     - skipped_trades_portfolio.csv  (trades skipped with reason)
"""

import os
import sys
import math
import glob
from collections import defaultdict
import pandas as pd
import numpy as np
from datetime import datetime

# ---------------- USER-TUNABLE PARAMETERS ----------------
INITIAL_EQUITY = 1_000_000.0
MAX_OPEN = 10             # max concurrent open positions
MAX_POS_PCT = 0.08        # max position size relative to equity (8%)
MIN_ACCEPT_SCALE = 0.5    # accept scaled position if >= 50% of original size
OUT_EQUITY_CSV = 'portfolio_equity.csv'
OUT_EXEC_CSV = 'executed_trades_portfolio.csv'
OUT_SKIPPED_CSV = 'skipped_trades_portfolio.csv'

# ---------------- Helper functions ----------------
def find_backtest_file():
    # priority: env var BACKTEST_FILE, CLI arg, else latest backtest*.csv in cwd
    env = os.environ.get('BACKTEST_FILE')
    if env and os.path.exists(env):
        return env
    # check for files matching backtest*.csv
    files = sorted(glob.glob('backtest*.csv'), key=os.path.getmtime, reverse=True)
    return files[0] if files else None

def safe_to_datetime(series):
    # coerce to datetime, keep NaT for bad values
    return pd.to_datetime(series, errors='coerce')

def load_backtest_csv(path):
    df = pd.read_csv(path)
    # normalize expected columns to lowercase keys for safety
    # but keep original columns for output
    return df

def try_get_numeric(df, col, default=0.0):
    if col in df.columns:
        return pd.to_numeric(df[col], errors='coerce').fillna(default)
    else:
        return pd.Series([default]*len(df), index=df.index)

def format_currency(x):
    return f"INR {x:,.2f}"

# ---------------- Main ----------------
def main():
    # CLI / env handling
    infile = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('BACKTEST_FILE')
    if infile is None:
        infile = find_backtest_file()
    if infile is None:
        print("No backtest CSV provided and no backtest*.csv found in current directory.")
        print("Usage: python portfolio_sim_from_trades.py [backtest.csv]")
        sys.exit(1)
    if not os.path.exists(infile):
        print("Input file not found:", infile)
        sys.exit(1)

    print(f"Running portfolio simulator on: {infile}")
    print(f"Initial equity: {format_currency(INITIAL_EQUITY)}, MAX_OPEN={MAX_OPEN}, MAX_POS_PCT={MAX_POS_PCT:.1%}")

    df = load_backtest_csv(infile)

    # parse dates safely
    for c in ['entry_date', 'exit_date']:
        if c in df.columns:
            df[c] = safe_to_datetime(df[c])

    # Ensure numeric columns exist
    # expected columns: entry_price, exit_price, shares, net_pnl
    df['entry_price'] = try_get_numeric(df, 'entry_price', np.nan)
    df['exit_price'] = try_get_numeric(df, 'exit_price', np.nan)
    df['shares'] = try_get_numeric(df, 'shares', 0).astype(int)
    df['net_pnl'] = try_get_numeric(df, 'net_pnl', 0.0)

    # filter out rows missing critical data
    valid_mask = (~df['entry_date'].isna()) & (~df['exit_date'].isna()) & (df['shares'] > 0) & (~df['entry_price'].isna())
    if not valid_mask.all():
        dropped = df.loc[~valid_mask].copy()
        if not dropped.empty:
            print(f"Warning: {len(dropped)} trades have missing entry/exit/share/price and will be skipped.")
        df = df.loc[valid_mask].copy()
    if df.empty:
        print("No valid trades after filtering. Exiting.")
        sys.exit(1)

    # Ensure exit_date >= entry_date; drop if not
    df = df.loc[df['exit_date'] >= df['entry_date']].copy()
    if df.empty:
        print("No trades with exit_date >= entry_date remain. Exiting.")
        sys.exit(1)

    # Build events list (date, type, idx)
    events = []
    for idx, row in df.iterrows():
        events.append((row['entry_date'].date(), 'entry', idx))
        events.append((row['exit_date'].date(), 'exit', idx))
    events.sort()

    # group events by date
    events_by_date = defaultdict(list)
    for d, typ, idx in events:
        events_by_date[d].append((typ, idx))
    unique_dates = sorted(events_by_date.keys())

    # simulation state
    cash = INITIAL_EQUITY
    reserved = {}          # idx -> reserved amount (entry_price * shares_used)
    open_trades = set()
    executed = set()       # indices executed
    skipped = {}           # idx -> reason
    executed_records = []  # to record executed trades with scaled shares and realized pnl

    equity_timeline = []

    # Process day by day
    for current_date in unique_dates:
        todays = events_by_date[current_date]

        # process exits first (free capital)
        for typ, idx in todays:
            if typ != 'exit':
                continue
            if idx in executed and idx in open_trades:
                # compute realized pnl: if we scaled shares, scale original net_pnl accordingly
                orig_shares = int(df.at[idx, 'shares'])
                orig_net = float(df.at[idx, 'net_pnl'])
                # get scaled shares/reserved if any
                scaled_shares = reserved.get(idx, None)
                if scaled_shares is None:
                    # should not happen (trade executed must be in reserved), but handle
                    # treat as zero effect
                    open_trades.discard(idx)
                    continue
                # reserved[idx] holds reserved_amount = scaled_shares * entry_price
                reserved_amount = reserved[idx]
                entry_price = float(df.at[idx, 'entry_price'])
                exit_price = float(df.at[idx, 'exit_price'])
                # compute scaled_net_pnl proportional to shares
                scaled_net_pnl = orig_net * (scaled_shares / orig_shares) if orig_shares > 0 else ( (exit_price - entry_price) * scaled_shares )
                # release reserved capital and add realized pnl
                cash += reserved_amount + scaled_net_pnl
                # record executed trade
                executed_records.append({
                    'idx': idx,
                    'symbol': df.at[idx, 'symbol'] if 'symbol' in df.columns else '',
                    'entry_date': df.at[idx, 'entry_date'],
                    'exit_date': df.at[idx, 'exit_date'],
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'orig_shares': orig_shares,
                    'executed_shares': int(scaled_shares),
                    'reserved_amount': reserved_amount,
                    'scaled_net_pnl': scaled_net_pnl,
                    'orig_net_pnl': orig_net,
                    'pass_count': int(df.at[idx, 'pass_count']) if 'pass_count' in df.columns else None
                })
                # cleanup
                open_trades.remove(idx)
                reserved.pop(idx, None)

        # process entries (after exits)
        entry_events = [e for e in todays if e[0] == 'entry']
        # sort by score if available
        if entry_events and 'score' in df.columns:
            entry_events.sort(key=lambda e: df.at[e[1], 'score'] if not pd.isna(df.at[e[1], 'score']) else 0.0, reverse=True)

        for typ, idx in entry_events:
            if idx in executed or idx in skipped:
                continue
            # enforce max open positions
            if len(open_trades) >= MAX_OPEN:
                skipped[idx] = 'max_open_reached'
                continue
            entry_price = float(df.at[idx, 'entry_price'])
            orig_shares = int(df.at[idx, 'shares'])
            if orig_shares <= 0 or math.isnan(entry_price):
                skipped[idx] = 'invalid_shares_or_price'
                continue
            nominal_value = entry_price * orig_shares
            # dynamic cap relative to current equity
            max_pos_value = MAX_POS_PCT * (cash + sum(reserved.values()))
            # if nominal > cap, attempt to scale down
            if nominal_value > max_pos_value:
                max_shares_affordable = int(math.floor(max_pos_value / entry_price))
                if max_shares_affordable <= 0:
                    skipped[idx] = 'position_too_large_for_equity'
                    continue
                # accept only if scaled >= MIN_ACCEPT_SCALE fraction
                if max_shares_affordable >= math.ceil(orig_shares * MIN_ACCEPT_SCALE):
                    scaled_shares = max_shares_affordable
                    scaled_value = scaled_shares * entry_price
                    # check cash
                    if cash >= scaled_value:
                        # execute scaled
                        cash -= scaled_value
                        reserved[idx] = scaled_shares
                        open_trades.add(idx)
                        executed.add(idx)
                    else:
                        # even scaled not affordable by available cash
                        skipped[idx] = 'not_enough_cash_after_scaling'
                        continue
                else:
                    skipped[idx] = 'would_scale_below_threshold'
                    continue
            else:
                # nominal fits within max_pos_value
                # check cash available
                if cash >= nominal_value:
                    cash -= nominal_value
                    reserved[idx] = orig_shares
                    open_trades.add(idx)
                    executed.add(idx)
                else:
                    # try to scale down based on cash only
                    max_shares_by_cash = int(math.floor(cash / entry_price))
                    if max_shares_by_cash >= math.ceil(orig_shares * MIN_ACCEPT_SCALE):
                        scaled_shares = max_shares_by_cash
                        scaled_value = scaled_shares * entry_price
                        cash -= scaled_value
                        reserved[idx] = scaled_shares
                        open_trades.add(idx)
                        executed.add(idx)
                    else:
                        skipped[idx] = 'not_enough_cash'
                        continue

        # snapshot equity: conservative view = cash + reserved (we treat reserved at cost)
        total_reserved = sum((reserved[idx] * float(df.at[idx, 'entry_price'])) for idx in reserved)
        total_equity = cash + total_reserved
        equity_timeline.append({
            'date': current_date,
            'equity': total_equity,
            'cash': cash,
            'reserved': total_reserved,
            'open_positions': len(open_trades)
        })

    # finished processing all dates
    # compute final metrics
    eq_df = pd.DataFrame(equity_timeline)
    final_equity = eq_df['equity'].iloc[-1] if not eq_df.empty else INITIAL_EQUITY

    total_executed = len(executed_records)
    total_skipped = len(skipped)

    exec_df = pd.DataFrame(executed_records) if executed_records else pd.DataFrame(columns=[
        'idx','symbol','entry_date','exit_date','entry_price','exit_price','orig_shares','executed_shares','reserved_amount','scaled_net_pnl','orig_net_pnl','pass_count'
    ])

    wins = (exec_df['scaled_net_pnl'] > 0).sum() if not exec_df.empty else 0
    losses = (exec_df['scaled_net_pnl'] <= 0).sum() if not exec_df.empty else 0
    win_rate = wins / total_executed if total_executed else 0.0
    total_net = exec_df['scaled_net_pnl'].sum() if not exec_df.empty else 0.0
    avg_net = exec_df['scaled_net_pnl'].mean() if not exec_df.empty else 0.0

    # drawdown and CAGR
    if not eq_df.empty:
        eq_df['peak'] = eq_df['equity'].cummax()
        eq_df['drawdown'] = (eq_df['equity'] - eq_df['peak']) / eq_df['peak']
        max_drawdown = eq_df['drawdown'].min()
        start_date = eq_df['date'].iloc[0]
        end_date = eq_df['date'].iloc[-1]
        years = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days / 365.25 if start_date and end_date else 0.0
        cagr = (final_equity / INITIAL_EQUITY) ** (1/years) - 1 if years > 0 and final_equity>0 else 0.0
    else:
        max_drawdown = 0.0
        cagr = 0.0

    avg_cash = eq_df['cash'].mean() if not eq_df.empty else INITIAL_EQUITY
    avg_reserved = eq_df['reserved'].mean() if not eq_df.empty else 0.0
    capital_utilization = avg_reserved / INITIAL_EQUITY if INITIAL_EQUITY else 0.0
    avg_open = eq_df['open_positions'].mean() if not eq_df.empty else 0.0

    # save outputs
    eq_df.to_csv(OUT_EQUITY_CSV, index=False)
    exec_df.to_csv(OUT_EXEC_CSV, index=False)
    # skipped details
    skipped_list = [{'idx': k, 'reason': v, 'symbol': df.at[k,'symbol'] if 'symbol' in df.columns else ''} for k,v in skipped.items()]
    pd.DataFrame(skipped_list).to_csv(OUT_SKIPPED_CSV, index=False)

    # print summary
    print("\n=== PORTFOLIO SIMULATION SUMMARY ===")
    print(f"Initial equity: {format_currency(INITIAL_EQUITY)}")
    print(f"Final equity:   {format_currency(final_equity)}")
    print(f"Net PnL (realized from executed trades): {format_currency(final_equity - INITIAL_EQUITY)}")

    print(f"\nTrades executed: {total_executed}  Trades skipped: {total_skipped}")
    print(f"Wins (executed): {wins}  Losses (executed): {losses}  Win rate: {win_rate:.3f}")
    print(f"Total net (executed trades): {format_currency(total_net)}  Avg net per executed trade: {format_currency(avg_net)}")

    print(f"\nMax drawdown: {max_drawdown:.3%}")
    print(f"Approx CAGR: {cagr:.2%}")

    print(f"\nSaved files:")
    print(f"  Equity curve: {OUT_EQUITY_CSV}")
    print(f"  Executed trades: {OUT_EXEC_CSV}")
    print(f"  Skipped trades: {OUT_SKIPPED_CSV}")

if __name__ == '__main__':
    main()

