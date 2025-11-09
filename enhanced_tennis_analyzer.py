import argparse, os, re, time, json, glob
from datetime import datetime
import requests

DEFAULT_TOTAL_STAKE = 100

# --------- Generic Utility (adapted from football) ----------

def compute_stakes(odds):
    valid = [(o,b) for o,b in odds if o>0]
    if len(valid) < 2: return []
    inv = sum(1/o for o,_ in valid)
    if inv >= 1: return []
    stakes = []
    for o,b in valid:
        stake = (DEFAULT_TOTAL_STAKE * (1/o)) / inv
        stakes.append((round(stake,2), o, b))
    profit = round(stakes[0][0]*odds[0][0]-DEFAULT_TOTAL_STAKE,2) if stakes else 0
    return stakes, profit

def check_surebet(odds):
    clean = [o for o,_ in odds if 1.01 <= o <= 69]
    if len(clean) < 2: return None
    inv = sum(1/o for o in clean)
    if inv < 1: return round((1-inv)*100,2)
    return None

# --------- Live download (tennis) ----------

def download_live_tennis(headless=True, retries=2, selenium_wait=8, scroll_steps=4, pages=1, verbose=False):
    print("🎾 Attempting to download live data from TopTiket (Tennis)...")
    # Fast attempt with requests (will likely be placeholder)
    try:
        r = requests.get("https://toptiket.rs/odds/tennis", headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
        if r.status_code==200 and len(r.text) > 5000 and "You need to enable JavaScript" not in r.text:
            with open("live_tennis_data.txt","w",encoding="utf-8") as f: f.write(r.text)
            print("✅ Tennis live data via simple request")
            return True
    except Exception as e:
        if verbose: print("(requests tennis) error", e)
    # Selenium fallback
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("❌ Selenium not installed for tennis scraping")
        return False
    attempt=0
    while attempt <= retries:
        attempt +=1
        print(f"📱 (Tennis) Selenium attempt {attempt}/{retries+1}...")
        try:
            opts = Options()
            if headless: opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-gpu"); opts.add_argument("--no-sandbox")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            try:
                driver.get("https://toptiket.rs/odds/tennis")
                WebDriverWait(driver, selenium_wait).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
                for s in range(scroll_steps):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);"); time.sleep(0.8)
                    if s==0: driver.execute_script("window.scrollTo(0,0);")
                page_content = driver.page_source
                combined = page_content
                if pages>1:
                    if verbose: print(f"↪️  Tennis pagination pages= {pages}")
                    for p in range(2,pages+1):
                        try:
                            btn = None
                            xpaths = [f"//button[normalize-space()='{p}']", f"//a[normalize-space()='{p}']"]
                            for xp in xpaths:
                                els = driver.find_elements(By.XPATH, xp)
                                if els:
                                    btn = els[0]; break
                            if not btn:
                                btn = driver.execute_script("return Array.from(document.querySelectorAll('button,a')).find(el=>el.textContent.trim()==='"+str(p)+"')")
                            if not btn:
                                if verbose: print(f"  • Tennis page {p} control not found")
                                break
                            try: btn.click()
                            except Exception: driver.execute_script("arguments[0].click();", btn)
                            time.sleep(1.1)
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);"); time.sleep(0.5)
                            driver.execute_script("window.scrollTo(0,0);")
                            new_src = driver.page_source
                            if len(new_src)!=len(page_content):
                                combined += f"\n<!-- PAGE {p} SPLIT -->\n" + new_src
                        except Exception as pe:
                            if verbose: print("  • Tennis pagination fail", pe)
                            break
                    page_content = combined
                # Heuristic acceptance
                decs = re.findall(r">\s*(\d+\.\d{2})\s*<", page_content)
                if len(page_content) > 25_000 and len(decs) > 10:
                    with open("live_tennis_data.txt","w",encoding="utf-8") as f: f.write(page_content)
                    print("✅ Tennis live data via Selenium")
                    return True
                else:
                    print("⚠️ Tennis content insufficient; retrying" if attempt<=retries else "❌ Tennis giving up")
            finally:
                driver.quit()
        except Exception as e:
            print("❌ Tennis Selenium attempt error", e)
            time.sleep(1.5)
    return False

# --------- Extraction / Parsing ----------

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

# Tennis market order (observed / provided):
# home win, guest win, H1, handicap spread, H2, manje (under), spread (again), vise (over)
# We'll label: Home, Away, H1, Handicap, H2, Under, Handicap2, Over
MARKET_SEQ = ['Home','Away','H1','Handicap','H2','Under','Handicap2','Over']

# Simple sequential numeric parser similar to football auto-plain

def parse_tennis_flat(lines, verbose=False):
    matches = []
    # Heuristic: line with ':' and digits preceding = time; next two lines players
    time_re = re.compile(r':\d{2}$')
    num_re = re.compile(r'^\d+(?:\.\d+)?$')
    i=0; n=len(lines)
    while i < n:
        if time_re.search(lines[i]) and i+2 < n:
            p1 = lines[i+1].strip(); p2 = lines[i+2].strip(); i+=3
            idx=0; odds_map={}
            while i<n and idx < len(MARKET_SEQ):
                l = lines[i].strip()
                if l.startswith('+') or time_re.search(l): break
                if num_re.match(l):
                    try:
                        val=float(l)
                        if 1.01 <= val <= 200:
                            odds_map[MARKET_SEQ[idx]] = (val,'AUTO')
                            if verbose: print(f"[tennis] {p1} vs {p2} capture {MARKET_SEQ[idx]}={val}")
                            idx+=1
                    except: pass
                i+=1
            if len(odds_map) >= 2:
                matches.append({'teams': f"{p1} vs {p2}", 'odds': odds_map})
                if verbose:
                    disp = ', '.join(f"{k}={v[0]}" for k,v in odds_map.items())
                    print(f"[tennis] {p1} vs {p2} -> {disp}")
        else:
            i+=1
    if verbose: print(f"[tennis] Total matches parsed: {len(matches)}")
    return matches

# --------- Surebet analysis for tennis ----------

def analyze_tennis_surebets(matches, min_profit=0.0):
    surebets=[]
    for m in matches:
        labels = m['odds']
        # Home vs Away
        if all(x in labels for x in ['Home','Away']):
            profit = check_surebet([labels['Home'], labels['Away']])
            if profit and profit >= min_profit:
                stakes, abs_p = compute_stakes([labels['Home'], labels['Away']])
                surebets.append({'match':m['teams'],'type':'Match Winner','profit':profit,'odds':{'Home':labels['Home'],'Away':labels['Away']},'stakes':stakes,'abs_profit':abs_p})
        # Handicap pair H1 vs H2
        if all(x in labels for x in ['H1','H2']):
            profit = check_surebet([labels['H1'], labels['H2']])
            if profit and profit >= min_profit:
                stakes, abs_p = compute_stakes([labels['H1'], labels['H2']])
                surebets.append({'match':m['teams'],'type':'Handicap','profit':profit,'odds':{'H1':labels['H1'],'H2':labels['H2']},'stakes':stakes,'abs_profit':abs_p})
        # Under / Over
        if all(x in labels for x in ['Under','Over']):
            profit = check_surebet([labels['Under'], labels['Over']])
            if profit and profit >= min_profit:
                stakes, abs_p = compute_stakes([labels['Under'], labels['Over']])
                surebets.append({'match':m['teams'],'type':'Totals','profit':profit,'odds':{'Under':labels['Under'],'Over':labels['Over']},'stakes':stakes,'abs_profit':abs_p})
    return surebets

# --------- Output ----------

def save_tennis(matches, surebets, source_type):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    mf = f"tennis_{source_type}_matches_{ts}.txt"
    sf = f"tennis_{source_type}_surebets_{ts}.txt"
    with open(mf,'w',encoding='utf-8') as f:
        f.write(f"Tennis Matches ({source_type}) - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write('='*60+'\n\n')
        for m in matches:
            f.write(m['teams']+'\n')
            for k,(o,b) in m['odds'].items():
                f.write(f"  {k}: {o} @ {b}\n")
            f.write('\n')
    with open(sf,'w',encoding='utf-8') as f:
        f.write(f"Tennis Surebets ({source_type}) - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write('='*60+'\n\n')
        if not surebets:
            f.write('No surebets found.\n')
        else:
            for sb in surebets:
                f.write(f"{sb['match']}\n  ✅ {sb['type']} SUREBET → Profit: {sb['profit']}%\n")
                odds_line = ', '.join(f"{k}={v[0]}" for k,v in sb['odds'].items())
                f.write(f"  Odds: {odds_line}\n\n")
    return mf, sf

# --------- Main ----------

def main():
    p = argparse.ArgumentParser(description='Enhanced Tennis Odds Analyzer')
    p.add_argument('--verbose', action='store_true')
    p.add_argument('--pages', type=int, default=1, help='Pagination pages to fetch')
    p.add_argument('--min-profit', type=float, default=0.0)
    p.add_argument('--no-headless', action='store_true')
    p.add_argument('--retries', type=int, default=2)
    args = p.parse_args()

    verbose=args.verbose
    ok = download_live_tennis(headless=not args.no_headless, retries=args.retries, pages=args.pages, verbose=verbose)
    if not ok:
        print('❌ Could not fetch tennis live data.'); return
    flat = flatten_html_to_text('live_tennis_data.txt','live_tennis_extracted.txt')
    if not flat:
        print('❌ Could not flatten tennis HTML.'); return
    with open(flat,'r',encoding='utf-8') as f: lines=[l.strip() for l in f if l.strip()]
    matches = parse_tennis_flat(lines, verbose=verbose)
    if not matches:
        print('❌ No tennis matches parsed.'); return
    print(f"📊 Parsed {len(matches)} tennis matches")
    surebets = analyze_tennis_surebets(matches, min_profit=args.min_profit)
    print(f"💰 Found {len(surebets)} tennis surebets (min-profit {args.min_profit}%)")
    mf,sf = save_tennis(matches, surebets, 'live')
    print(f"✅ Saved: {mf} & {sf}")
    if surebets:
        print('\n🎉 TENNIS SUREBET SUMMARY:')
        for sb in surebets[:10]:
            print(f"  • {sb['match']} - {sb['type']} - {sb['profit']}%")
    else:
        print('No surebet opportunities identified.')

if __name__ == '__main__':
    main()
