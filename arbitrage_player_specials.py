"""Automated Player Specials Surebet Analyzer (TopTiket Under/Over markets)

This script mirrors the structure and output style of `arbitrage_football.py` and `arbitrage_nfl.py`
but is adapted for player specials where Under/Over markets are analyzed for various player statistics.

Workflow:
 1. Capture (requests + Selenium fallback) player specials page from TopTiket.
 2. Parse text & DOM heuristically for player names and Under/Over odds.
 3. Detect pure surebets (Under/Over markets) across single-book feed.
 4. Output results to `player_specials_surebets.txt` with stake suggestions.

Environment overrides (optional):
  PLAYER_MIN_PROFIT   – minimum profit % to list (default 0)
  PLAYER_STAKE_TOTAL  – base bankroll to allocate across two outcomes (default 100)

Usage:
  python arbitrage_player_specials.py [--min-profit 1.0] [--stake 250] [--pages 4]

Note: True cross-book arbitrage usually requires combining multiple bookmakers.
"""

from __future__ import annotations
import os
import re
import time
import argparse
from typing import List, Dict, Any, Tuple
from datetime import datetime

# Reuse functions from enhanced_player_specials_analyzer
import enhanced_player_specials_analyzer as player_specials

DEFAULT_TOTAL_STAKE = 100.0
DEFAULT_MIN_PROFIT = 0.0
DEFAULT_PAGES = 4
VALID_ODDS_RANGE = (1.01, 50.0)

# ---------------- Utility ---------------- #

def is_surebet_two_way(o1: float, o2: float) -> Tuple[bool, float, float]:
    """Return (is_surebet, margin_pct, roi_pct) for 2-way odds."""
    inv = (1/o1) + (1/o2)
    if inv < 1:
        margin = (1 - inv) * 100
        roi = ((1/inv) - 1) * 100
        return True, round(margin, 2), round(roi, 2)
    return False, 0.0, 0.0

def allocate_stakes(o1: float, o2: float, total: float) -> Dict[str, float]:
    """Calculate optimal stake allocation for two-way arbitrage."""
    inv = (1/o1) + (1/o2)
    s1 = (1/o1)/inv * total
    s2 = (1/o2)/inv * total
    return {'Under': round(s1, 2), 'Over': round(s2, 2)}

# ---------------- Capture + Parse ---------------- #

def capture_and_parse(verbose=False, pages=4):
    """Capture and parse player specials data."""
    success = player_specials.download_live_player_specials(
        headless=True,
        retries=2,
        selenium_wait=15,
        scroll_steps=6,
        pages=pages,
        verbose=verbose
    )
    
    if not success:
        if verbose:
            print("⚠️ Player specials capture failed. Continuing with any existing data if present.")
    
    # Convert HTML to text
    flat_file = player_specials.flatten_html_to_text(
        'live_player_specials_data.txt',
        'live_player_specials_extracted.txt'
    )
    
    matches = []
    if flat_file:
        with open(flat_file, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.strip()]
        matches = player_specials.parse_player_specials_flat(lines, verbose=verbose)
    
    # Fallback to DOM parsing if text parsing failed
    if not matches:
        if verbose:
            print("ℹ️ Text parsing found 0 matches, attempting DOM parsing.")
        matches = player_specials.parse_player_specials_dom(verbose=verbose)
    
    return matches

# ---------------- Surebet Detection ---------------- #

def detect_player_surebets(matches: List[Dict[str, Any]], min_profit: float, total_stake: float):
    """Detect surebet opportunities in player specials Under/Over markets."""
    surebets = []
    
    for m in matches:
        odds_map = m.get('odds', {})
        
        if 'Under' not in odds_map or 'Over' not in odds_map:
            continue
        
        o1, b1 = odds_map['Under']
        o2, b2 = odds_map['Over']
        
        # Validate odds range
        if not (VALID_ODDS_RANGE[0] <= o1 <= VALID_ODDS_RANGE[1] and 
                VALID_ODDS_RANGE[0] <= o2 <= VALID_ODDS_RANGE[1]):
            continue
        
        # Check for surebet
        is_surebet, margin, roi = is_surebet_two_way(o1, o2)
        if not is_surebet or roi < min_profit:
            continue
        
        # Calculate stakes
        stakes = allocate_stakes(o1, o2, total_stake)
        
        surebet_info = {
            'match': m['teams'],
            'player': m['player'],
            'stat_type': m['stat_type'],
            'type': 'Under/Over',
            'margin_pct': margin,
            'roi_pct': roi,
            'odds': {
                'Under': {'odd': o1, 'book': b1},
                'Over': {'odd': o2, 'book': b2}
            },
            'stakes': stakes,
        }
        
        surebets.append(surebet_info)
    
    # Sort by ROI descending
    return sorted(surebets, key=lambda x: x['roi_pct'], reverse=True)

# ---------------- Output ---------------- #

def write_player_specials_results(matches: List[Dict], surebets: List[Dict], pages: int):
    """Write results to player_specials_surebets.txt in the standard format."""
    with open("player_specials_surebets.txt", "w", encoding="utf-8") as f:
        # Header
        f.write("TOPTIKET PLAYER SPECIALS ANALYSIS\n")
        f.write(f"Total player specials: {len(matches)}\n")
        f.write(f"Surebets found: {len(surebets)}\n")
        f.write(f"Pages scraped: {pages}\n\n")
        
        if surebets:
            f.write("SUREBETS (Risk-Free Profit)\n")
            f.write("--------------------------------\n")
            
            # Group by player for better readability
            grouped = {}
            for sb in surebets:
                player = sb['player']
                grouped.setdefault(player, []).append(sb)
            
            # Sort players by best ROI
            def best_roi(group):
                return max(bet['roi_pct'] for bet in group)
            
            for player, group in sorted(grouped.items(), key=lambda kv: best_roi(kv[1]), reverse=True):
                f.write(f"{player}\n")
                
                for bet in sorted(group, key=lambda x: x['roi_pct'], reverse=True):
                    stat_type = bet['stat_type']
                    odds_str = f"Under={bet['odds']['Under']['odd']}, Over={bet['odds']['Over']['odd']}"
                    stakes_str = f"Under={bet['stakes']['Under']}, Over={bet['stakes']['Over']}"
                    
                    f.write(f"   - {stat_type}: Margin {bet['margin_pct']}% | "
                           f"ROI {bet['roi_pct']}% | odds[{odds_str}] | stakes({stakes_str})\n")
                
                f.write('\n')
        else:
            f.write("No true surebets detected with single TopTiket feed. ")
            f.write("Add other bookmakers to find cross-book arbitrage.\n\n")
        
        # Add timestamp and method info
        f.write(f"Generated on {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write("Generated via mixed text+DOM parsing.\n")
        
        # Basic stats if surebets exist
        if surebets:
            margins = [b['margin_pct'] for b in surebets]
            rois = [b['roi_pct'] for b in surebets]
            
            f.write(f"\nSTATISTICS:\n")
            f.write(f"- Margin range: {min(margins):.2f}% to {max(margins):.2f}%\n")
            f.write(f"- ROI range: {min(rois):.2f}% to {max(rois):.2f}%\n")
            f.write(f"- Average ROI: {sum(rois)/len(rois):.2f}%\n")

# ---------------- Main ---------------- #

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Player Specials Surebet Analyzer (TopTiket Under/Over markets)')
    parser.add_argument('--min-profit', type=float, 
                       default=float(os.environ.get('PLAYER_MIN_PROFIT', DEFAULT_MIN_PROFIT)),
                       help='Minimum profit percentage for surebets')
    parser.add_argument('--stake', type=float,
                       default=float(os.environ.get('PLAYER_STAKE_TOTAL', DEFAULT_TOTAL_STAKE)),
                       help='Total stake to allocate across outcomes')
    parser.add_argument('--pages', type=int, default=DEFAULT_PAGES,
                       help='Number of pages to scrape (default: 4)')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose output')
    
    args = parser.parse_args()
    
    print("🎯 Starting Player Specials Surebet Analysis...")
    print(f"📋 Settings: min_profit={args.min_profit}%, stake_total={args.stake}, pages={args.pages}")
    
    # Capture and parse data
    print("🔄 Capturing player specials data...")
    matches = capture_and_parse(verbose=args.verbose, pages=args.pages)
    
    if not matches:
        print("❌ No player specials data could be parsed. Exiting.")
        return
    
    print(f"📊 Parsed {len(matches)} player specials")
    
    # Detect surebets
    print("🔍 Analyzing for surebet opportunities...")
    surebets = detect_player_surebets(matches, args.min_profit, args.stake)
    
    # Write results
    write_player_specials_results(matches, surebets, args.pages)
    
    # Summary output
    print(f"✅ Analysis complete!")
    print(f"   • Total player specials: {len(matches)}")
    print(f"   • Surebets found: {len(surebets)}")
    print(f"   • Results saved to: player_specials_surebets.txt")
    
    if surebets:
        print(f"\n🎉 TOP PLAYER SPECIALS SUREBETS:")
        for i, sb in enumerate(surebets[:5], 1):  # Show top 5
            print(f"   {i}. {sb['player']} ({sb['stat_type']}) - ROI: {sb['roi_pct']}%")
    else:
        print("\nℹ️ No profitable surebets found. Consider:")
        print("   • Lowering --min-profit threshold")
        print("   • Adding more bookmaker feeds for cross-book arbitrage")
        print("   • Checking if the page structure has changed")

if __name__ == '__main__':
    main()