import argparse, os, re, time
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

def download_live_basketball(headless=True, retries=2, selenium_wait=8, scroll_steps=4, pages=1, verbose=False, three_days=False, all_pages=False):
    print("🏀 Attempting to download live data from TopTiket (Basketball)...")
    try:
        r = requests.get(BASKETBALL_URL, headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
        if r.status_code==200 and len(r.text) > 5000 and "You need to enable JavaScript" not in r.text:
            with open("live_basketball_data.txt","w",encoding="utf-8") as f: f.write(r.text)
            print("✅ Basketball live data via simple request")
            return True
    except Exception as e:
        if verbose: print("(requests basketball) error", e)
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("❌ Selenium not installed for basketball scraping")
        return False
    attempt=0
    while attempt <= retries:
        attempt +=1
        print(f"⛹️  (Basketball) Selenium attempt {attempt}/{retries+1}...")
        try:
            opts = Options()
            if headless: opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-gpu"); opts.add_argument("--no-sandbox")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            try:
                driver.get(BASKETBALL_URL)
                WebDriverWait(driver, selenium_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))

                # Attempt cookie consent acceptance (non-fatal)
                try:
                    cbtn = WebDriverWait(driver,2).until(EC.element_to_be_clickable((By.CSS_SELECTOR,'.cookie-consent-container .accept-button')))
                    cbtn.click(); time.sleep(0.3)
                    if verbose: print('🍪 Basketball cookies accepted')
                except Exception:
                    pass

                # Activate 3-day filter if requested
                if three_days:
                    clicked=False
                    if verbose: print('🗓️ Attempting 3-day filter (Basketball)')
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
                        print('✅ 3-day filter clicked (Basketball)' if clicked else "⚠️ '3 dana' control not found (Basketball)")
                    time.sleep(1)

                # Initial scrolling for lazy loading
                for s in range(scroll_steps):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);"); time.sleep(0.7)
                    if s==0: driver.execute_script("window.scrollTo(0,0);")

                # Auto-detect total pages if requested
                if all_pages:
                    try:
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
                                if verbose: print(f'🔢 Auto-detected basketball pages: {auto_max}')
                                pages=auto_max
                    except Exception:
                        pass
                page_content = driver.page_source
                combined=page_content
                if pages>1:
                    if verbose: print(f"↪️  Basketball pagination pages= {pages}")
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
                                if verbose: print(f"  • Basketball page {p} control not found")
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
                            if verbose: print("  • Basketball pagination fail", pe)
                            break
                    page_content=combined
                decs = re.findall(r">\s*(\d+\.\d{2})\s*<", page_content)
                if len(page_content)>18_000 and len(decs)>10:
                    with open("live_basketball_data.txt","w",encoding="utf-8") as f: f.write(page_content)
                    print("✅ Basketball live data via Selenium")
                    return True
                else:
                    print("⚠️ Basketball content insufficient; retrying" if attempt<=retries else "❌ Basketball giving up")
            finally:
                driver.quit()
        except Exception as e:
            print("❌ Basketball Selenium attempt error", e)
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
    args = ap.parse_args()

    verbose=args.verbose
    ok = download_live_basketball(headless=not args.no_headless, retries=args.retries, pages=args.pages, verbose=verbose, three_days=args.three_days, all_pages=args.all_pages)
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
    if not args.no_telegram and send_long_message:
        try:
            msg = format_basketball_summary(surebets, len(matches), include_header=args.telegram_header)
            send_long_message(msg)
            print('📨 Basketball Telegram summary attempted.')
        except Exception as e:
            print(f'⚠️ Basketball Telegram send failed: {e}')
    elif not send_long_message:
        print('ℹ Telegram notifier not available (import failed).')

if __name__ == '__main__':
    main()
