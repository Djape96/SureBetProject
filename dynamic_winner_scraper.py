"""
Dynamic Winner Market Scraper for TopTiket
Processes all matches on the football page and extracts Winner (DNB) odds for each
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
    """
    Login to TopTiket
    """
    try:
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
            return False
        
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
            return False
        
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
            return True
        else:
            print("❌ Could not submit login form")
            return False
            
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return False

def find_match_links(driver, verbose=True):
    """
    Find all match links on the football page using enhanced detection for React SPA
    """
    try:
        if verbose:
            print("🔍 Looking for match links on football page...")
        
        driver.get('https://toptiket.rs/odds/football')
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        
        # Accept cookies if present
        try:
            cookie_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'OK') or contains(text(), 'Accept') or contains(text(), 'Prihvati')]")
            if cookie_buttons:
                cookie_buttons[0].click()
                time.sleep(1)
        except:
            pass
        
        # Wait for React app to load - look for specific content
        if verbose:
            print("   ⏳ Waiting for React app to load...")
        
        # Wait longer for dynamic content to load
        time.sleep(8)
        
        # Try to wait for specific elements that indicate matches are loaded
        wait_attempts = 0
        max_wait_attempts = 10
        
        while wait_attempts < max_wait_attempts:
            try:
                # Look for any elements that might contain match data
                potential_matches = driver.find_elements(By.XPATH, "//*[contains(text(), 'vs') or contains(text(), 'VS') or contains(text(), '-')]")
                if len(potential_matches) > 2:  # Found some match-like content
                    break
                    
                # Also look for common betting interface elements
                betting_elements = driver.find_elements(By.XPATH, "//*[contains(@class, 'odd') or contains(@class, 'bet') or contains(@class, 'match')]")
                if len(betting_elements) > 5:
                    break
                    
                # Check for numeric content that looks like odds
                numeric_content = driver.find_elements(By.XPATH, "//*[text()[contains(., '.') and string-length(.) < 6]]")
                if len(numeric_content) > 10:
                    break
                    
            except:
                pass
            
            if verbose:
                print(f"   ⏳ Waiting for content... attempt {wait_attempts + 1}")
            time.sleep(2)
            wait_attempts += 1
        
        # Scroll to trigger lazy loading
        if verbose:
            print("   📜 Scrolling to load more content...")
        
        for i in range(8):
            driver.execute_script(f"window.scrollTo(0, {i * 800});")
            time.sleep(1)
        
        # Save page source for debugging
        with open('football_page_dynamic.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        
        match_links = []
        
        # Strategy 1: Look for clickable elements with team names (React components)
        try:
            # More general approach for React apps
            potential_selectors = [
                "//*[contains(@class, 'match') or contains(@class, 'event') or contains(@class, 'game')]",
                "//*[contains(@class, 'row') and (contains(text(), 'vs') or contains(text(), 'VS') or contains(text(), '-'))]",
                "//div[contains(text(), 'vs') or contains(text(), 'VS')]",
                "//span[contains(text(), 'vs') or contains(text(), 'VS')]", 
                "//p[contains(text(), 'vs') or contains(text(), 'VS')]",
                "//h6[contains(text(), 'vs') or contains(text(), 'VS')]",
                "//button[contains(text(), 'vs') or contains(text(), 'VS')]",
                "//*[text()[contains(., ' - ') and string-length(.) > 5 and string-length(.) < 50]]"
            ]
            
            all_potential_elements = []
            for selector in potential_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    all_potential_elements.extend(elements)
                    if verbose and elements:
                        print(f"   Found {len(elements)} elements with selector: {selector}")
                except:
                    continue
            
            if verbose:
                print(f"   Strategy 1: Found {len(all_potential_elements)} potential match elements")
            
            # Process potential match elements
            for element in all_potential_elements[:30]:  # Limit to reasonable number
                try:
                    text = element.text.strip()
                    if not text or len(text) < 5 or len(text) > 100:
                        continue
                    
                    # Check if text looks like a match (contains vs, -, or team names)
                    text_lower = text.lower()
                    if not ('vs' in text_lower or ' - ' in text or 
                           (re.search(r'[a-zA-Z]+\s+[a-zA-Z]+', text) and 
                            any(word in text_lower for word in ['fc', 'ac', 'united', 'city', 'real', 'arsenal', 'chelsea']))):
                        continue
                    
                    # Try to make this element clickable and see if it leads to a match page
                    try:
                        original_url = driver.current_url
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                        time.sleep(0.3)
                        
                        # Try clicking the element or its parent
                        click_targets = [element]
                        
                        # Also try parent elements
                        try:
                            parent = element.find_element(By.XPATH, "..")
                            click_targets.append(parent)
                            grandparent = parent.find_element(By.XPATH, "..")
                            click_targets.append(grandparent)
                        except:
                            pass
                        
                        for target in click_targets:
                            try:
                                target.click()
                                time.sleep(2)
                                
                                new_url = driver.current_url
                                if '/odds/football/match/' in new_url and new_url != original_url:
                                    match_links.append({
                                        'url': new_url,
                                        'teams': text,
                                        'element': target,
                                        'strategy': 'react_click'
                                    })
                                    if verbose:
                                        print(f"   ✅ Found match: {text} -> {new_url}")
                                    
                                    # Go back for next match
                                    driver.back()
                                    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
                                    time.sleep(1)
                                    break
                                elif new_url != original_url:
                                    # Went somewhere else, go back
                                    driver.back()
                                    time.sleep(1)
                            except:
                                continue
                    except:
                        continue
                        
                except Exception as e:
                    if verbose:
                        print(f"   Element processing error: {e}")
                    continue
                    
        except Exception as e:
            if verbose:
                print(f"   Strategy 1 failed: {e}")
        
        # Strategy 2: JavaScript execution to find React component data
        try:
            if verbose:
                print("   Strategy 2: Searching React state for match data...")
            
            # Try to extract data from React components
            js_matches = driver.execute_script("""
                var matches = [];
                
                // Look for React Fiber nodes
                function walkFiber(node, depth) {
                    if (!node || depth > 10) return;
                    
                    try {
                        // Check for props that might contain match data
                        if (node.memoizedProps) {
                            var props = node.memoizedProps;
                            if (props.children || props.match || props.teams || props.event) {
                                var text = '';
                                if (typeof props.children === 'string') text = props.children;
                                else if (props.match && typeof props.match === 'object') {
                                    text = JSON.stringify(props.match);
                                }
                                
                                if (text && (text.includes('vs') || text.includes('VS') || text.includes(' - '))) {
                                    matches.push({
                                        text: text,
                                        type: 'react_props'
                                    });
                                }
                            }
                        }
                        
                        // Recurse through children
                        if (node.child) walkFiber(node.child, depth + 1);
                        if (node.sibling) walkFiber(node.sibling, depth + 1);
                    } catch (e) {}
                }
                
                // Try to find React root
                var reactRoots = document.querySelectorAll('#root, [data-reactroot]');
                for (var root of reactRoots) {
                    try {
                        var reactInstance = root._reactInternalInstance || 
                                          root._reactInternalFiber ||
                                          Object.keys(root).find(key => key.startsWith('__reactInternalInstance'));
                        if (reactInstance) {
                            walkFiber(reactInstance, 0);
                        }
                    } catch (e) {}
                }
                
                // Also look for any global match data
                if (window.__INITIAL_STATE__ || window.__REDUX_STATE__ || window.matchData) {
                    try {
                        var stateData = window.__INITIAL_STATE__ || window.__REDUX_STATE__ || window.matchData;
                        var stateStr = JSON.stringify(stateData);
                        if (stateStr.includes('match') || stateStr.includes('vs')) {
                            matches.push({
                                text: stateStr.substring(0, 1000),
                                type: 'global_state'
                            });
                        }
                    } catch (e) {}
                }
                
                return matches.slice(0, 20); // Limit results
            """)
            
            if js_matches and verbose:
                print(f"   Found {len(js_matches)} potential matches in React state")
                
            # Process JavaScript-found matches
            for js_match in js_matches[:10]:
                try:
                    text = js_match.get('text', '')
                    if 'vs' in text.lower() or 'VS' in text:
                        # Extract team names if possible
                        match_pattern = re.search(r'([A-Za-z\s]{3,25})\s*(?:vs|VS|-)\s*([A-Za-z\s]{3,25})', text)
                        if match_pattern:
                            teams = f"{match_pattern.group(1).strip()} vs {match_pattern.group(2).strip()}"
                            
                            # Try to find a clickable element with this text
                            try:
                                clickable = driver.find_element(By.XPATH, f"//*[contains(text(), '{teams[:20]}')]")
                                clickable.click()
                                time.sleep(2)
                                
                                new_url = driver.current_url
                                if '/odds/football/match/' in new_url:
                                    match_links.append({
                                        'url': new_url,
                                        'teams': teams,
                                        'element': clickable,
                                        'strategy': 'react_state'
                                    })
                                    driver.back()
                                    time.sleep(1)
                            except:
                                pass
                except:
                    continue
                    
        except Exception as e:
            if verbose:
                print(f"   Strategy 2 failed: {e}")
        
        # Strategy 3: Network monitoring for API calls
        try:
            if verbose:
                print("   Strategy 3: Checking browser console for API calls...")
            
            # Get browser logs to see if there were any API calls
            logs = driver.get_log('performance')
            for log_entry in logs[-50:]:  # Check recent logs
                try:
                    message = json.loads(log_entry['message'])
                    if message.get('message', {}).get('method') == 'Network.responseReceived':
                        url = message.get('message', {}).get('params', {}).get('response', {}).get('url', '')
                        if ('match' in url.lower() or 'football' in url.lower()) and 'api' in url.lower():
                            if verbose:
                                print(f"   📡 Found potential API call: {url}")
                except:
                    continue
                    
        except Exception as e:
            if verbose:
                print(f"   Strategy 3 failed (normal if no performance logs): {e}")
        
        # Remove duplicates
        unique_links = []
        seen_urls = set()
        for link in match_links:
            if link['url'] not in seen_urls:
                unique_links.append(link)
                seen_urls.add(link['url'])
        
        if verbose:
            print(f"\n✅ Found {len(unique_links)} unique match links total")
            
            # Group by strategy
            strategy_counts = {}
            for link in unique_links:
                strategy = link.get('strategy', 'unknown')
                strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
            
            for strategy, count in strategy_counts.items():
                print(f"   {strategy}: {count} matches")
            
            print(f"\nFirst 5 matches:")
            for i, link in enumerate(unique_links[:5]):
                print(f"   {i+1}. {link['teams']} -> {link['url']}")
            if len(unique_links) > 5:
                print(f"   ... and {len(unique_links) - 5} more matches")
        
        return unique_links
        
    except Exception as e:
        print(f"❌ Failed to find match links: {e}")
        return []

def extract_winner_odds_from_match(driver, match_url, match_teams, verbose=True):
    """
    Extract Winner (DNB) odds from a specific match page
    """
    try:
        if verbose:
            print(f"🎯 Processing: {match_teams}")
        
        driver.get(match_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        time.sleep(2)
        
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
            "//a[contains(translate(normalize-space(text()), 'PROLAZ WINNER', 'prolaz winner'), 'prolaz') and contains(translate(normalize-space(text()), 'PROLAZ WINNER', 'prolaz winner'), 'winner')]",
            "//button[contains(translate(normalize-space(text()), 'PROLAZ WINNER', 'prolaz winner'), 'prolaz') and contains(translate(normalize-space(text()), 'PROLAZ WINNER', 'prolaz winner'), 'winner')]",
            "//div[@role='tab' and contains(translate(normalize-space(text()), 'PROLAZ WINNER', 'prolaz winner'), 'prolaz') and contains(translate(normalize-space(text()), 'PROLAZ WINNER', 'prolaz winner'), 'winner')]",
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
        
        # Extract odds using enhanced method from winner_scraper_enhanced.py
        return extract_winner_dnb_odds(driver, verbose=verbose)
        
    except Exception as e:
        if verbose:
            print(f"   ❌ Failed to extract odds: {e}")
        return {}

def extract_winner_dnb_odds(driver, verbose=True):
    """
    Extract Winner (Draw No Bet) odds from all available bookmakers
    Returns the best odds for each outcome
    """
    try:
        # Get page source and parse with BeautifulSoup
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
        
        # Find all sections that contain odds
        all_bookmaker_odds = {}
        
        # Look for Winner/Prolaz sections
        winner_sections = soup.find_all(lambda tag: tag.name in ['div', 'section', 'table'] and 
                                       tag.get_text() and 
                                       ('winner' in tag.get_text().lower() or 'prolaz' in tag.get_text().lower()))
        
        for section in winner_sections:
            section_text = section.get_text(' ', strip=True).lower()
            
            # Extract odds from this section
            odds_elements = section.find_all(lambda tag: tag.name in ['span', 'div', 'button'] and 
                                           tag.get_text(strip=True) and 
                                           re.match(r'^\d+\.\d{2}$', tag.get_text(strip=True)))
            
            odds_values = []
            for elem in odds_elements:
                try:
                    odds_value = float(elem.get_text(strip=True))
                    if 1.01 <= odds_value <= 50.0:  # Reasonable odds range
                        odds_values.append(odds_value)
                except:
                    continue
            
            # Try to identify bookmaker
            for bookmaker, patterns in bookmaker_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, section_text):
                        if len(odds_values) >= 2:
                            all_bookmaker_odds[bookmaker] = {
                                'winner1': odds_values[0],
                                'winner2': odds_values[1]
                            }
                        break
                if bookmaker in all_bookmaker_odds:
                    break
        
        # If no specific bookmaker sections found, extract all odds and distribute
        if not all_bookmaker_odds:
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
            
            # Group odds in pairs (assuming they appear in Winner1, Winner2 pairs)
            if len(all_odds) >= 2:
                for i in range(0, len(all_odds)-1, 2):
                    bookmaker_name = f"Bookmaker_{i//2 + 1}"
                    all_bookmaker_odds[bookmaker_name] = {
                        'winner1': all_odds[i],
                        'winner2': all_odds[i+1]
                    }
        
        # Find the best odds
        best_winner1_odds = 0
        best_winner1_bookmaker = ""
        best_winner2_odds = 0
        best_winner2_bookmaker = ""
        
        for bookmaker, odds in all_bookmaker_odds.items():
            if odds['winner1'] > best_winner1_odds:
                best_winner1_odds = odds['winner1']
                best_winner1_bookmaker = bookmaker
            
            if odds['winner2'] > best_winner2_odds:
                best_winner2_odds = odds['winner2']
                best_winner2_bookmaker = bookmaker
        
        result = {
            'all_bookmakers': all_bookmaker_odds,
            'best_odds': {
                'winner1': {'odds': best_winner1_odds, 'bookmaker': best_winner1_bookmaker},
                'winner2': {'odds': best_winner2_odds, 'bookmaker': best_winner2_bookmaker}
            },
            'total_bookmakers': len(all_bookmaker_odds)
        }
        
        if verbose and best_winner1_odds > 0:
            print(f"   📊 Found odds from {len(all_bookmaker_odds)} bookmakers")
            print(f"   🏆 BEST Winner1 odds: {best_winner1_odds} ({best_winner1_bookmaker})")
            print(f"   🏆 BEST Winner2 odds: {best_winner2_odds} ({best_winner2_bookmaker})")
        
        return result
        
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

def process_all_matches(username, password, headless=False, max_matches=20, verbose=True):
    """
    Main function to process all matches on the football page
    """
    options = Options()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    # Enable performance logging
    options.add_argument('--enable-logging')
    options.add_argument('--log-level=0')
    
    # Add experimental options for better compatibility
    options.add_experimental_option('useAutomationExtension', False)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    # Set logging preferences properly
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    all_results = []
    surebets_found = []
    
    try:
        # Step 1: Login
        if not login_to_toptiket(driver, username, password, verbose):
            return None
        
        # Step 2: Find all match links
        match_links = find_match_links(driver, verbose)
        
        if not match_links:
            print("❌ No match links found")
            return None
        
        # Step 3: Process each match (limit to max_matches)
        matches_to_process = match_links[:max_matches]
        
        print(f"\n🚀 Processing {len(matches_to_process)} matches...")
        print("=" * 80)
        
        for i, match in enumerate(matches_to_process, 1):
            print(f"\n📊 Match {i}/{len(matches_to_process)}")
            
            odds_result = extract_winner_odds_from_match(
                driver, 
                match['url'], 
                match['teams'], 
                verbose
            )
            
            match_result = {
                'match_number': i,
                'teams': match['teams'],
                'url': match['url'],
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
            
            all_results.append(match_result)
            
            # Small delay between matches
            time.sleep(1)
        
        return {
            'total_matches_processed': len(all_results),
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
    max_matches = 20  # Limit number of matches to process
    
    print("🚀 Starting Dynamic Winner/DNB Scanner...")
    print("🎯 Target: All matches on TopTiket football page")
    print("🔍 Looking for Winner (Draw No Bet) best odds")
    print("=" * 80)
    
    results = process_all_matches(
        username=username,
        password=password,
        headless=False,  # Set to True for faster execution
        max_matches=max_matches,
        verbose=True
    )
    
    if results:
        print("\n" + "=" * 80)
        print("📈 FINAL SUMMARY:")
        print(f"Total matches processed: {results['total_matches_processed']}")
        print(f"Surebets found: {results['surebets_found']}")
        
        if results['surebet_matches']:
            print("\n🎉 SUREBET OPPORTUNITIES:")
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
        with open('dynamic_winner_results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Results saved to: dynamic_winner_results.json")
        
    else:
        print("❌ Processing failed - no results obtained")