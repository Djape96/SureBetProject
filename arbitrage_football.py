import re
import glob
import time
import os
import sys
import hashlib
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
try:
    from telegram_notifier import send_surebets_summary
except Exception:
    send_surebets_summary = None  # graceful fallback if not available

# Configuration flags
THREE_DAY_ONLY = True  # If True, skip separate 'today' scrape and go straight to 3-day ("3 dana") view
EXPECTED_3D_PAGES = 27  # Expected number of pages in 3-day view (user provided)
FORCE_MAX_3D_PAGES = 27  # Hard upper iteration bound
FAST_MODE = True         # Speed optimizations (lower waits & lightweight page loading)
PAGE_LIMIT = int(os.environ.get('FOOTBALL_PAGE_LIMIT', '0'))  # 0 = no early limit; set e.g. FOOTBALL_PAGE_LIMIT=3

# Optional CLI override: --page-limit N or --pages N
def _cli_page_limit():
    try:
        if '--page-limit' in sys.argv:
            i = sys.argv.index('--page-limit')
            return int(sys.argv[i+1])
        if '--pages' in sys.argv:
            i = sys.argv.index('--pages')
            return int(sys.argv[i+1])
    except Exception:
        return None
    return None

_pl = _cli_page_limit()
if _pl is not None:
    PAGE_LIMIT = _pl
    print(f"🔧 PAGE_LIMIT override via CLI: {PAGE_LIMIT}")
FAST_SCROLLS = 2         # Number of scroll cycles per page in FAST_MODE
NORMAL_SCROLLS = 4       # Scroll cycles when not fast
HASH_WAIT_LOOPS = 4      # loops to detect content change (reduced when fast)

def _extract_matches_dom(driver):
    """Attempt to extract match data directly from the rendered DOM.
    Returns list of dicts with keys: time, team1, team2, odds (dict).
    This relies on heuristic selection of elements containing teams and odds.
    """
    results = []
    try:
        # Grab all text nodes relevant inside body
        page_html = driver.page_source
        soup = BeautifulSoup(page_html, 'html.parser')
        # Heuristic: collect sequences of [TIME, TEAM1, TEAM2, O1,O2,O3,O4,O5, (O6),(O7)]
        # We'll scan text blocks but skip navigation; DOM helps because order is stable per match card.
        tokens = []
        for el in soup.find_all(text=True):
            text = el.strip()
            if not text:
                continue
            if len(text) > 60:
                continue
            tokens.append(text)
        invalid = set(['1','X','2','0-2','3+','GG','GG3+','Presented by:'])
        i = 0
        while i < len(tokens):
            if re.match(r'^\d{1,2}:\d{2}$', tokens[i]):
                t = tokens[i]
                if i+2 < len(tokens):
                    team1 = tokens[i+1]
                    team2 = tokens[i+2]
                    # Basic team validation
                    if all(len(x) > 2 for x in [team1, team2]) and team1 not in invalid and team2 not in invalid:
                        odds = []
                        j = i+3
                        while j < len(tokens) and len(odds) < 7:
                            try:
                                val = float(tokens[j].replace(',', '.'))
                                if 1.05 <= val <= 50:
                                    odds.append(val)
                                else:
                                    break
                            except ValueError:
                                break
                            j += 1
                        if len(odds) >= 5:
                            entry = {
                                'time': t,
                                'team1': team1,
                                'team2': team2,
                                'odds': {
                                    '1': odds[0],
                                    'X': odds[1],
                                    '2': odds[2],
                                    '0-2': odds[3],
                                    '3+': odds[4]
                                }
                            }
                            if len(odds) >= 6: entry['odds']['GG'] = odds[5]
                            if len(odds) >= 7: entry['odds']['NG'] = odds[6]
                            results.append(entry)
                            i = j
                            continue
            i += 1
    except Exception as e:
        print(f"⚠️ DOM extraction error: {e}")
    return results

def download_fresh_data():
    """Download fresh index files & DOM matches.
    Modes:
      - Default: scrape 'today' then switch to 3-day view.
      - THREE_DAY_ONLY=True: directly switch to 3-day and attempt up to EXPECTED_3D_PAGES pages.
    """
    mode_txt = "3-day only" if THREE_DAY_ONLY else "today + 3-day"
    print(f"🔄 Starting fresh data download from TopTiket ({mode_txt})...")

    # Delete existing index files (both today and 3d prefixes)
    for old_file in glob.glob("index_*.txt") + glob.glob("3d_index_*.txt"):
        try:
            os.remove(old_file)
            print(f"🗑️ Deleted old file: {old_file}")
        except Exception as e:
            print(f"⚠️ Could not delete {old_file}: {e}")

    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    if FAST_MODE:
        # Disable images / stylesheets to speed up
        prefs = {
            'profile.managed_default_content_settings.images': 2,
            'profile.managed_default_content_settings.stylesheets': 2,
            'profile.managed_default_content_settings.cookies': 1,
            'profile.managed_default_content_settings.javascript': 1
        }
        chrome_options.add_experimental_option('prefs', prefs)
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    def _detect_total_pages():
        fallback = 18
        try:
            time.sleep(1.5)
            pagination_candidates = driver.find_elements(By.XPATH, "//a[normalize-space()][@href or contains(@class,'page')]|//button[normalize-space()]")
            nums = []
            for el in pagination_candidates:
                txt = el.text.strip()
                if txt.isdigit():
                    try:
                        nums.append(int(txt))
                    except ValueError:
                        pass
            if nums:
                detected = max(nums)
                if 2 <= detected <= 100:
                    print(f"📄 Detected pages: {detected}")
                    return detected
            print(f"ℹ️ Using fallback pages: {fallback}")
            return fallback
        except Exception as e:
            print(f"⚠️ Page detection failed, fallback {fallback}: {e}")
            return fallback

    def _collect_pages(range_label: str, file_prefix: str, dom_list: list, seen_hashes: set):
        total_pages = _detect_total_pages()
        if range_label == '3d' and THREE_DAY_ONLY and total_pages < EXPECTED_3D_PAGES:
            print(f"⚠️ Forcing 3-day page count from {total_pages} to {EXPECTED_3D_PAGES}")
            total_pages = EXPECTED_3D_PAGES
        for page_num in range(1, total_pages + 1):
            try:
                start_page_ts = time.time()
                if not FAST_MODE:
                    print(f"📥 ({range_label}) page {page_num}/{total_pages} ...")
                if page_num == 1:
                    # just ensure we are at top
                    time.sleep(0.8 if FAST_MODE else 2)
                else:
                    # Try pagination click first
                    clicked = False
                    selectors = [
                        f"//a[normalize-space()='{page_num}']",
                        f"//button[normalize-space()='{page_num}']",
                        f"//li[a[normalize-space()='{page_num}']]//a"
                    ]
                    for sel in selectors:
                        try:
                            el = WebDriverWait(driver, 2 if not FAST_MODE else 0.8).until(EC.element_to_be_clickable((By.XPATH, sel)))
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                            driver.execute_script("arguments[0].click();", el)
                            clicked = True
                            time.sleep(0.9 if FAST_MODE else 2.2)
                            break
                        except Exception:
                            continue
                    if not clicked:
                        # fallback direct url param (may or may not work, harmless)
                        try:
                            driver.get(f"https://toptiket.rs/odds/football?page={page_num}")
                            time.sleep(0.9 if FAST_MODE else 2.2)
                        except Exception:
                            pass

                # Lazy load scroll
                try:
                    last_height = driver.execute_script("return document.body.scrollHeight")
                    scroll_loops = FAST_SCROLLS if FAST_MODE else NORMAL_SCROLLS
                    for _ in range(scroll_loops):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(0.55 if FAST_MODE else 1.0)
                        new_h = driver.execute_script("return document.body.scrollHeight")
                        if new_h == last_height:
                            break
                        last_height = new_h
                    driver.execute_script("window.scrollTo(0, 0);")
                except Exception:
                    pass

                time.sleep(0.5 if FAST_MODE else 1.2)
                page_source = driver.page_source
                content_hash = hashlib.md5(page_source.encode('utf-8')).hexdigest()
                # Skip duplicate HTML content across pages for all ranges to avoid bloating data
                if content_hash in seen_hashes:
                    if not FAST_MODE:
                        print(f"⚠️ Duplicate hash (skip) p{page_num}")
                    continue
                seen_hashes.add(content_hash)

                soup = BeautifulSoup(page_source, 'html.parser')
                text_content = soup.get_text(separator='\n', strip=True)
                lines = text_content.split('\n')
                filtered = []
                for line in lines:
                    line = line.strip()
                    if line and not any(sk in line.lower() for sk in ['cookie','javascript','gtm','script','function','window','document','meta','charset','viewport']):
                        filtered.append(line)
                filename = f"{file_prefix}{page_num}.txt"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(filtered))
                if not FAST_MODE:
                    print(f"✅ Saved {filename} ({content_hash[:8]})")
                dom_matches = _extract_matches_dom(driver)
                if not FAST_MODE:
                    print(f"   ↳ DOM matches: {len(dom_matches)}")
                for m in dom_matches:
                    m['page'] = page_num
                    m['range'] = range_label
                dom_list.extend(dom_matches)
                if FAST_MODE:
                    dur = time.time() - start_page_ts
                    print(f"⚡ {range_label} p{page_num} done in {dur:.2f}s (matches {len(dom_matches)})")
            except Exception as e:
                print(f"❌ Error ({range_label}) page {page_num}: {e}")
                continue

    dom_matches_all = []
    seen_hashes_today = set()
    seen_hashes_3d = set()
    try:
        print("🌐 Opening football odds page ...")
        driver.get("https://toptiket.rs/odds/football")
        WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        time.sleep(1.2 if FAST_MODE else 3)

        if not THREE_DAY_ONLY:
            print("📄 Collecting 'today' pages...")
            _collect_pages('today', 'index_', dom_matches_all, seen_hashes_today)

        # Helper to robustly click '3 dana'
        def click_three_day():
            # Try direct XPath text contains
            patterns = [
                "//button[contains(.,'3 dana')]",
                "//a[contains(.,'3 dana')]",
                "//*[contains(.,'3 dana') and (self::button or self::a or @role='button')]"
            ]
            for sel in patterns:
                try:
                    btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, sel)))
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2)
                    return True
                except Exception:
                    continue
            # JS brute force scan for innerText
            try:
                js = """
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                const targets = [];
                while(walker.nextNode()){
                  const el = walker.currentNode;
                  const t = (el.innerText||'').trim().toLowerCase();
                  if(t === '3 dana' || t.startsWith('3 dana')) targets.push(el);
                }
                return targets.map(e=>{
                  e.scrollIntoView({block:'center'}); e.click(); return e.innerText;});
                """
                res = driver.execute_script(js)
                if res:
                    time.sleep(2)
                    return True
            except Exception:
                pass
            return False

        print("🔀 Switching to 3-day view (3 dana)...")
        switched = click_three_day()
        if not switched:
            print("❌ Could not locate '3 dana' control. 3-day scrape aborted.")
        else:
            # Deep scroll to trigger load before counting pages
            try:
                scroll_cycles = 1 if FAST_MODE else 3
                for _ in range(scroll_cycles):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(0.6 if FAST_MODE else 1.2)
                    driver.execute_script("window.scrollTo(0,0);")
                    time.sleep(0.4 if FAST_MODE else 0.8)
            except Exception:
                pass
            # Iterative numeric + arrow pagination
            range_label = '3d'
            prefix = '3d_index_'
            current_page = 1
            visited_hashes = set()
            max_page_seen = 1
            def extract_and_save(page_no):
                page_source = driver.page_source
                content_hash = hashlib.md5(page_source.encode('utf-8')).hexdigest()
                if content_hash in visited_hashes:
                    print(f"⚠️ Duplicate page hash (skip content save) p{page_no}")
                    return 0
                visited_hashes.add(content_hash)
                soup = BeautifulSoup(page_source, 'html.parser')
                text_content = soup.get_text(separator='\n', strip=True)
                lines = [ln.strip() for ln in text_content.split('\n') if ln.strip() and not any(sk in ln.lower() for sk in ['cookie','javascript','gtm','script','function','window','document','meta','charset','viewport'])]
                filename = f"{prefix}{page_no}.txt"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
                dom_matches = _extract_matches_dom(driver)
                for m in dom_matches:
                    m['page'] = page_no
                    m['range'] = range_label
                dom_matches_all.extend(dom_matches)
                print(f"✅ Saved {filename} | DOM matches {len(dom_matches)}")
                return len(dom_matches)

            # Save first page
            extract_and_save(current_page)

            def scan_max_page():
                max_found = 0
                try:
                    pag_elems = driver.find_elements(By.XPATH, "//nav//*[self::a or self::button][normalize-space()]|//*[contains(@class,'pagination')]//*[self::a or self::button][normalize-space()]")
                    for el in pag_elems:
                        try:
                            t = el.text.strip()
                            if t.isdigit():
                                max_found = max(max_found, int(t))
                        except Exception:
                            continue
                except Exception:
                    pass
                return max_found if max_found else 1

            max_page_seen = scan_max_page()
            print(f"📄 Initial pagination reports max page {max_page_seen}")
            hard_cap = FORCE_MAX_3D_PAGES

            while current_page < hard_cap:
                # Refresh max each loop
                max_page_seen = max(max_page_seen, scan_max_page())
                if current_page >= max_page_seen and max_page_seen < EXPECTED_3D_PAGES:
                    # try arrow to extend
                    pass
                if current_page >= max_page_seen and max_page_seen >= EXPECTED_3D_PAGES:
                    print(f"✅ Reached detected last page {max_page_seen}")
                    break

                # Early user-defined page limit
                if PAGE_LIMIT and current_page >= PAGE_LIMIT:
                    print(f"🛑 PAGE_LIMIT={PAGE_LIMIT} reached; stopping pagination early.")
                    break

                next_page = current_page + 1
                clicked = False
                # Try direct numeric button
                for sel in [
                    f"//a[normalize-space()='{next_page}']",
                    f"//button[normalize-space()='{next_page}']",
                    f"//li[a[normalize-space()='{next_page}']]//a"
                ]:
                    try:
                        el = WebDriverWait(driver, 0.6 if FAST_MODE else 1).until(EC.element_to_be_clickable((By.XPATH, sel)))
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        driver.execute_script("arguments[0].click();", el)
                        clicked = True
                        if not FAST_MODE:
                            print(f"➡️ Clicked page {next_page} directly")
                        time.sleep(0.9 if FAST_MODE else 1.4)
                        break
                    except Exception:
                        continue
                # Fallback arrow
                if not clicked:
                    for arrow_sel in [
                        "//a[contains(.,'›')]",
                        "//button[contains(.,'›')]",
                        "//a[contains(@aria-label,'Next')]",
                        "//button[contains(@aria-label,'Next')]"
                    ]:
                        try:
                            el = WebDriverWait(driver, 0.6 if FAST_MODE else 1).until(EC.element_to_be_clickable((By.XPATH, arrow_sel)))
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                            driver.execute_script("arguments[0].click();", el)
                            clicked = True
                            if not FAST_MODE:
                                print("➡️ Clicked next arrow")
                            time.sleep(0.9 if FAST_MODE else 1.4)
                            break
                        except Exception:
                            continue
                if not clicked:
                    print(f"⚠️ Unable to advance from page {current_page}; stopping.")
                    break

                # Wait for content hash change
                prev_hash = None
                try:
                    prev_hash = hashlib.md5(driver.page_source.encode('utf-8')).hexdigest()
                    loops = 2 if FAST_MODE else HASH_WAIT_LOOPS
                    for _ in range(loops):
                        time.sleep(0.35 if FAST_MODE else 0.5)
                        new_hash = hashlib.md5(driver.page_source.encode('utf-8')).hexdigest()
                        if new_hash != prev_hash:
                            break
                except Exception:
                    pass

                current_page += 1
                extract_and_save(current_page)

        print(f"🏁 Pagination loop ended at page {current_page}; max seen {max_page_seen}{' (early stop)' if PAGE_LIMIT and current_page>=PAGE_LIMIT else ''}")

        try:
            with open('dom_matches.json', 'w', encoding='utf-8') as jf:
                json.dump(dom_matches_all, jf, ensure_ascii=False, indent=2)
            print(f"💾 Saved DOM structured matches: {len(dom_matches_all)} -> dom_matches.json")
        except Exception as je:
            print(f"⚠️ Could not save dom_matches.json: {je}")
    except Exception as e:
        print(f"❌ Error during download flow: {e}")
    finally:
        driver.quit()

def check_surebet(odds):
    clean_odds = [o for o, _ in odds if 0 < o < 50]  # ignore extreme invalid odds
    if len(clean_odds) < 2:
        return None
    inv_sum = sum(1 / o for o in clean_odds)
    if inv_sum < 1:
        return round((1 - inv_sum) * 100, 2)
    return None

def parse_file(filename):
    """Parse matches from a single index file - extract real TopTiket odds.
    Returns list of match dicts.
    """
    matches = []
    
    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"⚠️ File not found: {filename}")
        return matches
    except Exception as e:
        print(f"❌ Error reading {filename}: {e}")
        return matches
    
    i = 0
    while i < len(lines):
        # Look for time pattern first (like "13:30")
        if re.match(r'^\d+:\d+$', lines[i]):
            time = lines[i]
            
            # Next should be team 1
            if i + 1 < len(lines):
                team1 = lines[i + 1]
                
                # Filter out navigation elements and invalid team names
                invalid_teams = [
                    'top', 'tiket', 'sve lige', 'albanija', 'england', 'premier',
                    'scotland', 'championship', 'italy', 'serie', 'germany',
                    'bundesliga', 'spain', 'laliga', 'france', 'ligue', 'naredne',
                    'početna', 'kvote', 'novo', 'promocije', 'uloguj se', 'fudbal',
                    'košarka', 'tenis', 'hokej', 'omiljene lige', 'engleska',
                    'francuska', 'italija', 'nemačka', 'srbija', 'španija'
                ]
                
                if (team1.lower() in invalid_teams or len(team1) <= 3 or
                    any(skip in team1.lower() for skip in invalid_teams)):
                    i += 1
                    continue
                    
                # Next should be team 2  
                if i + 2 < len(lines):
                    team2 = lines[i + 2]
                    
                    # Filter team2 as well
                    if (team2.lower() in invalid_teams or len(team2) <= 3 or
                        any(skip in team2.lower() for skip in invalid_teams)):
                        i += 1
                        continue
                    
                    # Try to extract 5-7 odds after team2
                    odds = []
                    j = i + 3
                    while j < len(lines) and len(odds) < 10:  # Collect up to 10 potential odds
                        line = lines[j]
                        try:
                            # Check if it's a valid odds number
                            odds_val = float(line.replace(',', '.'))
                            if 1.1 <= odds_val <= 50.0:  # Valid odds range
                                odds.append(odds_val)
                            else:
                                # If we have some odds and hit invalid number, stop
                                if odds:
                                    break
                        except ValueError:
                            # If we hit non-numeric data and have some odds, stop
                            if odds:
                                break
                        j += 1
                    
                    # We need exactly 5-7 odds for a complete match (1X2 + O/U + maybe more)
                    if 5 <= len(odds) <= 7:
                        match = {
                            'teams': f"{team1} vs {team2}",
                            'team1': team1,
                            'team2': team2,
                            'time': time,
                            'odds': {
                                'TopTiket': {
                                    '1': odds[0],    # Home win
                                    'X': odds[1],    # Draw  
                                    '2': odds[2],    # Away win
                                    '0-2': odds[3],  # Under 2.5
                                    '3+': odds[4]    # Over 2.5
                                }
                            }
                        }
                        
                        # Add extra markets if available
                        if len(odds) >= 6:
                            match['odds']['TopTiket']['GG'] = odds[5]
                        if len(odds) >= 7:
                            match['odds']['TopTiket']['NG'] = odds[6]
                        
                        matches.append(match)
                        i = j
                        continue
        
        i += 1
    
    return matches
def detect_surebets(matches):
    """Return only true arbitrage (sum implied probabilities < 1) markets with stake allocation."""
    results = []
    for match in matches:
        odds_map = match['odds']['TopTiket']
        # 1X2
        if all(k in odds_map for k in ['1','X','2']):
            o1, ox, o2 = odds_map['1'], odds_map['X'], odds_map['2']
            inv_sum = (1/o1)+(1/ox)+(1/o2)
            if inv_sum < 1.0:
                margin_pct = (1 - inv_sum) * 100
                roi_pct = ((1/inv_sum) - 1) * 100
                total = 100.0
                stake1 = (1/o1)/inv_sum * total
                stakex = (1/ox)/inv_sum * total
                stake2 = (1/o2)/inv_sum * total
                results.append({
                    'match': match,
                    'type': '1X2',
                    'margin_pct': round(margin_pct,2),
                    'roi_pct': round(roi_pct,2),
                    'stakes': {'1': round(stake1,2), 'X': round(stakex,2), '2': round(stake2,2)},
                    'odds': f"1={o1}, X={ox}, 2={o2}"
                })
        # O/U
        if all(k in odds_map for k in ['0-2','3+']):
            u, ov = odds_map['0-2'], odds_map['3+']
            inv_sum = (1/u)+(1/ov)
            if inv_sum < 1.0:
                margin_pct = (1 - inv_sum) * 100
                roi_pct = ((1/inv_sum) - 1) * 100
                total = 100.0
                stake_u = (1/u)/inv_sum * total
                stake_o = (1/ov)/inv_sum * total
                results.append({
                    'match': match,
                    'type': 'O/U',
                    'margin_pct': round(margin_pct,2),
                    'roi_pct': round(roi_pct,2),
                    'stakes': {'0-2': round(stake_u,2), '3+': round(stake_o,2)},
                    'odds': f"0-2={u}, 3+={ov}"
                })
    return results

NOTIFY_MIN_ROI = float(os.environ.get('FOOTBALL_NOTIFY_MIN_ROI','2.5'))
NOTIFY_MAX_ROI = float(os.environ.get('FOOTBALL_NOTIFY_MAX_ROI','20'))

def _cli_arg_float(flag: str, default: float) -> float:
    try:
        if flag in sys.argv:
            i = sys.argv.index(flag)
            return float(sys.argv[i+1])
    except Exception:
        return default
    return default

def _cli_flag(flag: str) -> bool:
    return flag in sys.argv

def main():
    global NOTIFY_MIN_ROI, NOTIFY_MAX_ROI
    # Allow CLI overrides
    NOTIFY_MIN_ROI = _cli_arg_float('--notify-min-roi', NOTIFY_MIN_ROI)
    NOTIFY_MAX_ROI = _cli_arg_float('--notify-max-roi', NOTIFY_MAX_ROI)
    no_telegram = _cli_flag('--no-telegram')

    print("🚀 Starting TopTiket Football Analyzer...")
    USE_EXISTING = False
    if USE_EXISTING:
        print("♻️ Reusing existing dom_matches.json / index files.")
    else:
        print("📥 Downloading fresh data from TopTiket...")
        download_fresh_data()

    all_matches = []
    print("📊 Building match list (DOM preferred)...")
    dom_data = []
    if os.path.exists('dom_matches.json'):
        try:
            with open('dom_matches.json', 'r', encoding='utf-8') as jf:
                dom_data = json.load(jf)
            print(f"✅ Loaded DOM matches: {len(dom_data)}")
        except Exception as e:
            print(f"⚠️ Could not load dom_matches.json: {e}")

    if dom_data:
        seen = set()
        for m in dom_data:
            odds = m.get('odds', {})
            key = (m.get('time'), m.get('team1'), m.get('team2'), m.get('range'), tuple(odds.get(k) for k in ['1','X','2','0-2','3+','GG','NG']))
            if key in seen:
                continue
            seen.add(key)
            all_matches.append({
                'teams': f"{m.get('team1')} vs {m.get('team2')}",
                'team1': m.get('team1'),
                'team2': m.get('team2'),
                'time': m.get('time'),
                'page': m.get('page'),
                'range': m.get('range','today'),
                'odds': {'TopTiket': odds}
            })
        print(f"✅ Unique DOM matches retained: {len(all_matches)}")
    else:
        print("⚠️ Falling back to text parsing (DOM empty)")
        dedupe_key_set = set()
        for filename in sorted(glob.glob("index_*.txt")):
            raw_matches = parse_file(filename)
            for m in raw_matches:
                odds_tuple = tuple([m['odds']['TopTiket'].get(k) for k in ['1','X','2','0-2','3+','GG','NG']])
                key = (m['time'], m['team1'], m['team2'], odds_tuple)
                if key not in dedupe_key_set:
                    dedupe_key_set.add(key)
                    all_matches.append(m)
        print(f"✅ Total unique matches (text mode): {len(all_matches)}")

    print("🔍 Searching for true arbitrage (surebets)...")
    surebets = detect_surebets(all_matches)

    with open("football_surebets.txt", "w", encoding="utf-8") as f:
        header = [
            "TOPTIKET FOOTBALL ANALYSIS",
            f"Total unique matches: {len(all_matches)}",
            f"Surebets found: {len(surebets)}",
            ""
        ]
        f.write('\n'.join(header) + '\n')

        if surebets:
            f.write("SUREBETS (Risk-Free Profit)\n")
            f.write("--------------------------------\n")
            grouped = {}
            for sb in surebets:
                m = sb['match']
                ident = (m.get('range','today'), m.get('time'), m.get('teams'))
                grouped.setdefault(ident, []).append(sb)
            def best_roi(group):
                return max(item['roi_pct'] for item in group)
            for ident, group in sorted(grouped.items(), key=lambda kv: best_roi(kv[1]), reverse=True):
                rng, tm, teams = ident
                f.write(f"{tm} [{rng}] {teams}\n")
                for bet in sorted(group, key=lambda x: x['type']):
                    if bet['type'] == '1X2':
                        stakes_str = f"1={bet['stakes']['1']}, X={bet['stakes']['X']}, 2={bet['stakes']['2']}"
                    else:
                        stakes_str = f"U={bet['stakes']['0-2']}, O={bet['stakes']['3+']}"
                    f.write(f"   - {bet['type']}: Margin {bet['margin_pct']}% | ROI {bet['roi_pct']}% | odds[{bet['odds']}] | stakes({stakes_str})\n")
                f.write('\n')
        else:
            f.write("No true surebets (sum(1/odds)<1) detected with single TopTiket feed. Add other bookmakers to find cross-book arbitrage.\n\n")

        if surebets:
            margs = [b['margin_pct'] for b in surebets]
            rois = [b['roi_pct'] for b in surebets]
            f.write('\nSurebet Stats: margin% min={:.2f} max={:.2f} avg={:.2f} | ROI% min={:.2f} max={:.2f} avg={:.2f}\n'.format(min(margs), max(margs), sum(margs)/len(margs), min(rois), max(rois), sum(rois)/len(rois)))

        f.write('\nGenerated via DOM scraping mode.\n')

    print(f"✅ Analysis complete!")
    print(f"📁 Results saved to football_surebets.txt")
    print(f"🎯 Found {len(surebets)} surebets")
    # Filter for notification
    filtered_notify = [sb for sb in surebets if NOTIFY_MIN_ROI <= sb['roi_pct'] <= NOTIFY_MAX_ROI]
    print(f"🔎 Football notify filter: ROI between {NOTIFY_MIN_ROI}% and {NOTIFY_MAX_ROI}% -> {len(filtered_notify)} candidates")
    if no_telegram:
        print('ℹ️ Football Telegram disabled by --no-telegram flag.')
        return
    if not send_surebets_summary:
        print('ℹ️ Telegram notifier unavailable (import failed).')
        return
    if not filtered_notify:
        print('ℹ️ No football surebets within desired ROI range; skipping Telegram send.')
        return
    try:
        send_surebets_summary(filtered_notify, len(all_matches))
        print('📨 Football Telegram summary attempted (filtered).')
    except Exception as e:
        print(f'⚠️ Football Telegram send failed: {e}')

if __name__ == '__main__':
    main()
