import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime

def check_surebet(odds):
    clean_odds = [o for o, _ in odds if 0 < o < 50]  # ignore extreme invalid odds
    if len(clean_odds) < 2:
        return None
    inv_sum = sum(1 / o for o in clean_odds)
    if inv_sum < 1:
        return round((1 - inv_sum) * 100, 2)
    return None

def scrape_toptiket_football():
    """Scrape live football odds from toptiket.rs"""
    url = "https://toptiket.rs/odds/football"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        print("🌐 Fetching live data from toptiket.rs...")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        print(f"📡 Response status: {response.status_code}")
        print(f"📦 Content length: {len(response.content)} bytes")
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Debug: save the HTML content to see what we're getting
        with open("debug_html_content.txt", "w", encoding="utf-8") as f:
            f.write(soup.prettify())
        print("💾 Saved HTML content to debug_html_content.txt for inspection")
        
        matches = []
        
        print("📊 Parsing live odds data...")
        
        # Find all match containers - look for rows with teams and odds
        match_rows = soup.find_all('div', class_=lambda x: x and 'match' in str(x).lower())
        
        if not match_rows:
            # Try alternative parsing - look for text patterns
            print("🔍 Using alternative parsing method...")
            content = soup.get_text()
            
            # Debug: save the text content
            with open("debug_text_content.txt", "w", encoding="utf-8") as f:
                f.write(content)
            print("💾 Saved text content to debug_text_content.txt for inspection")
            
            matches = parse_text_content(content)
        else:
            # Parse structured HTML
            matches = parse_html_structure(soup)
            
        return matches
        
    except requests.RequestException as e:
        print(f"❌ Error fetching data: {e}")
        return []
    except Exception as e:
        print(f"❌ Error parsing data: {e}")
        return []

def parse_text_content(content):
    """Parse odds from raw text content"""
    matches = []
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    
    print(f"📝 Processing {len(lines)} lines of content...")
    
    i = 0
    while i < len(lines) - 2:
        line = lines[i]
        
        # Skip navigation and header content
        if any(skip in line.lower() for skip in [
            'početna', 'kvote', 'prognozer', 'promocije', 'fudbal', 'košarka', 'tenis', 
            'hockey', 'banner', 'copyright', '©', 'nastojimo', 'toptiket', 'mečevi',
            'dodaj', 'kladionicama', 'odgovornost', 'nepoklapanja', 'sva prava',
            'kontakt', 'marketing', 'uslovi', 'korišćenja', 'facebook', 'instagram',
            'telegram', 'twitter', 'personalizovali', 'sadržaj', 'oglase', 'omogućili',
            'funkcije', 'društvenih', 'medija', 'analizirali', 'saobraćaj'
        ]):
            i += 1
            continue
            
        # Look for time patterns (match time indicators)
        time_pattern = re.match(r'([a-z]{3},?\s*\d{1,2}\.\s*\d{1,2}\.?\s*\d{2}:\d{2})', line.lower())
        if time_pattern:
            # Next two lines should be team names
            if i + 2 < len(lines):
                team1 = lines[i + 1].strip()
                team2 = lines[i + 2].strip()
                
                # More flexible team name validation
                if (len(team1) > 2 and len(team2) > 2 and
                    not any(skip in team1.lower() for skip in ['banner', 'http', 'www', '©', 'toptiket']) and
                    not any(skip in team2.lower() for skip in ['banner', 'http', 'www', '©', 'toptiket']) and
                    not team1.isdigit() and not team2.isdigit()):
                    
                    print(f"🏆 Found match: {team1} vs {team2}")
                    
                    # Extract odds for this match
                    match_odds = extract_match_odds(lines, i + 3, min(len(lines), i + 30))
                    
                    print(f"📊 Extracted {len(match_odds)} odds for this match")
                    
                    if len(match_odds) >= 5:  # Need at least 5 odds (1X2 + O/U)
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
                        
                i += 3  # Skip team names
            else:
                i += 1
        else:
            i += 1
    
    print(f"🎯 Total matches found: {len(matches)}")
    return matches

def extract_match_odds(lines, start_idx, end_idx):
    """Extract odds from lines for a specific match"""
    odds = []
    
    for j in range(start_idx, end_idx):
        if j >= len(lines):
            break
            
        line = lines[j].strip()
        
        # Stop if we hit the next match time
        if re.match(r'[a-z]{3},?\s*\d{1,2}\.\s*\d{1,2}\.?\s*\d{2}:\d{2}', line.lower()):
            break
            
        # Stop if we hit a score indicator
        if re.match(r'^[\+\-]?\d{3}$', line):
            break
            
        # Skip empty lines and junk
        if not line or len(line) < 2:
            continue
            
        # Parse odds with bookmaker names
        parsed_odd = parse_odds_line(line)
        if parsed_odd:
            odds.append(parsed_odd)
            print(f"  📈 Found odds: {parsed_odd[0]} @ {parsed_odd[1]}")
            
        # Stop when we have enough odds
        if len(odds) >= 7:  # Get more odds to handle different structures
            break
    
    return odds

def parse_odds_line(line):
    """Parse a single line to extract odds and bookmaker"""
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
            if 0.5 <= odd <= 69 and bookmaker:
                return (odd, bookmaker)
        except ValueError:
            pass
    
    return None

def parse_html_structure(soup):
    """Parse odds from structured HTML (if available)"""
    matches = []
    # This would be implemented based on the actual HTML structure
    # For now, fallback to text parsing
    content = soup.get_text()
    return parse_text_content(content)

def analyze_surebets(matches):
    """Analyze matches for surebet opportunities"""
    surebets = []
    
    for match in matches:
        if len(match["odds"]) < 5:
            continue
            
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
    with open(f"live_football_matches_{timestamp}.txt", "w", encoding="utf-8") as f:
        f.write(f"Live Football Matches - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        
        for match in matches:
            f.write(f"{match['teams']}\n")
            if 'time' in match:
                f.write(f"  Time: {match['time']}\n")
            for label, (odd, book) in match['odds'].items():
                f.write(f"  {label}: {odd} @ {book}\n")
            f.write("\n")
    
    # Save surebets
    with open(f"live_football_surebets_{timestamp}.txt", "w", encoding="utf-8") as f:
        f.write(f"Live Football Surebets - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
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
    
    return f"live_football_surebets_{timestamp}.txt"

def main():
    """Main execution function"""
    print("🚀 Starting live football odds scraper...")
    print("🎯 Target: https://toptiket.rs/odds/football")
    print("-" * 50)
    
    # Scrape live data
    matches = scrape_toptiket_football()
    
    if not matches:
        print("❌ No matches found. The website structure might have changed.")
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
        print("💡 Try running again later as odds change frequently.")

if __name__ == "__main__":
    main()
