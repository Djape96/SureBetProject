import argparse, os, re, time, json, requests
from datetime import datetime
from bs4 import BeautifulSoup

HOCKEY_URL = "https://toptiket.rs/odds/hockey"

EXCLUDED_BOOKMAKERS = {
    '1xbet','brazil bet','brazilbet','brazil','365rs','365.rs','vivatbet','vivat bet'
}

DEFAULT_STAKE_MIN = 10000
DEFAULT_STAKE_MAX = 15000
DEFAULT_STAKE_ROUND = 100

MARKETS_PRIMARY = ['1','X','2','Under','Over']  # we only care about 1/X/2 and Totals (manje/više)

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

def check_surebet_generic(odds):
    clean = [o for o,_ in odds if 0.5 <= o <= 150]
    if len(clean) < 2: return None
    inv = sum(1/o for o in clean)
    if inv < 1:
        return round((1-inv)*100,2)
    return None

def compute_stakes(odds_list, total_stake, round_multiple):
    valid = [(o,b) for o,b in odds_list if o>0]
    if len(valid) < 2:
        return [],0,0,0,0,0
    inv_sum = sum(1/o for o,_ in valid)
    if inv_sum >= 1:
        return [],0,0,0,0,0
    if round_multiple < 1: round_multiple = 1
    unrounded = []
    for o,b in valid:
        stake = total_stake * (1/o) / inv_sum
        unrounded.append([stake,o,b])
    theoretical_return = total_stake / inv_sum
    theoretical_profit_abs = theoretical_return - total_stake
    theoretical_profit_pct = (1/inv_sum - 1) * 100
    rounded = []
    for stake,o,b in unrounded:
        floored = int(stake // round_multiple * round_multiple)
        if floored <= 0: floored = round_multiple
        rounded.append([floored,o,b])
    effective_total = sum(r[0] for r in rounded)
    diff = total_stake - effective_total
    def returns(): return [r[0]*r[1] for r in rounded]
    while diff >= round_multiple:
        rounded.sort(key=lambda x: x[0]*x[1])
        rounded[0][0] += round_multiple
        diff -= round_multiple
    effective_total = sum(r[0] for r in rounded)
    returns_final = returns()
    min_ret = min(returns_final)
    profit_abs_actual = min_ret - effective_total
    if profit_abs_actual <= 0:
        return [], effective_total, 0, 0, round(theoretical_profit_abs,2), round(theoretical_profit_pct,2)
    profit_pct_actual = round((profit_abs_actual / effective_total)*100,2)
    return [(r[0], r[1], r[2]) for r in rounded], round(profit_abs_actual,2), effective_total, profit_pct_actual, round(theoretical_profit_abs,2), round(theoretical_profit_pct,2)

def download_hockey_html(use_selenium=True, headless=True, selenium_wait=10, retries=1, verbose=False, debug_dom=False, three_days=False):
    try:
        if verbose: print("🌐 Hockey: simple HTTP request")
        resp = requests.get(HOCKEY_URL, headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
        if resp.status_code == 200 and len(resp.text) > 1500:
            with open('hockey_live_data.txt','w',encoding='utf-8') as f: f.write(resp.text)
            if verbose: print('✅ Hockey basic request saved')
            return True
    except Exception as e:
        if verbose: print('⚠️ Hockey basic request failed', e)
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
        if verbose: print('❌ Selenium not installed for Hockey')
        return False
    attempt=0
    while attempt <= retries:
        attempt +=1
        if verbose: print(f"🏒 Hockey Selenium attempt {attempt}/{retries+1}")
        try:
            opts = Options()
            if headless: opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox'); opts.add_argument('--disable-dev-shm-usage'); opts.add_argument('--window-size=1600,900')
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            try:
                driver.get(HOCKEY_URL)
                WebDriverWait(driver, selenium_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                time.sleep(1)
                # cookies
                try:
                    btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR,'.cookie-consent-container .accept-button')))
                    btn.click(); time.sleep(0.4)
                    if verbose: print('🍪 Hockey cookies accepted')
                except Exception:
                    if verbose: print('ℹ️ Hockey cookie banner not present')
                # 3 day filter
                if three_days:
                    clicked=False
                    if verbose: print('🗓️ Trying 3-day filter (Hockey)')
                    paths=[
                        (By.XPATH,"//button[contains(.,'3 dana') or contains(.,'3 Dana') or contains(.,'3 DANA')][not(@disabled)]"),
                        (By.XPATH,"//*[contains(@class,'day') and (contains(.,'3 dana') or contains(.,'3 Dana'))]"),
                        (By.XPATH,"//*[self::span or self::div or self::button][normalize-space()='3 dana']")
                    ]
                    for by,sel in paths:
                        try:
                            el = WebDriverWait(driver,3).until(EC.element_to_be_clickable((by,sel)))
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                            time.sleep(0.2)
                            try: el.click()
                            except Exception: driver.execute_script("arguments[0].click();", el)
                            clicked=True; break
                        except Exception: continue
                    if not clicked:
                        try:
                            js_clicked = driver.execute_script("const els=[...document.querySelectorAll('*')]; const t=els.find(e=>e.innerText && e.innerText.trim().toLowerCase()==='3 dana'); if(t){t.scrollIntoView({block:'center'}); t.click(); return true;} return false;")
                            if js_clicked: clicked=True
                        except Exception: pass
                    if verbose:
                        print('✅ 3-day filter clicked (Hockey)' if clicked else "⚠️ '3 dana' control not found (Hockey)")
                    time.sleep(1)
                # scroll
                for _ in range(3):
                    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);'); time.sleep(1)
                # final
                html = driver.page_source
                with open('hockey_live_data.txt','w',encoding='utf-8') as f: f.write(html)
                if verbose: print(f'✅ Hockey Selenium capture saved ({len(html)} chars)')
                if debug_dom:
                    with open('hockey_live_data_final.html','w',encoding='utf-8') as f: f.write(html)
                return True
            finally:
                driver.quit()
        except Exception as e:
            if verbose: print('⚠️ Hockey Selenium error', e)
            time.sleep(1.2)
    return False

def extract_hockey_text(html_path='hockey_live_data.txt', verbose=False):
    if not os.path.exists(html_path): return None
    with open(html_path,'r',encoding='utf-8',errors='ignore') as f: html=f.read()
    soup = BeautifulSoup(html,'html.parser')
    text = soup.get_text('\n', strip=True)
    with open('hockey_extracted.txt','w',encoding='utf-8') as f: f.write(text)
    if verbose: print('📄 Hockey text extracted -> hockey_extracted.txt')
    return 'hockey_extracted.txt'

TIME_RE = re.compile(r':\d{2}$')
# Odds are positive numbers; spreads / totals thresholds can be negative or small numbers. We'll differentiate.
ODD_NUM_RE = re.compile(r'^\d+(?:\.\d+)?$')
SPREAD_NUM_RE = re.compile(r'^[+-]?\d+(?:\.\d+)?$')

def parse_hockey_text(path, verbose=False):
    """Parse flattened text for hockey capturing ONLY 1, X, 2 odds.
    Original site sequence: 1, X, 2, H1, spread, H2, Under, spread, Over.
    We now intentionally ignore handicap (H1/H2) and totals (Under/Over) blocks.
    """
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f if l.strip()]
    matches = []
    i = 0
    n = len(lines)
    while i < n:
        if TIME_RE.search(lines[i]) and i + 2 < n:
            team1 = lines[i + 1]
            team2 = lines[i + 2]
            i += 3
            odds_map = {}
            # Capture sequentially the first 3 valid odds as 1, X, 2
            while i < n and len([k for k in odds_map if k in ('1', 'X', '2')]) < 3:
                l = lines[i]
                if l.startswith('+') or TIME_RE.search(l):
                    break
                if ODD_NUM_RE.match(l):
                    try:
                        val = float(l)
                        if 1.01 <= val <= 150:
                            if '1' not in odds_map:
                                odds_map['1'] = (val, 'AUTO')
                                if verbose:
                                    print(f"[hockey-text] {team1} vs {team2} 1={val}")
                            elif 'X' not in odds_map:
                                odds_map['X'] = (val, 'AUTO')
                                if verbose:
                                    print(f"[hockey-text] {team1} vs {team2} X={val}")
                            elif '2' not in odds_map:
                                odds_map['2'] = (val, 'AUTO')
                                if verbose:
                                    print(f"[hockey-text] {team1} vs {team2} 2={val}")
                    except:
                        pass
                i += 1
            matches.append({'teams': f"{team1} vs {team2}", 'odds': odds_map})
        else:
            i += 1
    if verbose:
        print(f"[hockey-text] Parsed {len(matches)} matches")
    return matches

def parse_hockey_dom(html_path='hockey_live_data.txt', verbose=False, debug=False):
    if not os.path.exists(html_path):
        return []
    with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    cand_nodes = soup.find_all(['div', 'section', 'li'])
    team_re = re.compile(r'^[A-Z].{2,40}$')
    odd_re = re.compile(r'^\d{1,2}(?:\.\d{1,2})?$')
    for node in cand_nodes:
        txt = node.get_text('\n', strip=True)
        if not txt or len(txt) > 360:
            continue
        lines = [l for l in txt.split('\n') if l]
        teams = [l for l in lines if team_re.match(l) and ' ' in l]
        odds_lines = [l for l in lines if odd_re.match(l)]
        if len(teams) < 2 or len(odds_lines) < 3:
            continue
        t1, t2 = teams[0], teams[1]
        # Identify first three odds >1 as 1/X/2
        one_x_two = []
        for val in odds_lines:
            try:
                fv = float(val)
                if 1.01 <= fv <= 150:
                    one_x_two.append(fv)
                    if len(one_x_two) == 3:
                        break
            except:
                pass
        if not one_x_two:
            continue
        odds_map = {'1': (one_x_two[0], 'AUTO')}
        if len(one_x_two) > 1:
            odds_map['X'] = (one_x_two[1], 'AUTO')
        if len(one_x_two) > 2:
            odds_map['2'] = (one_x_two[2], 'AUTO')
        results.append({'teams': f"{t1} vs {t2}", 'odds': odds_map})
        if len(results) > 120:
            break
    if verbose:
        print(f"[hockey-dom] Heuristic produced {len(results)} matches")
    if debug:
        try:
            with open('hockey_dom_debug.txt', 'w', encoding='utf-8') as f:
                for r in results:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        except:
            pass
    return results

def analyze_hockey_surebets(matches, min_profit=1.0, stake_min=None, stake_max=None, stake_total=None, stake_round=DEFAULT_STAKE_ROUND, verbose=False):
    excluded_norm = {_norm_book(b) for b in EXCLUDED_BOOKMAKERS}
    total_target = choose_total_stake(stake_min or DEFAULT_STAKE_MIN, stake_max or DEFAULT_STAKE_MAX, explicit=stake_total)
    results=[]
    for m in matches:
        odds_map = m['odds']
        # 1X2
        trio = [(odds_map[k][0], odds_map[k][1]) for k in ['1','X','2'] if k in odds_map]
        if len(trio)==3:
            profit = check_surebet_generic(trio)
            if profit and profit>0 and profit >= min_profit:
                stakes, abs_actual, eff_total, pct_actual, theo_abs, theo_pct = compute_stakes(trio, total_target, stake_round)
                if stakes and pct_actual >= min_profit:
                    has_online = any(_norm_book(bk) in excluded_norm for _,_,bk in stakes)
                    results.append({'match':m['teams'],'type':'1X2','profit':profit,'profit_actual':pct_actual,'profit_theoretical':theo_pct,'abs_profit':abs_actual,'abs_profit_theoretical':theo_abs,'odds':{k:odds_map[k] for k in ['1','X','2']},'stakes':stakes,'total_stake':eff_total,'category':'online' if has_online else 'local'})
    return results

def save_hockey_results(matches, surebets):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    mfile = f"hockey_matches_{ts}.txt"
    with open(mfile,'w',encoding='utf-8') as f:
        f.write(f"Hockey Matches - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write('='*60+'\n\n')
        for m in matches:
            f.write(m['teams']+'\n')
            for k,(o,b) in m['odds'].items():
                show = b if b and b!='AUTO' else ''
                if show:
                    f.write(f"  {k}: {o} @ {show}\n")
                else:
                    f.write(f"  {k}: {o}\n")
            f.write('\n')
    sfile = f"hockey_surebets_{ts}.txt"
    with open(sfile,'w',encoding='utf-8') as f:
        f.write(f"Hockey Surebets - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write('='*60+'\n\n')
        if not surebets:
            f.write('No surebets found.\n')
        else:
            local=[s for s in surebets if s.get('category')=='local']
            online=[s for s in surebets if s.get('category')=='online']
            def write_grp(title, grp):
                f.write(title+'\n'); f.write('-'*len(title)+'\n')
                if not grp: f.write('  (none)\n\n'); return
                for s in grp:
                    f.write(s['match']+'\n')
                    f.write(f"  ✅ {s['type']} SUREBET → Profit: {s['profit']}% (cat={s['category']})\n")
                    odds_line = ', '.join(f"{k}={v[0]:.2f}{('@'+v[1]) if (v[1] and v[1] != 'AUTO') else ''}" for k,v in s['odds'].items())
                    f.write(f"  Odds: {odds_line}\n\n")
            write_grp('LOCAL SUREBETS', local)
            write_grp('ONLINE SUREBETS', online)
    return mfile, sfile

def main():
    p = argparse.ArgumentParser(description='Enhanced Hockey Analyzer (1/X/2 only)')
    p.add_argument('--verbose', action='store_true')
    p.add_argument('--no-selenium', action='store_true')
    p.add_argument('--min-profit', type=float, default=1.5)
    p.add_argument('--stake-min-total', type=int, default=DEFAULT_STAKE_MIN)
    p.add_argument('--stake-max-total', type=int, default=DEFAULT_STAKE_MAX)
    p.add_argument('--stake-total', type=int, default=None)
    p.add_argument('--stake-round', type=int, default=DEFAULT_STAKE_ROUND)
    p.add_argument('--selenium-wait', type=int, default=12)
    p.add_argument('--no-headless', action='store_true')
    p.add_argument('--debug-dom', action='store_true')
    p.add_argument('--three-days', action='store_true')
    args = p.parse_args()

    verbose = args.verbose
    print('🚀 Starting Enhanced Hockey Analyzer (1/X/2 only)')
    if verbose: print('🔧 Verbose mode enabled')
    got = download_hockey_html(use_selenium=not args.no_selenium, headless=not args.no_headless, selenium_wait=args.selenium_wait, verbose=verbose, debug_dom=args.debug_dom, three_days=args.three_days)
    if not got:
        print('❌ Failed to capture hockey odds page.'); return
    txt_path = extract_hockey_text(verbose=verbose)
    matches = parse_hockey_text(txt_path, verbose=verbose)
    if not matches:
        if verbose: print('🔁 Text parsing produced 0 matches; trying DOM heuristic...')
        matches = parse_hockey_dom(verbose=verbose, debug=args.debug_dom)
    print(f'📊 Parsed {len(matches)} hockey matches (text+DOM)')
    surebets = analyze_hockey_surebets(matches, min_profit=args.min_profit, stake_min=args.stake_min_total, stake_max=args.stake_max_total, stake_total=args.stake_total, stake_round=args.stake_round, verbose=verbose)
    local_count = sum(1 for s in surebets if s.get('category')=='local')
    online_count = sum(1 for s in surebets if s.get('category')=='online')
    print(f'💰 Found {len(surebets)} hockey surebets (local={local_count}, online={online_count}, min-profit {args.min_profit}%)')
    mfile, sfile = save_hockey_results(matches, surebets)
    print(f'✅ Saved results -> {mfile}, {sfile}')
    if not matches:
        print('ℹ️ Still zero matches. Increase --selenium-wait, use --no-headless, or inspect hockey_live_data.txt.')
    if surebets:
        print('\n🎯 HOCKEY SUREBET SUMMARY:')
        ordered = [s for s in surebets if s.get('category')=='local'] + [s for s in surebets if s.get('category')=='online']
        for s in ordered[:12]:
            disp = f"{s.get('profit_actual', s['profit'])}% actual (theo {s.get('profit_theoretical', s['profit'])}%)"
            print(f"  • [{s['category'].upper()}] {s['match']} - {disp}")
            odds_str = ' | '.join(f"{k}:{v[0]:.2f}{(' @ '+v[1]) if (v[1] and v[1] != 'AUTO') else ''}" for k,v in s['odds'].items())
            print('    📊', odds_str)
            stake_parts = []
            for amt,odd,book in s['stakes']:
                stake_parts.append(f"{amt} RSD on {odd}{('@'+book) if (book and book!='AUTO') else ''}")
            print('    💼 Stakes:', ', '.join(stake_parts), f"(Total {s['total_stake']} RSD, Profit ≈ {s.get('abs_profit')} RSD (theo {s.get('abs_profit_theoretical')} RSD))")
    else:
        print('📊 No hockey surebet opportunities found.')

if __name__ == '__main__':
    main()
