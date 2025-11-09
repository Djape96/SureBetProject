"""
Selenium-based web scraper for TopTiket football odds

This script uses Selenium WebDriver to handle JavaScript-rendered content
and extract live football odds for surebet analysis.

Requirements:
- pip install selenium beautifulsoup4
- Download ChromeDriver from https://chromedriver.chromium.org/
- Or install via: pip install webdriver-manager
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime

def check_surebet(odds):
    """Check if odds represent a surebet opportunity"""
    clean_odds = [o for o, _ in odds if 0 < o < 50]  # ignore extreme invalid odds
    if len(clean_odds) < 2:
        return None
    inv_sum = sum(1 / o for o in clean_odds)
    if inv_sum < 1:
        return round((1 - inv_sum) * 100, 2)
    return None

def setup_driver():
    """Setup Chrome WebDriver with appropriate options"""
    try:
        # Chrome options for better compatibility
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in background
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # Try to create driver
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except ImportError:
            # Fallback to system ChromeDriver
            driver = webdriver.Chrome(options=chrome_options)
        
        return driver
        
    except Exception as e:
        print(f"❌ Error setting up Chrome WebDriver: {e}")
        print("💡 Make sure ChromeDriver is installed:")
        print("   pip install webdriver-manager")
        print("   or download from: https://chromedriver.chromium.org/")
        return None

def scrape_with_selenium():
    """Scrape football odds using Selenium WebDriver"""
    driver = setup_driver()
    if not driver:
        return []
    
    try:
        print("🌐 Loading TopTiket football page with Selenium...")
        url = "https://toptiket.rs/odds/football"
        driver.get(url)
        
        # Wait for page to load
        print("⏳ Waiting for page content to load...")
        time.sleep(5)
        
        # Wait for specific elements that indicate the page has loaded
        try:
            # Wait for matches to appear (adjust selector based on actual HTML)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            print("⚠️ Page load timeout, continuing with available content...")
        
        # Get page source after JavaScript execution
        page_source = driver.page_source
        
        # Save for debugging
        with open("selenium_page_source.html", "w", encoding="utf-8") as f:
            f.write(page_source)
        print("💾 Saved page source to selenium_page_source.html")
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Extract text content
        text_content = soup.get_text()
        with open("selenium_text_content.txt", "w", encoding="utf-8") as f:
            f.write(text_content)
        print("💾 Saved text content to selenium_text_content.txt")
        
        print(f"📦 Page content length: {len(text_content)} characters")
        
        # Parse the content
        matches = parse_selenium_content(text_content)
        
        return matches
        
    finally:
        driver.quit()

def parse_selenium_content(content):
    """Parse football matches from Selenium-extracted content"""
    matches = []
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    
    print(f"📝 Processing {len(lines)} lines from Selenium...")
    
    # Look for patterns that indicate football matches
    i = 0
    while i < len(lines) - 2:
        line = lines[i]
        
        # Skip navigation and common website elements
        skip_terms = [
            'početna', 'kvote', 'prognozer', 'promocije', 'bonusi', 'tiket',
            'javascript', 'enable', 'run', 'app', 'banner', 'copyright', '©',
            'facebook', 'instagram', 'telegram', 'twitter', 'personalizovali',
            'sadržaj', 'oglase', 'omogućili', 'funkcije', 'društvenih', 'medija',
            'mečevi', 'dodaj', 'izaberi', 'najbolje', 'kvote', 'kontakt', 'marketing'
        ]
        
        if any(term in line.lower() for term in skip_terms):
            i += 1
            continue
        
        # Look for time patterns indicating match start
        time_match = re.match(r'([a-z]{3},?\s*\d{1,2}\.\s*\d{1,2}\.?\s*\d{2}:\d{2})', line.lower())
        if time_match:
            # Check if next lines contain team names
            if i + 2 < len(lines):
                team1 = lines[i + 1].strip()
                team2 = lines[i + 2].strip()
                
                # Validate team names
                if (is_valid_team_name(team1) and is_valid_team_name(team2)):
                    print(f"🏆 Found match: {team1} vs {team2} at {line}")
                    
                    # Extract odds for this match
                    match_odds = extract_match_odds_selenium(lines, i + 3, min(len(lines), i + 40))
                    
                    if len(match_odds) >= 5:
                        # Take first 5 odds as Home, Draw, Away, 0-2, 3+
                        current_match = {
                            "teams": f"{team1} vs {team2}",
                            "time": line,
                            "odds": {
                                "Home": match_odds[0],
                                "Draw": match_odds[1],
                                "Away": match_odds[2],
                                "0-2": match_odds[3],
                                "3+": match_odds[4]
                            }
                        }
                        matches.append(current_match)
                        print(f"✅ Successfully parsed: {team1} vs {team2}")
                    else:
                        print(f"⚠️ Not enough odds found for {team1} vs {team2} (found {len(match_odds)})")
                
                i += 3  # Skip team names
            else:
                i += 1
        else:
            i += 1
    
    print(f"🎯 Total matches parsed: {len(matches)}")
    return matches

def is_valid_team_name(name):
    """Check if a string looks like a valid team name"""
    if not name or len(name) < 3:
        return False
    
    # Exclude common non-team words
    exclude_words = [
        'banner', 'http', 'www', 'toptiket', 'mozzart', 'admiral', 'soccer',
        'bet', 'merkur', 'brazil', 'oktagon', 'vivat', 'max', '365rs',
        'javascript', 'enable', 'app', 'presented', 'naredne', 'utakmice',
        'fudbal', 'košarka', 'tenis', 'hokej', 'ostali', 'sportovi'
    ]
    
    if any(word in name.lower() for word in exclude_words):
        return False
    
    # Should contain letters
    if not re.search(r'[a-zA-ZčćžšđČĆŽŠĐ]', name):
        return False
    
    # Should not be just numbers
    if name.isdigit():
        return False
    
    return True

def extract_match_odds_selenium(lines, start_idx, end_idx):
    """Extract odds from Selenium content for a specific match"""
    odds = []
    
    for j in range(start_idx, end_idx):
        if j >= len(lines):
            break
        
        line = lines[j].strip()
        
        # Stop conditions
        if not line:
            continue
        
        # Stop if we hit the next match time
        if re.match(r'[a-z]{3},?\s*\d{1,2}\.\s*\d{1,2}\.?\s*\d{2}:\d{2}', line.lower()):
            break
        
        # Stop if we hit a score indicator or large number
        if re.match(r'^[\+\-]?\d{3,4}$', line):
            break
        
        # Parse odds
        parsed_odd = parse_odds_line_selenium(line)
        if parsed_odd:
            odds.append(parsed_odd)
            print(f"  📈 Found odds: {parsed_odd[0]} @ {parsed_odd[1]}")
        
        # Get more odds but stop at reasonable limit
        if len(odds) >= 10:
            break
    
    return odds

def parse_odds_line_selenium(line):
    """Parse a single line to extract odds and bookmaker from Selenium content"""
    if not line or len(line) < 3:
        return None
    
    # Handle special bookmaker cases
    if line.endswith('1xBet'):
        try:
            odds_part = line[:-5]  # Remove '1xBet'
            odd = float(odds_part)
            if 0.5 <= odd <= 69:
                return (odd, '1xBet')
        except ValueError:
            pass
    
    if line.endswith('365rs'):
        try:
            odds_part = line[:-5]  # Remove '365rs'
            odd = float(odds_part)
            if 0.5 <= odd <= 69:
                return (odd, '365rs')
        except ValueError:
            pass
    
    # Standard parsing for other bookmakers
    match = re.match(r'^(\d+(?:\.\d+)?)([A-Za-z].*)$', line)
    if match:
        try:
            odd = float(match.group(1))
            bookmaker = match.group(2).strip()
            
            # Filter out unrealistic odds and validate bookmaker names
            if (0.5 <= odd <= 69 and 
                bookmaker and 
                len(bookmaker) > 2 and
                not any(skip in bookmaker.lower() for skip in ['http', 'www', 'banner', 'image'])):
                return (odd, bookmaker)
        except ValueError:
            pass
    
    return None

def analyze_surebets(matches):
    """Analyze matches for surebet opportunities"""
    surebets = []
    
    for match in matches:
        odds_list = [match["odds"][label] for label in ["Home", "Draw", "Away", "0-2", "3+"]]
        
        # Check 1X2 surebet
        profit_1x2 = check_surebet(odds_list[:3])
        if profit_1x2:
            surebet_info = {
                "match": match["teams"],
                "time": match.get("time", ""),
                "type": "1X2",
                "profit": profit_1x2,
                "odds": {k: match["odds"][k] for k in ["Home", "Draw", "Away"]}
            }
            surebets.append(surebet_info)
        
        # Check Over/Under surebet
        profit_ou = check_surebet(odds_list[3:5])
        if profit_ou:
            surebet_info = {
                "match": match["teams"],
                "time": match.get("time", ""),
                "type": "0-2 / 3+",
                "profit": profit_ou,
                "odds": {k: match["odds"][k] for k in ["0-2", "3+"]}
            }
            surebets.append(surebet_info)
    
    return surebets

def save_results(matches, surebets):
    """Save results to files"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save all matches
    with open(f"selenium_matches_{timestamp}.txt", "w", encoding="utf-8") as f:
        f.write(f"Selenium Football Matches - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        
        for match in matches:
            f.write(f"{match['teams']}\n")
            if 'time' in match:
                f.write(f"  Time: {match['time']}\n")
            for label, (odd, book) in match['odds'].items():
                f.write(f"  {label}: {odd} @ {book}\n")
            f.write("\n")
    
    # Save surebets
    surebet_file = f"selenium_surebets_{timestamp}.txt"
    with open(surebet_file, "w", encoding="utf-8") as f:
        f.write(f"Selenium Football Surebets - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        
        if not surebets:
            f.write("No surebets found at this time.\n")
        else:
            for surebet in surebets:
                f.write(f"{surebet['match']}\n")
                if surebet['time']:
                    f.write(f"  Time: {surebet['time']}\n")
                f.write(f"  ✅ {surebet['type']} SUREBET → Profit: {surebet['profit']}%\n")
                odds_text = ", ".join(f"{k}={v[0]:.2f}" for k, v in surebet['odds'].items())
                f.write(f"  Odds: {odds_text}\n")
                f.write("\n")
    
    return surebet_file

def main():
    """Main execution function"""
    print("🚀 Starting Selenium-based football odds scraper...")
    print("🎯 Target: https://toptiket.rs/odds/football")
    print("⚠️ This requires ChromeDriver to be installed!")
    print("-" * 50)
    
    try:
        # Scrape with Selenium
        matches = scrape_with_selenium()
        
        if not matches:
            print("❌ No matches found. Check debug files for details.")
            return
        
        print(f"📈 Found {len(matches)} matches")
        
        # Analyze for surebets
        print("🔍 Analyzing for surebet opportunities...")
        surebets = analyze_surebets(matches)
        
        print(f"💰 Found {len(surebets)} surebet opportunities")
        
        # Save results
        surebet_file = save_results(matches, surebets)
        
        print("-" * 50)
        print(f"✅ Results saved to: {surebet_file}")
        
        # Display summary
        if surebets:
            print("\n🎉 SUREBET SUMMARY:")
            for surebet in surebets:
                print(f"  • {surebet['match']} - {surebet['type']} - {surebet['profit']}% profit")
        else:
            print("\n📊 No surebet opportunities found at this time.")
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        print("💡 Make sure Selenium and ChromeDriver are properly installed:")
        print("   pip install selenium webdriver-manager beautifulsoup4")

if __name__ == "__main__":
    main()
