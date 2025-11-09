"""
Direct Winner Market Scraper for TopTiket
Navigates directly to specific match pages and extracts Winner 1/Winner 2 odds
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

def login_and_extract_winner(match_url, username, password, headless=False, verbose=True):
    """
    Login to TopTiket and extract Winner odds from a specific match page
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
            "input[type='text']",
            "input[placeholder*='user']",
            "input[placeholder*='korisn']"
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
                print("✅ Username field filled")
        else:
            print("❌ Could not find username field")
            return None
        
        # Find and fill password field
        password_selectors = [
            "input[name='password']",
            "input[type='password']",
            "input[placeholder*='pass']",
            "input[placeholder*='lozin']"
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
                print("✅ Password field filled")
        else:
            print("❌ Could not find password field")
            return None
        
        # Submit login
        login_button_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:contains('Prijavi')",
            "button:contains('Login')",
            "//button[contains(text(), 'Prijavi')]",
            "//button[contains(text(), 'Login')]"
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
            # Try submitting the form by pressing Enter on password field
            try:
                password_field.submit()
                login_submitted = True
            except:
                pass
        
        if login_submitted:
            if verbose:
                print("✅ Login form submitted")
            time.sleep(3)  # Wait for login to process
        else:
            print("❌ Could not submit login form")
            return None
        
        # Step 2: Navigate to the specific match
        if verbose:
            print(f"🏈 Navigating to match: {match_url}")
        
        driver.get(match_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        time.sleep(2)
        
        # Step 3: Click on Prolaz/Winner tab
        if verbose:
            print("🎯 Looking for Prolaz/Winner tab")
        
        tab_selectors = [
            "//a[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//button[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//div[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//span[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//a[contains(translate(text(), 'WINNER', 'winner'), 'winner')]",
            "//button[contains(translate(text(), 'WINNER', 'winner'), 'winner')]",
            "//div[contains(text(), 'Winner')]",
            "//span[contains(text(), 'Winner')]",
            "//a[text()='Prolaz']",
            "//button[text()='Prolaz']"
        ]
        
        tab_clicked = False
        for selector in tab_selectors:
            try:
                tab = driver.find_element(By.XPATH, selector)
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
                time.sleep(0.5)
                tab.click()
                tab_clicked = True
                if verbose:
                    print(f"✅ Clicked tab with selector: {selector}")
                time.sleep(2)
                break
            except Exception as e:
                continue
        
        if not tab_clicked:
            if verbose:
                print("⚠️ Could not find Prolaz/Winner tab, continuing with current page")
        
        # Step 4: Extract the page content
        page_source = driver.page_source
        
        # Save HTML for inspection
        with open('winner_match_page.html', 'w', encoding='utf-8') as f:
            f.write(page_source)
        
        if verbose:
            print("💾 Saved page HTML to winner_match_page.html")
        
        # Step 5: Parse Winner odds
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Look for Winner 1 and Winner 2 odds
        winner_odds = extract_winner_odds(soup, verbose=verbose)
        
        # Extract match info
        match_info = extract_match_info(soup, verbose=verbose)
        
        result = {
            'match_url': match_url,
            'match_info': match_info,
            'winner_odds': winner_odds,
            'page_title': driver.title
        }
        
        # Save results to JSON
        with open('winner_results.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        if verbose:
            print("💾 Saved results to winner_results.json")
            print(f"🏆 Match: {match_info.get('teams', 'Unknown')}")
            print(f"📊 Winner odds: {winner_odds}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during scraping: {e}")
        return None
        
    finally:
        driver.quit()

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
    
    # Try to find date/time
    time_patterns = [r'\d{1,2}:\d{2}', r'\d{1,2}\.\s*\d{1,2}\.', r'\d{1,2}/\d{1,2}']
    page_text = soup.get_text()
    
    for pattern in time_patterns:
        matches = re.findall(pattern, page_text)
        if matches:
            match_info['time'] = matches[0]
            break
    
    return match_info

def extract_winner_odds(soup, verbose=False):
    """Extract Winner 1 and Winner 2 odds from the page"""
    winner_odds = {}
    
    # Look for sections containing "winner" or "prolaz"
    page_text = soup.get_text().lower()
    
    if verbose:
        print("🔍 Searching for Winner odds...")
    
    # Strategy 1: Look for sections with "winner" or "prolaz" keywords
    possible_sections = soup.find_all(lambda tag: tag.name in ['div', 'section', 'table', 'tbody'] and 
                                     ('winner' in tag.get_text().lower() or 'prolaz' in tag.get_text().lower()))
    
    for section in possible_sections:
        odds_found = extract_odds_from_section(section, verbose=verbose)
        if odds_found:
            winner_odds.update(odds_found)
            break
    
    # Strategy 2: Look for any two-outcome markets (often Winner markets)
    if not winner_odds:
        if verbose:
            print("🔍 Looking for any two-outcome markets...")
        
        # Find all elements with odds-like numbers
        odds_pattern = r'\b(\d+\.\d{2})\b'
        all_elements = soup.find_all(lambda tag: tag.string and re.search(odds_pattern, tag.string))
        
        # Group nearby odds
        potential_pairs = []
        for i, elem in enumerate(all_elements):
            odds_text = elem.get_text(strip=True)
            odds_match = re.search(odds_pattern, odds_text)
            if odds_match:
                odds_value = float(odds_match.group(1))
                if 1.1 <= odds_value <= 10.0:  # Reasonable odds range
                    # Look for nearby elements with similar odds
                    for j in range(i+1, min(i+5, len(all_elements))):
                        next_elem = all_elements[j]
                        next_odds_text = next_elem.get_text(strip=True)
                        next_odds_match = re.search(odds_pattern, next_odds_text)
                        if next_odds_match:
                            next_odds_value = float(next_odds_match.group(1))
                            if 1.1 <= next_odds_value <= 10.0:
                                potential_pairs.append((odds_value, next_odds_value))
                                break
        
        # Take the first reasonable pair
        if potential_pairs:
            winner_odds['Winner1'] = potential_pairs[0][0]
            winner_odds['Winner2'] = potential_pairs[0][1]
            if verbose:
                print(f"✅ Found potential Winner odds: {winner_odds}")
    
    # Strategy 3: Look for specific button or clickable elements with odds
    if not winner_odds:
        buttons = soup.find_all(['button', 'a', 'div'], class_=re.compile(r'(odd|bet|coef)'))
        odds_values = []
        
        for button in buttons[:20]:  # Limit search
            text = button.get_text(strip=True)
            odds_match = re.search(r'\b(\d+\.\d{2})\b', text)
            if odds_match:
                odds_value = float(odds_match.group(1))
                if 1.1 <= odds_value <= 10.0:
                    odds_values.append(odds_value)
        
        if len(odds_values) >= 2:
            winner_odds['Winner1'] = odds_values[0]
            winner_odds['Winner2'] = odds_values[1]
            if verbose:
                print(f"✅ Found Winner odds from buttons: {winner_odds}")
    
    return winner_odds

def extract_odds_from_section(section, verbose=False):
    """Extract odds from a specific section"""
    odds = {}
    
    # Find all numbers that look like odds
    text = section.get_text()
    odds_pattern = r'\b(\d+\.\d{2})\b'
    found_odds = re.findall(odds_pattern, text)
    
    # Convert to floats and filter reasonable odds
    valid_odds = []
    for odd in found_odds:
        try:
            odd_float = float(odd)
            if 1.1 <= odd_float <= 10.0:  # Reasonable range for winner odds
                valid_odds.append(odd_float)
        except ValueError:
            continue
    
    # Take first two as Winner 1 and Winner 2
    if len(valid_odds) >= 2:
        odds['Winner1'] = valid_odds[0]
        odds['Winner2'] = valid_odds[1]
        if verbose:
            print(f"✅ Extracted odds from section: Winner1={valid_odds[0]}, Winner2={valid_odds[1]}")
    
    return odds

def calculate_surebet(winner1_odds, winner2_odds, verbose=True):
    """Calculate if Winner odds form a surebet"""
    try:
        odds1 = float(winner1_odds)
        odds2 = float(winner2_odds)
        
        # Calculate implied probabilities
        prob1 = 1 / odds1
        prob2 = 1 / odds2
        total_prob = prob1 + prob2
        
        if total_prob < 1.0:
            # It's a surebet!
            profit_margin = (1 - total_prob) * 100
            
            # Calculate stakes for a total of 10000 RSD
            total_stake = 10000
            stake1 = total_stake * prob1 / total_prob
            stake2 = total_stake * prob2 / total_prob
            
            # Calculate guaranteed profit
            return1 = stake1 * odds1
            return2 = stake2 * odds2
            guaranteed_return = min(return1, return2)
            profit = guaranteed_return - total_stake
            
            result = {
                'is_surebet': True,
                'profit_margin': round(profit_margin, 2),
                'total_stake': total_stake,
                'stake1': round(stake1, 2),
                'stake2': round(stake2, 2),
                'guaranteed_return': round(guaranteed_return, 2),
                'profit': round(profit, 2)
            }
            
            if verbose:
                print(f"🎉 SUREBET FOUND!")
                print(f"   Winner 1 odds: {odds1} - Stake: {result['stake1']} RSD")
                print(f"   Winner 2 odds: {odds2} - Stake: {result['stake2']} RSD")
                print(f"   Profit margin: {result['profit_margin']}%")
                print(f"   Guaranteed profit: {result['profit']} RSD")
            
            return result
        else:
            if verbose:
                print(f"❌ Not a surebet. Total probability: {total_prob:.4f} (needs to be < 1.0)")
            return {'is_surebet': False, 'total_probability': total_prob}
            
    except Exception as e:
        if verbose:
            print(f"❌ Error calculating surebet: {e}")
        return {'is_surebet': False, 'error': str(e)}

if __name__ == "__main__":
    # Configuration
    MATCH_URL = "https://toptiket.rs/odds/football/match/441570"  # Necaxa vs Puebla
    USERNAME = "djape96"
    PASSWORD = "Radonjic96$"
    
    print("🚀 Starting Winner Odds Scraper for TopTiket")
    print(f"🎯 Target match: {MATCH_URL}")
    print("-" * 60)
    
    # Extract winner odds
    result = login_and_extract_winner(MATCH_URL, USERNAME, PASSWORD, headless=False, verbose=True)
    
    if result and result['winner_odds']:
        print("\n" + "="*60)
        print("📊 RESULTS")
        print("="*60)
        
        winner_odds = result['winner_odds']
        
        if 'Winner1' in winner_odds and 'Winner2' in winner_odds:
            print(f"🏆 Match: {result['match_info'].get('teams', 'Necaxa vs Puebla')}")
            print(f"📈 Winner 1 odds: {winner_odds['Winner1']}")
            print(f"📈 Winner 2 odds: {winner_odds['Winner2']}")
            
            # Check for surebet
            surebet_result = calculate_surebet(winner_odds['Winner1'], winner_odds['Winner2'])
            
            if surebet_result.get('is_surebet'):
                print("\n🎉 This is a SUREBET opportunity!")
            else:
                print("\n❌ Not a surebet opportunity")
        else:
            print("⚠️ Could not extract both Winner odds")
    else:
        print("❌ Failed to extract winner odds")
    
    print("\n💾 Check the following files for detailed results:")
    print("   - winner_match_page.html (full page HTML)")
    print("   - winner_results.json (parsed results)")