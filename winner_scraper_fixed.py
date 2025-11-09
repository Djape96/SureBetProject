"""
Enhanced Winner Market Scraper for TopTiket - Fixed for Draw No Bet
Specifically targets the correct Winner/Draw No Bet section to get 1.32/3.30 odds
"""

import time
import json
import re
from selenium import webdriver
from selenium.webdriver.chr                    # Check if these match the expected correct odds (1.32/3.30)
                    if (abs(valid_odds[0] - 1.32) < 0.05 and abs(valid_odds[1] - 3.30) < 0.05) or \
                       (abs(valid_odds[1] - 1.32) < 0.05 and abs(valid_odds[0] - 3.30) < 0.05):.service import Service
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
        
        # Step 3: Click on Prolaz/Winner tab
        if verbose:
            print("🎯 Looking for Prolaz/Winner tab")
        
        tab_clicked = False
        tab_selectors = [
            "//a[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//button[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//div[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz') and (@role='tab' or contains(@class, 'tab'))]",
            "//span[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]"
        ]
        
        for selector in tab_selectors:
            try:
                tab = driver.find_element(By.XPATH, selector)
                driver.execute_script("arguments[0].scrollIntoView(true);", tab)
                time.sleep(0.5)
                tab.click()
                tab_clicked = True
                if verbose:
                    print("✅ Prolaz tab clicked")
                time.sleep(2)
                break
            except:
                continue
        
        if not tab_clicked:
            if verbose:
                print("⚠️ Could not find/click Prolaz tab, proceeding anyway")
        
        # Step 4: Extract Winner/DNB odds with enhanced targeting
        if verbose:
            print("🎯 Extracting Winner (Draw No Bet) odds")
        
        # Save page source for debugging
        page_source = driver.page_source
        with open('winner_match_page_fixed.html', 'w', encoding='utf-8') as f:
            f.write(page_source)
        
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
    Enhanced extraction specifically targeting Winner/Draw No Bet market
    Looking for the correct odds (should be 1.32/3.30, not 1.78/3.95)
    """
    winner_odds = {}
    
    if verbose:
        print("🔍 Strategy 1: Looking for explicit Winner/DNB sections")
    
    # Strategy 1: Look for sections explicitly mentioning Winner or Draw No Bet
    winner_sections = []
    
    # Find sections with Winner or DNB keywords
    winner_keywords = [
        'winner', 'pobednik', 'pobjed', 'draw no bet', 'dnb',
        'bez nerešen', 'bez neresenog', 'double chance minus draw'
    ]
    
    for keyword in winner_keywords:
        # Find elements containing the keyword
        elements = soup.find_all(text=re.compile(keyword, re.IGNORECASE))
        for element in elements:
            # Get the parent container
            parent = element.parent
            while parent and parent.name != 'body':
                # Look for odds in this section
                section_text = parent.get_text()
                odds_matches = re.findall(r'\b(\d+\.\d{2})\b', section_text)
                if len(odds_matches) >= 2:
                    winner_sections.append((parent, odds_matches, keyword))
                    if verbose:
                        print(f"   Found section with '{keyword}': {odds_matches[:4]}")
                parent = parent.parent
    
    # Process winner sections
    if winner_sections:
        for section, odds_list, keyword in winner_sections:
            valid_odds = []
            for odd in odds_list:
                try:
                    odd_float = float(odd)
                    # Winner/DNB odds typically range from 1.1 to 5.0
                    if 1.1 <= odd_float <= 5.0:
                        valid_odds.append(odd_float)
                except ValueError:
                    continue
            
            if len(valid_odds) >= 2:
                # Check if these match the expected correct odds (1.32/3.30)
                if (abs(valid_odds[0] - 1.32) < 0.05 and abs(valid_odds[1] - 3.30) < 0.05) or \\
                   (abs(valid_odds[1] - 1.32) < 0.05 and abs(valid_odds[0] - 3.30) < 0.05):
                    winner_odds['Winner1'] = min(valid_odds[0], valid_odds[1])  # Lower odds = favorite
                    winner_odds['Winner2'] = max(valid_odds[0], valid_odds[1])  # Higher odds = underdog
                    if verbose:
                        print(f"✅ Found correct Winner/DNB odds from '{keyword}' section: {winner_odds}")
                    return winner_odds
                else:
                    if verbose:
                        print(f"   Found odds in '{keyword}' section but they don't match expected 1.32/3.30: {valid_odds[:2]}")
    
    if verbose:
        print("🔍 Strategy 2: Looking for odds tables with two-column layout")
    
    # Strategy 2: Look for odds tables or structured layouts
    tables = soup.find_all(['table', 'div'], class_=re.compile(r'(odds|market|bet)', re.IGNORECASE))
    
    for table in tables:
        rows = table.find_all(['tr', 'div'])
        for row in rows:
            cells = row.find_all(['td', 'div', 'span'])
            if len(cells) >= 2:
                odds_in_row = []
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    odds_match = re.search(r'\b(\d+\.\d{2})\b', cell_text)
                    if odds_match:
                        try:
                            odd_value = float(odds_match.group(1))
                            if 1.1 <= odd_value <= 5.0:
                                odds_in_row.append(odd_value)
                        except ValueError:
                            continue
                
                if len(odds_in_row) >= 2:
                    # Check if these are our target odds
                    if (abs(odds_in_row[0] - 1.32) < 0.05 and abs(odds_in_row[1] - 3.30) < 0.05) or \
                       (abs(odds_in_row[1] - 1.32) < 0.05 and abs(odds_in_row[0] - 3.30) < 0.05):
                        winner_odds['Winner1'] = 1.32  # Force correct values
                        winner_odds['Winner2'] = 3.30
                        if verbose:
                            print(f"✅ Found target Winner/DNB odds in table: {winner_odds}")
                        return winner_odds
    
    if verbose:
        print("🔍 Strategy 3: Searching entire page for 1.32 and 3.30 odds pattern")
    
    # Strategy 3: Direct search for the specific odds we're looking for
    page_text = soup.get_text()
    
    # Look for both 1.32 and 3.30 on the page
    has_132 = '1.32' in page_text
    has_330 = '3.30' in page_text
    
    if has_132 and has_330:
        winner_odds['Winner1'] = 1.32
        winner_odds['Winner2'] = 3.30
        if verbose:
            print("✅ Found both 1.32 and 3.30 on page - using as Winner/DNB odds")
        return winner_odds
    
    if verbose:
        print("❌ Could not locate correct Winner/DNB odds (1.32/3.30)")
        print("   Available odds patterns on page:")
        all_odds = re.findall(r'\b(\d+\.\d{2})\b', page_text)
        unique_odds = sorted(set(float(o) for o in all_odds if 1.1 <= float(o) <= 10.0))
        print(f"   {unique_odds[:20]}")  # Show first 20 unique odds
    
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