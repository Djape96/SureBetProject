"""Automated NFL Surebet Analyzer (TopTiket 1/2 market)

This script mirrors the structure and output style of `arbitrage_football.py` but
is adapted for NFL where only 2-way (Home/Away) markets are currently parsed.

Workflow:
 1. Capture (requests + optional Selenium fallback) NFL odds page from TopTiket.
 2. Parse text & DOM heuristically (reusing logic from `enhanced_nfl_analyzer`).
 3. Detect pure surebets (1/2 market) across single-book feed (rare) – mainly
    provided for consistency; true cross-book edges usually require combining
    multiple bookmakers.
 4. Output results to `nfl_surebets.txt` with stake suggestions for a 100 unit
    bankroll allocation example.

Environment overrides (optional):
  NFL_MIN_PROFIT   – minimum profit % to list (default 0)
  NFL_STAKE_TOTAL  – base bankroll to allocate across two outcomes (default 100)

Usage:
  python arbitrage_nfl.py [--min-profit 1.0] [--stake 250]

Future extension: integrate additional bookmakers for cross-book arbitrage.
"""
from __future__ import annotations
import os, re, time, json, argparse
from typing import List, Dict, Any, Tuple

# Reuse functions from enhanced_nfl_analyzer instead of duplicating logic
import enhanced_nfl_analyzer as nfl

DEFAULT_TOTAL_STAKE = 100.0
DEFAULT_MIN_PROFIT = 0.0
VALID_ODDS_RANGE = (0.5, 69.0)

# ---------------- Utility ---------------- #

def is_surebet_two_way(o1: float, o2: float) -> Tuple[bool, float, float]:
    """Return (is_surebet, margin_pct, roi_pct) for 2-way odds."""
    inv = (1/o1) + (1/o2)
    if inv < 1:
        margin = (1 - inv) * 100
        roi = ((1/inv) - 1) * 100
        return True, round(margin,2), round(roi,2)
    return False, 0.0, 0.0

def allocate_stakes(o1: float, o2: float, total: float) -> Dict[str, float]:
    inv = (1/o1) + (1/o2)
    s1 = (1/o1)/inv * total
    s2 = (1/o2)/inv * total
    return {'Home': round(s1,2), 'Away': round(s2,2)}

# ---------------- Capture + Parse ---------------- #

def capture_and_parse(verbose=False, three_days=False):
    ok = nfl.download_nfl_html(use_selenium=True, headless=True, selenium_wait=10, verbose=verbose, three_days=three_days)
    if not ok:
        if verbose:
            print("⚠️ NFL capture failed. Continuing with any existing nfl_live_data.txt if present.")
    txt = nfl.extract_text_nfl(verbose=verbose)
    matches = []
    if txt:
        matches = nfl.parse_nfl_text(txt, verbose=verbose)
    if not matches:
        if verbose:
            print("ℹ️ Text parsing found 0 matches, attempting DOM heuristic.")
        matches = nfl.parse_nfl_dom(verbose=verbose)
    return matches

# ---------------- Surebet Detection ---------------- #

def detect_two_way_surebets(matches: List[Dict[str, Any]], min_profit: float, total_stake: float):
    surebets = []
    for m in matches:
        odds_map = m.get('odds', {})
        if 'Home' not in odds_map or 'Away' not in odds_map:
            continue
        o1, b1 = odds_map['Home']
        o2, b2 = odds_map['Away']
        if not (VALID_ODDS_RANGE[0] <= o1 <= VALID_ODDS_RANGE[1] and VALID_ODDS_RANGE[0] <= o2 <= VALID_ODDS_RANGE[1]):
            continue
        ok, margin, roi = is_surebet_two_way(o1, o2)
        if not ok or roi < min_profit:
            continue
        stakes = allocate_stakes(o1, o2, total_stake)
        surebets.append({
            'match': m['teams'],
            'type': '1/2',
            'margin_pct': margin,
            'roi_pct': roi,
            'odds': {'Home': {'odd': o1, 'book': b1}, 'Away': {'odd': o2, 'book': b2}},
            'stakes': stakes,
        })
    return sorted(surebets, key=lambda x: x['roi_pct'], reverse=True)

# ---------------- Main ---------------- #

def main():
    parser = argparse.ArgumentParser(description='NFL Surebet Analyzer (TopTiket 1/2 market)')
    parser.add_argument('--min-profit', type=float, default=float(os.environ.get('NFL_MIN_PROFIT', DEFAULT_MIN_PROFIT)))
    parser.add_argument('--stake', type=float, default=float(os.environ.get('NFL_STAKE_TOTAL', DEFAULT_TOTAL_STAKE)))
    parser.add_argument('--three-days', action='store_true', help='Attempt to activate 3-day filter like football script.')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    print('🏈 Starting NFL Surebet Analyzer...')
    if args.verbose:
        print(f"🔧 Args: min_profit={args.min_profit}, stake={args.stake}, three_days={args.three_days}")

    matches = capture_and_parse(verbose=args.verbose, three_days=args.three_days)
    print(f"📊 Parsed {len(matches)} NFL matches with 1/2 odds")

    surebets = detect_two_way_surebets(matches, min_profit=args.min_profit, total_stake=args.stake)

    out_file = 'nfl_surebets.txt'
    with open(out_file, 'w', encoding='utf-8') as f:
        header = [
            'TOPTIKET NFL ANALYSIS',
            f'Total matches: {len(matches)}',
            f'Surebets found: {len(surebets)}',
            ''
        ]
        f.write('\n'.join(header) + '\n')
        if surebets:
            f.write('SUREBETS (Risk-Free Profit)\n')
            f.write('--------------------------------\n')
            for sb in surebets:
                stakes = sb['stakes']
                odds_line = f"Home={sb['odds']['Home']['odd']}, Away={sb['odds']['Away']['odd']}"
                stake_line = f"Home={stakes['Home']}, Away={stakes['Away']}"
                f.write(f"{sb['match']}\n")
                f.write(f"   - {sb['type']}: Margin {sb['margin_pct']}% | ROI {sb['roi_pct']}% | odds[{odds_line}] | stakes({stake_line})\n\n")
        else:
            f.write('No true surebets detected with single TopTiket feed. Add other bookmakers for cross-book 1/2 arbitrage.\n')
        f.write('\nGenerated via mixed text+DOM parsing.\n')

    print(f"✅ Analysis complete. Results -> {out_file}")
    print(f"🎯 Surebets detected: {len(surebets)}")

if __name__ == '__main__':
    main()
