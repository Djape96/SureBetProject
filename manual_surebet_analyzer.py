"""
Manual Live Odds Input - Quick Surebet Analyzer

Since automated scraping has technical challenges, this tool allows you
to manually input current odds for specific matches and instantly check
for surebet opportunities.

Use this when you see current odds that differ from your static files.
"""

import re
from datetime import datetime

def check_surebet(odds):
    """Check if odds represent a surebet opportunity"""
    clean_odds = [o for o in odds if 0 < o < 50]  # ignore extreme invalid odds
    if len(clean_odds) < 2:
        return None
    inv_sum = sum(1 / o for o in clean_odds)
    if inv_sum < 1:
        return round((1 - inv_sum) * 100, 2)
    return None

def calculate_stakes(odds, total_stake=100):
    """Calculate optimal stakes for surebet"""
    inv_sum = sum(1 / o for o in odds)
    stakes = []
    for odd in odds:
        stake = (total_stake / inv_sum) * (1 / odd)
        stakes.append(round(stake, 2))
    return stakes

def input_match_odds():
    """Interactive input for match odds"""
    print("\n" + "="*60)
    print("📝 MANUAL ODDS INPUT")
    print("="*60)
    
    # Get match info
    team1 = input("🏠 Home team: ").strip()
    team2 = input("🏃 Away team: ").strip()
    
    print(f"\n🏆 Match: {team1} vs {team2}")
    print("-" * 40)
    
    # Get 1X2 odds
    print("📊 Enter 1X2 odds (decimal format, e.g., 1.85):")
    try:
        home_odd = float(input(f"  {team1} (Home) odds: "))
        home_bookie = input(f"  Bookmaker: ").strip()
        
        draw_odd = float(input("  Draw (X) odds: "))
        draw_bookie = input(f"  Bookmaker: ").strip()
        
        away_odd = float(input(f"  {team2} (Away) odds: "))
        away_bookie = input(f"  Bookmaker: ").strip()
        
        # Check 1X2 surebet
        odds_1x2 = [home_odd, draw_odd, away_odd]
        profit_1x2 = check_surebet(odds_1x2)
        
        result = {
            "match": f"{team1} vs {team2}",
            "1x2_odds": {
                "Home": (home_odd, home_bookie),
                "Draw": (draw_odd, draw_bookie), 
                "Away": (away_odd, away_bookie)
            },
            "1x2_profit": profit_1x2
        }
        
        # Optional: Get Over/Under odds
        print(f"\n📊 Enter Over/Under odds (optional, press Enter to skip):")
        try:
            under_input = input("  Under 2.5 goals odds: ").strip()
            if under_input:
                under_odd = float(under_input)
                under_bookie = input(f"  Bookmaker: ").strip()
                
                over_odd = float(input("  Over 2.5 goals odds: "))
                over_bookie = input(f"  Bookmaker: ").strip()
                
                # Check O/U surebet
                odds_ou = [under_odd, over_odd]
                profit_ou = check_surebet(odds_ou)
                
                result["ou_odds"] = {
                    "Under 2.5": (under_odd, under_bookie),
                    "Over 2.5": (over_odd, over_bookie)
                }
                result["ou_profit"] = profit_ou
        except:
            pass
            
        return result
        
    except ValueError:
        print("❌ Invalid number format. Please use decimal numbers (e.g., 1.85)")
        return None
    except KeyboardInterrupt:
        print("\n❌ Cancelled by user")
        return None

def display_analysis(result):
    """Display surebet analysis"""
    print("\n" + "="*60)
    print("🎯 SUREBET ANALYSIS")
    print("="*60)
    print(f"🏆 Match: {result['match']}")
    print("-" * 40)
    
    # 1X2 Analysis
    print("📊 1X2 MARKET:")
    for outcome, (odd, bookie) in result['1x2_odds'].items():
        print(f"  {outcome}: {odd:.2f} @ {bookie}")
    
    if result['1x2_profit']:
        print(f"✅ 1X2 SUREBET FOUND! Profit: {result['1x2_profit']:.2f}%")
        
        # Calculate stakes
        odds_only = [odd for odd, _ in result['1x2_odds'].values()]
        stakes_100 = calculate_stakes(odds_only, 100)
        stakes_1000 = calculate_stakes(odds_only, 1000)
        
        print(f"\n💰 Stake Distribution (for 100€ total):")
        outcomes = list(result['1x2_odds'].keys())
        for i, (outcome, (odd, bookie)) in enumerate(result['1x2_odds'].items()):
            stake = stakes_100[i]
            return_amount = stake * odd
            print(f"  {outcome}: {stake:.2f}€ @ {bookie} → Returns: {return_amount:.2f}€")
        
        print(f"\n💰 Stake Distribution (for 1000€ total):")
        for i, (outcome, (odd, bookie)) in enumerate(result['1x2_odds'].items()):
            stake = stakes_1000[i]
            return_amount = stake * odd
            print(f"  {outcome}: {stake:.2f}€ @ {bookie} → Returns: {return_amount:.2f}€")
            
    else:
        print(f"❌ No 1X2 surebet (margin: {(sum(1/odd for odd, _ in result['1x2_odds'].values()) - 1) * 100:.2f}%)")
    
    # O/U Analysis if available
    if 'ou_odds' in result:
        print(f"\n📊 OVER/UNDER 2.5 GOALS:")
        for outcome, (odd, bookie) in result['ou_odds'].items():
            print(f"  {outcome}: {odd:.2f} @ {bookie}")
        
        if result['ou_profit']:
            print(f"✅ O/U SUREBET FOUND! Profit: {result['ou_profit']:.2f}%")
            
            # Calculate stakes for O/U
            odds_only_ou = [odd for odd, _ in result['ou_odds'].values()]
            stakes_100_ou = calculate_stakes(odds_only_ou, 100)
            
            print(f"\n💰 O/U Stake Distribution (for 100€ total):")
            for i, (outcome, (odd, bookie)) in enumerate(result['ou_odds'].items()):
                stake = stakes_100_ou[i]
                return_amount = stake * odd
                print(f"  {outcome}: {stake:.2f}€ @ {bookie} → Returns: {return_amount:.2f}€")
        else:
            print(f"❌ No O/U surebet (margin: {(sum(1/odd for odd, _ in result['ou_odds'].values()) - 1) * 100:.2f}%)")

def save_manual_analysis(result):
    """Save manual analysis to file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"manual_surebet_analysis_{timestamp}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Manual Surebet Analysis - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Match: {result['match']}\n\n")
        
        f.write("1X2 Market:\n")
        for outcome, (odd, bookie) in result['1x2_odds'].items():
            f.write(f"  {outcome}: {odd:.2f} @ {bookie}\n")
        
        if result['1x2_profit']:
            f.write(f"\n✅ 1X2 SUREBET: {result['1x2_profit']:.2f}% profit\n")
        else:
            f.write(f"\n❌ No 1X2 surebet\n")
        
        if 'ou_odds' in result:
            f.write(f"\nOver/Under 2.5 Goals:\n")
            for outcome, (odd, bookie) in result['ou_odds'].items():
                f.write(f"  {outcome}: {odd:.2f} @ {bookie}\n")
            
            if result['ou_profit']:
                f.write(f"\n✅ O/U SUREBET: {result['ou_profit']:.2f}% profit\n")
            else:
                f.write(f"\n❌ No O/U surebet\n")
    
    return filename

def main():
    """Main function"""
    print("🚀 MANUAL LIVE ODDS SUREBET ANALYZER")
    print("📝 Input current odds to check for surebet opportunities")
    print("🎯 Perfect for when you see different odds than in static files")
    
    while True:
        try:
            result = input_match_odds()
            if result:
                display_analysis(result)
                filename = save_manual_analysis(result)
                print(f"\n💾 Analysis saved to: {filename}")
            
            print("\n" + "-"*60)
            another = input("❓ Analyze another match? (y/n): ").strip().lower()
            if another not in ['y', 'yes']:
                break
                
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
    
    print("✅ Manual analysis complete!")

if __name__ == "__main__":
    main()
