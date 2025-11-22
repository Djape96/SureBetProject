import argparse, os, re, time, sys
from datetime import datetime
import requests
from typing import List, Dict, Any
try:
    from telegram_notifier import send_long_message
except Exception:
    send_long_message = None  # graceful fallback

DEFAULT_TOTAL_STAKE = 100
BASKETBALL_URL = "https://toptiket.rs/odds/basketball"

# Market order provided: 1,2,H1,spread,H2,manje (Under), spread, vise (Over)
MARKET_SEQ = ['1','2','H1','Handicap','H2','Under','Handicap2','Over']

# ----------------- Generic Utility -----------------

def compute_stakes(odds):
    valid = [(o,b) for o,b in odds if o>0]
    if len(valid) < 2: return []
    inv = sum(1/o for o,_ in valid)
    if inv >= 1: return []
    stakes=[]
    for o,b in valid:
        stake=(DEFAULT_TOTAL_STAKE*(1/o))/inv
        stakes.append((round(stake,2), o, b))
    profit = round(stakes[0][0]*odds[0][0]-DEFAULT_TOTAL_STAKE,2) if stakes else 0
    return stakes, profit

def check_surebet(odds):
    clean=[o for o,_ in odds if 1.01<=o<=200]
    if len(clean)<2: return None
    inv=sum(1/o for o in clean)
    if inv<1: return round((1-inv)*100,2)
    return None

# ----------------- Live Download -----------------

def download_live_basketball(headless=True, retries=2, selenium_wait=8, scroll_steps=4, pages=1, verbose=False, three_days=False, all_pages=False, requests_only=False, max_runtime=90,
                             fast=False, request_min_len=5000, per_phase_limit=30):
    start_global = time.time()

    def debug(msg):
        # Centralized timestamped logger for this scraping phase
        print(f"[{datetime.now():%H:%M:%S}] 🏀 {msg}")

    debug("Starting basketball live data acquisition")
    debug(f"Params headless={headless} retries={retries} pages={pages} three_days={three_days} all_pages={all_pages} requests_only={requests_only} fast={fast} request_min_len={request_min_len} max_runtime={max_runtime}")
    if requests_only:
        if verbose: debug("Requests-only mode enabled; skipping Selenium fallback.")
    
    try:
        debug("Attempting simple requests fetch...")
        req_start = time.time()
        r = requests.get(BASKETBALL_URL, headers={'User-Agent':'Mozilla/5.0'}, timeout=12)
        debug(f"Requests status={r.status_code} size={len(r.text)} took={round(time.time()-req_start,2)}s")
        # Allow smaller threshold in fast/request-only mode
        effective_min_len = request_min_len if not fast else min(request_min_len, 2500)
        if r.status_code==200 and len(r.text) > effective_min_len and "You need to enable JavaScript" not in r.text:
            with open("live_basketball_data.txt","w",encoding="utf-8") as f: f.write(r.text)
            debug("✅ Basketball live data via simple request (sufficient content)")
            return True
        else:
            if verbose: debug(f"Requests response insufficient (len {len(r.text)} < {effective_min_len}); will consider Selenium")
    except Exception as e:
        if verbose: debug(f"(requests basketball) error: {type(e).__name__}: {e}")
    if requests_only or fast:
        print("❌ Requests response insufficient and Selenium disabled (requests-only/fast mode).")
        return False
    if os.environ.get('BASKETBALL_DISABLE_SELENIUM','0')=='1':
        print("❌ Selenium disabled by env BASKETBALL_DISABLE_SELENIUM=1.")
        return False
    try:
        debug("Importing Selenium stack...")
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
        debug("Selenium imports successful")
    except ImportError:
        debug("❌ Selenium not installed for basketball scraping")
        return False
    attempt=0
    while attempt <= retries:
        attempt +=1
        elapsed = time.time() - start_global
        if elapsed > max_runtime:
            print(f"⏱️  Basketball scraping exceeded max runtime ({max_runtime}s); aborting.")
            return False
        debug(f"Selenium attempt {attempt}/{retries+1} (elapsed {int(elapsed)}s)")
        try:
            opts = Options()
            if headless: opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-gpu"); opts.add_argument("--no-sandbox")
            # Container stability flags
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-browser-side-navigation")
            opts.add_argument("--disable-features=VizDisplayCompositor")
            install_start = time.time()
            debug("Provisioning ChromeDriver via webdriver_manager...")
            driver_path = ChromeDriverManager().install()
            install_dur = time.time() - install_start
            debug(f"Driver path resolved: {driver_path} (install {round(install_dur,2)}s)")
            if install_dur > per_phase_limit:
                debug(f"Driver install exceeded per_phase_limit {per_phase_limit}s; aborting Selenium attempts.")
                return False
            driver = webdriver.Chrome(service=Service(driver_path), options=opts)
            debug("WebDriver instance created")
            try:
                nav_start = time.time()
                debug("Navigating to basketball URL...")
                driver.get(BASKETBALL_URL)
                WebDriverWait(driver, selenium_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                debug(f"Page body detected (nav {round(time.time()-nav_start,2)}s)")

                # Attempt cookie consent acceptance (non-fatal)
                try:
                    cbtn = WebDriverWait(driver,2).until(EC.element_to_be_clickable((By.CSS_SELECTOR,'.cookie-consent-container .accept-button')))
                    cbtn.click(); time.sleep(0.3)
                    if verbose: debug('Cookies acceptance attempted (possibly succeeded)')
                except Exception:
                    pass

                # Activate 3-day filter if requested
                if three_days:
                    clicked=False
                    if verbose: debug('Attempting 3-day filter (Basketball)')
                    path_candidates=[
                        (By.XPATH,"//button[contains(.,'3 dana') or contains(.,'3 Dana') or contains(.,'3 DANA')][not(@disabled)]"),
                        (By.XPATH,"//*[contains(@class,'day') and (contains(.,'3 dana') or contains(.,'3 Dana'))]"),
                        (By.XPATH,"//*[self::span or self::div or self::button][normalize-space()='3 dana']"),
                    ]
                    for by,sel in path_candidates:
                        try:
                            el = WebDriverWait(driver,3).until(EC.element_to_be_clickable((by,sel)))
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                            time.sleep(0.15)
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
                        debug('3-day filter clicked' if clicked else "'3 dana' control not found")
                    time.sleep(1)

                # Initial scrolling for lazy loading
                debug(f"Initial lazy-load scrolling steps: {scroll_steps}")
                scroll_start = time.time()
                for s in range(scroll_steps):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);"); time.sleep(0.6)
                    if s==0: driver.execute_script("window.scrollTo(0,0);")
                debug(f"Finished initial scrolling phase (scroll {round(time.time()-scroll_start,2)}s)")

                # Guard: stop early if runtime drifting
                if time.time() - start_global > max_runtime:
                    print("⏱️  Runtime limit reached during initial scroll; aborting.")
                    return False

                # Auto-detect total pages if requested
                if all_pages:
                    try:
                        debug("Auto-detecting pagination buttons...")
                        elems = driver.find_elements(By.CSS_SELECTOR,'button,a')
                        nums=[]
                        for el in elems:
                            txt=el.text.strip()
                            if re.match(r'^\d+$', txt):
                                try: nums.append(int(txt))
                                except: pass
                        if nums:
                            auto_max=max(nums)
                            if auto_max > pages:
                                if verbose: debug(f'Auto-detected basketball pages: {auto_max}')
                                pages=auto_max
                    except Exception:
                        pass
                page_content = driver.page_source
                combined=page_content
                if pages>1:
                    if verbose: debug(f"Pagination target pages={pages}")
                    for p in range(2,pages+1):
                        try:
                            btn=None
                            xpaths=[f"//button[normalize-space()='{p}']", f"//a[normalize-space()='{p}']"]
                            for xp in xpaths:
                                els=driver.find_elements(By.XPATH,xp)
                                if els: btn=els[0]; break
                            if not btn:
                                btn = driver.execute_script("return Array.from(document.querySelectorAll('button,a')).find(el=>el.textContent.trim()==='"+str(p)+"')")
                            if not btn:
                                if verbose: debug(f"Page {p} control not found")
                                break
                            try: btn.click()
                            except Exception: driver.execute_script("arguments[0].click();", btn)
                            time.sleep(1.0)
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);"); time.sleep(0.4)
                            driver.execute_script("window.scrollTo(0,0);")
                            new_src=driver.page_source
                            if len(new_src)!=len(page_content):
                                combined += f"\n<!-- PAGE {p} SPLIT -->\n" + new_src
                        except Exception as pe:
                            if verbose: debug(f"Pagination fail p={p} err={pe}")
                            break
                    page_content=combined
                decs = re.findall(r">\s*(\d+\.\d{2})\s*<", page_content)
                debug(f"Collected decimals count={len(decs)} page_source_len={len(page_content)}")
                # Relax thresholds if fast mode
                min_page_len = 18_000 if not fast else 9_000
                min_decs = 10 if not fast else 6
                if len(page_content)>min_page_len and len(decs)>min_decs:
                    with open("live_basketball_data.txt","w",encoding="utf-8") as f: f.write(page_content)
                    debug("✅ Basketball live data via Selenium (content threshold met)")
                    return True
                else:
                    debug("Content insufficient; will retry" if attempt<=retries else "Giving up after final attempt")
            finally:
                debug("Quitting WebDriver")
                driver.quit()
        except Exception as e:
            debug(f"Basketball Selenium attempt error: {type(e).__name__}: {e}")
            time.sleep(1.5)
    return False

# ----------------- Flatten HTML -----------------

def flatten_html_to_text(html_path, out_txt):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("BeautifulSoup missing (pip install beautifulsoup4)"); return None
    if not os.path.exists(html_path): return None
    with open(html_path,'r',encoding='utf-8',errors='ignore') as f: html=f.read()
    soup = BeautifulSoup(html,'html.parser')
    text = soup.get_text('\n', strip=True)
    with open(out_txt,'w',encoding='utf-8') as f: f.write(text)
    return out_txt

# ----------------- Parsing -----------------

def parse_basketball_flat(lines, verbose=False):
    matches=[]
    time_re = re.compile(r':\d{2}$')
    num_re = re.compile(r'^\d+(?:\.\d+)?$')
    i=0;n=len(lines)
    while i<n:
        if time_re.search(lines[i]) and i+2<n:
            t1=lines[i+1].strip(); t2=lines[i+2].strip(); i+=3
            idx=0; odds_map={}
            while i<n and idx < len(MARKET_SEQ):
                l=lines[i].strip()
                if l.startswith('+') or time_re.search(l): break
                if num_re.match(l):
                    try:
                        val=float(l)
                        if 1.01 <= val <= 200:
                            odds_map[MARKET_SEQ[idx]] = (val,'AUTO')
                            if verbose: print(f"[basketball] {t1} vs {t2} {MARKET_SEQ[idx]}={val}")
                            idx+=1
                    except: pass
                i+=1
            if len(odds_map) >= 2:
                matches.append({'teams':f"{t1} vs {t2}", 'odds':odds_map})
                if verbose:
                    disp=', '.join(f"{k}={v[0]}" for k,v in odds_map.items())
                    print(f"[basketball] {t1} vs {t2} -> {disp}")
        else:
            i+=1
    if verbose: print(f"[basketball] Total matches parsed: {len(matches)}")
    return matches

# ----------------- Surebet Logic (only 1/2 and Under/Over) -----------------

def analyze_basketball_surebets(matches, min_profit=0.0, verbose=False):
    surebets=[]
    for m in matches:
        labels=m['odds']
        if all(x in labels for x in ['1','2']):
            profit = check_surebet([labels['1'], labels['2']])
            if profit and profit >= min_profit:
                stakes, abs_p = compute_stakes([labels['1'], labels['2']])
                surebets.append({'match':m['teams'],'type':'Moneyline','profit':profit,'odds':{'1':labels['1'],'2':labels['2']},'stakes':stakes,'abs_profit':abs_p})
        if 'Under' in labels and 'Over' in labels:
            profit = check_surebet([labels['Under'], labels['Over']])
            if profit and profit >= min_profit:
                stakes, abs_p = compute_stakes([labels['Under'], labels['Over']])
                surebets.append({'match':m['teams'],'type':'Totals','profit':profit,'odds':{'Under':labels['Under'],'Over':labels['Over']},'stakes':stakes,'abs_profit':abs_p})
    return surebets

# ----------------- Telegram Formatting -----------------

def format_basketball_summary(surebets: List[Dict[str, Any]], total_matches: int, include_header: bool=False) -> str:
    lines=[]
    if include_header:
        lines.extend([
            "🏀 Basketball Surebets Report",
            f"Total parsed basketball matches: {total_matches}",
            f"Surebets detected: {len(surebets)}",
            ""
        ])
    if not surebets:
        if include_header:
            lines.append('No basketball surebets.')
            return '\n'.join(lines)
        return 'No basketball surebets.'
    # Sort by profit desc
    top = sorted(surebets, key=lambda x: x['profit'], reverse=True)[:12]
    if include_header:
        lines.append('Top opportunities (profit desc):')
    for sb in top:
        match = sb['match']
        profit = sb['profit']
        t = sb['type']
        odds_line = ', '.join(f"{k}={v[0]}" for k,v in sb['odds'].items())
        lines.append(f"{match}\n  {t}: Profit {profit}% | {odds_line}")
    return '\n'.join(lines)

# ----------------- Output -----------------

def save_basketball(matches, surebets, source_type):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    mf = f"basketball_{source_type}_matches_{ts}.txt"
    sf = f"basketball_{source_type}_surebets_{ts}.txt"
    with open(mf,'w',encoding='utf-8') as f:
        f.write(f"Basketball Matches ({source_type}) - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write('='*60+'\n\n')
        for m in matches:
            f.write(m['teams']+'\n')
            for k,(o,b) in m['odds'].items():
                f.write(f"  {k}: {o} @ {b}\n")
            f.write('\n')
    with open(sf,'w',encoding='utf-8') as f:
        f.write(f"Basketball Surebets ({source_type}) - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write('='*60+'\n\n')
        if not surebets:
            f.write('No surebets found.\n')
        else:
            for sb in surebets:
                f.write(f"{sb['match']}\n  ✅ {sb['type']} SUREBET → Profit: {sb['profit']}%\n")
                odds_line = ', '.join(f"{k}={v[0]}" for k,v in sb['odds'].items())
                f.write(f"  Odds: {odds_line}\n\n")
    return mf, sf

# ----------------- Main -----------------

def main():
    ap = argparse.ArgumentParser(description='Enhanced Basketball Odds Analyzer')
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--pages', type=int, default=1, help='Number of pages to attempt (ignored if --all-pages)')
    ap.add_argument('--min-profit', type=float, default=0.0)
    ap.add_argument('--no-headless', action='store_true')
    ap.add_argument('--retries', type=int, default=2)
    ap.add_argument('--three-days', action='store_true', help='Activate 3-day ("3 dana") filter before scraping')
    ap.add_argument('--all-pages', action='store_true', help='Auto-detect and scrape all pagination pages')
    ap.add_argument('--no-telegram', action='store_true', help='Disable Telegram sending for basketball run')
    ap.add_argument('--telegram-header', action='store_true', help='Include header lines in Telegram message')
    ap.add_argument('--notify-min-roi', type=float, default=float(os.environ.get('BASKETBALL_NOTIFY_MIN_ROI','2.5')), help='Minimum profit%% (margin) to include in Telegram notification (default 2.5)')
    ap.add_argument('--notify-max-roi', type=float, default=float(os.environ.get('BASKETBALL_NOTIFY_MAX_ROI','20')), help='Maximum profit%% to include; above treated as suspicious (default 20)')
    ap.add_argument('--requests-only', action='store_true', help='Skip Selenium fallback and fail fast if requests HTML insufficient')
    ap.add_argument('--max-runtime', type=int, default=int(os.environ.get('BASKETBALL_MAX_RUNTIME','90')), help='Hard timeout (seconds) for total scraping phase')
    ap.add_argument('--fast', action='store_true', help='Fast mode: force requests-only attempt with relaxed thresholds; if insufficient skip Selenium')
    args = ap.parse_args()

    verbose=args.verbose
    # Environment-driven overrides
    env_force_requests = os.environ.get('BASKETBALL_FORCE_REQUESTS','0')=='1'
    env_disable_selenium = os.environ.get('BASKETBALL_DISABLE_SELENIUM','0')=='1'
    env_request_min_len = int(os.environ.get('BASKETBALL_REQUEST_MIN_LEN', '5000'))
    env_scroll_steps = int(os.environ.get('BASKETBALL_SCROLL_STEPS', '4'))
    env_selenium_retries = os.environ.get('BASKETBALL_SELENIUM_RETRIES')
    effective_retries = args.retries
    if env_selenium_retries is not None:
        try:
            effective_retries = max(0, int(env_selenium_retries))
        except: pass
    # Fast mode implies requests-only semantics
    effective_requests_only = args.requests_only or env_force_requests or env_disable_selenium or args.fast
    # Adjust scroll steps for fast mode
    if args.fast:
        env_scroll_steps = min(env_scroll_steps, 2)
    ok = download_live_basketball(headless=not args.no_headless,
                                  retries=effective_retries,
                                  pages=args.pages,
                                  verbose=verbose,
                                  three_days=args.three_days,
                                  all_pages=args.all_pages,
                                  requests_only=effective_requests_only,
                                  max_runtime=args.max_runtime,
                                  fast=args.fast,
                                  request_min_len=env_request_min_len,
                                  per_phase_limit=int(os.environ.get('BASKETBALL_PER_PHASE_LIMIT','30')),
                                  scroll_steps=env_scroll_steps)
    if not ok:
        print('❌ Could not fetch basketball live data.'); return
    flat = flatten_html_to_text('live_basketball_data.txt','live_basketball_extracted.txt')
    if not flat:
        print('❌ Could not flatten basketball HTML.'); return
    with open(flat,'r',encoding='utf-8') as f: lines=[l.strip() for l in f if l.strip()]
    matches = parse_basketball_flat(lines, verbose=verbose)
    if not matches:
        print('❌ No basketball matches parsed.'); return
    print(f"📊 Parsed {len(matches)} basketball matches")
    surebets = analyze_basketball_surebets(matches, min_profit=args.min_profit, verbose=verbose)
    print(f"💰 Found {len(surebets)} basketball surebets (min-profit {args.min_profit}%)")
    mf,sf = save_basketball(matches, surebets, 'live')
    print(f"✅ Saved: {mf} & {sf}")
    if surebets:
        print('\n🎉 BASKETBALL SUREBET SUMMARY:')
        for sb in surebets[:10]:
            print(f"  • {sb['match']} - {sb['type']} - {sb['profit']}%")
    else:
        print('No surebet opportunities identified.')
    # Telegram send (concise by default)
    # Filter for notification ROI/profit range
    filtered_notify = [sb for sb in surebets if args.notify_min_roi <= sb['profit'] <= args.notify_max_roi]
    print(f"🔎 Basketball notify filter: profit between {args.notify_min_roi}% and {args.notify_max_roi}% -> {len(filtered_notify)} candidates")
    if not args.no_telegram and send_long_message:
        if not filtered_notify:
            print('ℹ️ No basketball surebets within desired profit range; skipping Telegram send.')
        else:
            try:
                msg = format_basketball_summary(filtered_notify, len(matches), include_header=args.telegram_header)
                send_long_message(msg)
                print('📨 Basketball Telegram summary attempted (filtered).')
            except Exception as e:
                print(f'⚠️ Basketball Telegram send failed: {e}')
    elif not send_long_message:
        print('ℹ Telegram notifier not available (import failed).')

if __name__ == '__main__':
    main()
