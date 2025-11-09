#!/usr/bin/env python
"""
Necaxa vs Puebla Winner Odds Analysis
Comparing your corrected odds vs extracted odds
"""

def calculate_surebet_analysis(winner1_odds, winner2_odds, total_stake=10000):
    try:
        odds1 = float(winner1_odds)
        odds2 = float(winner2_odds)
        
        # Calculate implied probabilities
        prob1 = 1 / odds1
        prob2 = 1 / odds2
        total_prob = prob1 + prob2
        
        print(f"📊 ODDS ANALYSIS:")
        print(f"   Winner 1: {odds1} (implied probability: {prob1:.4f} = {prob1*100:.2f}%)")
        print(f"   Winner 2: {odds2} (implied probability: {prob2:.4f} = {prob2*100:.2f}%)")
        print(f"   Total probability: {total_prob:.4f}")
        
        if total_prob < 1.0:
            profit_margin = (1 - total_prob) * 100
            stake1 = total_stake * prob1 / total_prob
            stake2 = total_stake * prob2 / total_prob
            return1 = stake1 * odds1
            return2 = stake2 * odds2
            guaranteed_return = min(return1, return2)
            profit = guaranteed_return - total_stake
            
            print()
            print("🎉 SUREBET CONFIRMED!")
            print(f"   Profit Margin: {profit_margin:.2f}%")
            print("   Recommended Stakes:")
            print(f"     • {stake1:.0f} RSD on Winner 1 ({odds1}) → Return: {return1:.0f} RSD")
            print(f"     • {stake2:.0f} RSD on Winner 2 ({odds2}) → Return: {return2:.0f} RSD")
            print(f"   Total Investment: {total_stake} RSD")
            print(f"   Guaranteed Profit: {profit:.0f} RSD")
            return True
        else:
            margin = (total_prob - 1) * 100
            print()
            print("❌ NOT A SUREBET")
            print(f"   Bookmaker margin: {margin:.2f}%")
            print(f"   Total probability exceeds 100% by {margin:.2f}%")
            return False
    except Exception as e:
        print(f"❌ Error in calculation: {e}")
        return False

if __name__ == "__main__":
    # Manual odds input based on your correction
    MANUAL_ODDS_1 = 1.32
    MANUAL_ODDS_2 = 3.30

    print("🚀 Winner Odds Analysis Tool")
    print("=" * 60)

    # Analysis with your corrected odds
    print(f"🎯 ANALYZING YOUR SPECIFIED ODDS: {MANUAL_ODDS_1} / {MANUAL_ODDS_2}")
    print("=" * 60)

    result1 = calculate_surebet_analysis(MANUAL_ODDS_1, MANUAL_ODDS_2)

    # Also analyze the previously extracted odds for comparison
    print()
    print("=" * 60)
    print("🔍 COMPARISON: Previously extracted odds (1.78 / 3.95)")
    print("=" * 60)
    result2 = calculate_surebet_analysis(1.78, 3.95)

    print()
    print("=" * 60)
    print("📋 SUMMARY")
    print("=" * 60)
    surebet1_text = "✅ SUREBET" if result1 else "❌ Not surebet"
    surebet2_text = "✅ SUREBET" if result2 else "❌ Not surebet"
    
    print(f"Your specified odds (1.32/3.30): {surebet1_text}")
    print(f"Previously found odds (1.78/3.95): {surebet2_text}")
    print()
    print("💡 RECOMMENDATION:")
    if not result1 and result2:
        print("   • Your corrected odds (1.32/3.30) are NOT a surebet")
        print("   • The extracted odds (1.78/3.95) ARE a surebet with 18.5% profit")
        print("   • Double-check which odds are currently live on TopTiket")
        print("   • The page might show multiple Winner markets with different odds")
    elif result1:
        print("   • Your odds represent an excellent surebet opportunity!")
    else:
        print("   • Neither set of odds represents a surebet opportunity")