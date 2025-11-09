import argparse, os, re, time
from datetime import datetime
import requests

HAND_BALL_URL = "https://toptiket.rs/odds/handball"
# Market order heuristic: 1, X (draw), 2, Handicap1, Handicap2, Under, Over
MARKET_SEQ = ['1','X','2','Handicap1','Handicap2','Under','Over']
# We will treat certain numeric tokens as line values (spread / total) rather than odds.
# Heuristics:
#  - Handicap line likely between 1.5 and 30 (integer or half) but appears before two handicap odds ~1.6-2.3
#  - Total points line typically between 30 and 80 (e.g., 61.5, 65.5) before two total odds ~1.6-2.3
# Parser will capture structure: 1, X, 2, (optional handicap_line), Handicap1 odd, Handicap2 odd, (optional total_line), Under odd, Over odd.
DEFAULT_TOTAL_STAKE = 100

# ---------------- Utility ----------------

def check_surebet(odds):
    clean=[o for o,_ in odds if 1.01 <= o <= 200]
    if len(clean) < 2: return None
    inv=sum(1/o for o in clean)
    if inv < 1:
        return round((1-inv)*100,2)
    return None

def compute_stakes(odds):
    valid=[(o,b) for o,b in odds if o>0]
    if len(valid) < 2: return [],0
    inv=sum(1/o for o,_ in valid)
    if inv >= 1: return [],0
    stakes=[]
    for o,b in valid:
        stake=(DEFAULT_TOTAL_STAKE*(1/o))/inv
        stakes.append((round(stake,2), o, b))
    profit=round(stakes[0][0]*odds[0][0]-DEFAULT_TOTAL_STAKE,2) if stakes else 0
    return stakes, profit

# ---------------- Live Download ----------------

def download_live_handball(headless=True, retries=2, selenium_wait=8, scroll_steps=4, pages=1, verbose=False, three_days=False, all_pages=False):
    print("🤾 Attempting to download live data from TopTiket (Handball)...")
    try:
        r=requests.get(HAND_BALL_URL, headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
        if r.status_code==200 and len(r.text) > 4000 and "You need to enable JavaScript" not in r.text:
            with open('live_handball_data.txt','w',encoding='utf-8') as f: f.write(r.text)
            print('✅ Handball live data via simple request')
            return True
    except Exception as e:
        if verbose: print('(requests handball) error', e)
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print('❌ Selenium not installed for handball scraping')
        return False
    attempt=0
    while attempt <= retries:
        attempt+=1
        print(f"🧪 (Handball) Selenium attempt {attempt}/{retries+1}...")
        try:
            opts=Options()
            if headless: opts.add_argument('--headless=new')
            opts.add_argument('--window-size=1920,1080')
            opts.add_argument('--disable-gpu'); opts.add_argument('--no-sandbox')
            driver=webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            try:
                driver.get(HAND_BALL_URL)
                WebDriverWait(driver, selenium_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                # Cookies
                try:
                    cbtn=WebDriverWait(driver,2).until(EC.element_to_be_clickable((By.CSS_SELECTOR,'.cookie-consent-container .accept-button')))
                    cbtn.click(); time.sleep(0.3)
                    if verbose: print('🍪 Handball cookies accepted')
                except Exception: pass
                # 3-day filter
                if three_days:
                    clicked=False
                    if verbose: print('🗓️ Attempting 3-day filter (Handball)')
                    path_candidates=[
                        (By.XPATH,"//button[contains(.,'3 dana') or contains(.,'3 Dana') or contains(.,'3 DANA')][not(@disabled)]"),
                        (By.XPATH,"//*[contains(@class,'day') and (contains(.,'3 dana') or contains(.,'3 Dana'))]"),
                        (By.XPATH,"//*[self::span or self::div or self::button][normalize-space()='3 dana']"),
                    ]
                    for by,sel in path_candidates:
                        try:
                            el=WebDriverWait(driver,3).until(EC.element_to_be_clickable((by,sel)))
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                            time.sleep(0.15)
                            try: el.click()
                            except Exception: driver.execute_script('arguments[0].click();', el)
                            clicked=True; break
                        except Exception: continue
                    if not clicked:
                        try:
                            js_clicked = driver.execute_script("const els=[...document.querySelectorAll('*')]; const t=els.find(e=>e.innerText && e.innerText.trim().toLowerCase()==='3 dana'); if(t){t.scrollIntoView({block:'center'}); t.click(); return true;} return false;")
                            if js_clicked: clicked=True
                        except Exception: pass
                    if verbose: print('✅ 3-day filter clicked (Handball)' if clicked else "⚠️ '3 dana' control not found (Handball)")
                    time.sleep(1)
                # initial scroll
                for s in range(scroll_steps):
                    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);'); time.sleep(0.7)
                    if s==0: driver.execute_script('window.scrollTo(0,0);')
                # auto pages
                if all_pages:
                    try:
                        elems=driver.find_elements(By.CSS_SELECTOR,'button,a')
                        nums=[]
                        for el in elems:
                            txt=el.text.strip()
                            if re.match(r'^\d+$', txt):
                                try: nums.append(int(txt))
                                except: pass
                        if nums:
                            auto_max=max(nums)
                            if auto_max > pages:
                                if verbose: print(f'🔢 Auto-detected handball pages: {auto_max}')
                                pages=auto_max
                    except Exception: pass
                page_content = driver.page_source
                combined=page_content
                if pages>1:
                    if verbose: print(f'↪️  Handball pagination pages= {pages}')
                    for p in range(2,pages+1):
                        try:
                            btn=None
                            xpaths=[f"//button[normalize-space()='{p}']", f"//a[normalize-space()='{p}']"]
                            for xp in xpaths:
                                els=driver.find_elements(By.XPATH,xp)
                                if els: btn=els[0]; break
                            if not btn:
                                btn=driver.execute_script("return Array.from(document.querySelectorAll('button,a')).find(el=>el.textContent.trim()==='"+str(p)+"')")
                            if not btn:
                                if verbose: print(f"  • Handball page {p} control not found")
                                break
                            try: btn.click()
                            except Exception: driver.execute_script('arguments[0].click();', btn)
                            time.sleep(1.0)
                            driver.execute_script('window.scrollTo(0, document.body.scrollHeight);'); time.sleep(0.4)
                            driver.execute_script('window.scrollTo(0,0);')
                            new_src=driver.page_source
                            if len(new_src)!=len(page_content):
                                combined += f"\n<!-- PAGE {p} SPLIT -->\n" + new_src
                        except Exception as pe:
                            if verbose: print('  • Handball pagination fail', pe)
                            break
                    page_content=combined
                decs=re.findall(r">\s*(\d+\.\d{2})\s*<", page_content)
                if len(page_content) > 15_000 and len(decs) > 10:
                    with open('live_handball_data.txt','w',encoding='utf-8') as f: f.write(page_content)
                    print('✅ Handball live data via Selenium')
                    return True
                else:
                    print('⚠️ Handball content insufficient; retrying' if attempt<=retries else '❌ Handball giving up')
            finally:
                driver.quit()
        except Exception as e:
            print('❌ Handball Selenium attempt error', e)
            time.sleep(1.2)
    return False

# ---------------- Flatten ----------------

def flatten_html_to_text(html_path, out_txt):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print('BeautifulSoup missing (pip install beautifulsoup4)'); return None
    if not os.path.exists(html_path): return None
    with open(html_path,'r',encoding='utf-8',errors='ignore') as f: html=f.read()
    soup=BeautifulSoup(html,'html.parser')
    text=soup.get_text('\n', strip=True)
    with open(out_txt,'w',encoding='utf-8') as f: f.write(text)
    return out_txt

# ---------------- Parsing ----------------

def parse_handball_flat(lines, verbose=False):
    matches=[]
    time_re=re.compile(r':\d{2}$')
    num_re=re.compile(r'^\d+(?:\.\d+)?$')
    i=0; n=len(lines)
    while i<n:
        if time_re.search(lines[i]) and i+2 < n:
            team1=lines[i+1].strip(); team2=lines[i+2].strip(); i+=3
            odds_map={}; handicap_line=None; total_line=None
            stage='moneyline'  # transitions: moneyline -> handicap -> totals
            # Collect tokens until next time header or plus marker
            block=[]
            start_i=i
            while i<n and not time_re.search(lines[i]) and not lines[i].startswith('+'):
                block.append(lines[i].strip()); i+=1
            # Parse block
            # 1/X/2 first three qualifying odds in range 1.01-50 (allow draw big up to maybe 30)
            ml_odds=[]
            for token in block:
                if len(ml_odds) >= 3: break
                if num_re.match(token):
                    try:
                        v=float(token)
                        if 1.01 <= v <= 70:  # broaden for large draw odds
                            ml_odds.append(v)
                    except: pass
            if len(ml_odds)==3:
                odds_map['1']=(ml_odds[0],'AUTO'); odds_map['X']=(ml_odds[1],'AUTO'); odds_map['2']=(ml_odds[2],'AUTO')
            # Remove consumed ml tokens
            remaining=block[len(ml_odds):]
            # Handicap segment: pattern [handicap_line (~1.5-30 maybe not fractional >30)] then two odds ~1.5-2.3
            h_candidates=[]
            for t in remaining:
                if num_re.match(t):
                    try: h_candidates.append(float(t))
                    except: pass
                if len(h_candidates)>=3: break
            # Decide handicap: if have at least 3 numbers and first between 1 and 30 and next two between 1.4 and 3.2 treat as handicap line + odds
            if len(h_candidates)>=3:
                hl, h1, h2 = h_candidates[:3]
                if 1 <= hl <= 30 and 1.2 <= h1 <= 5 and 1.2 <= h2 <= 5:
                    handicap_line=hl
                    odds_map['Handicap1']=(h1,'AUTO'); odds_map['Handicap2']=(h2,'AUTO')
                    # Remove these from remaining
                    # Find their string occurrences
                    consumed=0; new_remaining=[]
                    for t in remaining:
                        if consumed<3 and num_re.match(t):
                            consumed+=1; continue
                        new_remaining.append(t)
                    remaining=new_remaining
            # Totals: look for total line ( >30 & < 120 ) then two odds ~1.2-3.5
            t_candidates=[]
            for t in remaining:
                if num_re.match(t):
                    try: t_candidates.append(float(t))
                    except: pass
                if len(t_candidates)>=3: break
            if len(t_candidates)>=3:
                tl, uo1, uo2 = t_candidates[:3]
                if 30 <= tl <= 120 and 1.01 <= uo1 <= 5 and 1.01 <= uo2 <= 5:
                    total_line=tl
                    odds_map['Under']=(uo1,'AUTO'); odds_map['Over']=(uo2,'AUTO')
            record={'teams':f"{team1} vs {team2}", 'odds':odds_map}
            if handicap_line is not None: record['handicap_line']=handicap_line
            if total_line is not None: record['total_line']=total_line
            if len(odds_map) >= 2:
                matches.append(record)
                if verbose:
                    disp=', '.join([f"{k}={v[0]}" for k,v in odds_map.items()])
                    extra=f" HL={handicap_line}" if handicap_line is not None else ''
                    extra+=f" TL={total_line}" if total_line is not None else ''
                    print(f"[handball] {team1} vs {team2} -> {disp}{extra}")
        else:
            i+=1
    if verbose: print(f"[handball] Total matches parsed: {len(matches)}")
    return matches

# ---------------- Surebet ----------------

def analyze_handball_surebets(matches, min_profit=0.0, verbose=False):
    surebets=[]
    for m in matches:
        labels=m['odds']
        # 1X2 surebet
        if all(x in labels for x in ['1','X','2']):
            profit=check_surebet([labels['1'], labels['X'], labels['2']])
            if profit and profit >= min_profit:
                stakes, abs_p = compute_stakes([labels['1'], labels['X'], labels['2']])
                surebets.append({'match':m['teams'],'type':'1X2','profit':profit,'odds':{'1':labels['1'],'X':labels['X'],'2':labels['2']},'stakes':stakes,'abs_profit':abs_p})
        # Totals surebet
        if 'Under' in labels and 'Over' in labels:
            profit=check_surebet([labels['Under'], labels['Over']])
            if profit and profit >= min_profit:
                stakes, abs_p = compute_stakes([labels['Under'], labels['Over']])
                surebets.append({'match':m['teams'],'type':'Totals','profit':profit,'odds':{'Under':labels['Under'],'Over':labels['Over']},'stakes':stakes,'abs_profit':abs_p})
    return surebets

# ---------------- Output ----------------

def save_handball(matches, surebets, source_type):
    ts=datetime.now().strftime('%Y%m%d_%H%M%S')
    mf=f"handball_{source_type}_matches_{ts}.txt"
    sf=f"handball_{source_type}_surebets_{ts}.txt"
    with open(mf,'w',encoding='utf-8') as f:
        f.write(f"Handball Matches ({source_type}) - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write('='*60+'\n\n')
        for m in matches:
            f.write(m['teams']+'\n')
            for k,(o,b) in m['odds'].items():
                f.write(f"  {k}: {o} @ {b}\n")
            f.write('\n')
    with open(sf,'w',encoding='utf-8') as f:
        f.write(f"Handball Surebets ({source_type}) - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write('='*60+'\n\n')
        if not surebets:
            f.write('No surebets found.\n')
        else:
            for sb in surebets:
                f.write(f"{sb['match']}\n  ✅ {sb['type']} SUREBET → Profit: {sb['profit']}%\n")
                odds_line=', '.join(f"{k}={v[0]}" for k,v in sb['odds'].items())
                f.write(f"  Odds: {odds_line}\n\n")
    return mf,sf

# ---------------- Main ----------------

def main():
    ap=argparse.ArgumentParser(description='Enhanced Handball Odds Analyzer')
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--pages', type=int, default=1, help='Number of pages to attempt (ignored if --all-pages)')
    ap.add_argument('--min-profit', type=float, default=0.0)
    ap.add_argument('--no-headless', action='store_true')
    ap.add_argument('--retries', type=int, default=2)
    ap.add_argument('--three-days', action='store_true', help='Activate 3-day ("3 dana") filter before scraping')
    ap.add_argument('--all-pages', action='store_true', help='Auto-detect and scrape all pagination pages')
    args=ap.parse_args()

    verbose=args.verbose
    ok=download_live_handball(headless=not args.no_headless, retries=args.retries, pages=args.pages, verbose=verbose, three_days=args.three_days, all_pages=args.all_pages)
    if not ok:
        print('❌ Could not fetch handball live data.'); return
    flat=flatten_html_to_text('live_handball_data.txt','live_handball_extracted.txt')
    if not flat:
        print('❌ Could not flatten handball HTML.'); return
    with open(flat,'r',encoding='utf-8') as f: lines=[l.strip() for l in f if l.strip()]
    matches=parse_handball_flat(lines, verbose=verbose)
    if not matches:
        print('❌ No handball matches parsed.'); return
    print(f'📊 Parsed {len(matches)} handball matches')
    surebets=analyze_handball_surebets(matches, min_profit=args.min_profit, verbose=verbose)
    print(f'💰 Found {len(surebets)} handball surebets (min-profit {args.min_profit}%)')
    mf,sf=save_handball(matches, surebets, 'live')
    print(f'✅ Saved: {mf} & {sf}')
    if surebets:
        print('\n🎉 HANDBALL SUREBET SUMMARY:')
        for sb in surebets[:10]:
            print(f"  • {sb['match']} - {sb['type']} - {sb['profit']}%")
    else:
        print('No surebet opportunities identified.')

if __name__ == '__main__':
    main()
