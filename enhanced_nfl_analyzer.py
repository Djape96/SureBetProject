import os, re, glob, json, time, argparse, requests
from datetime import datetime

# Reuse bookmaker exclusion logic
EXCLUDED_BOOKMAKERS = {
    '1xbet', 'brazil bet','brazilbet','brazil', '365rs','365.rs', 'vivatbet','vivat bet'
}

DEFAULT_STAKE_MIN = 10000
DEFAULT_STAKE_MAX = 15000
DEFAULT_STAKE_ROUND = 100

# ---------------- Utility ---------------- #

def _norm_book(b: str):
    b = (b or '').lower().strip()
    return b.replace(' ', '').replace('.', '')

def choose_total_stake(min_total, max_total, explicit=None):
    if explicit is not None:
        return explicit
    if max_total < min_total:
        max_total = min_total
    mid = (min_total + max_total) // 2
    mid = int(round(mid / 100) * 100)
    return max(min_total, min(mid, max_total))

# 2-way surebet check

def check_surebet_2way(o1, o2):
    if not (0.5 <= o1 <= 69 and 0.5 <= o2 <= 69):
        return None
    inv = 1/o1 + 1/o2
    if inv < 1:
        return round((1 - inv) * 100, 2)
    return None

# Stake allocation for 2-way market (similar to football version simplified)

def compute_stakes_two_way(odds_tuple, total_stake, round_multiple):
    # odds_tuple = [(odd, book),(odd, book)]
    clean = [(o,b) for o,b in odds_tuple if o > 0]
    if len(clean) != 2:
        return [], 0, 0, 0, 0, 0
    o1, b1 = clean[0]
    o2, b2 = clean[1]
    inv_sum = 1/o1 + 1/o2
    if inv_sum >= 1:
        return [], 0, 0, 0, 0, 0
    if round_multiple < 1:
        round_multiple = 1
    # theoretical stakes
    s1_exact = total_stake * (1/o1) / inv_sum
    s2_exact = total_stake * (1/o2) / inv_sum
    # floor
    s1 = int(s1_exact // round_multiple * round_multiple)
    s2 = int(s2_exact // round_multiple * round_multiple)
    if s1 <= 0: s1 = round_multiple
    if s2 <= 0: s2 = round_multiple
    eff_total = s1 + s2
    diff = total_stake - eff_total
    def returns():
        return [s1*o1, s2*o2]
    while diff >= round_multiple:
        # give extra unit to outcome with lower return
        r = returns()
        if r[0] <= r[1]:
            s1 += round_multiple
        else:
            s2 += round_multiple
        eff_total = s1 + s2
        diff = total_stake - eff_total
    r_final = returns()
    min_ret = min(r_final)
    profit_abs_actual = min_ret - eff_total
    if profit_abs_actual <= 0:
        theoretical_return = total_stake / inv_sum
        theo_abs = theoretical_return - total_stake
        theo_pct = (1/inv_sum - 1) * 100
        return [], eff_total, 0, 0, round(theo_abs,2), round(theo_pct,2)
    profit_pct_actual = round((profit_abs_actual / eff_total) * 100, 2)
    theoretical_return = total_stake / inv_sum
    theo_abs = round(theoretical_return - total_stake, 2)
    theo_pct = round((1/inv_sum - 1) * 100, 2)
    return [(s1, o1, b1), (s2, o2, b2)], round(profit_abs_actual,2), eff_total, profit_pct_actual, theo_abs, theo_pct

# ---------------- Fetching ---------------- #

NFL_URL = "https://toptiket.rs/odds/NFL"

def download_nfl_html(use_selenium=True, headless=True, selenium_wait=10, retries=1, verbose=False, debug_dom=False, three_days=False):
    """Capture NFL odds page.

    Strategy:
      1. Try plain requests (may return shell only; still saved for inspection).
      2. Selenium: load page, accept cookies, click timeframe stepper buttons (1h,12h,1 dan, etc.) to force data load,
         scroll to bottom to trigger lazy loading. Save final HTML to nfl_live_data.txt . If debug_dom=True, also save
         intermediate snapshots (nfl_live_data_stepX.html) after each interaction for troubleshooting.
    """
    try:
        if verbose:
            print("🌐 NFL: simple HTTP request")
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(NFL_URL, headers=headers, timeout=10)
        if resp.status_code == 200 and len(resp.text) > 1200:
            with open('nfl_live_data.txt','w',encoding='utf-8') as f:
                f.write(resp.text)
            if verbose:
                print("✅ NFL basic request saved")
            return True
    except Exception as e:
        if verbose:
            print(f"⚠️ NFL basic request failed: {e}")
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
        if verbose:
            print("❌ Selenium not installed for NFL capture")
        return False
    attempt = 0
    while attempt <= retries:
        attempt += 1
        if verbose:
            print(f"🏈 NFL Selenium attempt {attempt}/{retries+1}")
        try:
            opts = Options()
            if headless:
                opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--window-size=1600,900')
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            try:
                driver.get(NFL_URL)
                WebDriverWait(driver, selenium_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                time.sleep(1.5)

                # Accept cookie consent if present
                try:
                    btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, '.cookie-consent-container .accept-button')))
                    btn.click()
                    if verbose:
                        print('🍪 Accepted cookie banner')
                    time.sleep(0.5)
                except Exception:
                    if verbose:
                        print('ℹ️ Cookie banner not found / already accepted')

                # Optionally click 3-day filter similar to football analyzer before iterating icons
                if three_days:
                    clicked = False
                    if verbose:
                        print("🗓️ Attempting to activate 3-day range filter…")
                    try_candidates = [
                        (By.XPATH, "//button[contains(.,'3 dana') or contains(.,'3 Dana') or contains(.,'3 DANA')][not(@disabled)]"),
                        (By.XPATH, "//*[contains(@class,'day') and (contains(.,'3 dana') or contains(.,'3 Dana'))]"),
                        (By.XPATH, "//*[self::span or self::div or self::button][normalize-space()='3 dana']"),
                    ]
                    for by, sel in try_candidates:
                        try:
                            el = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((by, sel)))
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
                    if clicked and verbose:
                        print("✅ 3-day filter clicked")
                    elif verbose:
                        print("⚠️ Could not find '3 dana' control (NFL page may not offer it)")

                # Click each stepper icon to prompt data load (these correspond to timeframe filters)
                # They have attribute icon="1", "2", ... inside svg elements used in the stepper
                step_icons = []
                try:
                    step_icons = driver.find_elements(By.CSS_SELECTOR, '.MuiStepLabel-iconContainer svg[icon]')
                except Exception:
                    step_icons = []
                for idx, icon in enumerate(step_icons):
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", icon)
                        icon.click()
                        if verbose:
                            print(f'🕒 Clicked timeframe step {icon.get_attribute("icon")}')
                        time.sleep(0.8)
                        if debug_dom:
                            snap = driver.page_source
                            with open(f'nfl_live_data_step{idx+1}.html','w',encoding='utf-8') as f:
                                f.write(snap)
                    except Exception:
                        pass

                # Scroll to bottom to trigger potential lazy loading
                try:
                    last_height = driver.execute_script('return document.body.scrollHeight')
                    for _ in range(3):
                        driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                        time.sleep(1)
                        new_height = driver.execute_script('return document.body.scrollHeight')
                        if new_height == last_height:
                            break
                        last_height = new_height
                except Exception:
                    pass

                # Final wait for dynamic content
                time.sleep(1.2)
                html = driver.page_source
                # Save primary capture
                with open('nfl_live_data.txt','w',encoding='utf-8') as f:
                    f.write(html)
                if verbose:
                    print(f'✅ NFL Selenium capture saved (size {len(html)} chars)')
                if debug_dom:
                    with open('nfl_live_data_final.html','w',encoding='utf-8') as f:
                        f.write(html)
                # success even if still shell; downstream parser will decide
                return True
            finally:
                driver.quit()
        except Exception as e:
            if verbose:
                print(f"⚠️ NFL Selenium error: {e}")
            time.sleep(1.5)
    return False

# ---------------- Parsing ---------------- #

from bs4 import BeautifulSoup

def extract_text_nfl(html_path='nfl_live_data.txt', verbose=False):
    if not os.path.exists(html_path):
        return None
    with open(html_path,'r',encoding='utf-8',errors='ignore') as f:
        html = f.read()
    soup = BeautifulSoup(html,'html.parser')
    text = soup.get_text('\n', strip=True)
    with open('nfl_extracted.txt','w',encoding='utf-8') as f:
        f.write(text)
    if verbose:
        print('📄 NFL text extracted -> nfl_extracted.txt')
    return 'nfl_extracted.txt'

def parse_nfl_dom(html_path='nfl_live_data.txt', verbose=False, debug=False):
    """Attempt to parse the dynamic HTML directly for NFL matches.

    The provided captured HTML (shell) shows zero matches (counter 'Mečevi 0'). When matches exist, we expect additional
    containers. Since we don't yet know exact class names for match rows (React/MUI generated), we employ heuristics:
      - Find elements whose text contains 'vs' OR two team name tokens separated by line breaks inside a small container.
      - For each candidate, search sibling/descendant spans/divs with numeric odds patterns (\d+(\.\d+)?), capture first two.

    This is a best‑effort parser; if no matches found it returns empty list. With --debug-dom we emit a lightweight log file
    listing candidate blocks and extracted odds to aid refinement once real match HTML is captured.
    """
    if not os.path.exists(html_path):
        return []
    with open(html_path,'r',encoding='utf-8',errors='ignore') as f:
        html = f.read()
    soup = BeautifulSoup(html,'html.parser')
    # Heuristic: collect blocks with at least 2 team name like spans (capitalized words) and some odds numbers nearby
    candidates = []
    text_blocks = soup.find_all(['div','section','li'])
    team_name_re = re.compile(r'^[A-Z][A-Za-z0-9 .\-]{2,}$')
    odd_re = re.compile(r'^(\d{1,2}(?:\.\d{1,2})?)$')
    results = []
    for blk in text_blocks:
        # skip very large containers to reduce noise
        txt = blk.get_text(separator='\n', strip=True)
        if not txt or len(txt) > 400:
            continue
        lines = [l for l in (s.strip() for s in txt.split('\n')) if l]
        # Need at least two candidate team lines and two numeric odds lines
        team_lines = [l for l in lines if team_name_re.match(l) and ' ' in l and len(l) < 40]
        if len(team_lines) < 2:
            continue
        odds_lines = [l for l in lines if odd_re.match(l)]
        if len(odds_lines) < 2:
            continue
        # Use first two team lines and first two odds
        team1, team2 = team_lines[0], team_lines[1]
        try:
            o1 = float(odds_lines[0]); o2 = float(odds_lines[1])
        except ValueError:
            continue
        if not (0.5 <= o1 <= 69 and 0.5 <= o2 <= 69):
            continue
        results.append({'teams': f"{team1} vs {team2}", 'odds': {'Home': (o1, 'AUTO'), 'Away': (o2, 'AUTO')}})
        if len(results) > 150:  # safety cap
            break
    if verbose:
        print(f"🧪 DOM heuristic parser produced {len(results)} tentative NFL matches")
    if debug:
        try:
            with open('nfl_dom_debug.txt','w',encoding='utf-8') as df:
                df.write(f"DOM heuristic parsed {len(results)} matches\n")
                for r in results:
                    df.write(json.dumps(r, ensure_ascii=False)+"\n")
        except Exception:
            pass
    return results

TEAM_LINE_RE = re.compile(r'^[A-Za-z].{1,60}$')
TIME_RE = re.compile(r':\d{2}$')
WEEKDAY_RE = re.compile(r'^(pon|uto|sre|čet|pet|sub|ned),', re.IGNORECASE)

# We only care about main 1/2 market (equivalent to Home/Away). We'll map first two odds lines after detecting two team lines.

def parse_nfl_text(txt_path, verbose=False):
    if not os.path.exists(txt_path):
        return []
    with open(txt_path,'r',encoding='utf-8',errors='ignore') as f:
        lines = [l.strip() for l in f if l.strip()]
    matches = []
    i = 0
    n = len(lines)
    while i < n:
        # Look for a weekday then a time then two team lines similar to football pattern
        if WEEKDAY_RE.search(lines[i]) and i+3 < n and TIME_RE.search(lines[i+1]):
            team1 = lines[i+2]
            team2 = lines[i+3]
            if TEAM_LINE_RE.match(team1) and TEAM_LINE_RE.match(team2):
                # Advance pointer to odds lines after teams
                j = i + 4
                odds = []
                # capture up to, say, 6 subsequent numeric/bookmaker lines until next weekday/time or plus code
                while j < n and len(odds) < 2:
                    l = lines[j]
                    if WEEKDAY_RE.search(l) and j+1 < n and TIME_RE.search(lines[j+1]):
                        break
                    if l.startswith('+'):
                        j += 1
                        break
                    m = re.match(r'^(\d+(?:\.\d+)?)([A-Za-z].*)$', l)
                    if m:
                        try:
                            odd = float(m.group(1))
                            book = m.group(2).strip()
                            if 0.5 <= odd <= 69:
                                odds.append((odd, book))
                        except ValueError:
                            pass
                    else:
                        # pure numeric fallback (assign AUTO placeholder)
                        if re.match(r'^\d+(?:\.\d+)?$', l):
                            try:
                                odd = float(l)
                                if 0.5 <= odd <= 69:
                                    odds.append((odd, 'AUTO'))
                            except ValueError:
                                pass
                    j += 1
                if len(odds) == 2:
                    matches.append({
                        'teams': f"{team1} vs {team2}",
                        'odds': {'Home': odds[0], 'Away': odds[1]}
                    })
                    if verbose:
                        print(f"[nfl] {team1} vs {team2} -> Home={odds[0][0]}@{odds[0][1]}, Away={odds[1][0]}@{odds[1][1]}")
                i = j
                continue
        i += 1
    if verbose:
        print(f"[nfl] Parsed {len(matches)} matches")
    return matches

# ---------------- Surebet Analysis ---------------- #

def analyze_nfl_surebets(matches, min_profit=0.0, stake_min=None, stake_max=None, stake_total=None, stake_round=DEFAULT_STAKE_ROUND, verbose=False):
    results = []
    excluded_norm = {_norm_book(b) for b in EXCLUDED_BOOKMAKERS}
    total_target = choose_total_stake(stake_min or DEFAULT_STAKE_MIN, stake_max or DEFAULT_STAKE_MAX, explicit=stake_total)
    for m in matches:
        if 'Home' not in m['odds'] or 'Away' not in m['odds']:
            continue
        home = m['odds']['Home']
        away = m['odds']['Away']
        profit = check_surebet_2way(home[0], away[0])
        if profit is None or profit < min_profit or profit <= 0:
            continue
        stakes, abs_actual, eff_total, pct_actual, theo_abs, theo_pct = compute_stakes_two_way([home, away], total_target, stake_round)
        if not stakes:
            if verbose:
                print(f"ℹ️ Rounding removed NFL edge for {m['teams']} (theo {profit}%)")
            continue
        if pct_actual < min_profit:
            continue
        has_online = any(_norm_book(bk) in excluded_norm for _,_,bk in stakes)
        results.append({
            'match': m['teams'],
            'type': '1/2',
            'profit': profit,
            'profit_theoretical': theo_pct,
            'profit_actual': pct_actual,
            'abs_profit': abs_actual,
            'abs_profit_theoretical': theo_abs,
            'odds': {'Home': home, 'Away': away},
            'stakes': stakes,
            'total_stake': eff_total,
            'category': 'online' if has_online else 'local'
        })
    return results

# ---------------- Output ---------------- #

def save_nfl_results(matches, surebets):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    matches_file = f"nfl_matches_{ts}.txt"
    with open(matches_file,'w',encoding='utf-8') as f:
        f.write(f"NFL Matches - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write('='*60 + '\n\n')
        for m in matches:
            f.write(m['teams']+'\n')
            for label,(odd,book) in m['odds'].items():
                shown = book if book and book != 'AUTO' else ''
                if shown:
                    f.write(f"  {label}: {odd} @ {shown}\n")
                else:
                    f.write(f"  {label}: {odd}\n")
            f.write('\n')
    surebets_file = f"nfl_surebets_{ts}.txt"
    with open(surebets_file,'w',encoding='utf-8') as f:
        f.write(f"NFL Surebets - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write('='*60 + '\n\n')
        if not surebets:
            f.write('No surebets found.\n')
        else:
            local = [s for s in surebets if s.get('category','local')=='local']
            online = [s for s in surebets if s.get('category')=='online']
            def write_group(title, group):
                f.write(title+'\n')
                f.write('-'*len(title)+'\n')
                if not group:
                    f.write('  (none)\n\n')
                    return
                for s in group:
                    f.write(s['match']+'\n')
                    f.write(f"  ✅ {s['type']} SUREBET → Profit: {s['profit']}% (cat={s.get('category')})\n")
                    def _fmt(b):
                        return b if b and b != 'AUTO' else ''
                    odds_text = ", ".join(f"{k}={v[0]:.2f}{('@'+_fmt(v[1])) if _fmt(v[1]) else ''}" for k,v in s['odds'].items())
                    f.write(f"  Odds: {odds_text}\n\n")
            write_group('LOCAL SUREBETS', local)
            write_group('ONLINE SUREBETS', online)
    return matches_file, surebets_file

# ---------------- Main ---------------- #

def main():
    parser = argparse.ArgumentParser(description='Enhanced NFL Odds Analyzer (1/2 markets only)')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--no-selenium', action='store_true')
    parser.add_argument('--min-profit', type=float, default=1.5)
    parser.add_argument('--stake-min-total', type=int, default=DEFAULT_STAKE_MIN)
    parser.add_argument('--stake-max-total', type=int, default=DEFAULT_STAKE_MAX)
    parser.add_argument('--stake-total', type=int, default=None)
    parser.add_argument('--stake-round', type=int, default=DEFAULT_STAKE_ROUND)
    parser.add_argument('--selenium-wait', type=int, default=10, help='Max seconds to wait for initial body load')
    parser.add_argument('--no-headless', action='store_true', help='Run Selenium with visible browser')
    parser.add_argument('--debug-dom', action='store_true', help='Save intermediate DOM snapshots and dom debug file')
    parser.add_argument('--three-days', action='store_true', help='Activate 3-day filter (tries to click "3 dana")')
    args = parser.parse_args()

    verbose = args.verbose
    print('🚀 Starting Enhanced NFL Odds Analyzer (1/2 only)')
    if verbose:
        print('🔧 Verbose mode enabled')

    # Capture / reuse logic (simple: always refresh now)
    got = download_nfl_html(use_selenium=not args.no_selenium, headless=not args.no_headless, selenium_wait=args.selenium_wait, verbose=verbose, debug_dom=args.debug_dom, three_days=args.three_days)
    if not got:
        print('❌ Failed to capture NFL odds page.')
        return
    txt = extract_text_nfl(verbose=verbose)
    if not txt:
        print('❌ Failed to extract text from NFL HTML')
        return
    matches = parse_nfl_text(txt, verbose=verbose)
    if not matches:
        if verbose:
            print('🔁 Text parsing produced 0 matches, attempting DOM heuristic...')
        matches = parse_nfl_dom(verbose=verbose, debug=args.debug_dom)
    print(f'📊 Parsed {len(matches)} NFL matches with 1/2 odds (text+DOM)')

    surebets = analyze_nfl_surebets(matches, min_profit=args.min_profit, stake_min=args.stake_min_total, stake_max=args.stake_max_total, stake_total=args.stake_total, stake_round=args.stake_round, verbose=verbose)
    local_count = sum(1 for s in surebets if s.get('category')=='local')
    online_count = sum(1 for s in surebets if s.get('category')=='online')
    print(f'💰 Found {len(surebets)} NFL surebets (local={local_count}, online={online_count}, min-profit {args.min_profit}%)')
    if not matches:
        print('ℹ️ Still zero NFL matches. Likely the site loads data via XHR after interactions we have not captured yet. Try increasing --selenium-wait, running with --no-headless to observe, or inspect saved nfl_live_data.txt and *_step*.html when using --debug-dom.')

    mfile, sfile = save_nfl_results(matches, surebets)
    print(f'✅ Saved results -> {mfile}, {sfile}')

    if surebets:
        print('\n🎉 NFL SUREBET SUMMARY:')
        ordered = [s for s in surebets if s.get('category')=='local'] + [s for s in surebets if s.get('category')=='online']
        for s in ordered[:10]:
            display_pct = f"{s.get('profit_actual', s['profit'])}% actual (theo {s.get('profit_theoretical', s['profit'])}%)" if 'profit_actual' in s else f"{s['profit']}%"
            print(f"  • [{s.get('category','local').upper()}] {s['match']} - {display_pct}")
            odds_str = ' | '.join(f"{k}: {v[0]:.2f}{(' @ '+v[1]) if (v[1] and v[1] != 'AUTO') else ''}" for k,v in s['odds'].items())
            print('    📊', odds_str)
            stake_parts = []
            for amt, odd, book in s['stakes']:
                if not book or book == 'AUTO':
                    stake_parts.append(f"{amt} RSD on {odd}")
                else:
                    stake_parts.append(f"{amt} RSD on {odd}@{book}")
            print('    💼 Stakes:', ', '.join(stake_parts), f"(Total {s['total_stake']} RSD, Profit ≈ {s.get('abs_profit')} RSD (theo {s.get('abs_profit_theoretical')} RSD))")
    else:
        print('📊 No NFL surebet opportunities found.')

if __name__ == '__main__':
    main()
