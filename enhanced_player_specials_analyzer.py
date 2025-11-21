"""Enhanced Player Specials Analyzer for TopTiket

This module scrapes and analyzes player special bets (points, assists, rebounds, etc.)
from TopTiket's player specials page. It focuses on Under/Over markets for various
player statistics and can handle multiple pages of data.

Features:
- Selenium-based scraping for JavaScript-heavy pages
- Multi-page support (3-4 pages as mentioned)
- Parsing of player names and their Under/Over odds
- Text extraction and DOM parsing
- Surebet detection for Under/Over player stats

Usage:
    python enhanced_player_specials_analyzer.py [--pages 4] [--verbose] [--min-profit 1.0]
"""

import argparse
import os
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import requests

# Default settings
DEFAULT_TOTAL_STAKE = 100
PLAYER_SPECIALS_URL = "https://toptiket.rs/odds/playerSpecial"

# Market sequence for player specials (typically Under/Over for various stats)
STAT_TYPES = [
    'Points', 'Assists', 'Rebounds', 'Threes', 'Steals', 'Blocks',
    'Turnovers', 'Minutes', 'Field Goals', 'Free Throws'
]

# ----------------- Generic Utility -----------------

def compute_stakes(odds):
    """Compute optimal stakes for arbitrage betting."""
    valid = [(o, b) for o, b in odds if o > 0]
    if len(valid) < 2:
        return [], 0
    
    inv = sum(1/o for o, _ in valid)
    if inv >= 1:
        return [], 0
    
    stakes = []
    for o, b in valid:
        stake = (DEFAULT_TOTAL_STAKE * (1/o)) / inv
        stakes.append((round(stake, 2), o, b))
    
    profit = round(stakes[0][0] * stakes[0][1] - DEFAULT_TOTAL_STAKE, 2) if stakes else 0
    return stakes, profit

def check_surebet(odds):
    """Check if odds present an arbitrage opportunity."""
    clean = [o for o, _ in odds if 1.01 <= o <= 200]
    if len(clean) < 2:
        return None
    
    inv = sum(1/o for o in clean)
    if inv < 1:
        return round((1 - inv) * 100, 2)
    return None

# ----------------- Live Download -----------------

def download_live_player_specials(headless=True, retries=2, selenium_wait=15, scroll_steps=6, pages=None, verbose=False):
    """Download player specials data from TopTiket using requests first, then Selenium fallback.

    Features added:
      - Infinite scroll until page height stabilizes.
      - Attempt to click Euroleague/Evroliga filter.
      - Pagination support for additional pages.
    """
    print("🎯 Attempting to download live player specials data from TopTiket...")

    # --- Simple requests attempt ---
    try:
        headers = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36' }
        r = requests.get(PLAYER_SPECIALS_URL, headers=headers, timeout=15)
        if r.status_code == 200 and len(r.text) > 5000 and 'You need to enable JavaScript' not in r.text:
            with open('live_player_specials_data.txt', 'w', encoding='utf-8') as f:
                f.write(r.text)
            print('✅ Player specials data via simple request')
            return True
    except Exception as e:
        if verbose:
            print(f"(requests player specials) error: {e}")

    # --- Selenium fallback ---
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print('❌ Selenium not installed for player specials scraping')
        return False

    for attempt in range(1, retries + 2):
        print(f"🎯 (Player Specials) Selenium attempt {attempt}/{retries+1}...")
        try:
            opts = Options()
            if headless:
                opts.add_argument('--headless=new')
            opts.add_argument('--window-size=1920,1080')
            opts.add_argument('--disable-gpu')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            try:
                driver.get(PLAYER_SPECIALS_URL)
                WebDriverWait(driver, selenium_wait).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

                # Initial fixed scrolls
                for s in range(scroll_steps):
                    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                    time.sleep(0.9)
                    if s == 0:
                        driver.execute_script('window.scrollTo(0,0);')

                # Infinite scroll stabilization
                if verbose:
                    print('↪️ Starting infinite scroll phase')
                stable = 0
                last_height = driver.execute_script('return document.body.scrollHeight')
                while stable < 3:
                    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                    time.sleep(1.1)
                    new_height = driver.execute_script('return document.body.scrollHeight')
                    if new_height == last_height:
                        stable += 1
                    else:
                        stable = 0
                        last_height = new_height
                    if verbose:
                        print(f'   • Scroll height={new_height} stable_pass={stable}')
                    if new_height > 3_000_000:
                        break

                # League filter attempt
                try:
                    labels = ['Evroliga', 'Euroleague', 'EUROLIGA', 'EUROLEAGUE']
                    for lab in labels:
                        elems = driver.find_elements(By.XPATH, f"//button[contains(normalize-space(.), '{lab}')] | //div[contains(@class,'Mui')][contains(normalize-space(.), '{lab}')]")
                        if elems:
                            elems[0].click()
                            if verbose:
                                print(f'✅ Clicked league filter: {lab}')
                            time.sleep(1.2)
                            break
                except Exception as league_err:
                    if verbose:
                        print(f'⚠️ League filter attempt failed: {league_err}')

                page_content = driver.page_source
                combined = page_content

                # Determine pagination automatically if pages not provided
                pages_to_scrape = pages
                if pages_to_scrape is None:
                    try:
                        detected = driver.execute_script("return Array.from(document.querySelectorAll('button,a,span,div')).map(e=>e.textContent.trim()).filter(t=>/^\\d+$/.test(t)).map(Number)")
                        if detected:
                            pages_to_scrape = max(detected)
                        else:
                            pages_to_scrape = 1
                    except Exception:
                        pages_to_scrape = 1
                    if verbose:
                        print(f'↪️ Auto-detected player specials pagination pages = {pages_to_scrape}')
                else:
                    if verbose:
                        print(f'↪️ Player specials pagination pages (requested) = {pages_to_scrape}')

                # Pagination loop
                if pages_to_scrape > 1:
                    for p in range(2, pages_to_scrape + 1):
                        try:
                            # locate page control
                            btn = None
                            search_xpaths = [
                                f"//button[normalize-space()='{p}']",
                                f"//a[normalize-space()='{p}']",
                                f"//span[normalize-space()='{p}']",
                                f"//*[contains(@class,'page') and normalize-space()='{p}']",
                                f"//*[contains(@class,'pagination') and normalize-space()='{p}']",
                                f"//*[text()='{p}']"
                            ]
                            for xp in search_xpaths:
                                els = driver.find_elements(By.XPATH, xp)
                                if els:
                                    btn = els[0]
                                    if verbose:
                                        print(f'  • Found page {p} control via {xp}')
                                    break
                            if not btn:
                                btn = driver.execute_script("return Array.from(document.querySelectorAll('button,a,span,div')).find(el=>el.textContent.trim()==='" + str(p) + "')")
                                if btn and verbose:
                                    print(f'  • Found page {p} via JS fallback')
                            if not btn:
                                if verbose:
                                    print(f'  • Page {p} control not found; stopping pagination')
                                break
                            try:
                                btn.click()
                            except Exception:
                                driver.execute_script('arguments[0].click();', btn)
                            if verbose:
                                print(f'  • Clicked page {p}')
                            time.sleep(1.8)
                            for _ in range(2):
                                driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                                time.sleep(0.6)
                            driver.execute_script('window.scrollTo(0,0);')
                            new_src = driver.page_source
                            if len(new_src) != len(page_content):
                                combined += f"\n<!-- PAGE {p} SPLIT -->\n" + new_src
                                if verbose:
                                    print(f'  • Page {p} content added ({len(new_src)} chars)')
                        except Exception as pag_err:
                            if verbose:
                                print(f'  • Pagination fail page {p}: {pag_err}')
                            break
                    page_content = combined

                odds_decimals = re.findall(r">\s*(\d+\.\d{2})\s*<", page_content)
                player_names = re.findall(r"[A-Z][a-z]+ [A-Z][a-z]+", page_content)
                if len(page_content) > 10000 and len(odds_decimals) > 10 and len(player_names) > 5:
                    with open('live_player_specials_data.txt', 'w', encoding='utf-8') as f:
                        f.write(page_content)
                    print('✅ Player specials data via Selenium')
                    return True
                else:
                    print('⚠️ Player specials content insufficient; retrying' if attempt <= retries else '❌ Player specials giving up')
                    if verbose:
                        print(f'  Content length={len(page_content)} odds={len(odds_decimals)} players={len(player_names)}')
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass
        except Exception as e:
            print(f'❌ Player specials Selenium attempt error: {e}')
            time.sleep(2.0)
    return False

# ----------------- Flatten HTML -----------------

def flatten_html_to_text(html_path, out_txt):
    """Convert HTML to plain text using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("BeautifulSoup missing (pip install beautifulsoup4)")
        return None
    
    if not os.path.exists(html_path):
        return None
    
    with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text('\n', strip=True)
    
    with open(out_txt, 'w', encoding='utf-8') as f:
        f.write(text)
    
    return out_txt

# ----------------- Parsing -----------------

def parse_player_specials_flat(lines, verbose=False):
    """Parse player specials from flattened text lines.

    Strategy:
      1. Primary pattern: Player line, Team line, Under, Stat, Over.
      2. Supports name formats:
         - Full name: "Khadeen Carrington"
         - Initial + surname: "K. Sloukas"
         - Surname + initial: "Carrington K." (future-proof)
      3. Fallback heuristic: scan sliding windows to infer (under, stat, over) triplets near a name.
      4. Debug logging for skipped candidates when verbose.
    """
    matches = []
    i = 0
    n = len(lines)

    # Regex patterns
    decimal_re = re.compile(r'^(?:\d+\.\d+|\d+)$')  # Accept integer or decimal
    # Player name patterns combined: full name, initial + surname, surname + initial
    # Allow:
    #  - Mixed case names
    #  - ALL CAPS surnames (SLOUKAS)
    #  - Initial + ALLCAPS surname (K. SLOUKAS)
    #  - Basic Greek letter ranges (Κ, Σ, Λ etc.)
    player_name_re = re.compile(
        r'^(?:'
        r'(?:[A-ZΑ-Ω][a-zά-ώα-ω]+\s+[A-ZΑ-Ω][a-zά-ώα-ω]+(?:\s+[A-ZΑ-Ω][a-zά-ώα-ω]+)*)'      # Full name(s)
        r'|(?:[A-ZΑ-Ω]\.?\s+[A-ZΑ-Ω][a-zά-ώα-ω]+(?:\s+[A-ZΑ-Ω][a-zά-ώα-ω]+)*)'                   # Initial + surname
        r'|(?:[A-ZΑ-Ω][a-zά-ώα-ω]+\s+[A-ZΑ-Ω]\.?\s?)'                                            # Surname + initial (space optional)
        r'|(?:[A-ZΑ-Ω]\.?\s+[A-ZΑ-Ω]{2,})'                                                       # K. SLOUKAS
        r'|(?:[A-ZΑ-Ω][a-zά-ώα-ω]+\s+[A-ZΑ-Ω]{2,})'                                               # Kostas SLOUKAS
        r'|(?:[A-ZΑ-Ω]{2,}\s+[A-ZΑ-Ω]{2,})'                                                       # SLOUKAS KOSTAS
        r')$'
    )
    team_name_re = re.compile(r'^[A-Za-z][A-Za-z0-9\s\-\'\.]+$')

    def log(msg):
        if verbose:
            print(msg)

    def detect_stat_type(context_lines):
        joined = ' '.join(context_lines).lower()
        if 'assist' in joined:
            return 'Assists'
        if 'reb' in joined or 'skok' in joined:
            return 'Rebounds'
        if 'three' in joined or '3pt' in joined or 'troj' in joined:
            return 'Threes'
        return 'Points'

    def add_match(player_name, team_line, under_odds, stat_value, over_odds, source, ctx=None):
        stat_type = detect_stat_type(ctx or [])
        match_id = f"{player_name} - {stat_type} {stat_value}"
        odds_map = {
            'Under': (under_odds, 'TopTiket'),
            'Over': (over_odds, 'TopTiket')
        }
        matches.append({
            'player': player_name,
            'team': team_line,
            'stat_type': stat_type,
            'stat_value': stat_value,
            'teams': match_id,
            'odds': odds_map,
            'parsed_via': source
        })
        inv_sum = (1/under_odds) + (1/over_odds)
        is_surebet = inv_sum < 1.0
        profit = (1 - inv_sum) * 100 if is_surebet else 0
        surebet_str = f" *** SUREBET {profit:.2f}% ***" if is_surebet else ""
        log(f"[player_specials:{source}] {player_name} ({team_line}) {stat_value} {stat_type} -> Under={under_odds}, Over={over_odds}{surebet_str}")

    # Primary sequential parse
    while i < n:
        line = lines[i].strip()
        if player_name_re.match(line) and i + 1 < n:
            player_name = line
            team_candidate = lines[i + 1].strip()
            if team_name_re.match(team_candidate) and i + 4 < n:
                under_line = lines[i + 2].strip()
                stat_line = lines[i + 3].strip()
                over_line = lines[i + 4].strip()
                if (decimal_re.match(under_line) and decimal_re.match(stat_line) and decimal_re.match(over_line)):
                    try:
                        under_odds = float(under_line)
                        over_odds = float(over_line)
                        stat_value = stat_line
                        if 1.01 <= under_odds <= 50 and 1.01 <= over_odds <= 50:
                            context_slice = lines[max(0, i-3): min(n, i+6)]
                            add_match(player_name, team_candidate, under_odds, stat_value, over_odds, 'primary', context_slice)
                            i += 5
                            continue
                        else:
                            log(f"[skip:odds-range] {player_name} {under_line}/{over_line}")
                    except ValueError:
                        log(f"[skip:value-error] {player_name} raw={under_line},{stat_line},{over_line}")
            # If failed, fall through to heuristic attempt below
        i += 1

    # Fallback heuristic: locate player names first, then search nearby window for odds triplet
    if verbose:
        log("[heuristic] Starting secondary scan for missed players")
    for idx, line in enumerate(lines):
        if not player_name_re.match(line):
            continue
        # Skip if already captured
        if any(m['player'] == line for m in matches):
            continue
        # Look ahead up to 12 lines
        window = lines[idx+1: idx+13]
        # Attempt to find pattern: team (non-numeric), under (decimal), stat (decimal with .5 likely), over (decimal)
        for w_pos in range(len(window) - 3):
            t_candidate = window[w_pos].strip()
            a = window[w_pos + 1].strip()
            b = window[w_pos + 2].strip()
            c = window[w_pos + 3].strip()
            if (team_name_re.match(t_candidate) and decimal_re.match(a) and decimal_re.match(b) and decimal_re.match(c)):
                try:
                    under_odds = float(a)
                    stat_value = b
                    over_odds = float(c)
                    if 1.01 <= under_odds <= 50 and 1.01 <= over_odds <= 50:
                        context_slice = lines[max(0, idx-3): min(n, idx+10)]
                        add_match(line, t_candidate, under_odds, stat_value, over_odds, 'heuristic', context_slice)
                        break
                except ValueError:
                    continue
        else:
            if verbose:
                log(f"[heuristic:miss] Could not resolve odds block for {line}")

    if verbose:
        log(f"[player_specials] Total player specials parsed: {len(matches)} (primary+heuristic)")
    return matches

def parse_player_specials_dom(html_file="live_player_specials_data.txt", verbose=False):
    """Parse player specials directly from DOM structure."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        if verbose:
            print("BeautifulSoup not available for DOM parsing")
        return []
    
    if not os.path.exists(html_file):
        if verbose:
            print(f"HTML file {html_file} not found")
        return []
    
    with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    matches = []
    
    # Look for player names and associated odds
    # This is a heuristic approach - may need adjustment based on actual DOM structure
    player_elements = soup.find_all(text=re.compile(r'^[A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$'))
    
    for player_text in player_elements:
        if not isinstance(player_text, str):
            continue
            
        player_name = player_text.strip()
        parent = player_text.parent
        
        if not parent:
            continue
        
        # Look for odds in nearby elements
        odds_elements = []
        
        # Search in parent and siblings
        for elem in [parent] + list(parent.find_next_siblings())[:5]:
            if elem:
                odds_texts = elem.find_all(text=re.compile(r'^\d+\.\d{2}$'))
                odds_elements.extend(odds_texts)
        
        # Try to pair odds as Under/Over
        valid_odds = []
        for odds_text in odds_elements:
            try:
                odds_val = float(odds_text.strip())
                if 1.01 <= odds_val <= 50.0:
                    valid_odds.append(odds_val)
            except (ValueError, AttributeError):
                continue
        
        # If we have at least 2 odds, treat first two as Under/Over
        if len(valid_odds) >= 2:
            under_odds = valid_odds[0]
            over_odds = valid_odds[1]
            
            match_id = f"{player_name} - Points"  # Default to points
            odds_map = {
                'Under': (under_odds, 'TopTiket'),
                'Over': (over_odds, 'TopTiket')
            }
            
            matches.append({
                'player': player_name,
                'stat_type': 'Points',
                'teams': match_id,
                'odds': odds_map
            })
            
            if verbose:
                print(f"[player_specials_dom] {match_id} -> Under={under_odds}, Over={over_odds}")
    
    if verbose:
        print(f"[player_specials_dom] Total player specials parsed: {len(matches)}")
    
    return matches

# ----------------- Surebet Logic -----------------

def analyze_player_specials_surebets(matches, min_profit=0.0, verbose=False):
    """Analyze player specials for surebet opportunities."""
    surebets = []
    
    for m in matches:
        odds_data = m['odds']
        
        # Check Under/Over for each player stat
        if 'Under' in odds_data and 'Over' in odds_data:
            under_odds = odds_data['Under']
            over_odds = odds_data['Over']
            
            profit = check_surebet([under_odds, over_odds])
            if profit and profit >= min_profit:
                stakes, abs_profit = compute_stakes([under_odds, over_odds])
                
                surebet_info = {
                    'match': m['teams'],
                    'player': m['player'],
                    'stat_type': m['stat_type'],
                    'type': 'Under/Over',
                    'profit': profit,
                    'odds': {
                        'Under': under_odds,
                        'Over': over_odds
                    },
                    'stakes': stakes,
                    'abs_profit': abs_profit
                }
                
                surebets.append(surebet_info)
                
                if verbose:
                    print(f"SUREBET: {m['teams']} - Profit: {profit}%")
    
    return surebets

# ----------------- Output -----------------

def save_player_specials(matches, surebets, source_type):
    """Save matches and surebets to files."""
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    matches_file = f"player_specials_{source_type}_matches_{ts}.txt"
    surebets_file = f"player_specials_{source_type}_surebets_{ts}.txt"
    
    # Save matches
    with open(matches_file, 'w', encoding='utf-8') as f:
        f.write(f"Player Specials Matches ({source_type}) - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write('=' * 80 + '\n\n')
        
        for m in matches:
            f.write(f"{m['teams']}\n")
            for stat, (odds, book) in m['odds'].items():
                f.write(f"  {stat}: {odds} @ {book}\n")
            f.write('\n')
    
    # Save surebets
    with open(surebets_file, 'w', encoding='utf-8') as f:
        f.write(f"Player Specials Surebets ({source_type}) - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write('=' * 80 + '\n\n')
        
        if not surebets:
            f.write('No surebets found.\n')
        else:
            f.write(f"Found {len(surebets)} surebet opportunities:\n\n")
            for sb in surebets:
                f.write(f"{sb['match']}\n")
                f.write(f"  ✅ {sb['type']} SUREBET → Profit: {sb['profit']}%\n")
                
                odds_line = ', '.join(f"{k}={v[0]}" for k, v in sb['odds'].items())
                f.write(f"  Odds: {odds_line}\n")
                
                if sb['stakes']:
                    stakes_line = ', '.join(f"{stat}=${stake[0]}" for stake, stat in zip(sb['stakes'], ['Under', 'Over']))
                    f.write(f"  Stakes: {stakes_line}\n")
                
                f.write('\n')
    
    return matches_file, surebets_file

# ----------------- Main -----------------

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Enhanced Player Specials Odds Analyzer')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--pages', type=int, help='Number of pages to scrape; omit to auto-detect maximum')
    parser.add_argument('--min-profit', type=float, default=0.0, help='Minimum profit percentage for surebets')
    parser.add_argument('--no-headless', action='store_true', help='Run browser in visible mode')
    parser.add_argument('--retries', type=int, default=2, help='Number of retry attempts')
    args = parser.parse_args()
    
    verbose = args.verbose
    
    # Download live data
    print("🎯 Starting player specials analysis...")
    success = download_live_player_specials(
        headless=not args.no_headless,
        retries=args.retries,
        pages=args.pages,
        verbose=verbose
    )
    
    if not success:
        print('❌ Could not fetch player specials live data.')
        return
    
    # Convert HTML to text
    flat_file = flatten_html_to_text('live_player_specials_data.txt', 'live_player_specials_extracted.txt')
    if not flat_file:
        print('❌ Could not flatten player specials HTML.')
        return
    
    # Parse the data
    with open(flat_file, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f if l.strip()]
    
    matches = parse_player_specials_flat(lines, verbose=verbose)
    
    # If text parsing didn't work well, try DOM parsing
    if not matches:
        if verbose:
            print("ℹ️ Text parsing found 0 matches, attempting DOM parsing.")
        matches = parse_player_specials_dom(verbose=verbose)
    
    if not matches:
        print('❌ No player specials matches parsed.')
        return
    
    print(f"📊 Parsed {len(matches)} player specials")
    
    # Analyze for surebets
    surebets = analyze_player_specials_surebets(matches, min_profit=args.min_profit, verbose=verbose)
    print(f"💰 Found {len(surebets)} player specials surebets (min-profit {args.min_profit}%)")
    
    # Save results
    matches_file, surebets_file = save_player_specials(matches, surebets, 'live')
    print(f"✅ Saved: {matches_file} & {surebets_file}")
    
    # Display summary
    if surebets:
        print('\n🎉 PLAYER SPECIALS SUREBET SUMMARY:')
        for sb in surebets[:10]:  # Show top 10
            print(f"  • {sb['player']} ({sb['stat_type']}) - {sb['profit']}%")
    else:
        print('\nℹ️ No surebet opportunities identified in player specials.')

if __name__ == '__main__':
    main()