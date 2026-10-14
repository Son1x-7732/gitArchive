#!/usr/bin/env python3
"""
run_pipeline.py

Run scanner -> backtest -> portfolio simulator in sequence.
Assumes:
 - core scripts live in ~/trading-venv/core/
   - india_scanner_optimized.py
   - backtest_with_costs.py
   - portfolio_sim_from_trades.py
 - default tickers file: ~/trading-venv/data/nifty200.csv

Usage (from any folder, but venv should be activated):
  python ~/trading-venv/core/run_pipeline.py
  or with explicit tickers:
  python ~/trading-venv/core/run_pipeline.py --tickers ~/trading-venv/data/nifty200.csv
"""

import os
import sys
import argparse
import subprocess
import glob
import csv
from pathlib import Path

SCRIPT_DIR_DEFAULT = os.path.expanduser("~/trading-venv/core")
TICKERS_DEFAULT = os.path.expanduser("~/trading-venv/data/nifty200.csv")
EXPECTED_BACKTEST = "backtest_trades_with_costs_optimized.csv"

def summary_from_backtest(path):
    """Lightweight CSV summary using stdlib csv (no pandas)."""
    total = 0
    wins = 0
    gross = 0.0
    net = 0.0
    avg = None
    med = None

    vals = []
    try:
        with open(path, newline='') as f:
            reader = csv.DictReader(f)
            for r in reader:
                total += 1
                # defensive parsing
                try:
                    net_p = float(r.get('net_pnl') or 0.0)
                except Exception:
                    net_p = 0.0
                try:
                    gross_p = float(r.get('gross_pnl') or 0.0)
                except Exception:
                    gross_p = 0.0
                gross += gross_p
                net += net_p
                vals.append(net_p)
                if net_p > 0:
                    wins += 1
    except FileNotFoundError:
        return None

    avg = (net / total) if total else 0.0
    # median
    vals.sort()
    if vals:
        mid = len(vals) // 2
        med = (vals[mid] if len(vals)%2==1 else (vals[mid-1]+vals[mid])/2)
    else:
        med = 0.0

    return {
        'total_trades': total,
        'wins': wins,
        'win_rate': (wins/total if total else 0.0),
        'gross_pnl': gross,
        'net_pnl': net,
        'avg_net': avg,
        'median_net': med
    }

def find_backtest_file(cwd):
    # check expected name first
    p_expected = os.path.join(cwd, EXPECTED_BACKTEST)
    if os.path.exists(p_expected):
        return p_expected
    # fallback: newest backtest*.csv
    files = glob.glob(os.path.join(cwd, "backtest*.csv"))
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def run_cmd(args, cwd):
    print(f"\n>> Running: {' '.join(args)} (cwd={cwd})\n")
    # run and forward output to console; raise CalledProcessError if exit != 0
    subprocess.run(args, cwd=cwd, check=True)

def main():
    parser = argparse.ArgumentParser(description="Run scanner -> backtest -> portfolio sim pipeline")
    parser.add_argument("--core-dir", default=SCRIPT_DIR_DEFAULT, help="Directory with core scripts (default ~/trading-venv/core)")
    parser.add_argument("--tickers", default=TICKERS_DEFAULT, help="Tickers CSV (default ~/trading-venv/data/nifty200.csv)")
    parser.add_argument("--no-portfolio", action="store_true", help="Run scanner+backtest only (skip portfolio sim)")
    parser.add_argument("--python", default=sys.executable, help="Python executable to run scripts (default current interpreter)")
    args = parser.parse_args()

    core_dir = os.path.abspath(os.path.expanduser(args.core_dir))
    tickers = os.path.abspath(os.path.expanduser(args.tickers))
    py_exec = args.python

    # sanity checks
    if not os.path.isdir(core_dir):
        print("ERROR: core directory not found:", core_dir)
        sys.exit(1)

    scanner = os.path.join(core_dir, "india_scanner_optimized.py")
    backtest = os.path.join(core_dir, "backtest_with_costs.py")
    portfolio = os.path.join(core_dir, "portfolio_sim_from_trades.py")

    for p in (scanner, backtest, portfolio):
        if not os.path.exists(p):
            print(f"ERROR: required script not found: {p}")
            sys.exit(1)

    if not os.path.exists(tickers):
        print("ERROR: tickers file not found:", tickers)
        sys.exit(1)

    print("Pipeline settings:")
    print("  core dir :", core_dir)
    print("  tickers  :", tickers)
    print("  python   :", py_exec)
    print("  skip portfolio:", args.no_portfolio)

    try:
        # 1) Run scanner
        run_cmd([py_exec, scanner, tickers], cwd=core_dir)

        # 2) Run backtest
        run_cmd([py_exec, backtest, tickers], cwd=core_dir)

        # find the generated backtest CSV
        backtest_csv = find_backtest_file(core_dir)
        if not backtest_csv:
            print("ERROR: backtest CSV not found after backtest run.")
            sys.exit(1)
        print("\nBacktest CSV found at:", backtest_csv)

        # print small summary (no pandas)
        s = summary_from_backtest(backtest_csv)
        if s:
            print("\n=== Backtest summary (quick) ===")
            print(f"Total trades: {s['total_trades']}")
            print(f"Wins: {s['wins']}  Win rate: {s['win_rate']:.4f}")
            print(f"Total gross PnL: {s['gross_pnl']:.2f}")
            print(f"Total net PnL: {s['net_pnl']:.2f}")
            print(f"Avg net per trade: {s['avg_net']:.2f}  Median net: {s['median_net']:.2f}")
        else:
            print("Could not summarize backtest CSV.")

        # 3) Run portfolio simulator (unless skipped)
        if not args.no_portfolio:
            run_cmd([py_exec, portfolio, backtest_csv], cwd=core_dir)
            # look for portfolio_equity.csv in core_dir
            pe = os.path.join(core_dir, "portfolio_equity.csv")
            exec_tr = os.path.join(core_dir, "executed_trades_portfolio.csv")
            skip_tr = os.path.join(core_dir, "skipped_trades_portfolio.csv")
            print("\nPortfolio outputs (if produced):")
            for f in (pe, exec_tr, skip_tr):
                if os.path.exists(f):
                    print("  -", f)
                else:
                    print("  - not found:", f)
        else:
            print("Skipped portfolio simulation as requested.")

        print("\nPipeline finished. Inspect the CSVs in", core_dir)
        print("Useful quick checks:")
        print("  head -n 8 ranked_candidates.csv")
        print("  head -n 8", os.path.basename(backtest_csv))
        print("  head -n 8 executed_trades_portfolio.csv (after portfolio run)")

    except subprocess.CalledProcessError as e:
        print("\nERROR: a step failed. See the earlier output for details.")
        sys.exit(e.returncode)
    except Exception as e:
        print("\nERROR:", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()

