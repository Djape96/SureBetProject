#!/usr/bin/env python3
"""
Analysis of different odds to identify correct Winner/DNB market
"""

def analyze_odds_market(odds1, odds2, market_name):
    prob1 = 1/odds1
    prob2 = 1/odds2
    total_prob = prob1 + prob2
    margin = (total_prob - 1) * 100 if total_prob > 1 else 0
    
    print(f'{market_name}:')
    print(f'  Odds: {odds1} / {odds2}')
    print(f'  Implied probabilities: {prob1:.1%} / {prob2:.1%}')
    print(f'  Total probability: {total_prob:.4f}')
    print(f'  Bookmaker margin: {margin:.2f}%')
    surebet_status = '✅ YES' if total_prob < 1 else '❌ NO'
    print(f'  Surebet: {surebet_status}')
    if total_prob < 1:
        profit = (1 - total_prob) * 100
        print(f'  Arbitrage profit: {profit:.2f}%')
    print()

def main():
    print('🔍 ODDS ANALYSIS COMPARISON')
    print('=' * 50)

    # The odds I incorrectly extracted
    analyze_odds_market(1.78, 3.95, 'EXTRACTED ODDS (1.78/3.95) - UNKNOWN MARKET')

    # Your correct Winner/DNB odds  
    analyze_odds_market(1.32, 3.30, 'CORRECT WINNER/DNB ODDS (1.32/3.30)')

    # For comparison, let's see what a typical 1X2 market might look like
    analyze_odds_market(1.95, 4.80, 'ESTIMATED 1X2 HOME/AWAY (for reference)')

    print('💡 CONCLUSION:')
    print('• Your Winner/DNB odds (1.32/3.30) are NOT a surebet (normal market)')
    print('• The extracted odds (1.78/3.95) ARE a surebet but from wrong market')
    print('• Need to fix scraper to target the correct Winner/DNB section')
    print('• Winner = Draw No Bet (stake refunded if draw)')
    print()
    print('🔧 NEXT STEPS:')
    print('• Update winner_scraper.py to find correct Winner/DNB section')
    print('• Look for specific "Winner" or "Draw No Bet" labels')
    print('• Avoid other markets like Asian Handicap, Over/Under, etc.')

if __name__ == "__main__":
    main()