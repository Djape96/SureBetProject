import requests
import json
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

def try_api_endpoints():
    """Try to find API endpoints that provide the odds data"""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://toptiket.rs/odds/football',
        'Origin': 'https://toptiket.rs'
    }
    
    # Common API endpoint patterns
    api_endpoints = [
        'https://toptiket.rs/api/odds/football',
        'https://toptiket.rs/api/football/odds',
        'https://toptiket.rs/api/v1/odds/football',
        'https://toptiket.rs/api/v2/odds/football',
        'https://api.toptiket.rs/odds/football',
        'https://api.toptiket.rs/football/odds',
        'https://toptiket.rs/odds/api/football',
        'https://toptiket.rs/football/api/odds'
    ]
    
    print("🔍 Searching for API endpoints...")
    
    for endpoint in api_endpoints:
        try:
            print(f"🌐 Trying: {endpoint}")
            response = requests.get(endpoint, headers=headers, timeout=5)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"✅ Found working API endpoint: {endpoint}")
                    print(f"📦 Response type: JSON with {len(data) if isinstance(data, (list, dict)) else 'unknown'} items")
                    
                    # Save the response for analysis
                    with open("api_response.json", "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    
                    return endpoint, data
                except json.JSONDecodeError:
                    print(f"📄 Response is not JSON, content length: {len(response.content)}")
            else:
                print(f"❌ Status: {response.status_code}")
                
        except requests.RequestException as e:
            print(f"❌ Error: {e}")
        
        time.sleep(0.5)  # Be respectful with requests
    
    return None, None

def parse_api_data(data):
    """Parse football odds data from API response"""
    matches = []
    
    if not data:
        return matches
        
    # Try different data structures
    if isinstance(data, dict):
        # Check for common keys
        possible_keys = ['matches', 'games', 'events', 'fixtures', 'data', 'results']
        for key in possible_keys:
            if key in data and isinstance(data[key], list):
                print(f"📊 Found matches in key: {key}")
                matches = parse_matches_list(data[key])
                break
        
        # If no list found, maybe the whole dict is a match
        if not matches and 'home' in str(data).lower() or 'away' in str(data).lower():
            matches = [parse_single_match(data)]
    
    elif isinstance(data, list):
        print(f"📊 Parsing list of {len(data)} items")
        matches = parse_matches_list(data)
    
    return matches

def parse_matches_list(matches_list):
    """Parse a list of match data"""
    parsed_matches = []
    
    for item in matches_list:
        if isinstance(item, dict):
            match = parse_single_match(item)
            if match:
                parsed_matches.append(match)
    
    return parsed_matches

def parse_single_match(match_data):
    """Parse a single match from API data"""
    try:
        # Try to extract team names
        teams = extract_team_names(match_data)
        if not teams:
            return None
        
        # Try to extract odds
        odds = extract_odds(match_data)
        if len(odds) < 5:
            return None
        
        return {
            "teams": f"{teams[0]} vs {teams[1]}",
            "odds": {
                "Home": odds[0],
                "Draw": odds[1], 
                "Away": odds[2],
                "0-2": odds[3],
                "3+": odds[4]
            },
            "raw_data": match_data  # Keep for debugging
        }
        
    except Exception as e:
        print(f"❌ Error parsing match: {e}")
        return None

def extract_team_names(match_data):
    """Extract team names from match data"""
    team_keys = [
        ['home', 'away'], ['home_team', 'away_team'], 
        ['team1', 'team2'], ['homeTeam', 'awayTeam'],
        ['teams'], ['participants']
    ]
    
    for keys in team_keys:
        if len(keys) == 2:
            if keys[0] in match_data and keys[1] in match_data:
                return [match_data[keys[0]], match_data[keys[1]]]
        elif len(keys) == 1:
            if keys[0] in match_data:
                teams_data = match_data[keys[0]]
                if isinstance(teams_data, list) and len(teams_data) >= 2:
                    return teams_data[:2]
    
    return None

def extract_odds(match_data):
    """Extract odds from match data"""
    odds = []
    
    # Common odds keys
    odds_keys = ['odds', 'markets', 'prices', 'outcomes']
    
    for key in odds_keys:
        if key in match_data:
            odds_data = match_data[key]
            if isinstance(odds_data, dict):
                # Try to find 1X2 and Over/Under markets
                extracted = extract_from_markets(odds_data)
                if extracted:
                    odds.extend(extracted)
            elif isinstance(odds_data, list):
                extracted = extract_from_list(odds_data)
                if extracted:
                    odds.extend(extracted)
    
    return odds

def extract_from_markets(odds_data):
    """Extract odds from market-based structure"""
    odds = []
    
    # Look for 1X2 market
    if '1x2' in odds_data or '1X2' in odds_data:
        market = odds_data.get('1x2', odds_data.get('1X2'))
        if isinstance(market, dict):
            for outcome in ['1', 'X', '2']:
                if outcome in market:
                    odds.append((float(market[outcome]), 'API'))
    
    # Look for Over/Under market
    if 'over_under' in odds_data or 'totals' in odds_data:
        market = odds_data.get('over_under', odds_data.get('totals'))
        if isinstance(market, dict):
            for outcome in ['under', 'over']:
                if outcome in market:
                    odds.append((float(market[outcome]), 'API'))
    
    return odds

def extract_from_list(odds_data):
    """Extract odds from list structure"""
    odds = []
    
    for item in odds_data:
        if isinstance(item, dict) and 'price' in item:
            odds.append((float(item['price']), 'API'))
        elif isinstance(item, (int, float)):
            odds.append((float(item), 'API'))
    
    return odds

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
                "type": "0-2 / 3+",
                "profit": profit_ou,
                "odds": {k: match["odds"][k] for k in ["0-2", "3+"]}
            }
            surebets.append(surebet_info)
    
    return surebets

def save_results(matches, surebets):
    """Save results to files"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save surebets
    surebet_file = f"api_football_surebets_{timestamp}.txt"
    with open(surebet_file, "w", encoding="utf-8") as f:
        f.write(f"API Football Surebets - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        
        if not surebets:
            f.write("No surebets found at this time.\n")
        else:
            for surebet in surebets:
                f.write(f"{surebet['match']}\n")
                f.write(f"  ✅ {surebet['type']} SUREBET → Profit: {surebet['profit']}%\n")
                odds_text = ", ".join(f"{k}={v[0]:.2f}" for k, v in surebet['odds'].items())
                f.write(f"  Odds: {odds_text}\n")
                f.write("\n")
    
    return surebet_file

def main():
    """Main execution function"""
    print("🚀 Starting API-based football odds scraper...")
    print("🎯 Searching for TopTiket API endpoints...")
    print("-" * 50)
    
    # Try to find working API endpoints
    endpoint, data = try_api_endpoints()
    
    if not endpoint:
        print("❌ No working API endpoints found.")
        print("💡 The website might use different API structure or require authentication.")
        print("🔧 Alternative: Use Selenium WebDriver to handle JavaScript-rendered content.")
        return
    
    print(f"✅ Using API endpoint: {endpoint}")
    
    # Parse the API data
    matches = parse_api_data(data)
    
    if not matches:
        print("❌ Could not parse match data from API response.")
        print("💾 Check api_response.json for the raw data structure.")
        return
    
    print(f"📈 Found {len(matches)} matches from API")
    
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

if __name__ == "__main__":
    main()
