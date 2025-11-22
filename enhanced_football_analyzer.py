"""
Live Football Odds Scraper - Complete Solution

This script provides multiple approaches to scrape live football odds:
1. Parse existing static files (like your current index_*.txt files)
2. Web scraping with requests (for non-JS sites)
3. Selenium-based scraping (for JS-heavy sites like TopTiket)

The advantage is that you can use your existing working parser while
having the framework ready for live scraping when needed.
"""

import glob
import re
import requests
from datetime import datetime
import os
import argparse
import time
import json

# ---------------- Configuration / Utility ---------------- #
DEFAULT_TOTAL_STAKE = 100  # Used for stake distribution example in verbose output
BEST_AGGREGATE = False  # global flag to pick best odds per market instead of first
EXCLUDED_BOOKMAKERS = set()  # Empty set - no bookmakers excluded

def compute_stakes(odds, total_stake=DEFAULT_TOTAL_STAKE, round_multiple=1):
    """Allocate stakes for a list of (odd, bookmaker) tuples forming a surebet.

    Correct formula (unrounded):
        inv_sum = Σ (1/odd_i)
        stake_i = total * (1/odd_i) / inv_sum  (so every outcome returns total / inv_sum)
        theoretical_return = total / inv_sum
        theoretical_profit_abs = theoretical_return - total
        theoretical_profit_pct = (1/inv_sum - 1) * 100

    Rounding strategy (discrete bet sizes in RSD):
        1. Floor each stake to nearest lower multiple (round_multiple)
        2. Distribute leftover units (round_multiple each) one-by-one to the outcome
           currently with the lowest projected return (stake * odd) to maximise the
           guaranteed minimum return.

    After rounding we compute the ACTUAL guaranteed profit using the minimum
    (stake_i * odd_i) – effective_total. If rounding destroys arbitrage the
    function returns empty stakes.

    Returns tuple:
        (stakes_list, profit_abs_actual, effective_total, profit_pct_actual,
         profit_abs_theoretical, profit_pct_theoretical)
    """
    valid = [(o, b) for o, b in odds if o > 0]
    if len(valid) < 2:
        return [], 0.0, 0, 0.0, 0.0, 0.0
    inv_sum = sum(1 / o for o, _ in valid)
    if inv_sum >= 1:  # not a surebet
        return [], 0.0, 0, 0.0, 0.0, 0.0

    if round_multiple < 1:
        round_multiple = 1

    # Theoretical (precise) stake sizes
    unrounded = []
    for o, b in valid:
        stake = total_stake * (1 / o) / inv_sum
        unrounded.append([stake, o, b])

    theoretical_return = total_stake / inv_sum
    theoretical_profit_abs = theoretical_return - total_stake
    theoretical_profit_pct = (1 / inv_sum - 1) * 100

    # 1. Floor rounding
    rounded = []
    for stake, o, b in unrounded:
        floored = int(stake // round_multiple * round_multiple)
        if floored <= 0:  # ensure at least one unit if stake was positive
            floored = round_multiple
        rounded.append([floored, o, b])
    effective_total = sum(r[0] for r in rounded)
    # 2. Distribute leftover to match or exceed target total (but not exceed by more than one step per cycle)
    diff = total_stake - effective_total
    # If diff negative (floors overshot due to adjustments), we will remove units from outcomes with highest return surplus
    # but given pure flooring diff should be >= 0 normally unless forced minimal stakes above target.
    # Distribute positive diff greedily to lowest current return.
    def current_min_return():
        return min(r[0] * r[1] for r in rounded)
    while diff >= round_multiple and rounded:
        # pick outcome with lowest current return (stake * odd)
        rounded.sort(key=lambda x: x[0] * x[1])
        rounded[0][0] += round_multiple
        diff -= round_multiple
    # If we still have a small positive diff (< round_multiple) we ignore (can't allocate a partial unit)
    effective_total = sum(r[0] for r in rounded)

    # Compute actual guaranteed profit after rounding
    returns = [r[0] * r[1] for r in rounded]
    min_return = min(returns)
    profit_abs_actual = min_return - effective_total
    profit_pct_actual = (profit_abs_actual / effective_total * 100) if effective_total > 0 else 0.0

    # If arbitrage lost (profit <= 0) return empty to signal caller to skip (rounding killed edge)
    if profit_abs_actual <= 0:
        return [], 0.0, effective_total, 0.0, round(theoretical_profit_abs, 2), round(theoretical_profit_pct, 2)

    # Round values for presentation
    profit_abs_actual = round(profit_abs_actual, 2)
    profit_pct_actual = round(profit_pct_actual, 2)
    theoretical_profit_abs = round(theoretical_profit_abs, 2)
    theoretical_profit_pct = round(theoretical_profit_pct, 2)

    stakes_list = [(r[0], r[1], r[2]) for r in rounded]
    return (stakes_list, profit_abs_actual, effective_total, profit_pct_actual,
            theoretical_profit_abs, theoretical_profit_pct)

# Helper to choose a concrete total stake within range (simple: pick mid or explicit override)
def choose_total_stake(min_total, max_total, explicit=None):
    if explicit is not None:
        return explicit
    if max_total < min_total:
        max_total = min_total
    # Simple strategy: midpoint rounded to nearest 100
    mid = (min_total + max_total) // 2
    # Align to 100 for default RSD betting convenience
    mid = int(round(mid / 100) * 100)
    return max(min_total, min(mid, max_total))

def check_surebet(odds):
    """Check if odds represent a surebet opportunity.
    odds: list[(odd, bookmaker)]
    Returns profit_percent (float) or None.
    """
    clean = [o for o, _ in odds if 0.5 <= o <= 69]
    if len(clean) < 2:
        return None
    inv_sum = sum(1/o for o in clean)
    if inv_sum < 1:
        return round((1 - inv_sum) * 100, 2)
    return None

# ---------------- AUTO SNAPSHOT RAW PARSER ---------------- #
def _parse_auto_snapshot_lines(lines, verbose=False):
    """Parse AUTO-SNAPSHOT raw fallback including bookmaker names with resilient grouping.

    Strategy:
      1. Identify match header line containing time pattern (':MM').
      2. Next two lines = teams.
      3. Consume following lines until '+' code or next header; treat sequences of hyphen lines as separators between markets.
      4. For each market, take FIRST odds line shaped <number><bookie> where bookie may start with letter or digit.
      5. Map markets in order: Home, Draw, Away, 0-2, 3+, GG, GG3+.
    """
    matches = []
    order = ['Home','Draw','Away','0-2','3+','GG','GG3+']
    dt_re = re.compile(r':\d{2}$')
    sep_re = re.compile(r'^-+$')
    odd_re = re.compile(r'^(\d+(?:\.\d+)?)([A-Za-z0-9].*)$')  # allow bookie beginning with digit
    pure_num_re = re.compile(r'^\d+(?:\.\d+)?$')
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        if dt_re.search(line) and i+2 < n:
            team1 = lines[i+1].strip()
            team2 = lines[i+2].strip()
            i += 3
            block_lines = []
            while i < n and not lines[i].startswith('+') and not dt_re.search(lines[i]):
                block_lines.append(lines[i])
                i += 1
            # skip plus code line
            if i < n and lines[i].startswith('+'):
                i += 1
            market_idx = 0
            odds_map = {}
            have_in_market = False
            for bl in block_lines:
                if market_idx >= len(order):
                    break
                if sep_re.match(bl):
                    # separator; advance market only if we have captured something for current
                    if have_in_market:
                        market_idx += 1
                        have_in_market = False
                    continue
                # Accept numeric+bookie on same line OR pure numeric (assign placeholder bookie AUTO)
                m = odd_re.match(bl)
                if m and not have_in_market:
                    try:
                        val = float(m.group(1))
                        book = m.group(2).strip()
                        if 0.5 <= val <= 700:
                            odds_map[order[market_idx]] = (val, book)
                            have_in_market = True
                            continue
                    except ValueError:
                        pass
                if not have_in_market and pure_num_re.match(bl):
                    try:
                        val = float(bl)
                        if 0.5 <= val <= 700:
                            odds_map[order[market_idx]] = (val, 'AUTO')
                            have_in_market = True
                            continue
                    except ValueError:
                        pass
            if len(odds_map) >= 3:
                matches.append({'teams': f"{team1} vs {team2}", 'odds': odds_map})
                if verbose:
                    disp = ', '.join(f"{k}={v[0]}@{v[1]}" for k,v in odds_map.items())
                    print(f"[auto-raw] {team1} vs {team2} -> {disp}")
        else:
            i += 1
    if verbose:
        print(f"[auto-raw] Total matches parsed: {len(matches)}")
    return matches

def _parse_auto_snapshot_plain(lines, verbose=False):
    """Sequential numeric-first parser for AUTO snapshot when structured grouping fails.

    Improvements vs earlier version:
      - Accept pure numeric lines (e.g. '2.15') as odds without bookmaker; assign placeholder 'AUTO'.
      - Accept combined <number><bookie> lines (retain bookmaker name).
      - Preserve full decimal (avoid truncating final digit forming artifacts like 2.1@5).
      - Stops at plus code line (+XYZ) or next time header.
    """
    order = ['Home','Draw','Away','0-2','3+','GG','GG3+']
    dt_re = re.compile(r':\d{2}$')
    num_only_re = re.compile(r'^\d+(?:\.\d+)?$')
    num_bookie_re = re.compile(r'^(\d+(?:\.\d+)?)([A-Za-z][A-Za-z0-9].*)$')
    matches = []
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        if dt_re.search(line) and i+2 < n:
            team1 = lines[i+1].strip(); team2 = lines[i+2].strip()
            i += 3
            idx = 0
            odds_map = {}
            while i < n and idx < len(order):
                l = lines[i].strip()
                if l.startswith('+'):
                    i += 1
                    break
                if dt_re.search(l):
                    break
                # numeric + bookie pattern first
                mb = num_bookie_re.match(l)
                if mb:
                    try:
                        val = float(mb.group(1))
                        book = mb.group(2).strip()
                        if 0.5 <= val <= 700:
                            odds_map[order[idx]] = (val, book)
                            idx += 1
                            if verbose:
                                print(f"[auto-plain] captured {order[idx-1]} {val} {book}")
                            i += 1
                            continue
                    except ValueError:
                        pass
                # pure numeric fallback
                if num_only_re.match(l):
                    try:
                        val = float(l)
                        if 0.5 <= val <= 700:
                            odds_map[order[idx]] = (val, 'AUTO')
                            if verbose:
                                print(f"[auto-plain] captured {order[idx]} {val} AUTO")
                            idx += 1
                    except ValueError:
                        pass
                i += 1
            if len(odds_map) >= 3:
                matches.append({'teams': f"{team1} vs {team2}", 'odds': odds_map})
                if verbose:
                    disp = ', '.join(f"{k}={v[0]}@{v[1]}" for k,v in odds_map.items())
                    print(f"[auto-plain] {team1} vs {team2} -> {disp}")
        else:
            i += 1
    if verbose:
        print(f"[auto-plain] Total matches parsed: {len(matches)}")
    return matches

def fetch_api_json(api_url, headers=None, timeout=8, save_raw=True, verbose=False):
    """Attempt to fetch odds from a JSON API endpoint.
    This is a generic scaffold: it just GETs the URL and returns parsed JSON (or None).
    Headers can include auth / user-agent if required.
    If the response is not JSON it returns None.
    """
    try:
        if verbose:
            print(f"🌐 API request → {api_url}")
        h = headers or {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        resp = requests.get(api_url, headers=h, timeout=timeout)
        if resp.status_code != 200:
            if verbose:
                print(f"⚠️ API status {resp.status_code}")
            return None
        ct = resp.headers.get("Content-Type", "")
        if "json" not in ct.lower():
            if verbose:
                print("⚠️ API response not JSON content-type")
            # Try anyway
        try:
            data = resp.json()
        except ValueError:
            if verbose:
                print("⚠️ Failed to parse JSON body")
            return None
        if save_raw:
            with open("api_raw.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        if verbose:
            size = len(json.dumps(data))
            print(f"✅ API JSON received (approx {size/1024:.1f} KB)")
        return data
    except Exception as e:
        if verbose:
            print(f"❌ API fetch error: {e}")
        return None

def transform_api_json_to_matches(data, verbose=False):
    """Best-effort transformation of a generic JSON payload into internal match list.
    This is heuristic: it searches for objects containing team names and odds fields.
    Expected output: list of { teams: 'A vs B', odds: {Label: (odd, 'API')} }
    You must adapt the mapping once you know the real API structure.
    """
    matches = []
    if not data:
        return matches

    # If data is a dict and contains a top-level list candidate
    candidates = []
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        # pick the largest list value
        list_values = [v for v in data.values() if isinstance(v, list)]
        if list_values:
            candidates = max(list_values, key=len)
    
    processed = 0
    for item in candidates:
        if not isinstance(item, dict):
            continue
        # Heuristic keys
        home = item.get('home') or item.get('homeTeam') or item.get('team1') or item.get('Home')
        away = item.get('away') or item.get('awayTeam') or item.get('team2') or item.get('Away')
        if not (home and away):
            continue
        odds_map = {}
        # 1X2 market
        for key in ['homePrice','homeOdd','home_odds','homeOdds','home']:  # possible variants
            if key in item and isinstance(item[key], (int,float)):
                odds_map['Home'] = (float(item[key]), 'API')
                break
        for key in ['drawPrice','drawOdd','draw_odds','drawOdds','x','draw']:
            if key in item and isinstance(item[key], (int,float)):
                odds_map['Draw'] = (float(item[key]), 'API')
                break
        for key in ['awayPrice','awayOdd','away_odds','awayOdds','away']:
            if key in item and isinstance(item[key], (int,float)):
                odds_map['Away'] = (float(item[key]), 'API')
                break
        # Over/Under style example (very speculative)
        if 'under25' in item and isinstance(item['under25'], (int,float)):
            odds_map['0-2'] = (float(item['under25']), 'API')
        if 'over25' in item and isinstance(item['over25'], (int,float)):
            odds_map['3+'] = (float(item['over25']), 'API')

        if len(odds_map) >= 2:
            matches.append({
                'teams': f"{home} vs {away}",
                'odds': odds_map
            })
            processed += 1
    if verbose:
        print(f"🧩 API transformation produced {processed} tentative matches")
    return matches

def parse_file(filename):
    """Parse a single file for matches and odds"""
    matches = []
    with open(filename, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    # Auto snapshot raw fallback detection
    if lines and lines[0].startswith('AUTO-SNAPSHOT RAW FALLBACK'):
        m1 = _parse_auto_snapshot_lines(lines, verbose=True)
        if not m1:
            m1 = _parse_auto_snapshot_plain(lines, verbose=True)
        return m1
    
    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip junk lines
        if any(x in line.lower() for x in ["fudbal", "košarka", "tenis", "promo", "banner", "http"]) \
           or re.match(r'^[\-\+\*]', line) \
           or line.isdigit():
            i += 1
            continue

        # Detect team lines
        if re.match(r'^[A-Za-zČĆŽŠĐ][A-ZaelatČĆŽŠĐ\s\-\.]+$', line):
            if i + 1 < len(lines) and re.match(r'^[A-Za-zČĆŽŠĐ][A-ZaelatČĆŽŠĐ\s\-\.]+$', lines[i + 1]):
                team1, team2 = line, lines[i + 1]
                current_match = {"teams": f"{team1} vs {team2}", "odds": {}}
                i += 2

                # Scan next 30 lines for odds, organizing by separator sections
                end = min(len(lines), i + 30)
                sections = []
                current_section = []
                
                for j in range(i, end):
                    l = lines[j].replace(',', '.')
                    
                    # Check for separator lines or match end markers
                    if ('----' in l or 
                        re.match(r'^[\+\-]?\d+$', l) or 
                        any(x in l.lower() for x in ["sre,", "uto,", "ned,", "čet,"]) or
                        j == end - 1):
                        if current_section:
                            sections.append(current_section)
                            current_section = []
                        # Stop if we see a date/time pattern indicating next match
                        if any(x in l.lower() for x in ["sre,", "uto,", "ned,", "čet,"]):
                            break
                        continue
                        
                    # Skip other junk lines
                    if re.match(r'^[\-\+]', l):
                        continue
                        
                    # Parse odds - handle special cases for bookmakers with numbers
                    if l.endswith('1xBet'):
                        # Special handling for 1xBet: extract odds from the beginning
                        odds_part = l[:-5]  # Remove '1xBet' from the end
                        try:
                            odd = float(odds_part)
                            book = '1xBet'
                            # Filter out extreme odds that are likely parsing errors
                            if 0.5 <= odd <= 69:  # Reasonable range for sports betting odds
                                current_section.append((odd, book))
                            continue
                        except ValueError:
                            pass
                    
                    if l.endswith('365rs'):
                        # Special handling for 365rs: extract odds from the beginning
                        odds_part = l[:-5]  # Remove '365rs' from the end
                        try:
                            odd = float(odds_part)
                            book = '365rs'
                            # Filter out extreme odds that are likely parsing errors
                            if 0.5 <= odd <= 69:  # Reasonable range for sports betting odds
                                current_section.append((odd, book))
                            continue
                        except ValueError:
                            pass
                    
                    # Regular parsing for other bookmakers
                    m = re.match(r'^(\d+(?:\.\d+)?)([A-Za-z].*)$', l)
                    if m:
                        odd = float(m.group(1))
                        book = m.group(2).strip()
                        # Filter out extreme odds that are likely parsing errors
                        if 0.5 <= odd <= 69:  # Reasonable range for sports betting odds
                            current_section.append((odd, book))
                
                # Add the last section if it exists
                if current_section:
                    sections.append(current_section)
                
                # Process sections: expect at least 4 sections for proper parsing
                if len(sections) >= 4:
                    if all(len(section) >= 1 for section in sections[:4]):
                        # Helper to choose best or first
                        def pick(section_list):
                            return max(section_list, key=lambda x: x[0]) if (BEST_AGGREGATE and section_list) else section_list[0]
                        # Home
                        current_match["odds"]["Home"] = pick(sections[0])
                        # Draw
                        current_match["odds"]["Draw"] = pick(sections[1])
                        # Away
                        current_match["odds"]["Away"] = pick(sections[2])
                        # 0-2: candidates from remaining in section2 (excluding the picked one) + section3 first elem if needed
                        zero_two_candidates = []
                        if len(sections[2]) > 1:
                            # remove chosen away if best aggregation might have picked not first; exclude exactly the tuple chosen
                            for tup in sections[2]:
                                if tup is current_match["odds"]["Away"]:
                                    continue
                                zero_two_candidates.append(tup)
                        if len(sections) > 3 and sections[3]:
                            zero_two_candidates.append(sections[3][0])
                        if zero_two_candidates:
                            current_match["odds"]["0-2"] = max(zero_two_candidates, key=lambda x: x[0]) if BEST_AGGREGATE else zero_two_candidates[0]
                        # 3+ candidates: remaining section3 (exclude any used for 0-2 if same object) or next section
                        plus_candidates = []
                        if len(sections) > 3:
                            start_index = 0
                            # if we used sections[3][0] exclusively for 0-2, allow picking another if available
                            if "0-2" in current_match["odds"] and sections[3]:
                                # If 0-2 came from sections[3][0], skip it for 3+ unless no alternative
                                src_02 = current_match["odds"]["0-2"]
                                for tup in sections[3]:
                                    if tup is src_02:
                                        continue
                                    plus_candidates.append(tup)
                            # If still empty, reuse first element
                            if not plus_candidates and sections[3]:
                                plus_candidates.append(sections[3][0])
                        if not plus_candidates and len(sections) > 4 and sections[4]:
                            plus_candidates.append(sections[4][0])
                        if plus_candidates:
                            current_match["odds"]["3+"] = max(plus_candidates, key=lambda x: x[0]) if BEST_AGGREGATE else plus_candidates[0]
                
                if len(current_match["odds"]) >= 4:  # At least 4 odds needed for meaningful analysis
                    matches.append(current_match)
            else:
                i += 1
        else:
            i += 1
    return matches

# ---------------- Flat Block Fallback Parser ---------------- #
def parse_flat_blocks(lines, min_odds_per_match=3, take_best=False, verbose=False):
    """Parse simplified repeating blocks in flattened live_extracted style.

    Pattern per match:
      <weekday token line>
      <time line with :MM>
      Team1
      Team2
      Seven odds lines (Home, Draw, Away, 0-2, 3+, GG, GG3+)
      +<code>

    We scan for time pattern then read forward.
    """
    dt_re = re.compile(r":\d{2}$")
    weekday_re = re.compile(r"^(sre|uto|ned|čet|pet|pon|sub),", re.IGNORECASE)
    num_re = re.compile(r"^\d+(?:\.\d+)?$")
    plus_re = re.compile(r"^\+")
    order = ['Home','Draw','Away','0-2','3+','GG','GG3+']
    out = []
    i = 0
    n = len(lines)
    while i < n:
        # Find weekday + time + two team lines
        if weekday_re.search(lines[i]) and i+3 < n and dt_re.search(lines[i+1]):
            time_line = lines[i+1]
            team1 = lines[i+2]
            team2 = lines[i+3]
            # Validate that team lines contain letter characters
            if not (re.search(r"[A-Za-z]", team1) and re.search(r"[A-Za-z]", team2)):
                i += 1
                continue
            i += 4
            odds_map = {}
            idx = 0
            collected_odds = []  # Track all collected odds first
            
            # Collect ALL odds until plus code or next weekday/time header
            while i < n:
                l = lines[i]
                if plus_re.match(l):
                    i += 1
                    break
                if weekday_re.search(l) and i+1 < n and dt_re.search(lines[i+1]):
                    # next block starting
                    break
                if num_re.match(l):
                    try:
                        val = float(l)
                        if 0.5 <= val <= 700:
                            collected_odds.append(val)
                    except ValueError:
                        pass
                i += 1
            
            # Only process matches with exactly 7 odds to avoid misinterpretation
            if len(collected_odds) == 7:
                for idx, val in enumerate(collected_odds):
                    label = order[idx]
                    if take_best and label in odds_map:
                        # store max
                        if val > odds_map[label][0]:
                            odds_map[label] = (val, 'AUTO')
                    else:
                        odds_map[label] = (val, 'AUTO')
                
                # Validate that we have reasonable odds distribution for surebet analysis
                # 1X2 odds should be >= 1.01, O/U odds should be reasonable
                has_1x2 = all(label in odds_map for label in ['Home', 'Draw', 'Away'])
                has_ou = all(label in odds_map for label in ['0-2', '3+'])
                
                # Additional validation: O/U odds should be complementary (not too similar)
                ou_valid = True
                if has_ou:
                    odd_02 = odds_map['0-2'][0]
                    odd_3plus = odds_map['3+'][0]
                    # If both O/U odds are very similar, it might be misaligned data
                    # Also check if the gap is too small for realistic O/U markets
                    if abs(odd_02 - odd_3plus) < 0.3:
                        ou_valid = False
                        if verbose:
                            print(f"   ⚠️ Suspicious O/U odds for {team1} vs {team2}: 0-2={odd_02}, 3+={odd_3plus} (too close: {abs(odd_02 - odd_3plus):.2f})")
                    # Additional check: O/U odds should have reasonable ranges
                    elif not (1.1 <= odd_02 <= 10.0 and 1.1 <= odd_3plus <= 10.0):
                        ou_valid = False
                        if verbose:
                            print(f"   ⚠️ Invalid O/U odds range for {team1} vs {team2}: 0-2={odd_02}, 3+={odd_3plus}")
                
                # Only add to output if we have exactly 7 odds AND valid market structure
                if len(odds_map) == 7 and has_1x2 and has_ou and ou_valid:
                    out.append({'teams': f"{team1} vs {team2}", 'odds': odds_map})
                    if verbose:
                        print(f"[flat] {team1} vs {team2} -> " + ', '.join(f"{k}={v[0]}" for k,v in odds_map.items()))
                elif verbose:
                    print(f"   ⚠️ Skipping {team1} vs {team2}: invalid market structure (7 odds but failed validation)")
            elif verbose and len(collected_odds) > 0:
                print(f"   ⚠️ Skipping {team1} vs {team2}: found {len(collected_odds)} odds, expected 7")
        else:
            i += 1
    if verbose:
        print(f"[flat] Parsed {len(out)} flat blocks (min_odds_per_match={min_odds_per_match})")
    return out

def download_live_data(
    use_selenium=True,
    headless=True,
    selenium_wait=8,
    min_content_kb=15,
    retries=2,
    verbose=False,
    scroll_steps=6,
    selector=None,
    log=None,
    pages=1,
    infinite_scroll_loops=0,
    three_days=False,
    verify_days=False,
    all_pages=False
):
    """
    Attempt to download live data from TopTiket using multiple methods
    """
    print("🌐 Attempting to download live data from TopTiket...")
    if log: log("Attempting live download")
    
    # Method 1: Try simple requests first (faster)
    try:
        print("📱 Trying simple HTTP request...")
        if log: log("Simple request start")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get("https://toptiket.rs/odds/football", headers=headers, timeout=10)
        if response.status_code == 200 and len(response.text) > 1000:
            with open("live_data.txt", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("✅ Live data downloaded with simple request!")
            if "You need to enable JavaScript" in response.text or len(response.text) < (min_content_kb * 1024):
                if verbose:
                    print("⚠️  Detected placeholder / small content after simple request, will try Selenium.")
                if log: log("Placeholder detected after requests; escalating to Selenium")
            else:
                if log: log("Simple request success & accepted")
                return True
        else:
            print(f"⚠️ Simple request failed (status: {response.status_code}, size: {len(response.text)})")
            if log: log(f"Simple request failed status={response.status_code} size={len(response.text)}")
    except Exception as e:
        print(f"⚠️ Simple request error: {str(e)}")
        if log: log(f"Simple request exception {e}")
    
    # Method 2: Try Selenium if allowed
    if not use_selenium:
        return False
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("❌ Selenium or dependencies not installed. Install: pip install selenium webdriver-manager")
        if log: log("Selenium import failed")
        return False

    attempt = 0
    while attempt <= retries:
        attempt += 1
        print(f"📱 Trying Selenium WebDriver (attempt {attempt}/{retries+1})...")
        if log: log(f"Selenium attempt {attempt}")
        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--window-size=1920,1080")
            # Container stability flags
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--disable-setuid-sandbox")
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-background-networking")
            chrome_options.add_argument("--disable-crash-reporter")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            try:
                driver.get("https://toptiket.rs/odds/football")

                # Wait for body
                WebDriverWait(driver, selenium_wait).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )

                # Apply 3-day filter (Selenium context only)
                if three_days:
                    clicked = False
                    if verbose:
                        print("🗓️  Attempting to activate 3-day range filter…")
                    candidates = [
                        (By.XPATH, "//button[contains(.,'3 dana') or contains(.,'3 Dana') or contains(.,'3 DANA')][not(@disabled)]"),
                        (By.XPATH, "//*[contains(@class,'day') and (contains(.,'3 dana') or contains(.,'3 Dana'))]"),
                        (By.XPATH, "//*[self::span or self::div or self::button][normalize-space()='3 dana']"),
                        (By.CSS_SELECTOR, "button,div,span")
                    ]
                    for by, sel in candidates:
                        try:
                            if by == By.CSS_SELECTOR:
                                els = driver.find_elements(by, sel)
                                for el in els:
                                    try:
                                        txt = el.text.strip().lower()
                                        if txt in ("3 dana", "3 dana »", "3 dana»"):
                                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                                            time.sleep(0.2)
                                            try:
                                                el.click()
                                            except Exception:
                                                driver.execute_script("arguments[0].click();", el)
                                            clicked = True
                                            break
                                    except Exception:
                                        continue
                                if clicked:
                                    break
                            else:
                                el = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((by, sel)))
                                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                                time.sleep(0.2)
                                try:
                                    el.click()
                                except Exception:
                                    driver.execute_script("arguments[0].click();", el)
                                clicked = True
                                break
                        except Exception:
                            continue
                    if not clicked:
                        try:
                            js_clicked = driver.execute_script("const els=[...document.querySelectorAll('*')]; const t=els.find(e=>e.innerText && e.innerText.trim().toLowerCase()==='3 dana'); if(t){t.scrollIntoView({block:'center'}); t.click(); return true;} return false;")
                            if js_clicked:
                                clicked = True
                        except Exception:
                            pass
                    if clicked:
                        if verbose:
                            print("✅ 3-day filter clicked; waiting for expansion…")
                        if log: log("Clicked 3-day filter")
                        pre_wait = driver.page_source
                        time.sleep(1.4)
                        post_wait = driver.page_source
                        if len(post_wait) <= len(pre_wait) and verbose:
                            print("⚠️  Page size didn't grow after click (may already be active or layout changed)")
                    else:
                        if verbose:
                            print("⚠️  Could not find '3 dana' control; continuing with default (1 day)")

                # Scroll attempts to trigger lazy load
                for scroll_step in range(scroll_steps):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.1)
                    if verbose and scroll_step == 0:
                        driver.execute_script("window.scrollTo(0, 0);")

                # Optional explicit selector wait for odds container
                if selector:
                    try:
                        WebDriverWait(driver, max(3, int(selenium_wait/2))).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        if verbose:
                            print(f"✅ Selector '{selector}' appeared")
                        if log: log(f"Selector {selector} present")
                    except Exception as se:
                        if verbose:
                            print(f"⚠️ Selector '{selector}' not found: {se}")
                        if log: log(f"Selector {selector} missing")

                # Heuristic wait for odds: look for numbers pattern
                page_content = driver.page_source
                combined_html = page_content
                if verbose:
                    print(f"   DOM size: {len(page_content)/1024:.1f} KB before selector checks")
                if log: log(f"DOM size {len(page_content)} bytes")

                # Basic heuristic: ensure certain keywords or multiple decimal odds appear
                decimal_matches = re.findall(r">\s*(\d+\.\d{2})\s*<", page_content)
                if verbose:
                    print(f"   Detected {len(decimal_matches)} decimal-looking odds fragments")
                if log: log(f"Decimal fragments {len(decimal_matches)}")

                # Try to extract embedded JSON (heuristic) for future direct parsing
                json_snippets = re.findall(r"<script[^>]*>.*?(\{\s*\"[A-Za-z0-9_]+\".*?\})</script>", page_content, flags=re.DOTALL)
                extracted_json = None
                for jsn in json_snippets:
                    if 'match' in jsn.lower() and 'odd' in jsn.lower():
                        try:
                            extracted_json = json.loads(jsn)
                            if verbose:
                                print("🧩 Extracted a JSON blob that looks like it contains odds.")
                            if log: log("Extracted JSON blob with odds keywords")
                            break
                        except Exception:
                            continue

                # Detect total pages automatically if requested
                if all_pages:
                    try:
                        max_pages_js = """
                            const nums = Array.from(document.querySelectorAll('button, a'))
                              .map(el => el.textContent && el.textContent.trim())
                              .filter(t => /^\d+$/.test(t))
                              .map(t => parseInt(t,10));
                            return nums.length ? Math.max(...nums) : 1;
                        """
                        detected_max = driver.execute_script(max_pages_js)
                        if isinstance(detected_max, int) and detected_max > pages:
                            if verbose:
                                print(f"🧮 Detected pagination total pages = {detected_max}")
                            pages = detected_max
                        elif verbose:
                            print(f"🧮 Auto-pagination detected {detected_max} pages (requested {pages})")
                    except Exception as e:
                        if verbose:
                            print(f"⚠️ Auto pagination detection failed: {e}")

                # Handle pagination (Selenium only)
                if pages > 1:
                    if verbose:
                        print(f"↪️  Attempting to navigate additional pages (2..{pages})")
                    for pnum in range(2, pages+1):
                        try:
                            # Try common clickable elements containing page number
                            found = None
                            xpath_variants = [
                                f"//button[normalize-space()='{pnum}']",
                                f"//a[normalize-space()='{pnum}']",
                                f"//li[.//button[normalize-space()='{pnum}']]//button[normalize-space()='{pnum}']",
                                f"//li[.//a[normalize-space()='{pnum}']]//a[normalize-space()='{pnum}']"
                            ]
                            for xp in xpath_variants:
                                elems = driver.find_elements(By.XPATH, xp)
                                if elems:
                                    found = elems[0]
                                    break
                            if not found:
                                # Fallback: generic JS query for numeric button
                                found = driver.execute_script(
                                    "return Array.from(document.querySelectorAll('button, a')).find(el => el.textContent && el.textContent.trim()==='"+str(pnum)+"');")
                            if not found:
                                # Attempt to click a 'next' style control if present
                                next_candidates = driver.find_elements(By.XPATH, "//button[contains(.,'›') or contains(.,'>>')] | //a[contains(.,'›') or contains(.,'>>')]")
                                if next_candidates:
                                    found = next_candidates[0]
                            if not found:
                                # Try aria-label pagination
                                found = driver.execute_script("return Array.from(document.querySelectorAll('[aria-label*=Next],[aria-label*=Dalje]')).shift() || null;")
                            if not found:
                                if verbose:
                                    print(f"  • Page {pnum} control not found, stopping pagination")
                                break
                            if verbose:
                                print(f"  • Opening page {pnum}")
                            try:
                                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", found)
                            except Exception:
                                pass
                            try:
                                found.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", found)
                            # Wait a bit longer for multi-day heavy pages
                            time.sleep(1.8 if three_days else 1.2)
                            # Light scroll to trigger lazy load
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(0.9)
                            driver.execute_script("window.scrollTo(0, 0);")
                            new_source = driver.page_source
                            # Simple heuristic: add only if different length
                            if len(new_source) != len(page_content):
                                combined_html += f"\n<!-- PAGE {pnum} SPLIT -->\n" + new_source
                        except Exception as pe:
                            if verbose:
                                print(f"  • Pagination to page {pnum} failed: {pe}")
                            break
                    page_content = combined_html

                # Optional infinite scroll mode (keep scrolling until content length stabilises)
                if infinite_scroll_loops and infinite_scroll_loops > 0:
                    if verbose:
                        print(f"🌀 Infinite-scroll mode: up to {infinite_scroll_loops} additional scroll cycles")
                    stable = 0
                    last_len = len(page_content)
                    for loop in range(infinite_scroll_loops):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1.2)
                        new_source = driver.page_source
                        new_len = len(new_source)
                        if new_len <= last_len:
                            stable += 1
                        else:
                            stable = 0
                            combined_html = new_source
                            page_content = combined_html
                            last_len = new_len
                        if verbose:
                            print(f"   • Scroll loop {loop+1}: size={new_len/1024:.1f} KB stable_streak={stable}")
                        if stable >= 2:  # two consecutive non-growth cycles
                            if verbose:
                                print("   • Content stabilized; stopping infinite scroll")
                            break

                # Optional verification of multiple day tokens
                day_summary = None
                if verify_days or three_days:
                    # Common Serbian locale abbreviations in site (čet, pet, sub, ned, pon, uto, sre)
                    day_tokens = ["pon", "uto", "sre", "čet", "pet", "sub", "ned"]
                    found = {}
                    for tok in day_tokens:
                        cnt = len(re.findall(r"\b"+tok+",?\b", page_content.lower()))
                        if cnt:
                            found[tok] = cnt
                    day_summary = found
                    if verify_days and verbose:
                        print(f"🗓️  Day token counts: {found}")

                if len(page_content) >= min_content_kb * 1024 and len(decimal_matches) > 20:
                    with open("live_data.txt", "w", encoding="utf-8") as f:
                        f.write(page_content)
                    print("✅ Live data downloaded with Selenium!")
                    if log: log("Selenium success accepted")
                    if day_summary is not None and (verify_days or verbose):
                        print("ℹ️  Detected day abbreviations:", day_summary)
                    if extracted_json:
                        with open("live_embedded.json", "w", encoding="utf-8") as jf:
                            json.dump(extracted_json, jf, ensure_ascii=False, indent=2)
                        if verbose:
                            print("💾 Saved embedded JSON to live_embedded.json")
                    return True
                else:
                    print("⚠️ Content still too small or insufficient odds markers; will retry" if attempt <= retries else "❌ Giving up after retries")
                    if log: log("Content insufficient; retrying" if attempt <= retries else "Content insufficient after retries")
            finally:
                driver.quit()
        except Exception as e:
            print(f"❌ Selenium attempt {attempt} error: {e}")
            if log: log(f"Selenium exception {e}")
            time.sleep(2)

    return False

def parse_live_html_data(filename="live_data.txt"):
    """
    Parse HTML content from live data file
    """
    try:
        from bs4 import BeautifulSoup
        with open(filename, "r", encoding="utf-8", errors='ignore') as f:
            html_content = f.read()
        MAX_PARSE_BYTES = 6 * 1024 * 1024
        if len(html_content) > MAX_PARSE_BYTES:
            head = html_content[:3*1024*1024]
            tail = html_content[-512*1024:]
            html_content = head + "\n<!--TRIMMED-->\n" + tail
        html_content = re.sub(r"<script[\s\S]*?</script>", "", html_content, flags=re.IGNORECASE)
        soup = BeautifulSoup(html_content, 'html.parser')
        text_content = soup.get_text(separator='\n', strip=True)
        text_filename = "live_extracted.txt"
        with open(text_filename, "w", encoding="utf-8") as f:
            f.write(text_content)
        print(f"✅ Live data extracted to {text_filename}")
        return text_filename
        
    except ImportError:
        print("❌ BeautifulSoup not installed. Install with: pip install beautifulsoup4")
        return None
    except Exception as e:
        print(f"❌ Error parsing HTML: {str(e)}")
        return None

def dump_html_structure(html_path, max_lines=400, verbose=False):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("⚠️ BeautifulSoup not installed; cannot dump structure")
        return
    if not os.path.exists(html_path):
        print("⚠️ HTML file not found for dump")
        return
    with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    classes = {}
    for tag in soup.find_all(True):
        cls_list = tag.get('class') or []
        for c in cls_list:
            classes[c] = classes.get(c,0)+1
    top = sorted(classes.items(), key=lambda x: x[1], reverse=True)[:40]
    with open('live_html_classes.txt','w',encoding='utf-8') as f:
        for c,count in top:
            f.write(f"{c}: {count}\n")
    snippet = '\n'.join(html.splitlines()[:max_lines])
    with open('live_html_head_snippet.html','w',encoding='utf-8') as f:
        f.write(snippet)
    print("📝 Dumped class frequency -> live_html_classes.txt and head snippet -> live_html_head_snippet.html")

def parse_live_html_dom(html_path="live_data.txt", verbose=False):
    """Heuristic DOM parser for live odds HTML.
    Attempts to pair team name blocks and find nearby odds nodes.
    """
    matches = []
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        if verbose:
            print("⚠️ BeautifulSoup not installed; DOM heuristic unavailable")
        return matches
    if not os.path.exists(html_path):
        return matches
    with open(html_path,'r',encoding='utf-8',errors='ignore') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    team_nodes = soup.find_all(lambda tag: tag.name in ['div','span','p'] and tag.get_text(strip=True) and 3 <= len(tag.get_text(strip=True)) <= 55 and re.search(r'[A-Za-z]', tag.get_text()))
    containers = set()
    for node in team_nodes:
        parent = node.find_parent('div')
        if parent:
            containers.add(parent)
    for cont in list(containers)[:800]:
        ts = [t.get_text(strip=True) for t in cont.find_all(lambda tag: tag.name in ['div','span','p'] and tag.get_text(strip=True) and len(tag.get_text(strip=True))<55) if re.search(r'[A-Za-z]', t.get_text())]
        uniq = []
        for t in ts:
            if t not in uniq:
                uniq.append(t)
        if len(uniq) < 2:
            continue
        team1, team2 = uniq[0], uniq[1]
        odds_tags = cont.find_all(lambda tag: tag.name in ['span','button','div'] and re.fullmatch(r'\d+(?:\.\d+)?', tag.get_text(strip=True) or ''))
        odds_values = []
        for ot in odds_tags:
            try:
                val = float(ot.get_text(strip=True))
                if 1.01 <= val <= 69:
                    odds_values.append(val)
            except ValueError:
                pass
        if len(odds_values) < 2:
            continue
        odds_map = {}
        label_seq = ['Home','Draw','Away']
        for idx, val in enumerate(odds_values[:3]):
            label = label_seq[idx] if idx < len(label_seq) else f'O{idx}'
            odds_map[label] = (val,'LIVE')
        if len(odds_map) >= 2:
            matches.append({'teams': f"{team1} vs {team2}", 'odds': odds_map})
    dedup = {}
    for m in matches:
        dedup[m['teams']] = m
    final = list(dedup.values())
    if verbose:
        print(f"🧪 DOM heuristic produced {len(final)} matches (pre-filter {len(matches)})")
    return final

def enrich_with_winner_markets(matches, base_html_path="live_data.txt", max_details=15, detail_wait=6, headless=True, verbose=False, login_user=None, login_pass=None):
    """Visit individual match pages (limited) to extract Winner (two-way) market.
    Heuristic: locate links in base HTML pointing to /odds/football/match/<id> then match by team names.
    Extract odds under section labels containing 'Winner' or 'Prolaz' then first two odds interpreted as Winner1/Winner2.
    """
    if not matches or max_details <= 0:
        return matches
    if not os.path.exists(base_html_path):
        return matches
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        if verbose: print("⚠️ BeautifulSoup missing; cannot enrich winner markets")
        return matches
    with open(base_html_path,'r',encoding='utf-8',errors='ignore') as f:
        html=f.read()
    soup=BeautifulSoup(html,'html.parser')
    # Collect match links (unauthenticated static snapshot first)
    link_elems = soup.find_all('a', href=True)
    link_map = []
    for a in link_elems:
        href = a['href']
        if '/odds/football/match/' in href:
            text = a.get_text(' ', strip=True)
            if text and ' vs ' in text.lower():
                link_map.append((href, text))
    # Helper to parse link candidates out of raw HTML text (anchors, data-href, data-link JSON-ish fragments)
    def _augment_links_from_html(raw_html):
        found = 0
        for m in re.finditer(r"(/odds/football/match/\d+)", raw_html):
            href = m.group(1)
            # We don't always have text; fallback later by mapping via team names
            if not any(href == existing[0] for existing in link_map):
                link_map.append((href, ''))
                found += 1
        return found
    if not link_map:
        _augment_links_from_html(html)
    # Dynamic fallback if no links found in saved HTML
    if not link_map:
        if verbose:
            print("🔄 No match links in static HTML; attempting authenticated live listing fetch...")
        try:
            from selenium import webdriver as _wd
            from selenium.webdriver.chrome.service import Service as _Service
            from selenium.webdriver.chrome.options import Options as _Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager as _CDM
            _opts=_Options()
            if headless: _opts.add_argument('--headless=new')
            _opts.add_argument('--blink-settings=imagesEnabled=false')
            _opts.add_argument('--disable-gpu'); _opts.add_argument('--no-sandbox'); _opts.add_argument('--disable-dev-shm-usage')
            _listing_drv=_wd.Chrome(service=_Service(_CDM().install()), options=_opts)
            try:
                # Login first if credentials provided
                if login_user and login_pass:
                    try:
                        _listing_drv.get('https://toptiket.rs/login')
                        WebDriverWait(_listing_drv, detail_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                        time.sleep(0.4)
                        # Fill user
                        for css in ["input[name='username']","input[name*='user']","input[type='text']"]:
                            try:
                                el=_listing_drv.find_element(By.CSS_SELECTOR, css)
                                el.clear(); el.send_keys(login_user); break
                            except: pass
                        for css in ["input[name='password']","input[type='password']"]:
                            try:
                                el=_listing_drv.find_element(By.CSS_SELECTOR, css)
                                el.clear(); el.send_keys(login_pass); break
                            except: pass
                        # Submit login
                        try:
                            btn=_listing_drv.find_element(By.XPATH, "//button[contains(translate(.,'PRIJ','prij'),'prij') or contains(translate(.,'ULOGUJ','uloguj'),'uloguj')]")
                        except:
                            btn=None
                        if not btn:
                            try: btn=_listing_drv.find_elements(By.TAG_NAME,'button')[0]
                            except: btn=None
                        if btn:
                            try: btn.click(); time.sleep(0.7)
                            except: pass
                        if verbose:
                            print("🔐 Listing fetch: login attempted")
                    except Exception as _le:
                        if verbose:
                            print(f"⚠️ Listing login error (continuing unauth): {_le}")
                _listing_drv.get('https://toptiket.rs/odds/football')
                WebDriverWait(_listing_drv, detail_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                # Scroll to load more content
                for _ in range(4):
                    _listing_drv.execute_script('window.scrollBy(0, 900);'); time.sleep(0.3)
                listing_html = _listing_drv.page_source
                # Persist for inspection
                try:
                    with open('winner_listing_source.html','w',encoding='utf-8') as wf:
                        wf.write(listing_html)
                except: pass
                # Parse anchors again
                lsoup=BeautifulSoup(listing_html,'html.parser')
                for a in lsoup.find_all('a', href=True):
                    href=a['href']
                    if '/odds/football/match/' in href:
                        text=a.get_text(' ', strip=True)
                        if href and not any(href == existing[0] for existing in link_map):
                            link_map.append((href, text))
                # Also parse data-href/data-link attributes
                for tag in lsoup.find_all(True):
                    for attr in ['data-href','data-link','data-url']:
                        v = tag.get(attr)
                        if v and '/odds/football/match/' in v and not any(v == existing[0] for existing in link_map):
                            link_map.append((v, tag.get_text(' ', strip=True)))
                # Raw regex augment
                _augment_links_from_html(listing_html)
                if verbose:
                    print(f"   ↪ Auth listing fetch produced {len(link_map)} link candidates")
            finally:
                try: _listing_drv.quit()
                except: pass
        except Exception as _e_lauth:
            if verbose:
                print(f"⚠️ Auth listing attempt failed: {_e_lauth}")
    if verbose: print(f"🔗 Found {len(link_map)} potential match detail links")
    # Normalize match key function
    def norm_team(t):
        return re.sub(r'\s+',' ', t.lower().strip())
    def make_key(teams):
        if ' vs ' in teams:
            a,b = teams.split(' vs ',1)
            return norm_team(a)+"|"+norm_team(b)
        return norm_team(teams)
    match_index = { make_key(m['teams']): m for m in matches }
    # Build candidate visit list linking by overlapping tokens
    visits = []
    for href, txt in link_map:
        # Attempt to extract two teams from link text (split by common separators)
        parts = re.split(r'\s+vs\s+|\s+-\s+|\s+@\s+', txt, flags=re.IGNORECASE)
        if len(parts) >= 2:
            key = norm_team(parts[0])+"|"+norm_team(parts[1])
            if key in match_index:
                full_url = href if href.startswith('http') else ('https://toptiket.rs'+href)
                visits.append((full_url, match_index[key]))
    # De-duplicate
    seen=set(); filtered=[]
    for url, m in visits:
        if url not in seen:
            filtered.append((url,m)); seen.add(url)
    if verbose: print(f"🧭 Mapped {len(filtered)} detail links to current matches (limiting to {max_details})")
    # If still no links, attempt SPA route discovery by clicking potential match rows and watching URL changes / history pushState
    if not filtered:
        if verbose:
            print("🧭 Attempting SPA route discovery (click sweep)...")
        try:
            from selenium import webdriver as _wd3
            from selenium.webdriver.chrome.service import Service as _S3
            from selenium.webdriver.chrome.options import Options as _O3
            from selenium.webdriver.common.by import By as _By3
            from selenium.webdriver.support.ui import WebDriverWait as _WW3
            from selenium.webdriver.support import expected_conditions as _EC3
            from webdriver_manager.chrome import ChromeDriverManager as _CDM3
            _o3=_O3()
            if headless: _o3.add_argument('--headless=new')
            _o3.add_argument('--blink-settings=imagesEnabled=false')
            _o3.add_argument('--disable-gpu'); _o3.add_argument('--no-sandbox'); _o3.add_argument('--disable-dev-shm-usage')
            # Enable performance logging to sniff network calls for hidden match/odds endpoints
            try:
                _o3.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
            except Exception:
                pass
            _drv3=_wd3.Chrome(service=_S3(_CDM3().install()), options=_o3)
            spa_urls=set()
            try:
                # Optional login
                if login_user and login_pass:
                    try:
                        _drv3.get('https://toptiket.rs/login')
                        _WW3(_drv3, detail_wait).until(_EC3.presence_of_element_located((_By3.TAG_NAME,'body')))
                        time.sleep(0.4)
                        for css in ["input[name='username']","input[name*='user']","input[type='text']"]:
                            try: el=_drv3.find_element(_By3.CSS_SELECTOR, css); el.clear(); el.send_keys(login_user); break
                            except: pass
                        for css in ["input[name='password']","input[type='password']"]:
                            try: el=_drv3.find_element(_By3.CSS_SELECTOR, css); el.clear(); el.send_keys(login_pass); break
                            except: pass
                        try:
                            btn=_drv3.find_element(_By3.XPATH, "//button[contains(translate(.,'PRIJ','prij'),'prij') or contains(translate(.,'ULOGUJ','uloguj'),'uloguj') or contains(translate(.,'LOG','log'))]")
                        except: btn=None
                        if btn:
                            try: btn.click(); time.sleep(0.6)
                            except: pass
                    except Exception as _espa_login:
                        if verbose: print(f"⚠️ SPA login issue (continuing): {_espa_login}")
                _drv3.get('https://toptiket.rs/odds/football')
                _WW3(_drv3, detail_wait).until(_EC3.presence_of_element_located((_By3.TAG_NAME,'body')))
                time.sleep(0.8)
                # Accept cookie if present
                try:
                    btns=_drv3.find_elements(_By3.XPATH, "//button[contains(.,'OK') or contains(translate(.,'PRIHV','prihv'),'prihv')]")
                    if btns:
                        btns[0].click(); time.sleep(0.3)
                except: pass
                for _ in range(8):
                    _drv3.execute_script('window.scrollBy(0, 1200);'); time.sleep(0.25)
                # Hook pushState & record route changes
                _drv3.execute_script("(function(){if(window.__rtHook)return;window.__collectedRoutes=[];var op=history.pushState;history.pushState=function(a,b,u){if(u&&/\\/odds\\/football\\/match\\//.test(u)){window.__collectedRoutes.push(u);}return op.apply(this,arguments);};window.__rtHook=true;})();")
                # Candidate elements: generic heuristic
                candidate_elems = _drv3.find_elements(_By3.XPATH, "//div[contains(@class,'match') or contains(@class,'event') or contains(@class,'fixture') or contains(@class,'row')][.//span or .//div]")
                if verbose:
                    print(f"   🔎 SPA candidate elements: {len(candidate_elems)}")
                seen_urls=set();
                for idx, el in enumerate(candidate_elems[:120]):
                    try:
                        _drv3.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        time.sleep(0.05)
                        _drv3.execute_script("try{arguments[0].click();}catch(e){}");
                        time.sleep(0.35)
                        cur=_drv3.current_url
                        if '/odds/football/match/' in cur and cur not in seen_urls:
                            seen_urls.add(cur)
                            # collect route
                            spa_urls.add(cur)
                            # attempt back
                            _drv3.back();
                            _WW3(_drv3, detail_wait).until(_EC3.presence_of_element_located((_By3.TAG_NAME,'body')))
                            time.sleep(0.3)
                    except Exception as _eclk:
                        if verbose and idx < 5:
                            print(f"   ⚠️ Click issue idx {idx}: {_eclk}")
                        continue
                # Also retrieve pushState-recorded routes
                try:
                    routes=_drv3.execute_script("return (window.__collectedRoutes||[]).slice(0,150);")
                    for r in routes:
                        if r not in spa_urls:
                            spa_urls.add(r)
                except: pass
                # Shadow DOM anchor harvesting
                try:
                    shadow_hrefs = _drv3.execute_script('return (function(){const acc=new Set();function walk(n){if(!n)return;try{if(n.shadowRoot){walk(n.shadowRoot);} }catch(e){} let anchors=[];try{anchors=n.querySelectorAll? n.querySelectorAll("a[href*=\"/odds/football/match/\"]"):[];}catch(e){} anchors.forEach(a=>{let h=a.getAttribute("href"); if(h && /\\\/odds\\\/football\\\/match\\\//.test(h)) acc.add(h);}); if(n.children){for(const c of n.children){walk(c);}}} walk(document.documentElement); return Array.from(acc);})()')
                    added=0
                    for h in shadow_hrefs[:120]:
                        full = h if h.startswith('http') else 'https://toptiket.rs'+h
                        if full not in spa_urls:
                            spa_urls.add(full); added+=1
                    if verbose and added:
                        print(f"   🌑 Shadow DOM anchors added {added} routes")
                except Exception as _eshad:
                    if verbose:
                        print(f"   (shadow scan skip: {_eshad})")
                # Iframe scanning (switch into limited number)
                try:
                    iframes=_drv3.find_elements(_By3.TAG_NAME,'iframe')
                    if verbose and iframes:
                        print(f"   🪟 Found {len(iframes)} iframes (scanning up to 5)")
                    for i, fr in enumerate(iframes[:5]):
                        try:
                            _drv3.switch_to.frame(fr)
                            time.sleep(0.2)
                            # Collect anchors inside frame
                            frame_anchors = _drv3.find_elements(_By3.XPATH, "//a[contains(@href,'/odds/football/match/')]")
                            for a in frame_anchors[:120]:
                                try:
                                    href=a.get_attribute('href') or a.get_attribute('data-href')
                                    if href and '/odds/football/match/' in href:
                                        if href not in spa_urls:
                                            spa_urls.add(href)
                                except: pass
                        except Exception as _efr:
                            if verbose and i==0:
                                print(f"   (iframe scan issue: {_efr})")
                        finally:
                            try: _drv3.switch_to.default_content()
                            except: pass
                except Exception as _eif:
                    if verbose:
                        print(f"   (iframe enumeration failed: {_eif})")
                # Performance log sniffing
                try:
                    logs=_drv3.get_log('performance')
                    sniff_added=0
                    for entry in logs[:400]:
                        try:
                            msg=json.loads(entry.get('message','{}')).get('message',{})
                            url=(msg.get('params',{}) or {}).get('request',{}).get('url') or ''
                            if '/odds/football/match/' in url:
                                if url not in spa_urls:
                                    spa_urls.add(url); sniff_added+=1
                        except: continue
                    if sniff_added and verbose:
                        print(f"   📡 Network log added {sniff_added} routes")
                except Exception as _elog:
                    if verbose:
                        print(f"   (perf log unavailable: {_elog})")
                if verbose:
                    print(f"   🧾 Discovered {len(spa_urls)} match routes via SPA click sweep")
                # If still zero candidates and headless, try one headful retry with extra expansion and fetch/XHR interception
                if not spa_urls and headless:
                    if verbose:
                        print("   🔁 Headless found 0 routes → retrying headful with expansion & network hook")
                    try:
                        _drv3.quit()
                    except: pass
                    # Recreate driver headful
                    _o3b=_O3()
                    _o3b.add_argument('--disable-gpu'); _o3b.add_argument('--no-sandbox'); _o3b.add_argument('--disable-dev-shm-usage')
                    try:_o3b.set_capability('goog:loggingPrefs', {'performance':'ALL'})
                    except: pass
                    _drv3=_wd3.Chrome(service=_S3(_CDM3().install()), options=_o3b)
                    _drv3.get('https://toptiket.rs/odds/football')
                    _WW3(_drv3, detail_wait).until(_EC3.presence_of_element_located((_By3.TAG_NAME,'body')))
                    time.sleep(1.2)
                    # Inject fetch/XHR interception
                    try:
                        _drv3.execute_script("""
                        (function(){
                          if(window.__netHooked)return;window.__netHooked=true;window.__netLogs=[];
                          function store(t,u,b){try{window.__netLogs.push({ts:Date.now(),type:t,url:u,body:b&&b.slice?b.slice(0,800):''});}catch(e){}}
                          const origFetch=window.fetch;window.fetch=function(){try{let url=arguments[0]; let body=''; try{body=arguments[1]&&arguments[1].body||'';}catch(e){}; let p=origFetch.apply(this,arguments); p.then(r=>{try{r.clone().text().then(txt=>{store('fetch',url,txt);});}catch(e){}}); return p;}catch(e){return origFetch.apply(this,arguments);}}
                          const OrigOpen=XMLHttpRequest.prototype.open; const OrigSend=XMLHttpRequest.prototype.send;
                          XMLHttpRequest.prototype.open=function(m,u){this.__url=u; return OrigOpen.apply(this,arguments)};
                          XMLHttpRequest.prototype.send=function(body){try{this.addEventListener('load',()=>{try{store('xhr',this.__url,this.responseText);}catch(e){}});}catch(e){}; return OrigSend.apply(this,arguments)};
                                                    // WebSocket tap
                                                    try{
                                                         const _WS=window.WebSocket; window.WebSocket=function(url,proto){const ws=new _WS(url,proto); try{ws.addEventListener('message',ev=>{try{let d=ev.data||''; if(typeof d==='string' && /prolaz|winner/i.test(d)){store('ws',url,d.slice(0,800));}}catch(e){}});}catch(e){} return ws;};
                                                    }catch(e){}
                                                    // JSON.parse hook to sniff structured objects mentioning prolaz/winner with odds
                                                    try{
                                                         const jparse=JSON.parse; JSON.parse=function(t){let o=jparse(t); try{if(o && typeof o==='object'){let txt=JSON.stringify(o); if(/prolaz|winner/i.test(txt) && /\d+\.\d{2}/.test(txt)){store('json','inline',txt.slice(0,800));}}}catch(e){} return o;};
                                                    }catch(e){}
                                                    // MutationObserver to capture inserted DOM blocks containing prolaz/winner and odds
                                                    try{
                                                        const mo=new MutationObserver(muts=>{muts.forEach(mu=>{(mu.addedNodes||[]).forEach(n=>{try{if(!n.innerText)return;const t=n.innerText; if(/prolaz|winner/i.test(t) && /(\d+\.\d{2}).*(\d+\.\d{2})/.test(t)){store('dom','block',t.slice(0,800));}}catch(e){}});});});
                                                        mo.observe(document.documentElement,{subtree:true,childList:true});
                                                    }catch(e){}
                        })();
                        """)
                    except Exception as _enet:
                        if verbose: print(f"      (net hook failed: {_enet})")
                    # Expansion clicks: click anything that looks expandable (plus icons, league rows, caret, arrow)
                    expand_xpaths=[
                        "//button[contains(@class,'expand') or contains(@class,'toggle') or contains(@class,'plus')]",
                        "//div[contains(@class,'expand') or contains(@class,'toggle') or contains(@class,'plus')]",
                        "//span[contains(@class,'expand') or contains(@class,'toggle') or contains(@class,'plus')]",
                        "//div[contains(@class,'league') and (@role='button' or contains(@class,'header'))]",
                        "//button[contains(.,'+') or contains(.,'More') or contains(.,'Show')]",
                        "//div[contains(@class,'caret') or contains(@class,'arrow') or contains(@class,'chevron')]",
                    ]
                    clicked_expand=0
                    for xp in expand_xpaths:
                        try:
                            elems=_drv3.find_elements(_By3.XPATH, xp)
                            for e in elems[:40]:
                                try:
                                    _drv3.execute_script("arguments[0].scrollIntoView({block:'center'});", e)
                                    e.click(); clicked_expand+=1; time.sleep(0.05)
                                except Exception:
                                    continue
                        except Exception:
                            continue
                    if verbose and clicked_expand:
                        print(f"      ↕️ Clicked {clicked_expand} expandable elements (headful)")
                    # After expansion, try clicking candidate match rows heuristically to trigger detail fetch/XHR
                    try:
                        cand_rows=_drv3.find_elements(_By3.XPATH, "//div[contains(@class,'row') and .//span[contains(text(),' - ')]]")
                        clicked_rows=0
                        for r in cand_rows[:60]:
                            try:
                                _drv3.execute_script("arguments[0].scrollIntoView({block:'center'});", r)
                                r.click(); clicked_rows+=1; time.sleep(0.04)
                            except Exception:
                                continue
                        if verbose and clicked_rows:
                            print(f"      🏃 Trigger-clicked {clicked_rows} candidate rows")
                    except Exception as _erows:
                        if verbose:
                            print(f"      (row click sweep failed: {_erows})")
                    time.sleep(1.0)
                    # Harvest hooked network logs
                    try:
                        net_logs=_drv3.execute_script("return window.__netLogs||[];") or []
                        new_urls=0
                        for ln in net_logs[-400:]:
                            try:
                                u=ln.get('url','')
                                if '/odds/football/match/' in u and u not in spa_urls:
                                    spa_urls.add(u); new_urls+=1
                            except Exception:
                                continue
                        if verbose:
                            print(f"      📥 Hooked network entries: {len(net_logs)} (new routes {new_urls})")
                        # Persist raw network log for debugging
                        try:
                            with open('winner_network_log.json','w',encoding='utf-8') as _wnl:
                                json.dump(net_logs, _wnl, ensure_ascii=False, indent=2)
                        except Exception as _werr:
                            if verbose:
                                print(f"      (failed writing winner_network_log.json: {_werr})")
                    except Exception as _hlog:
                        if verbose:
                            print(f"      (network hook harvest failed: {_hlog})")
                    # Re-scan performance logs post expansion
                    try:
                        logs=_drv3.get_log('performance')
                        added=0
                        for entry in logs[-400:]:
                            try:
                                msg=json.loads(entry.get('message','{}')).get('message',{})
                                url=(msg.get('params',{}) or {}).get('request',{}).get('url') or ''
                                if '/odds/football/match/' in url and url not in spa_urls:
                                    spa_urls.add(url); added+=1
                            except Exception:
                                continue
                        if verbose and added:
                            print(f"      🔎 Perf log post-expansion added {added} routes")
                    except Exception as _per2:
                        if verbose:
                            print(f"      (post-expansion perf log read failed: {_per2})")
            finally:
                try: _drv3.quit()
                except: pass
            if spa_urls:
                # Build filtered list using discovered routes
                for url in list(spa_urls)[:max_details]:
                    # Map URL to match by later; we attempt to parse detail page anyway
                    filtered.append((url, None))  # match object resolved later
        except Exception as _espa:
            if verbose:
                print(f"⚠️ SPA route discovery failed: {_espa}")

    if not filtered:
        # In-place listing click fallback (no standalone detail links discovered)
        if verbose:
            print("🖱 Attempting in-place listing click Winner scrape (no detail links)...")
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service as _Service2
            from selenium.webdriver.chrome.options import Options as _Options2
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager as _CDM2
            _opts2 = _Options2()
            if headless: _opts2.add_argument('--headless=new')
            _opts2.add_argument('--blink-settings=imagesEnabled=false')
            _opts2.add_argument('--disable-gpu'); _opts2.add_argument('--no-sandbox'); _opts2.add_argument('--disable-dev-shm-usage')
            drv = webdriver.Chrome(service=_Service2(_CDM2().install()), options=_opts2)
            enriched_local = 0
            try:
                drv.get('https://toptiket.rs/odds/football')
                WebDriverWait(drv, detail_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                time.sleep(0.8)
                # Optional login first if credentials supplied
                if login_user and login_pass:
                    try:
                        drv.get('https://toptiket.rs/login')
                        WebDriverWait(drv, detail_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                        time.sleep(0.4)
                        # Basic login attempt
                        for css in ["input[name='username']","input[name*='user']","input[type='text']"]:
                            try:
                                el = drv.find_element(By.CSS_SELECTOR, css)
                                el.clear(); el.send_keys(login_user); break
                            except: pass
                        for css in ["input[name='password']","input[type='password']"]:
                            try:
                                el = drv.find_element(By.CSS_SELECTOR, css)
                                el.clear(); el.send_keys(login_pass); break
                            except: pass
                        # Submit (look for button containing 'Prij' or generic first button)
                        btn = None
                        try:
                            btn = drv.find_element(By.XPATH, "//button[contains(translate(.,'PRIJ','prij'),'prij')]" )
                        except: pass
                        if not btn:
                            try:
                                btn = drv.find_elements(By.TAG_NAME,'button')[0]
                            except: btn=None
                        if btn:
                            try: btn.click(); time.sleep(0.8)
                            except: pass
                        # Return to listing
                        drv.get('https://toptiket.rs/odds/football')
                        WebDriverWait(drv, detail_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                        time.sleep(0.6)
                        if verbose:
                            print("🔐 In-place mode: login attempt executed")
                    except Exception as _le:
                        if verbose:
                            print(f"⚠️ In-place mode login failed: {_le}")
                # Heuristic candidate containers
                candidate_xpath = (
                    "//div[contains(@class,'match') or contains(@class,'event') or contains(@class,'game') or contains(@class,'row')][.//*[contains(text(),' vs ') or contains(text(),' VS ') or contains(text(),' - ')]]"
                )
                try:
                    candidates = drv.find_elements(By.XPATH, candidate_xpath)
                except Exception:
                    candidates = []
                if verbose:
                    print(f"🔍 In-place mode: {len(candidates)} candidate containers")
                # Extended fallback: if no candidates, attempt shadow DOM + iframe scan for text containing ' vs '
                if len(candidates) == 0:
                    try:
                        shadow_blocks = drv.execute_script("return (function(){const out=[];function walk(n){if(!n)return;try{if(n.shadowRoot){walk(n.shadowRoot);} }catch(e){} let txt='';try{txt=n.innerText||'';}catch(e){} if(/\s(vs|VS)\s/.test(txt) && txt.length<220){out.push(txt);} if(n.children){for(const c of n.children){walk(c);}}} walk(document.documentElement); return out.slice(0,80);} )()")
                        if verbose and shadow_blocks:
                            print(f"   🌑 Shadow DOM produced {len(shadow_blocks)} blocks with 'vs'")
                        # Create pseudo elements list from shadow blocks
                        class _ShadowWrap:  # minimal wrapper
                            def __init__(self, text): self.text=text
                        candidates = [_ShadowWrap(t) for t in shadow_blocks]
                    except Exception as _esh:
                        if verbose:
                            print(f"   (shadow fallback failed: {_esh})")
                    # Iframe traversal for match rows
                    if not candidates:
                        try:
                            ifr=drv.find_elements(By.TAG_NAME,'iframe')
                            if verbose and ifr:
                                print(f"   🪟 In-place: scanning {min(len(ifr),5)} iframes")
                            for i, fr in enumerate(ifr[:5]):
                                try:
                                    drv.switch_to.frame(fr); time.sleep(0.25)
                                    frame_txt = drv.find_element(By.TAG_NAME,'body').text
                                    blocks = [b for b in frame_txt.split('\n') if ' vs ' in b.lower() and 5 < len(b) < 200]
                                    if blocks:
                                        class _IframeWrap:
                                            def __init__(self, text): self.text=text
                                        candidates.extend([_IframeWrap(b) for b in blocks[:40]])
                                except: pass
                                finally:
                                    try: drv.switch_to.default_content()
                                    except: pass
                        except Exception as _eifl:
                            if verbose:
                                print(f"   (iframe scan skip: {_eifl})")
                # Scroll a little to load more if very few
                if len(candidates) < 5:
                    for _ in range(3):
                        drv.execute_script('window.scrollBy(0, 800);'); time.sleep(0.4)
                    try:
                        candidates = drv.find_elements(By.XPATH, candidate_xpath)
                    except Exception:
                        pass
                # Build key map for matching
                def _norm_team_nm(t):
                    return re.sub(r'\s+',' ', t.lower().strip())
                def _extract_pair(text_block):
                    # Try 'Team1 vs Team2'
                    m = re.search(r'([A-Za-z0-9 .\-]{2,})\s+vs\s+([A-Za-z0-9 .\-]{2,})', text_block, flags=re.IGNORECASE)
                    if not m:
                        m = re.search(r'([A-Za-z0-9 .\-]{2,})\s+-\s+([A-Za-z0-9 .\-]{2,})', text_block)
                    if m:
                        return _norm_team_nm(m.group(1)), _norm_team_nm(m.group(2))
                    return None
                reverse_index = { (_norm_team_nm(a.split(' vs ')[0]), _norm_team_nm(a.split(' vs ')[1])): m for a,m in match_index.items() if ' vs ' in a }
                visited_pairs = set()
                for elem in candidates[:120]:  # hard cap for performance
                    if enriched_local >= max_details:
                        break
                    try:
                        block_text = elem.text.replace('\n',' ').strip()
                        if not block_text or len(block_text) < 5:
                            continue
                        pair = _extract_pair(block_text)
                        if not pair:
                            continue
                        if pair in visited_pairs:
                            continue
                        visited_pairs.add(pair)
                        key = pair[0] + '|' + pair[1]
                        match_obj = match_index.get(key)
                        if not match_obj:
                            continue
                        # Click to expand / reveal markets
                        try:
                            drv.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                            time.sleep(0.15)
                            elem.click()
                            time.sleep(0.5)
                        except Exception:
                            pass
                        # Search for Winner/Prolaz text now in DOM
                        try:
                            winner_blocks = drv.find_elements(By.XPATH, "//*[contains(translate(.,'WINERPROLAZ','winerprolaz'),'winner') or contains(translate(.,'WINERPROLAZ','winerprolaz'),'prolaz')]")
                        except Exception:
                            winner_blocks = []
                        best_two = None
                        for wb in winner_blocks[:12]:
                            t = wb.text
                            if not t or len(t) < 6:
                                continue
                            nums = re.findall(r"\b(\d+(?:\.\d+)?)\b", t)
                            odds_f = []
                            for nv in nums:
                                try:
                                    fv = float(nv)
                                    if 1.01 <= fv <= 69:
                                        if fv not in odds_f:
                                            odds_f.append(fv)
                                except: pass
                            if len(odds_f) >= 2:
                                best_two = odds_f[:2]
                                break
                        if best_two and 'Winner1' not in match_obj['odds']:
                            match_obj['odds']['Winner1'] = (best_two[0], 'AUTO')
                            match_obj['odds']['Winner2'] = (best_two[1], 'AUTO')
                            enriched_local += 1
                            if verbose:
                                print(f"   ✅ In-place Winner captured for {match_obj['teams']} -> {best_two[0]}, {best_two[1]}")
                    except Exception as _ie:
                        if verbose:
                            print(f"   ⚠️ In-place candidate error: {_ie}")
                if verbose:
                    print(f"🏁 In-place listing scrape complete: {enriched_local} matches updated")
            finally:
                try: drv.quit()
                except: pass
        except ImportError:
            if verbose:
                print("⚠️ Selenium not available for in-place fallback")
        except Exception as _eip:
            if verbose:
                print(f"⚠️ In-place Winner scrape failed: {_eip}")
        return matches
    # Selenium fetch loop
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        if verbose: print('⚠️ Selenium not installed; skipping winner enrichment')
        return matches
    opts = Options()
    if headless: opts.add_argument('--headless=new')
    # Performance: disable images/css
    opts.add_argument('--blink-settings=imagesEnabled=false')
    opts.add_argument('--disable-gpu'); opts.add_argument('--no-sandbox'); opts.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    enriched=0
    try:
        # Optional login for detail pages (performed once)
        if login_user and login_pass:
            try:
                driver.get('https://toptiket.rs/login')
                WebDriverWait(driver, detail_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                time.sleep(0.5)
                # Try multiple selectors for username/password
                user_fields = [
                    (By.CSS_SELECTOR, "input[name='username']"),
                    (By.CSS_SELECTOR, "input[name*='user']"),
                    (By.CSS_SELECTOR, "input[type='text']")
                ]
                pass_fields = [
                    (By.CSS_SELECTOR, "input[name='password']"),
                    (By.CSS_SELECTOR, "input[type='password']")
                ]
                uel = None; pel = None
                for by,sel in user_fields:
                    try:
                        uel = WebDriverWait(driver,2).until(EC.presence_of_element_located((by,sel)))
                        if uel: break
                    except: continue
                for by,sel in pass_fields:
                    try:
                        pel = WebDriverWait(driver,2).until(EC.presence_of_element_located((by,sel)))
                        if pel: break
                    except: continue
                if uel and pel:
                    try:
                        uel.clear(); uel.send_keys(login_user)
                        pel.clear(); pel.send_keys(login_pass)
                        # Submit via ENTER or find button
                        pel.submit()
                        time.sleep(0.8)
                    except Exception:
                        try:
                            btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                            btn.click(); time.sleep(0.8)
                        except Exception:
                            pass
                if verbose:
                    print("🔐 Winner enrichment: login attempt complete (not verifying success explicitly)")
            except Exception as e:
                if verbose:
                    print(f"⚠️ Winner enrichment login skipped/failure: {e}")
        for url, m in filtered[:max_details]:
            try:
                driver.get(url)
                WebDriverWait(driver, detail_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                time.sleep(0.6)
                # Try to click Prolaz/Winner tab if present (improves odds visibility)
                try:
                    tab = None
                    # Broaden selectors: allow punctuation/spacing variants e.g. "Prolaz , P" or abbreviations like "Prol" or mixed case
                    tab_xpaths = [
                        "//a[matches(translate(normalize-space(.),'PROLAZ,','prolaz,'),'prolaz|prol|prl')]",
                        "//button[matches(translate(normalize-space(.),'PROLAZ,','prolaz,'),'prolaz|prol|prl')]",
                        "//div[@role='tab' and matches(translate(normalize-space(.),'PROLAZ,','prolaz,'),'prolaz|prol|prl')]",
                        # Fallback contains without matches (for XPath 1 engines)
                        "//a[contains(translate(.,'PROLAZ','prolaz'),'prolaz')]",
                        "//button[contains(translate(.,'PROLAZ','prolaz'),'prolaz')]",
                        "//div[contains(translate(.,'PROLAZ','prolaz'),'prolaz') and @role='tab']",
                        # P variant if site abbreviates to a standalone single letter in tab bar
                        "//a[normalize-space(.)='P']",
                        "//button[normalize-space(.)='P']",
                        "//div[@role='tab' and normalize-space(.)='P']",
                    ]
                    for xp in tab_xpaths:
                        try:
                            tab = driver.find_element(By.XPATH, xp)
                            if tab:
                                break
                        except:
                            continue
                    if tab:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
                        time.sleep(0.15)
                        try:
                            tab.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", tab)
                        time.sleep(0.6)
                except Exception as _etab:
                    if verbose:
                        print(f"   ⚠️ Prolaz tab click failed: {_etab}")
                page = driver.page_source
                psoup = BeautifulSoup(page,'html.parser')
                # Find a section mentioning Winner or Prolaz
                section = None
                cand_divs = psoup.find_all(lambda tag: tag.name in ['div','section','table'] and tag.get_text(strip=True))
                for div in cand_divs:
                    txt = div.get_text(' ', strip=True)
                    low = txt.lower()
                    if ('winner' in low or 'prolaz' in low) and re.search(r'\b\d+\.\d{2}\b', low):
                        section = div
                        break
                    # Secondary heuristic: search for table headers containing Winner
                    tables = psoup.find_all('table')
                    for tb in tables:
                        head_txt = tb.get_text(' ', strip=True).lower()
                        if 'winner' in head_txt and re.search(r'\b\d+\.\d{2}\b', head_txt):
                            section = tb; break
                if not section:
                    continue
                odds_text = section.get_text('\n', strip=True)
                # Extract odds numbers
                odds_vals = re.findall(r'\b(\d+(?:\.\d+)?)\b', odds_text)
                odds_floats = []
                for ov in odds_vals:
                    try:
                        fv=float(ov)
                        if 1.01 <= fv <= 100:
                            odds_floats.append(fv)
                    except: pass
                # Take first two distinct odds as Winner1 / Winner2
                uniq=[]
                for v in odds_floats:
                    if v not in uniq:
                        uniq.append(v)
                    if len(uniq) == 2:
                        break
                # If m is None (from SPA route discovery), attempt to map by team names in page header
                if len(uniq)==2:
                    target_match = m
                    if target_match is None:
                        # Try to extract teams from page header (look for vs or large heading pieces)
                        header_txt = ''
                        for hsel in ['h1','h2','h3','title']:
                            node = psoup.find(hsel)
                            if node and len(node.get_text(strip=True))<140:
                                header_txt = node.get_text(' ', strip=True)
                                break
                        # Fallback: search for two sequential blocks with big odds boxes above (extract preceding script? skip)
                        # Attempt splitting by common delimiters
                        mt = re.search(r"([A-Za-z0-9 .\-]{3,})\s+vs\s+([A-Za-z0-9 .\-]{3,})", header_txt, flags=re.IGNORECASE)
                        if not mt:
                            # Some pages may use ' - '
                            mt = re.search(r"([A-Za-z0-9 .\-]{3,})\s+-\s+([A-Za-z0-9 .\-]{3,})", header_txt)
                        if mt:
                            t1=mt.group(1).strip(); t2=mt.group(2).strip()
                            key = norm_team(t1)+"|"+norm_team(t2)
                            target_match = match_index.get(key)
                    if target_match is None:
                        if verbose:
                            print("   ⚠️ Could not map Winner odds to an existing match (skipping)")
                    else:
                        target_match['odds']['Winner1']=(uniq[0],'AUTO')
                        target_match['odds']['Winner2']=(uniq[1],'AUTO')
                        enriched+=1
                        if verbose:
                            print(f"   ✅ Winner odds added: {target_match['teams']} -> {uniq[0]}, {uniq[1]}")
            except Exception as e:
                if verbose: print(f"⚠️ Detail fetch failed for {url}: {e}")
    finally:
        driver.quit()
    if verbose: print(f"✅ Winner enrichment complete: {enriched} matches updated")
    return matches

def auto_capture_static(headless=True, verbose=False, scroll_steps=6, pages=1, raw_lines_limit=800, three_days=False, all_pages=False):
    """Capture live site and write a synthetic index_AUTO_<timestamp>.txt file that matches parse_file() expected layout.

    Steps:
    1. Use existing download_live_data + parse_live_html_dom pipeline.
    2. If DOM heuristic produces matches, serialize them into a pseudo index file with sections separated by '----'.
    3. Return path to the created file or None.
    """
    ok = download_live_data(use_selenium=True, headless=headless, verbose=verbose, scroll_steps=scroll_steps, pages=pages, three_days=three_days, all_pages=all_pages)
    if not ok:
        if verbose:
            print("⚠️ auto_capture_static: live download failed")
        return None
    # Try plain text flatten first (in case existing parser can already read something)
    txt = parse_live_html_data()
    dom_matches = parse_live_html_dom(verbose=verbose)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_file = f"index_AUTO_{ts}.txt"
    if not dom_matches:
        # Fallback: write a raw snapshot shell so user can inspect & future parser can adapt
        if verbose:
            print("⚠️ auto_capture_static: DOM heuristic found 0 matches; writing raw flattened snapshot")
        try:
            with open(txt or 'live_extracted.txt','r',encoding='utf-8',errors='ignore') as rf:
                raw_lines = [l.strip() for l in rf.readlines() if l.strip()]
        except Exception:
            raw_lines = []
        with open(out_file,'w',encoding='utf-8') as f:
            f.write("AUTO-SNAPSHOT RAW FALLBACK\n----\n")
            if raw_lines_limit <= 0:
                raw_subset = raw_lines
            else:
                raw_subset = raw_lines[:raw_lines_limit]
            for l in raw_subset:
                f.write(l+"\n")
            if verbose and raw_lines_limit > 0 and len(raw_lines) > raw_lines_limit:
                print(f"⚠️ Truncated raw snapshot lines {raw_lines_limit}/{len(raw_lines)} (increase --raw-lines-limit)")
        return out_file
    # Normal path when matches exist
    with open(out_file,'w',encoding='utf-8') as f:
        for m in dom_matches:
            teams = m['teams'].split(' vs ')
            if len(teams) != 2:
                continue
            f.write(teams[0].strip()+"\n")
            f.write(teams[1].strip()+"\n")
            # Build sections: Home, Draw, Away + combined (0-2 & 3+) if present
            home = m['odds'].get('Home')
            draw = m['odds'].get('Draw')
            away = m['odds'].get('Away')
            ou1 = m['odds'].get('0-2') or m['odds'].get('Under')
            ou2 = m['odds'].get('3+') or m['odds'].get('Over')
            # Section 0
            if home:
                f.write(f"{home[0]}AUTOBook\n")
            f.write("----\n")
            # Section 1
            if draw:
                f.write(f"{draw[0]}AUTOBook\n")
            f.write("----\n")
            # Section 2
            if away:
                f.write(f"{away[0]}AUTOBook\n")
            if ou1:
                f.write(f"{ou1[0]}AUTOBook\n")
            f.write("----\n")
            # Section 3
            if ou2:
                f.write(f"{ou2[0]}AUTOBook\n")
            f.write("\n")
    if verbose:
        print(f"💾 auto_capture_static: wrote {len(dom_matches)} matches to {out_file}")
    return out_file

def get_latest_data_source(no_live=False, live_only=False, allow_static=False, **live_kwargs):
    """
    Determine the best data source to use
    Returns: (source_type, files_list)
    """
    # Try API first if provided
    api_url = live_kwargs.pop('api_url', None)
    api_enabled = live_kwargs.pop('api_enabled', False)
    api_verbose = live_kwargs.get('verbose', False)
    api_matches_cache = []
    if api_enabled and api_url:
        data = fetch_api_json(api_url, verbose=api_verbose)
        if data:
            api_matches_cache = transform_api_json_to_matches(data, verbose=api_verbose)
            if api_matches_cache:
                # Save interim file to unify downstream parsing
                tmp_api_file = "api_matches_dump.txt"
                with open(tmp_api_file, 'w', encoding='utf-8') as f:
                    for m in api_matches_cache:
                        f.write(m['teams'] + "\n")
                        for label,(odd,book) in m['odds'].items():
                            f.write(f"  {label}: {odd} @ {book}\n")
                        f.write("\n")
                print(f"✅ Using API data ({len(api_matches_cache)} matches)")
                return 'api', [tmp_api_file]
            else:
                print("⚠️ API returned JSON but no matches detected (adjust transform)")
        else:
            print("⚠️ API fetch failed or empty")

    # Allow skipping live fetch (HTML)
    if not no_live and download_live_data(**live_kwargs):
        live_text_file = parse_live_html_data()
        if live_text_file and os.path.exists(live_text_file):
            print("✅ Using live data from TopTiket")
            return "live", [live_text_file]
        else:
            print("⚠️ Live data download succeeded but parsing failed")
    
    # Fall back to existing index files
    if allow_static:
        index_files = sorted(glob.glob("index_*.txt"))
        if index_files and not live_only:
            print(f"📁 Using {len(index_files)} existing index files (static data)")
            return "static", index_files
    
    # No data available
    print("❌ No data sources available")
    return "none", []

def analyze_surebets(matches, verbose=False, min_profit=0.0, stake_min=None, stake_max=None, stake_total=None, stake_round=1):
    """Analyze matches for surebet opportunities with stake controls.
    Returns list of surebet info dicts including rounded stakes.
    """
    surebets = []
    # Normalize excluded bookmaker names (strip spaces & punctuation variations like '365.rs')
    def _norm_book(b: str):
        b = b.lower().strip()
        # remove dots and spaces for broader matching
        return b.replace('.', '').replace(' ', '')
    excluded_norm = {_norm_book(b) for b in EXCLUDED_BOOKMAKERS}
    total_target = choose_total_stake(stake_min or 10000, stake_max or 15000, explicit=stake_total)
    
    for match in matches:
        if len(match.get("odds", {})) < 2:
            continue
        available_labels = list(match["odds"].keys())
        # 1X2
        if all(label in available_labels for label in ["Home", "Draw", "Away"]):
            odds_1x2 = [match["odds"][label] for label in ["Home", "Draw", "Away"]]
            # Determine category (online if ANY excluded bookmaker present, else offline)
            has_online = any(_norm_book(book) in excluded_norm for _, book in odds_1x2)
            profit_1x2 = check_surebet(odds_1x2)
            if profit_1x2 is not None and profit_1x2 >= min_profit and profit_1x2 > 0:
                stakes, abs_profit_actual, eff_total, profit_pct_actual, theo_abs, theo_pct = compute_stakes(
                    odds_1x2, total_stake=total_target, round_multiple=stake_round)
                if stakes:
                    if profit_pct_actual >= min_profit:
                        surebets.append({
                            "match": match["teams"],
                            "type": "1X2",
                            "profit": profit_1x2,  # theoretical percent retained
                            "odds": {k: match["odds"][k] for k in ["Home", "Draw", "Away"]},
                            "stakes": stakes,
                            "abs_profit": abs_profit_actual,              # actual absolute profit
                            "profit_actual": profit_pct_actual,
                            "abs_profit_theoretical": theo_abs,
                            "profit_theoretical": theo_pct,
                            "total_stake": eff_total,
                            "category": "online" if has_online else "local"
                        })
                    elif verbose:
                        print(f"ℹ️  Rounding removed edge (< {min_profit}% actual) for {match['teams']} 1X2 (theoretical={profit_1x2}%, actual={profit_pct_actual}%)")
            elif verbose and profit_1x2 is not None:
                print(f"ℹ️  Not profitable (profit={profit_1x2}%) for {match['teams']} 1X2")
        # Over/Under
        if all(label in available_labels for label in ["0-2", "3+"]):
            odds_ou = [match["odds"][label] for label in ["0-2", "3+"]]
            has_online_ou = any(_norm_book(book) in excluded_norm for _, book in odds_ou)
            profit_ou = check_surebet(odds_ou)
            if profit_ou is not None and profit_ou >= min_profit and profit_ou > 0:
                stakes, abs_profit_actual, eff_total, profit_pct_actual, theo_abs, theo_pct = compute_stakes(
                    odds_ou, total_stake=total_target, round_multiple=stake_round)
                if stakes:
                    if profit_pct_actual >= min_profit:
                        surebets.append({
                            "match": match["teams"],
                            "type": "0-2 / 3+",
                            "profit": profit_ou,
                            "odds": {k: match["odds"][k] for k in ["0-2", "3+"]},
                            "stakes": stakes,
                            "abs_profit": abs_profit_actual,
                            "profit_actual": profit_pct_actual,
                            "abs_profit_theoretical": theo_abs,
                            "profit_theoretical": theo_pct,
                            "total_stake": eff_total,
                            "category": "online" if has_online_ou else "local"
                        })
                    elif verbose:
                        print(f"ℹ️  Rounding removed edge (< {min_profit}% actual) for {match['teams']} OU (theoretical={profit_ou}%, actual={profit_pct_actual}%)")
            elif verbose and profit_ou is not None:
                print(f"ℹ️  Not profitable (profit={profit_ou}%) for {match['teams']} OU")
        # Winner (two-way) market fetched from detail pages (labels Winner1/Winner2)
        if all(label in available_labels for label in ["Winner1", "Winner2"]):
            odds_win = [match["odds"][label] for label in ["Winner1", "Winner2"]]
            has_online_w = any(_norm_book(book) in excluded_norm for _, book in odds_win)
            profit_w = check_surebet(odds_win)
            if profit_w is not None and profit_w >= min_profit and profit_w > 0:
                stakes, abs_profit_actual, eff_total, profit_pct_actual, theo_abs, theo_pct = compute_stakes(
                    odds_win, total_stake=total_target, round_multiple=stake_round)
                if stakes:
                    if profit_pct_actual >= min_profit:
                        surebets.append({
                            "match": match["teams"],
                            "type": "Winner",
                            "profit": profit_w,
                            "odds": {k: match["odds"][k] for k in ["Winner1", "Winner2"]},
                            "stakes": stakes,
                            "abs_profit": abs_profit_actual,
                            "profit_actual": profit_pct_actual,
                            "abs_profit_theoretical": theo_abs,
                            "profit_theoretical": theo_pct,
                            "total_stake": eff_total,
                            "category": "online" if has_online_w else "local"
                        })
                    elif verbose:
                        print(f"ℹ️  Rounding removed edge (< {min_profit}% actual) for {match['teams']} Winner (theoretical={profit_w}%, actual={profit_pct_actual}%)")
            elif verbose and profit_w is not None:
                print(f"ℹ️  Not profitable (profit={profit_w}%) for {match['teams']} Winner")
    return surebets

def save_results(matches, surebets, source_type):
    """Save results to files"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save all matches
    canonical_type = source_type
    if source_type in ("live","auto"):
        canonical_type = "live"  # unify naming for live-only usage
    matches_file = f"{canonical_type}_football_matches_{timestamp}.txt"
    with open(matches_file, "w", encoding="utf-8") as f:
        f.write(f"Football Matches ({source_type}) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        
        for match in matches:
            f.write(f"{match['teams']}\n")
            for label, (odd, book) in match['odds'].items():
                shown_book = book if book and book != 'AUTO' else ''
                if shown_book:
                    f.write(f"  {label}: {odd} @ {shown_book}\n")
                else:
                    f.write(f"  {label}: {odd}\n")
            f.write("\n")
    
    # Save surebets (separated by category if present)
    surebet_file = f"{canonical_type}_football_surebets_{timestamp}.txt"
    with open(surebet_file, "w", encoding="utf-8") as f:
        f.write(f"Football Surebets ({source_type}) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        
        if not surebets:
            f.write("No surebets found at this time.\n")
        else:
            # Group by category (default offline if missing)
            offline = [s for s in surebets if s.get('category','local') == 'local']
            online = [s for s in surebets if s.get('category') == 'online']
            def write_group(title, group):
                f.write(f"{title}\n")
                f.write("-" * len(title) + "\n")
                if not group:
                    f.write("  (none)\n\n")
                    return
                for surebet in group:
                    f.write(f"{surebet['match']}\n")
                    f.write(f"  ✅ {surebet['type']} SUREBET → Profit: {surebet['profit']}% (cat={surebet.get('category','offline')})\n")
                    def _format_book(b):
                        return b if b and b != 'AUTO' else ''
                    odds_text = ", ".join(
                        f"{k}={v[0]:.2f}{('@'+_format_book(v[1])) if _format_book(v[1]) else ''}" for k, v in surebet['odds'].items()
                    )
                    f.write(f"  Odds: {odds_text}\n\n")
            write_group("LOCAL SUREBETS", offline)
            write_group("ONLINE SUREBETS", online)
    
    return surebet_file

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Enhanced Football Odds Analyzer")
    parser.add_argument("--verbose", action="store_true", help="Show detailed debug info")
    parser.add_argument("--no-live", action="store_true", help="Skip attempting live download")
    parser.add_argument("--live-only", action="store_true", help="Fail if live data not available (no static fallback)")
    parser.add_argument("--no-headless", action="store_true", help="Show browser window during Selenium fetch")
    parser.add_argument("--selenium-wait", type=int, default=10, help="Max wait seconds for initial body load")
    parser.add_argument("--min-content-kb", type=int, default=15, help="Minimum expected live HTML size in KB before accepting")
    parser.add_argument("--retries", type=int, default=2, help="Selenium retry attempts")
    parser.add_argument("--scroll-steps", type=int, default=6, help="Number of scroll cycles for lazy load")
    parser.add_argument("--pages", type=int, default=1, help="Number of pagination pages to fetch (Selenium only)")
    parser.add_argument("--selector", type=str, default=None, help="CSS selector to wait for (odds container)")
    parser.add_argument("--min-profit", type=float, default=1.5, help="Minimum surebet percent to include (default 1.5)")
    parser.add_argument("--min-odds-per-match", type=int, default=4, help="Minimum odds entries required to keep a match (flat fallback parser may lower this)")
    parser.add_argument("--take-best", action="store_true", help="When multiple odds encountered for same market in fallback, keep the highest")
    parser.add_argument("--flat-threshold", type=int, default=60, help="If parsed matches below this and many time headers exist, use flat fallback")
    parser.add_argument("--three-days", action="store_true", help="Select 3-day range in live Selenium capture (expands pages)")
    parser.add_argument("--verify-days", action="store_true", help="Print detected day abbreviation counts during live capture")
    parser.add_argument("--all-pages", action="store_true", help="When used with live/3-day capture, auto-detect and fetch ALL pagination pages")
    parser.add_argument("--best-aggregate", action="store_true", help="Pick highest odds per market (within sections) instead of first encountered")
    parser.add_argument("--raw-lines-limit", type=int, default=2000, help="Max lines to retain in RAW FALLBACK snapshot (0 = unlimited)")
    parser.add_argument("--infinite-scroll", type=int, default=0, help="Extra infinite scroll cycles after pagination until content stabilizes")
    parser.add_argument("--log-file", type=str, default=None, help="File to append diagnostic log lines")
    parser.add_argument("--api-url", type=str, default=None, help="Direct JSON odds API endpoint (experimental)")
    parser.add_argument("--api-only", action="store_true", help="Only attempt API; no HTML or static fallback")
    parser.add_argument("--dump-html", action="store_true", help="Dump class frequency + snippet for live HTML")
    parser.add_argument("--auto-static", action="store_true", help="Capture live site and generate index_AUTO file before analysis")
    parser.add_argument("--include-static", action="store_true", help="Allow using existing index_*.txt files (opt-in)")
    parser.add_argument("--live-force", action="store_true", help="Exit with error if live/API capture not successful (implies --no-static)")
    parser.add_argument("--reuse-live-minutes", type=int, default=30, help="If recent live_data.txt exists within N minutes, reuse instead of new Selenium run (default 30)")
    # Stake control options
    parser.add_argument("--stake-min-total", type=int, default=10000, help="Minimum total stake (RSD) for allocation (default 10000)")
    parser.add_argument("--stake-max-total", type=int, default=15000, help="Maximum total stake (RSD) for allocation (default 15000)")
    parser.add_argument("--stake-total", type=int, default=None, help="Explicit total stake (RSD) overriding min/max range")
    parser.add_argument("--stake-round", type=int, default=100, help="Round each individual stake to nearest multiple (default 100 RSD)")
    # Winner detail scraping options
    parser.add_argument("--fetch-winner", action="store_true", help="Fetch Winner (two-way) market by visiting individual match pages")
    parser.add_argument("--max-match-details", type=int, default=12, help="Max number of match detail pages to visit for Winner market (default 12)")
    parser.add_argument("--detail-wait", type=int, default=6, help="Wait seconds for each detail page body (default 6)")
    parser.add_argument("--debug-winner", action="store_true", help="After enrichment, print only matches that have Winner1/Winner2 odds")
    parser.add_argument("--login-user", type=str, default=os.environ.get('TOPTIKET_USER'), help="Login username (or set env TOPTIKET_USER)")
    parser.add_argument("--login-pass", type=str, default=os.environ.get('TOPTIKET_PASS'), help="Login password (or set env TOPTIKET_PASS)")
    args = parser.parse_args()

    verbose = args.verbose
    # Set global for parse_file aggregation behavior
    global BEST_AGGREGATE
    BEST_AGGREGATE = args.best_aggregate
    print("🚀 Starting Enhanced Football Odds Analyzer...")
    print("🎯 Supports both static files and live data")
    if verbose:
        print("🔧 Verbose mode enabled")
    print("-" * 50)
    
    # Determine data source
    # Simple logger
    def _log(msg):
        if args.log_file:
            with open(args.log_file, 'a', encoding='utf-8') as lf:
                lf.write(f"{datetime.now().isoformat()} | {msg}\n")

    # Auto static mode short-circuit
    force_live = args.live_force
    # force_live still meaningful; static disabled by default anyway
    source_type = None
    files = []
    # Helper: purge old text data files (.txt) when refreshing stale data
    def purge_old_text_files(verbose=False):
        removed = 0
        for fn in os.listdir('.'):
            if fn.endswith('.txt') and not fn.startswith('README'):
                try:
                    os.remove(fn)
                    removed += 1
                except Exception:
                    pass
        if verbose:
            print(f"🧹 Purged {removed} old .txt files before fresh capture")
    
    # Auto-refresh logic: if live_data.txt exists but older than reuse threshold -> purge and force fresh capture
    if args.reuse_live_minutes > 0 and os.path.exists('live_data.txt'):
        try:
            age_min = (datetime.now().timestamp() - os.path.getmtime('live_data.txt')) / 60.0
            if age_min <= args.reuse_live_minutes:
                if verbose:
                    print(f"♻️  Reusing existing live_data.txt (age {age_min:.1f} min ≤ {args.reuse_live_minutes} min)")
                txt = parse_live_html_data()
                if txt and os.path.exists(txt):
                    source_type = 'cached-live'
                    files = [txt]
            else:
                if verbose:
                    print(f"⏰ live_data.txt age {age_min:.1f} min > {args.reuse_live_minutes} min → refreshing data")
                purge_old_text_files(verbose=verbose)
                # Remove stale live_data so downstream logic performs a new capture
                try:
                    os.remove('live_data.txt')
                except Exception:
                    pass
        except Exception:
            pass

    if source_type is None and args.auto_static:
        print("🛠 Auto-static mode: capturing live snapshot → synthetic index file")
        auto_file = auto_capture_static(headless=not args.no_headless, verbose=verbose, scroll_steps=args.scroll_steps, pages=args.pages, raw_lines_limit=args.raw_lines_limit, three_days=args.three_days, all_pages=args.all_pages)
        if auto_file and os.path.exists(auto_file):
            source_type = 'auto'
            files = [auto_file]
            print(f"✅ Using auto snapshot {auto_file}")
        else:
            print("⚠️ Auto-static capture failed; falling back to normal source discovery")
            args.auto_static = False  # allow normal flow

    if source_type is None and not args.auto_static:
        effective_live_only = True  # default now live-only unless include-static explicitly enables fallback
        if args.include_static:
            effective_live_only = args.live_only or args.api_only
        source_type, files = get_latest_data_source(
            no_live=args.no_live,
            live_only=effective_live_only,
            allow_static=args.include_static,
            use_selenium=True,
            headless=not args.no_headless,
            selenium_wait=args.selenium_wait,
            min_content_kb=args.min_content_kb,
            retries=args.retries,
            verbose=verbose,
            scroll_steps=args.scroll_steps,
            pages=args.pages,
            selector=args.selector,
            infinite_scroll_loops=args.infinite_scroll,
            log=_log if args.log_file else None,
            api_url=args.api_url,
            api_enabled=bool(args.api_url),
            all_pages=args.all_pages,
            three_days=args.three_days
        )
    if force_live and source_type in ("static", "none"):
        print("❌ live-force: live/API capture not successful (ended with source='" + source_type + "').")
        return
    
    if source_type == "none":
        print("❌ No data sources available.")
        print("💡 Make sure you have index_*.txt files or implement live data fetching.")
        return
    
    # Parse matches from available sources
    all_matches = []
    
    for filename in files:
        if os.path.exists(filename):
            print(f"📖 Parsing {filename}...")
            matches = parse_file(filename)
            if verbose:
                print(f"   • Parsed {len(matches)} matches from {filename}")
            # If zero matches but weekday headers present (multi-day pattern), invoke flat block parser
            if not matches:
                with open(filename,'r',encoding='utf-8',errors='ignore') as lf:
                    raw_lines = [l.strip() for l in lf if l.strip()]
                weekday_headers = sum(1 for l in raw_lines if re.match(r"^(sre|uto|ned|čet|pet|pon|sub),", l, re.IGNORECASE))
                if verbose and weekday_headers:
                    print(f"   ⏱ Detected {weekday_headers} weekday headers with 0 structured matches → running flat parser")
                if weekday_headers:
                    flat_from_zero = parse_flat_blocks(raw_lines, min_odds_per_match=args.min_odds_per_match, take_best=args.take_best, verbose=verbose)
                    if flat_from_zero:
                        if verbose:
                            print(f"   🔄 Flat parser recovered {len(flat_from_zero)} matches from zero state")
                        matches = flat_from_zero
            # Fallback flat parser decision
            if matches and len(matches) < args.flat_threshold:
                # Count potential time headers in file to gauge if we missed many
                with open(filename,'r',encoding='utf-8',errors='ignore') as lf:
                    raw_lines = [l.strip() for l in lf if l.strip()]
                time_headers = sum(1 for l in raw_lines if re.match(r"^(sre|uto|ned|čet|pet|pon|sub),", l, re.IGNORECASE))
                if verbose:
                    print(f"   ⏱ Detected {time_headers} weekday header lines vs {len(matches)} parsed matches")
                if time_headers > len(matches)*1.5:  # heuristic: many more headers than matches
                    flat = parse_flat_blocks(raw_lines, min_odds_per_match=args.min_odds_per_match, take_best=args.take_best, verbose=verbose)
                    if flat:
                        # Merge keeping existing richer odds if duplicates
                        existing_index = {m['teams']: m for m in matches}
                        for fm in flat:
                            if fm['teams'] in existing_index:
                                # Merge odds (optionally replace with better odds)
                                for k,v in fm['odds'].items():
                                    if k not in existing_index[fm['teams']]['odds']:
                                        existing_index[fm['teams']]['odds'][k] = v
                                    elif args.take_best and v[0] > existing_index[fm['teams']]['odds'][k][0]:
                                        existing_index[fm['teams']]['odds'][k] = v
                        matches = list(existing_index.values())
                        if verbose:
                            print(f"   🔄 After flat merge: {len(matches)} matches")
            all_matches.extend(matches)
        else:
            print(f"⚠️ File not found: {filename}")
    
    if not all_matches and source_type == 'live':
        # Attempt DOM heuristic
        if verbose:
            print("🧪 Text parse yielded 0 matches; trying DOM heuristic parser...")
        dom_matches = parse_live_html_dom(verbose=verbose)
        if dom_matches:
            print(f"✅ DOM heuristic recovered {len(dom_matches)} matches")
            all_matches.extend(dom_matches)
        else:
            print("⚠️ DOM heuristic also found 0 matches")
            if args.dump_html:
                dump_html_structure('live_data.txt', verbose=verbose)
    if not all_matches:
        print("❌ No matches found in data sources.")
        if args.dump_html and source_type == 'live':
            dump_html_structure('live_data.txt', verbose=verbose)
        return
    
    # Enforce min odds per match filter (could drop those from initial parser if user lowered requirement)
    if args.min_odds_per_match > 0:
        before = len(all_matches)
        all_matches = [m for m in all_matches if len(m['odds']) >= args.min_odds_per_match]
        if verbose and before != len(all_matches):
            print(f"   🔧 Filtered matches by min-odds-per-match={args.min_odds_per_match}: {before} -> {len(all_matches)}")

    print(f"📊 Found {len(all_matches)} matches total (min-odds-per-match={args.min_odds_per_match})")
    if verbose and all_matches:
        sample = all_matches[:3]
        print("🧪 Sample matches:")
        for m in sample:
            # Suppress placeholder bookmaker 'AUTO' in display
            def _fmt_pair(item):
                k, v = item
                odd, book = v
                return f"{k}={odd}" if (not book or str(book).upper() == 'AUTO') else f"{k}={odd}@{book}"
            print(f"   {m['teams']} -> " + ", ".join(_fmt_pair(it) for it in m['odds'].items()))
    
    # Optional enrichment: Winner market
    if args.fetch_winner:
        if verbose:
            print(f"🛠 Enriching matches with Winner markets (limit {args.max_match_details}) ...")
        all_matches = enrich_with_winner_markets(all_matches, max_details=args.max_match_details, detail_wait=args.detail_wait, headless=not args.no_headless, verbose=verbose, login_user=args.login_user, login_pass=args.login_pass)
        if args.debug_winner:
            enriched = [m for m in all_matches if 'Winner1' in m.get('odds',{}) and 'Winner2' in m.get('odds',{})]
            print(f"🔎 Winner debug: {len(enriched)} matches enriched")
            for m in enriched[:20]:
                w1 = m['odds']['Winner1'][0]
                w2 = m['odds']['Winner2'][0]
                print(f"   • {m['teams']} -> Winner1={w1} Winner2={w2}")

    # Analyze for surebets
    print("🔍 Analyzing for surebet opportunities...")
    surebets = analyze_surebets(all_matches, verbose=verbose, min_profit=args.min_profit,
                                stake_min=args.stake_min_total, stake_max=args.stake_max_total,
                                stake_total=args.stake_total, stake_round=args.stake_round)
    
    # Simple category split summary
    offline_count = sum(1 for s in surebets if s.get('category','local') == 'local')
    online_count = sum(1 for s in surebets if s.get('category') == 'online')
    print(f"💰 Found {len(surebets)} surebet opportunities (local={offline_count}, online={online_count}, min-profit filter: {args.min_profit}%)")
    
    # Save results
    surebet_file = save_results(all_matches, surebets, source_type)
    
    print("-" * 50)
    print(f"✅ Results saved to: {surebet_file}")
    
    # Display summary
    if surebets:
        print("\n🎉 SUREBET SUMMARY:")
        # Prioritize local first in summary listing
        ordered = [s for s in surebets if s.get('category','local') == 'local'] + [s for s in surebets if s.get('category') == 'online']
        for surebet in ordered[:10]:  # Show first 10 overall
            # Show both theoretical (input filter) and actual (after rounding) profit figures
            theo_pct = surebet.get('profit_theoretical', surebet.get('profit'))
            actual_pct = surebet.get('profit_actual', surebet.get('profit'))
            display_pct = f"{actual_pct}% actual (theo {theo_pct}%)" if 'profit_actual' in surebet else f"{theo_pct}%"
            cat = surebet.get('category','local')
            print(f"  • [{cat.upper()}] {surebet['match']} - {surebet['type']} - {display_pct} profit")
            odds_details = []
            for outcome, (odd, bookmaker) in surebet['odds'].items():
                if not bookmaker or str(bookmaker).upper() == 'AUTO':
                    odds_details.append(f"{outcome}: {odd:.2f}")
                else:
                    odds_details.append(f"{outcome}: {odd:.2f} @ {bookmaker}")
            print(f"    📊 {' | '.join(odds_details)}")
            if 'stakes' in surebet and surebet['stakes']:
                fmt_stake_parts = []
                for s in surebet['stakes']:
                    amount, odd_val, book = s
                    if not book or str(book).upper() == 'AUTO':
                        fmt_stake_parts.append(f"{amount} RSD on {odd_val}")
                    else:
                        fmt_stake_parts.append(f"{amount} RSD on {odd_val}@{book}")
                stake_str = ", ".join(fmt_stake_parts)
                abs_act = surebet.get('abs_profit','?')
                abs_theo = surebet.get('abs_profit_theoretical')
                if abs_theo is not None:
                    profit_part = f"Profit ≈ {abs_act} RSD (theo {abs_theo} RSD)"
                else:
                    profit_part = f"Profit ≈ {abs_act} RSD"
                print(f"    💼 Stakes: {stake_str} (Total {surebet.get('total_stake')} RSD, {profit_part})")
            print()
            
        if len(surebets) > 10:
            print(f"  ... and {len(surebets) - 10} more surebets")
    else:
        print(f"\n📊 No surebet opportunities found among {len(all_matches)} matches.")
    
    print(f"\n💡 Analysis complete! Check {surebet_file} for full details.")

if __name__ == "__main__":
    main()
