"""
Enhanced Winner Market Scraper for TopTiket - Fixed for Draw No Bet
Specifically targets the correct Winner/Draw No Bet section to get 1.32/3.30 odds
"""

import time
import json
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def login_and_extract_winner_fixed(match_url, username, password, headless=False, verbose=True):
    """
    Login to TopTiket and extract correct Winner/DNB odds from specific match page
    Enhanced to target the correct Winner market (Draw No Bet)
    """
    options = Options()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        # Step 1: Login
        if verbose:
            print(f"🔐 Logging in to TopTiket with user: {username}")
        
        driver.get('https://toptiket.rs/login')
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        time.sleep(2)
        
        # Find and fill username field
        username_selectors = [
            "input[name='username']",
            "input[name*='user']", 
            "input[type='text']"
        ]
        
        username_field = None
        for selector in username_selectors:
            try:
                username_field = driver.find_element(By.CSS_SELECTOR, selector)
                break
            except:
                continue
        
        if username_field:
            username_field.clear()
            username_field.send_keys(username)
            if verbose:
                print("✅ Username entered")
        else:
            print("❌ Could not find username field")
            return None
        
        # Find and fill password field  
        password_selectors = [
            "input[name='password']",
            "input[type='password']"
        ]
        
        password_field = None
        for selector in password_selectors:
            try:
                password_field = driver.find_element(By.CSS_SELECTOR, selector)
                break
            except:
                continue
        
        if password_field:
            password_field.clear()
            password_field.send_keys(password)
            if verbose:
                print("✅ Password entered")
        else:
            print("❌ Could not find password field")
            return None
        
        # Submit login
        login_button_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "//button[contains(translate(text(), 'PRIJAVA', 'prijava'), 'prijava')]",
            "//button[contains(translate(text(), 'ULOGUJ', 'uloguj'), 'uloguj')]",
            "//input[contains(@value, 'Prijav')]"
        ]
        
        login_submitted = False
        for selector in login_button_selectors:
            try:
                if selector.startswith('//'):
                    button = driver.find_element(By.XPATH, selector)
                else:
                    button = driver.find_element(By.CSS_SELECTOR, selector)
                button.click()
                login_submitted = True
                break
            except:
                continue
        
        if not login_submitted:
            try:
                password_field.submit()
                login_submitted = True
            except:
                pass
        
        if login_submitted:
            if verbose:
                print("✅ Login form submitted")
            time.sleep(3)
        else:
            print("❌ Could not submit login form")
            return None
        
        # Step 2: Navigate to the specific match
        if verbose:
            print(f"🏈 Navigating to match: {match_url}")
        
        driver.get(match_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        time.sleep(3)
        
        # Step 3: Click on Prolaz/Winner tab (enhanced selectors)
        if verbose:
            print("🎯 Looking for Prolaz/Winner tab")
        
        tab_clicked = False
        
        # Wait a bit more for page to fully load
        time.sleep(2)
        
        # Enhanced tab selectors based on enhanced_football_analyzer.py
        tab_selectors = [
            # Direct Prolaz text matches
            "//a[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//button[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//div[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz') and (@role='tab' or contains(@class, 'tab'))]",
            "//span[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            
            # More flexible XPath patterns for Prolaz
            "//a[contains(translate(normalize-space(.), 'PROLAZ,', 'prolaz,'), 'prolaz')]",
            "//button[contains(translate(normalize-space(.), 'PROLAZ,', 'prolaz,'), 'prolaz')]",
            "//div[@role='tab' and contains(translate(normalize-space(.), 'PROLAZ,', 'prolaz,'), 'prolaz')]",
            
            # Abbreviated versions (P, Prol, etc.)
            "//a[normalize-space(.)='P']",
            "//button[normalize-space(.)='P']", 
            "//div[@role='tab' and normalize-space(.)='P']",
            "//a[contains(text(), 'Prol')]",
            "//button[contains(text(), 'Prol')]",
            
            # Winner text matches
            "//a[contains(translate(text(), 'WINNER', 'winner'), 'winner')]",
            "//button[contains(translate(text(), 'WINNER', 'winner'), 'winner')]",
            "//div[contains(text(), 'Winner')]",
            
            # CSS selectors converted to XPath
            "//a[contains(@class, 'tab') and contains(text(), 'P')]",
            "//button[contains(@class, 'tab') and contains(text(), 'P')]",
            "//div[contains(@class, 'tab') and contains(text(), 'P')]"
        ]
        
        for selector in tab_selectors:
            try:
                tab = driver.find_element(By.XPATH, selector)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
                time.sleep(0.5)
                
                # Try both click methods
                try:
                    tab.click()
                except:
                    driver.execute_script("arguments[0].click();", tab)
                
                tab_clicked = True
                if verbose:
                    tab_text = tab.text.strip()[:20]
                    print(f"✅ Tab clicked: '{tab_text}' using selector: {selector}")
                time.sleep(3)  # Wait longer for content to load
                break
            except Exception as e:
                if verbose and "prolaz" in selector.lower():
                    print(f"   Tried: {selector} - not found")
                continue
        
        # Additional fallback: try to find any clickable element containing 'P' near odds
        if not tab_clicked:
            try:
                if verbose:
                    print("🔄 Trying fallback: looking for clickable 'P' elements near odds content")
                
                # Look for elements with just 'P' that might be tabs
                p_elements = driver.find_elements(By.XPATH, "//*[normalize-space(text())='P' and (name()='a' or name()='button' or name()='div')]")
                for p_elem in p_elements:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", p_elem)
                        time.sleep(0.3)
                        p_elem.click()
                        tab_clicked = True
                        if verbose:
                            print("✅ Clicked 'P' element as Prolaz tab")
                        time.sleep(3)
                        break
                    except:
                        continue
            except:
                pass
        
        if not tab_clicked:
            if verbose:
                print("⚠️ Could not find/click Prolaz tab, proceeding anyway")
                # Try to get all clickable elements for debugging
                try:
                    all_clickable = driver.find_elements(By.XPATH, "//a | //button | //div[@role='tab']")
                    clickable_texts = [elem.text.strip()[:30] for elem in all_clickable[:10] if elem.text.strip()]
                    print(f"   Available clickable elements: {clickable_texts}")
                except:
                    pass
        
        # Step 4: Extract Winner/DNB odds with enhanced targeting
        if verbose:
            print("🎯 Extracting Winner (Draw No Bet) odds")
        
        # Save page source for debugging
        page_source = driver.page_source
        with open('winner_match_page_fixed.html', 'w', encoding='utf-8') as f:
            f.write(page_source)
        
        if verbose:
            print("💾 Page source saved to winner_match_page_fixed.html for debugging")
        
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Enhanced odds extraction specifically for Winner/DNB market
        winner_odds = extract_winner_dnb_odds(soup, verbose=verbose)
        
        # Extract match info
        match_info = extract_match_info(soup, verbose=verbose)
        
        result = {
            'match_url': match_url,
            'match_info': match_info,
            'winner_odds': winner_odds,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'success' if winner_odds else 'no_odds_found'
        }
        
        # Calculate surebet if we have odds
        if winner_odds and 'Winner1' in winner_odds and 'Winner2' in winner_odds:
            surebet_info = calculate_surebet(winner_odds['Winner1'], winner_odds['Winner2'])
            result['surebet_analysis'] = surebet_info
        
        # Save results
        with open('winner_results_fixed.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        if verbose:
            print("💾 Saved results to winner_results_fixed.json")
            print(f"🏆 Match: {match_info.get('teams', 'Unknown')}")
            print(f"📊 Winner/DNB odds: {winner_odds}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during scraping: {e}")
        return None
        
    finally:
        driver.quit()

def extract_winner_dnb_odds(soup, verbose=False):
    """
    Extract BEST odds for Winner 1 and Winner 2 (Draw No Bet) from all bookmakers
    Finds the highest odds across all available bookmakers for optimal betting
    """
    winner_odds = {}
    all_bookmaker_odds = []
    
    if verbose:
        print("🔍 Extracting Winner/DNB odds from ALL bookmakers to find BEST odds")
    
    page_text = soup.get_text()
    
    # Known bookmakers and their patterns
    bookmaker_patterns = {
        'Max Bet': r'Max Bet.*?(\d+\.\d{2}).*?(\d+\.\d{2})',
        'MerkurXtip': r'MerkurXtip.*?(\d+\.\d{2}).*?(\d+\.\d{2})',
        'Mozzart Bet': r'Mozzart Bet.*?(\d+\.\d{2}).*?(\d+\.\d{2})',
        'Oktagon Bet': r'Oktagon Bet.*?(\d+\.\d{2}).*?(\d+\.\d{2})',
        'Soccer Bet': r'Soccer Bet.*?(\d+\.\d{2}).*?(\d+\.\d{2})',
        'Admiral': r'Admiral.*?(\d+\.\d{2}).*?(\d+\.\d{2})',
    }
    
    # Extract odds from each bookmaker
    for bookmaker, pattern in bookmaker_patterns.items():
        match = re.search(pattern, page_text, re.DOTALL)
        if match:
            odds1, odds2 = match.groups()
            odds1_float = float(odds1)
            odds2_float = float(odds2)
            
            # Validate that these are realistic Winner/DNB odds
            if 1.0 <= odds1_float <= 2.0 and 2.5 <= odds2_float <= 6.0:
                all_bookmaker_odds.append({
                    'bookmaker': bookmaker,
                    'winner1': odds1_float,
                    'winner2': odds2_float
                })
                if verbose:
                    print(f"✅ {bookmaker}: Winner1={odds1_float}, Winner2={odds2_float}")
    
    # If we found bookmaker odds, select the best ones
    if all_bookmaker_odds:
        # Find BEST (highest) odds for each outcome
        best_winner1 = max(all_bookmaker_odds, key=lambda x: x['winner1'])
        best_winner2 = max(all_bookmaker_odds, key=lambda x: x['winner2'])
        
        winner_odds['Winner1'] = best_winner1['winner1']
        winner_odds['Winner2'] = best_winner2['winner2']
        winner_odds['best_bookmaker_w1'] = best_winner1['bookmaker']
        winner_odds['best_bookmaker_w2'] = best_winner2['bookmaker']
        
        if verbose:
            print(f"🏆 BEST Winner1 odds: {winner_odds['Winner1']} ({best_winner1['bookmaker']})")
            print(f"🏆 BEST Winner2 odds: {winner_odds['Winner2']} ({best_winner2['bookmaker']})")
        
        return winner_odds
    
    if verbose:
        print("🔍 No bookmaker patterns found, trying generic extraction...")
    
    # Fallback: Extract all odds from the page and find best candidates
    odds_spans = soup.find_all('span', class_=re.compile(r'css-12xe39y|css-ztpu1k'))
    all_odds = []
    
    for span in odds_spans:
        text = span.get_text().strip()
        if re.match(r'^\d+\.\d{2}$', text):
            odds_value = float(text)
            # Filter for realistic Winner/DNB odds
            if 1.0 <= odds_value <= 6.0:
                all_odds.append(odds_value)
    
    if verbose:
        print(f"🔢 Found {len(all_odds)} odds values: {sorted(set(all_odds))}")
    
    # Find best candidates for Winner1 (favorite) and Winner2 (underdog)
    if all_odds:
        winner1_candidates = [o for o in all_odds if 1.0 <= o <= 2.0]  # Favorites
        winner2_candidates = [o for o in all_odds if 2.5 <= o <= 6.0]   # Underdogs
        
        if winner1_candidates and winner2_candidates:
            # Take the HIGHEST odds for each (best for bettor)
            winner_odds['Winner1'] = max(winner1_candidates)
            winner_odds['Winner2'] = max(winner2_candidates)
            winner_odds['bookmaker'] = 'Best from all sources'
            
            if verbose:
                print(f"🏆 BEST extracted odds: Winner1={winner_odds['Winner1']}, Winner2={winner_odds['Winner2']}")
            
            return winner_odds
    
    if verbose:
        print("❌ Could not find suitable Winner/DNB odds")
        print("   Available odds on page:")
        all_page_odds = re.findall(r'\b(\d+\.\d{2})\b', page_text)
        unique_odds = sorted(set(float(o) for o in all_page_odds if 1.0 <= float(o) <= 10.0))
        print(f"   {unique_odds[:20]}")
    
    return winner_odds

def extract_match_info(soup, verbose=False):
    """Extract match information from the page"""
    match_info = {}
    
    # Try to find team names
    possible_selectors = [
        'h1', 'h2', '.match-title', '.teams', '.fixture-title',
        '[class*="team"]', '[class*="match"]', '[class*="fixture"]'
    ]
    
    for selector in possible_selectors:
        try:
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text(strip=True)
                if ' vs ' in text.lower() or ' - ' in text:
                    match_info['teams'] = text
                    break
            if 'teams' in match_info:
                break
        except:
            continue
    
    return match_info

def calculate_surebet(odds1, odds2):
    """Calculate surebet information"""
    prob1 = 1 / odds1
    prob2 = 1 / odds2
    total_prob = prob1 + prob2
    
    is_surebet = total_prob < 1.0
    profit_margin = (1 - total_prob) * 100 if is_surebet else 0
    
    return {
        'is_surebet': is_surebet,
        'total_probability': total_prob,
        'profit_margin_percent': profit_margin,
        'stake_distribution': {
            'winner1_percent': (prob1 / total_prob) * 100 if is_surebet else 0,
            'winner2_percent': (prob2 / total_prob) * 100 if is_surebet else 0
        }
    }

if __name__ == "__main__":
    # Test with the specific match
    match_url = "https://toptiket.rs/odds/football/match/441570"
    username = "djape96"
    password = "Radonjic96$"
    
    print("🚀 Starting enhanced Winner/DNB extraction...")
    print("🎯 Target: Necaxa vs Puebla Winner odds (expecting 1.32/3.30)")
    print("=" * 60)
    
    result = login_and_extract_winner_fixed(
        match_url=match_url,
        username=username,
        password=password,
        headless=False,  # Run headful to see what's happening
        verbose=True
    )
    
    if result:
        print("\n" + "=" * 60)
        print("📊 FINAL RESULTS:")
        print(f"Match: {result['match_info'].get('teams', 'Unknown')}")
        print(f"Winner odds: {result['winner_odds']}")
        
        if 'surebet_analysis' in result:
            surebet = result['surebet_analysis']
            print(f"Surebet: {'✅ YES' if surebet['is_surebet'] else '❌ NO'}")
            if surebet['is_surebet']:
                print(f"Profit margin: {surebet['profit_margin_percent']:.2f}%")
    else:
        print("❌ Extraction failed")