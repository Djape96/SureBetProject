import re
import glob
import time
import os
import json
import hashlib
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from telegram_notifier import send_surebets_summary  # Telegram integration
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# Configuration flags (mirroring football implementation)
THREE_DAY_ONLY = True  # Go straight to 3-day ("3 dana") view
EXPECTED_3D_PAGES = 27  # User hinted page count target (may differ for tennis)
FORCE_MAX_3D_PAGES = 30  # Hard cap safety
MIN_ODDS = 1.01
MAX_ODDS = 80.0

print("🚀 Starting TopTiket Tennis Arbitrage Scraper...")

def _extract_matches_dom(driver):
    """Extract tennis matches from DOM heuristically (aligned to observed layout).

    Observed raw text pattern per match (after filtering navigation):
        <day marker>
        HH:MM
        Player1
        Player2
        1.60   (home)
        2.55   (away)
        1.80   (H1 value)
        -1.5   (handicap line -> skip as non decimal odds)
        1.93   (H2 value)
        1.89   (Under)
        20.5   (total line -> skip)
        1.88   (Over)
        +34    (expander / ignore)

    We therefore treat a match as:
        time line -> two player name lines -> sequence of tokens where
          - valid odds are numeric with optional decimal (float-able) AND within MIN/MAX range
          - handicap / total line tokens (contain '+' or '-' or end with '.5' but followed by odds) are separators, not odds values

    We map first 2 odds -> Home/Away, next 2 odds -> H1/H2, next 2 -> Under/Over (if present).
    """
    results = []
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        raw_tokens = []
        for el in soup.find_all(string=True):
            t = el.strip()
            if not t: continue
            if len(t) > 70: continue
            raw_tokens.append(t)
        time_pat = re.compile(r'^\d{1,2}:\d{2}$')
        number_pat = re.compile(r'^-?\d+(?:[\.,]\d+)?$')
        i = 0
        n = len(raw_tokens)
        while i < n:
            if time_pat.match(raw_tokens[i]):
                match_time = raw_tokens[i]
                if i+2 < n:
                    p1 = raw_tokens[i+1]
                    p2 = raw_tokens[i+2]
                    if (re.match(r'^[A-Za-zČĆŽŠĐšđčćž\s\.,\-]{3,}$', p1) and
                        re.match(r'^[A-Za-zČĆŽŠĐšđčćž\s\.,\-]{3,}$', p2) and p1.lower() != p2.lower()):
                        j = i + 3
                        odds_home = odds_away = None
                        h1 = h2 = None
                        under = over = None
                        handicap_line = None
                        total_line = None
                        phase = 0  # 0=match,1=handicap,2=totals
                        safety = 0
                        def is_potential_line(token: str, numeric: float, phase: int) -> bool:
                            # Handicap lines: may be -1.5, 4.5 (no sign) etc; totals lines: 19.5, 21.5 etc (>10 and .5)
                            if phase == 1:  # handicap
                                if any(ch in token for ch in ['+','-']) and token.replace('+','').replace('-','').replace(',','.').replace('.','',1).isdigit():
                                    return True
                                # plain 4.5 / 2.5 style and followed later by another odds -> treat as line if endswith .5
                                if token.endswith('.5') or token.endswith(',5'):
                                    return True
                            if phase == 2:  # totals
                                if (token.endswith('.5') or token.endswith(',5')) and numeric and numeric > 10:
                                    return True
                            return False
                        while j < n and safety < 50:
                            safety += 1
                            tok = raw_tokens[j]
                            if time_pat.match(tok):  # next match reached
                                break
                            if tok.startswith('+') and tok[1:].isdigit():  # expansion control
                                j += 1
                                break
                            numeric = None
                            try:
                                numeric = float(tok.replace(',', '.'))
                            except ValueError:
                                numeric = None
                            if phase == 0:  # match winner expects 2 odds
                                if numeric is not None and MIN_ODDS <= numeric <= MAX_ODDS:
                                    if odds_home is None:
                                        odds_home = numeric
                                    elif odds_away is None:
                                        odds_away = numeric
                                        phase = 1
                                    else:
                                        # Extra numeric before switching phases: ignore
                                        pass
                                else:
                                    # non numeric break not expected yet
                                    if odds_home and odds_away:
                                        phase = 1
                                j += 1
                                continue
                            if phase == 1:  # handicap: H1 odd, line, H2 odd
                                if h1 is None:
                                    if numeric is not None and MIN_ODDS <= numeric <= MAX_ODDS:
                                        h1 = numeric
                                        j += 1
                                        continue
                                    else:
                                        j += 1
                                        continue
                                if handicap_line is None:
                                    if numeric is not None and is_potential_line(tok, numeric, phase):
                                        handicap_line = tok
                                        j += 1
                                        continue
                                    # If not a line but an odds -> might be h2 directly (no displayed line)
                                    if numeric is not None and MIN_ODDS <= numeric <= MAX_ODDS:
                                        h2 = numeric
                                        phase = 2
                                        j += 1
                                        continue
                                    j += 1
                                    continue
                                if h2 is None:
                                    if numeric is not None and MIN_ODDS <= numeric <= MAX_ODDS:
                                        h2 = numeric
                                        phase = 2
                                    j += 1
                                    continue
                                # If all set move to totals
                                phase = 2
                                continue
                            if phase == 2:  # totals: first odd, line, second odd
                                if under is None:
                                    if numeric is not None and MIN_ODDS <= numeric <= MAX_ODDS:
                                        under = numeric
                                    j += 1
                                    continue
                                if total_line is None:
                                    if numeric is not None and is_potential_line(tok, numeric, phase):
                                        total_line = tok
                                        j += 1
                                        continue
                                    # If not a line and an odds we assume no line visible -> treat as over and finish
                                    if numeric is not None and MIN_ODDS <= numeric <= MAX_ODDS:
                                        over = numeric
                                        phase = 3
                                    j += 1
                                    continue
                                if over is None:
                                    if numeric is not None and MIN_ODDS <= numeric <= MAX_ODDS:
                                        over = numeric
                                    j += 1
                                    phase = 3
                                    continue
                                # Completed totals
                                phase = 3
                                j += 1
                                continue
                            if phase >= 3:
                                break
                        if odds_home and odds_away:
                            rec = {
                                'time': match_time,
                                'player1': p1,
                                'player2': p2,
                                'odds': {}
                            }
                            rec['odds']['Home'] = odds_home
                            rec['odds']['Away'] = odds_away
                            if h1 and h2:
                                rec['odds']['H1'] = h1
                                rec['odds']['H2'] = h2
                            if under and over:
                                rec['odds']['Under'] = under
                                rec['odds']['Over'] = over
                            if handicap_line:
                                rec['handicap_line'] = handicap_line
                            if total_line:
                                rec['total_line'] = total_line
                            results.append(rec)
                            i = j
                            continue
            i += 1
    except Exception as e:
        print(f"⚠️ Tennis DOM extraction error: {e}")
    return results

def _init_driver():
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1920,1080')
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

def _click_three_day(driver):
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
    # JS brute force
    try:
        js = """
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
        const targets = [];
        while(walker.nextNode()){
          const el = walker.currentNode;
          const t = (el.innerText||'').trim().toLowerCase();
          if(t === '3 dana' || t.startsWith('3 dana')) targets.push(el);
        }
        return targets.map(e=>{e.scrollIntoView({block:'center'}); e.click(); return e.innerText;});
        """
        res = driver.execute_script(js)
        if res:
            time.sleep(2)
            return True
    except Exception:
        pass
    return False

def _scan_max_page(driver):
    max_found = 1
    try:
        pag_elems = driver.find_elements(By.XPATH, "//nav//*[self::a or self::button][normalize-space()]|//*[contains(@class,'pagination')]//*[self::a or self::button][normalize-space()]")
        for el in pag_elems:
            t = el.text.strip()
            if t.isdigit():
                val = int(t)
                if 1 <= val <= 150:
                    max_found = max(max_found, val)
    except Exception:
        pass
    return max_found

def _save_page(driver, prefix, page_no, dom_matches_all, visited_hashes):
    page_source = driver.page_source
    h = hashlib.md5(page_source.encode('utf-8')).hexdigest()
    if h in visited_hashes:
        print(f"⚠️ Duplicate page hash skip p{page_no}")
        return 0
    visited_hashes.add(h)
    soup = BeautifulSoup(page_source, 'html.parser')
    text_content = soup.get_text('\n', strip=True)
    lines = [ln.strip() for ln in text_content.split('\n') if ln.strip() and not any(sk in ln.lower() for sk in ['cookie','javascript','gtm','script','function','window','document','meta','charset','viewport'])]
    filename = f"{prefix}{page_no}.txt"
    with open(filename,'w',encoding='utf-8') as f:
        f.write('\n'.join(lines))
    dom_matches = _extract_matches_dom(driver)
    for m in dom_matches:
        m['page'] = page_no
        m['range'] = '3d'
    dom_matches_all.extend(dom_matches)
    print(f"✅ Saved {filename} | DOM matches {len(dom_matches)}")
    return len(dom_matches)

def download_tennis():
    # Clean old
    for old in glob.glob('tennis_3d_index_*.txt'):
        try: os.remove(old)
        except Exception: pass
    driver = _init_driver()
    try:
        print('🌐 Opening tennis odds page ...')
        driver.get('https://toptiket.rs/odds/tennis')
        WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
        time.sleep(3)
        print('🔀 Switching to 3-day view...')
        if not _click_three_day(driver):
            print("❌ '3 dana' control not found for tennis. Aborting 3-day scrape.")
            return []
        # Pre-load scroll
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);"); time.sleep(1.0)
            driver.execute_script("window.scrollTo(0,0);"); time.sleep(0.6)
        dom_matches_all = []
        visited_hashes = set()
        prefix = 'tennis_3d_index_'
        current_page = 1
        _save_page(driver, prefix, current_page, dom_matches_all, visited_hashes)
        max_seen = _scan_max_page(driver)
        print(f"📄 Initial tennis max page detected: {max_seen}")
        hard_cap = FORCE_MAX_3D_PAGES
        while current_page < hard_cap:
            max_seen = max(max_seen, _scan_max_page(driver))
            if current_page >= max_seen:
                if max_seen >= EXPECTED_3D_PAGES:
                    print(f"✅ Reached detected last tennis page {max_seen}")
                    break
            next_page = current_page + 1
            clicked = False
            # Direct numeric
            for sel in [
                f"//a[normalize-space()='{next_page}']",
                f"//button[normalize-space()='{next_page}']",
                f"//li[a[normalize-space()='{next_page}']]//a"
            ]:
                try:
                    el = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.XPATH, sel)))
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    driver.execute_script("arguments[0].click();", el)
                    clicked = True
                    print(f"➡️ Clicked tennis page {next_page}")
                    time.sleep(1.4)
                    break
                except Exception:
                    continue
            if not clicked:
                # Arrow fallback
                for arrow_sel in [
                    "//a[contains(.,'›')]",
                    "//button[contains(.,'›')]",
                    "//a[contains(@aria-label,'Next')]",
                    "//button[contains(@aria-label,'Next')]"
                ]:
                    try:
                        el = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.XPATH, arrow_sel)))
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        driver.execute_script("arguments[0].click();", el)
                        clicked = True
                        print("➡️ Clicked tennis next arrow")
                        time.sleep(1.4)
                        break
                    except Exception:
                        continue
            if not clicked:
                print(f"⚠️ Tennis pagination stopped at page {current_page}")
                break
            # Small wait for content change
            base_hash = hashlib.md5(driver.page_source.encode('utf-8')).hexdigest()
            for _ in range(6):
                time.sleep(0.5)
                new_hash = hashlib.md5(driver.page_source.encode('utf-8')).hexdigest()
                if new_hash != base_hash:
                    break
            current_page += 1
            _save_page(driver, prefix, current_page, dom_matches_all, visited_hashes)
        print(f"🏁 Tennis pagination ended at page {current_page}; max seen {max_seen}")
        return dom_matches_all
    finally:
        driver.quit()

def detect_tennis_surebets(matches):
    results = []
    for m in matches:
        odds = m['odds']
        # Match Winner
        if all(k in odds for k in ['Home','Away']):
            o1, o2 = odds['Home'], odds['Away']
            inv = (1/o1)+(1/o2)
            if inv < 1:
                margin = (1-inv)*100
                roi = ((1/inv)-1)*100
                total = 100.0
                stake1 = (1/o1)/inv * total
                stake2 = (1/o2)/inv * total
                results.append({
                    'match': m,
                    'type': 'Match Winner',
                    'margin_pct': round(margin,2),
                    'roi_pct': round(roi,2),
                    'stakes': {'Home': round(stake1,2), 'Away': round(stake2,2)},
                    'odds_str': f"Home={o1}, Away={o2}"
                })
        # Handicap pair
        if all(k in odds for k in ['H1','H2']):
            h1, h2 = odds['H1'], odds['H2']
            inv = (1/h1)+(1/h2)
            if inv < 1:
                margin = (1-inv)*100
                roi = ((1/inv)-1)*100
                total = 100.0
                stake1 = (1/h1)/inv * total
                stake2 = (1/h2)/inv * total
                results.append({
                    'match': m,
                    'type': 'Handicap',
                    'margin_pct': round(margin,2),
                    'roi_pct': round(roi,2),
                    'stakes': {'H1': round(stake1,2), 'H2': round(stake2,2)},
                    'odds_str': f"H1={h1}, H2={h2}"
                })
        # Totals pair
        if all(k in odds for k in ['Under','Over']):
            u, o = odds['Under'], odds['Over']
            inv = (1/u)+(1/o)
            if inv < 1:
                margin = (1-inv)*100
                roi = ((1/inv)-1)*100
                total = 100.0
                stakeu = (1/u)/inv * total
                stakeo = (1/o)/inv * total
                results.append({
                    'match': m,
                    'type': 'Totals',
                    'margin_pct': round(margin,2),
                    'roi_pct': round(roi,2),
                    'stakes': {'Under': round(stakeu,2), 'Over': round(stakeo,2)},
                    'odds_str': f"Under={u}, Over={o}"
                })
    return results

def main():
    import argparse
    ap = argparse.ArgumentParser(description='TopTiket Tennis Arbitrage Scraper')
    ap.add_argument('--notify-min-roi', type=float, default=float(os.environ.get('TENNIS_NOTIFY_MIN_ROI', '2.5')), help='Minimum ROI%% required to send a Telegram notification (default 2.5)')
    ap.add_argument('--notify-max-roi', type=float, default=float(os.environ.get('TENNIS_NOTIFY_MAX_ROI', '20')), help='Maximum ROI%% (upper bound) to notify; values above treated as likely data errors (default 20)')
    ap.add_argument('--no-telegram', action='store_true', help='Skip Telegram sending entirely')
    args = ap.parse_args()

    dom_matches = download_tennis()
    if not dom_matches:
        print('❌ No tennis DOM matches captured.')
        return
    # Dedupe
    deduped = []
    seen = set()
    for m in dom_matches:
        key = (m.get('time'), m['player1'], m['player2'], tuple(m['odds'].values()))
        if key in seen: continue
        seen.add(key)
        deduped.append(m)
    print(f"✅ Tennis unique DOM matches: {len(deduped)}")
    with open('tennis_dom_matches.json','w',encoding='utf-8') as jf:
        json.dump(deduped, jf, ensure_ascii=False, indent=2)
    surebets = detect_tennis_surebets(deduped)
    # Simplified output file: only individual surebet lines (no headers/stats/stakes)
    with open('tennis_surebets.txt','w',encoding='utf-8') as f:
        if surebets:
            grouped = {}
            for sb in surebets:
                m = sb['match']
                ident = (m.get('time'), f"{m['player1']} vs {m['player2']}")
                grouped.setdefault(ident, []).append(sb)
            def best_roi(group): return max(item['roi_pct'] for item in group)
            for ident, group in sorted(grouped.items(), key=lambda kv: best_roi(kv[1]), reverse=True):
                tm, teams = ident
                for bet in sorted(group, key=lambda x: x['type']):
                    f.write(f"{tm or '?'} | {teams}\n  {bet['type']}: ROI {bet['roi_pct']}% | Margin {bet['margin_pct']}% | {bet['odds_str']}\n\n")
        else:
            f.write('No surebets.\n')
    print('✅ Tennis analysis complete!')
    print(f"🎯 Found {len(surebets)} tennis surebets")
    # Filter for notification
    filtered_notify = [sb for sb in surebets if args.notify_min_roi <= sb['roi_pct'] <= args.notify_max_roi]
    print(f"🔎 Tennis notify filter: ROI between {args.notify_min_roi}% and {args.notify_max_roi}% -> {len(filtered_notify)} candidates")
    if args.no_telegram:
        print('ℹ️ Tennis Telegram sending skipped by --no-telegram flag.')
        return
    if not filtered_notify:
        print('ℹ️ No tennis surebets within desired ROI range; no Telegram message sent.')
        return
    try:
        send_surebets_summary(filtered_notify, len(deduped))
        print("📨 Tennis Telegram summary attempted (filtered).")
    except Exception as e:
        print(f"⚠️ Tennis Telegram send failed: {e}")

if __name__ == '__main__':
    main()
