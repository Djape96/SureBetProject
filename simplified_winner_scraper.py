"""
Simplified Dynamic Winner Market Scraper for TopTiket
Uses a hybrid approach: tests known match URL and builds a simple discovery mechanism
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

def login_to_toptiket(driver, username, password, verbose=True):
    """Login to TopTiket"""
    try:
        if verbose:
            print(f"🔐 Logging in to TopTiket with user: {username}")
        
        driver.get('https://toptiket.rs/login')
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        time.sleep(2)
        
        # Username
        for selector in ["input[name='username']", "input[name*='user']", "input[type='text']"]:
            try:
                field = driver.find_element(By.CSS_SELECTOR, selector)
                field.clear()
                field.send_keys(username)
                if verbose:
                    print("✅ Username entered")
                break
            except:
                continue
        
        # Password
        for selector in ["input[name='password']", "input[type='password']"]:
            try:
                field = driver.find_element(By.CSS_SELECTOR, selector)
                field.clear()
                field.send_keys(password)
                if verbose:
                    print("✅ Password entered")
                break
            except:
                continue
        
        # Submit
        try:
            submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            submit_btn.click()
        except:
            try:
                password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                password_field.submit()
            except:
                pass
        
        if verbose:
            print("✅ Login form submitted")
        time.sleep(3)
        return True
        
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return False

def get_sample_match_urls(driver, verbose=True):
    """
    Get sample match URLs using multiple strategies
    """
    if verbose:
        print("🔍 Getting sample match URLs...")
    
    sample_urls = []
    
    # Strategy 1: Use the known working match URL as a base
    known_match = "https://toptiket.rs/odds/football/match/441570"
    sample_urls.append({
        'url': known_match,
        'teams': 'Necaxa vs Puebla',
        'strategy': 'known_match'
    })
    
    # Strategy 2: Try to find other matches by modifying the match ID
    base_id = 441570
    for offset in [-5, -4, -3, -2, -1, 1, 2, 3, 4, 5, -10, 10, -20, 20]:
        new_id = base_id + offset
        test_url = f"https://toptiket.rs/odds/football/match/{new_id}"
        sample_urls.append({
            'url': test_url,
            'teams': f'Match {new_id}',
            'strategy': 'id_increment'
        })
    
    # Strategy 3: Check if we can navigate and find real match data
    try:
        driver.get('https://toptiket.rs/odds/football')
        time.sleep(5)  # Wait for page to load
        
        # Try to get current page URL and see if it has changed
        current_url = driver.current_url
        if verbose:
            print(f"   Current URL after navigation: {current_url}")
        
        # Get page source and look for any match URLs
        page_source = driver.page_source
        
        # Save for debugging
        with open('football_listing_debug.html', 'w', encoding='utf-8') as f:
            f.write(page_source)
        
        # Look for match URLs in the page source
        match_urls = re.findall(r'(?:href=["\']/odds/football/match/(\d+)["\']|/odds/football/match/(\d+))', page_source)
        
        found_ids = set()
        for match in match_urls:
            match_id = match[0] or match[1]  # One of these will be non-empty
            if match_id and match_id not in found_ids:
                found_ids.add(match_id)
                sample_urls.append({
                    'url': f'https://toptiket.rs/odds/football/match/{match_id}',
                    'teams': f'Match {match_id}',
                    'strategy': 'page_source'
                })
        
        if verbose:
            print(f"   Found {len(found_ids)} match IDs in page source")
            
    except Exception as e:
        if verbose:
            print(f"   Strategy 3 failed: {e}")
    
    # Remove duplicates
    unique_urls = []
    seen_urls = set()
    for match in sample_urls:
        if match['url'] not in seen_urls:
            unique_urls.append(match)
            seen_urls.add(match['url'])
    
    if verbose:
        print(f"✅ Generated {len(unique_urls)} sample match URLs")
        for i, match in enumerate(unique_urls[:5]):
            print(f"   {i+1}. {match['teams']} -> {match['url']}")
        if len(unique_urls) > 5:
            print(f"   ... and {len(unique_urls) - 5} more matches")
    
    return unique_urls

def extract_winner_odds_from_match(driver, match_url, match_teams, verbose=True):
    """Extract Winner (DNB) odds from a specific match page"""
    try:
        if verbose:
            print(f"🎯 Processing: {match_teams}")
        
        driver.get(match_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        time.sleep(3)
        
        # Check if the page actually exists (not 404)
        if "404" in driver.title.lower() or "not found" in driver.page_source.lower():
            if verbose:
                print("   ❌ Match page not found (404)")
            return None
        
        # Enhanced tab selectors for Prolaz/Winner
        tab_selectors = [
            "//a[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//button[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//div[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz') and (@role='tab' or contains(@class, 'tab'))]",
            "//span[contains(translate(text(), 'PROLAZ', 'prolaz'), 'prolaz')]",
            "//a[contains(translate(text(), 'WINNER', 'winner'), 'winner')]",
            "//button[contains(translate(text(), 'WINNER', 'winner'), 'winner')]",
            "//div[contains(translate(text(), 'WINNER', 'winner'), 'winner') and (@role='tab' or contains(@class, 'tab'))]",
            "//span[contains(translate(text(), 'WINNER', 'winner'), 'winner')]",
            "//a[normalize-space(text())='P']",
            "//button[normalize-space(text())='P']",
            "//div[@role='tab' and normalize-space(text())='P']"
        ]
        
        # Try to click the Prolaz/Winner tab
        tab_clicked = False
        for selector in tab_selectors:
            try:
                tab = driver.find_element(By.XPATH, selector)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
                time.sleep(0.5)
                tab.click()
                time.sleep(2)
                tab_clicked = True
                if verbose:
                    print(f"   ✅ Tab clicked: '{tab.text.strip()}'")
                break
            except:
                continue
        
        if not tab_clicked and verbose:
            print("   ⚠️ No Prolaz/Winner tab found, proceeding with default view")
        
        # Extract odds
        return extract_winner_dnb_odds(driver, verbose=verbose)
        
    except Exception as e:
        if verbose:
            print(f"   ❌ Failed to extract odds: {e}")
        return None

def extract_winner_dnb_odds(driver, verbose=True):
    """Extract Winner (Draw No Bet) odds from all available bookmakers"""
    try:
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Enhanced bookmaker patterns
        bookmaker_patterns = {
            'Max Bet': [r'max\s*bet', r'maxbet'],
            'MerkurXtip': [r'merkur\s*xtip', r'merkurxtip', r'merkur'],
            'Mozzart Bet': [r'mozzart\s*bet', r'mozzartbet', r'mozzart'],
            'Oktagon Bet': [r'oktagon\s*bet', r'oktagonbet', r'oktagon'],
            'Soccer Bet': [r'soccer\s*bet', r'soccerbet', r'soccer'],
            'Admiral': [r'admiral'],
            'Bet365': [r'bet365', r'365'],
            'Pinnacle': [r'pinnacle'],
            'Unibet': [r'unibet']
        }
        
        # Find all odds values on the page
        all_odds = []
        odds_elements = soup.find_all(lambda tag: tag.name in ['span', 'div', 'button'] and 
                                     tag.get_text(strip=True) and 
                                     re.match(r'^\d+\.\d{2}$', tag.get_text(strip=True)))
        
        for elem in odds_elements:
            try:
                odds_value = float(elem.get_text(strip=True))
                if 1.01 <= odds_value <= 50.0:
                    all_odds.append(odds_value)
            except:
                continue
        
        if verbose:
            print(f"   📊 Found {len(all_odds)} odds values on the page")
        
        # Simple approach: take the first two reasonable odds as Winner1/Winner2
        if len(all_odds) >= 2:
            # Remove duplicates while preserving order
            unique_odds = []
            for odds in all_odds:
                if odds not in unique_odds:
                    unique_odds.append(odds)
                if len(unique_odds) >= 2:
                    break
            
            if len(unique_odds) >= 2:
                result = {
                    'all_bookmakers': {
                        'Default': {
                            'winner1': unique_odds[0],
                            'winner2': unique_odds[1]
                        }
                    },
                    'best_odds': {
                        'winner1': {'odds': unique_odds[0], 'bookmaker': 'Default'},
                        'winner2': {'odds': unique_odds[1], 'bookmaker': 'Default'}
                    },
                    'total_bookmakers': 1,
                    'all_odds_found': all_odds[:10]  # For debugging
                }
                
                if verbose:
                    print(f"   🏆 Winner1 odds: {unique_odds[0]}")
                    print(f"   🏆 Winner2 odds: {unique_odds[1]}")
                
                return result
        
        if verbose:
            print("   ❌ Could not find sufficient odds")
        
        return {
            'all_bookmakers': {},
            'best_odds': {'winner1': {'odds': 0, 'bookmaker': ''}, 'winner2': {'odds': 0, 'bookmaker': ''}},
            'total_bookmakers': 0,
            'all_odds_found': all_odds[:10]
        }
        
    except Exception as e:
        if verbose:
            print(f"   ❌ Odds extraction failed: {e}")
        return {}

def calculate_surebet(odds1, odds2):
    """Calculate surebet information"""
    if odds1 <= 0 or odds2 <= 0:
        return {'is_surebet': False, 'total_probability': 0, 'profit_margin_percent': 0}
    
    prob1 = 1 / odds1
    prob2 = 1 / odds2
    total_prob = prob1 + prob2
    
    is_surebet = total_prob < 1.0
    profit_margin = (1 - total_prob) * 100 if is_surebet else 0
    
    return {
        'is_surebet': is_surebet,
        'total_probability': total_prob * 100,
        'profit_margin_percent': profit_margin,
        'stake_distribution': {
            'winner1_percent': (prob1 / total_prob) * 100 if total_prob > 0 else 0,
            'winner2_percent': (prob2 / total_prob) * 100 if total_prob > 0 else 0
        }
    }

def process_sample_matches(username, password, headless=False, max_matches=10, verbose=True):
    """Main function to process sample matches"""
    options = Options()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    all_results = []
    surebets_found = []
    valid_matches_found = []
    
    try:
        # Step 1: Login
        if not login_to_toptiket(driver, username, password, verbose):
            return None
        
        # Step 2: Get sample match URLs
        sample_matches = get_sample_match_urls(driver, verbose)
        
        if not sample_matches:
            print("❌ No sample match URLs generated")
            return None
        
        # Step 3: Process each match (limit to max_matches)
        matches_to_process = sample_matches[:max_matches]
        
        print(f"\n🚀 Processing {len(matches_to_process)} sample matches...")
        print("=" * 80)
        
        for i, match in enumerate(matches_to_process, 1):
            print(f"\n📊 Match {i}/{len(matches_to_process)}")
            
            odds_result = extract_winner_odds_from_match(
                driver, 
                match['url'], 
                match['teams'], 
                verbose
            )
            
            # Skip if match doesn't exist or no odds found
            if not odds_result or odds_result.get('total_bookmakers', 0) == 0:
                if verbose:
                    print(f"   ⏭️ Skipping - no valid data")
                continue
            
            valid_matches_found.append(match)
            
            match_result = {
                'match_number': len(valid_matches_found),
                'teams': match['teams'],
                'url': match['url'],
                'strategy': match['strategy'],
                'odds_data': odds_result
            }
            
            # Calculate surebet if we have best odds
            if odds_result and 'best_odds' in odds_result:
                best = odds_result['best_odds']
                if best['winner1']['odds'] > 0 and best['winner2']['odds'] > 0:
                    surebet_analysis = calculate_surebet(
                        best['winner1']['odds'], 
                        best['winner2']['odds']
                    )
                    match_result['surebet_analysis'] = surebet_analysis
                    
                    if surebet_analysis['is_surebet']:
                        surebets_found.append(match_result)
                        print(f"   🎉 SUREBET FOUND! Profit: {surebet_analysis['profit_margin_percent']:.2f}%")
                    else:
                        print(f"   📊 Total probability: {surebet_analysis['total_probability']:.1f}% (margin: {100 - surebet_analysis['total_probability']:.1f}%)")
            
            all_results.append(match_result)
            
            # Small delay between matches
            time.sleep(1)
        
        print(f"\n📈 Summary: Processed {len(all_results)} valid matches out of {len(matches_to_process)} attempts")
        
        return {
            'total_matches_attempted': len(matches_to_process),
            'valid_matches_found': len(all_results),
            'matches': all_results,
            'surebets_found': len(surebets_found),
            'surebet_matches': surebets_found
        }
        
    except Exception as e:
        print(f"❌ Processing failed: {e}")
        return None
    finally:
        driver.quit()

if __name__ == "__main__":
    # Configuration
    username = "djape96"
    password = "Radonjic96$"
    max_matches = 15  # Try more matches to find valid ones
    
    print("🚀 Starting Simplified Winner/DNB Scanner...")
    print("🎯 Target: Sample matches using multiple discovery strategies")
    print("🔍 Looking for Winner (Draw No Bet) odds")
    print("=" * 80)
    
    results = process_sample_matches(
        username=username,
        password=password,
        headless=False,  # Set to True for faster execution
        max_matches=max_matches,
        verbose=True
    )
    
    if results:
        print("\n" + "=" * 80)
        print("📈 FINAL SUMMARY:")
        print(f"Matches attempted: {results['total_matches_attempted']}")
        print(f"Valid matches found: {results['valid_matches_found']}")
        print(f"Surebets found: {results['surebets_found']}")
        
        if results['matches']:
            print(f"\n📊 VALID MATCHES:")
            for i, match in enumerate(results['matches'], 1):
                teams = match['teams']
                best = match['odds_data']['best_odds']
                strategy = match.get('strategy', 'unknown')
                
                print(f"\n{i}. {teams} ({strategy})")
                print(f"   Winner1: {best['winner1']['odds']} ({best['winner1']['bookmaker']})")
                print(f"   Winner2: {best['winner2']['odds']} ({best['winner2']['bookmaker']})")
                
                if 'surebet_analysis' in match:
                    analysis = match['surebet_analysis']
                    if analysis['is_surebet']:
                        print(f"   🎉 SUREBET - Profit: {analysis['profit_margin_percent']:.2f}%")
                    else:
                        print(f"   📊 Probability: {analysis['total_probability']:.1f}%")
        
        if results['surebet_matches']:
            print(f"\n🎉 SUREBET OPPORTUNITIES:")
            for i, surebet in enumerate(results['surebet_matches'], 1):
                teams = surebet['teams']
                best = surebet['odds_data']['best_odds']
                analysis = surebet['surebet_analysis']
                
                print(f"\n{i}. {teams}")
                print(f"   Winner1: {best['winner1']['odds']} ({best['winner1']['bookmaker']})")
                print(f"   Winner2: {best['winner2']['odds']} ({best['winner2']['bookmaker']})")
                print(f"   Profit: {analysis['profit_margin_percent']:.2f}%")
                print(f"   Stakes: {analysis['stake_distribution']['winner1_percent']:.1f}% / {analysis['stake_distribution']['winner2_percent']:.1f}%")
        
        # Save results to JSON
        with open('simplified_winner_results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Results saved to: simplified_winner_results.json")
        
    else:
        print("❌ Processing failed - no results obtained")