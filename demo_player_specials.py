"""Demo script to show player specials surebet detection with simulated data

This demonstrates how the player specials analyzer would detect and display surebets
if there were arbitrage opportunities in the data.
"""

def simulate_player_specials_surebets():
    """Simulate some player specials data with surebet opportunities."""
    
    # Simulated data with some surebet opportunities
    simulated_matches = [
        {
            'player': 'LeBron James',
            'team': 'Lakers',
            'stat_type': 'Points',
            'stat_value': '27.5',
            'teams': 'LeBron James - Points 27.5',
            'odds': {
                'Under': (2.10, 'TopTiket'),  # These create a surebet
                'Over': (1.85, 'TopTiket')    # 1/2.10 + 1/1.85 = 0.476 + 0.541 = 1.017 > 1 (not surebet)
            }
        },
        {
            'player': 'Stephen Curry',
            'team': 'Warriors', 
            'stat_type': 'Points',
            'stat_value': '26.5',
            'teams': 'Stephen Curry - Points 26.5',
            'odds': {
                'Under': (2.20, 'TopTiket'),  # These create a surebet
                'Over': (1.75, 'TopTiket')    # 1/2.20 + 1/1.75 = 0.455 + 0.571 = 1.026 > 1 (not surebet)
            }
        },
        {
            'player': 'Giannis Antetokounmpo',
            'team': 'Bucks',
            'stat_type': 'Points', 
            'stat_value': '29.5',
            'teams': 'Giannis Antetokounmpo - Points 29.5',
            'odds': {
                'Under': (2.25, 'TopTiket'),  # This creates a surebet
                'Over': (1.70, 'TopTiket')    # 1/2.25 + 1/1.70 = 0.444 + 0.588 = 1.032 > 1 (not surebet)
            }
        },
        {
            'player': 'Kevin Durant',
            'team': 'Suns',
            'stat_type': 'Points',
            'stat_value': '25.5', 
            'teams': 'Kevin Durant - Points 25.5',
            'odds': {
                'Under': (2.35, 'TopTiket'),  # This creates a surebet!
                'Over': (1.65, 'TopTiket')    # 1/2.35 + 1/1.65 = 0.426 + 0.606 = 1.032 > 1 (not surebet)
            }
        },
        {
            'player': 'Nikola Jokic',
            'team': 'Nuggets',
            'stat_type': 'Points',
            'stat_value': '24.5',
            'teams': 'Nikola Jokic - Points 24.5', 
            'odds': {
                'Under': (2.10, 'TopTiket'),  # This is a REAL surebet!
                'Over': (1.95, 'TopTiket')    # 1/2.10 + 1/1.95 = 0.476 + 0.513 = 0.989 < 1 (SUREBET!)
            }
        }
    ]
    
    return simulated_matches

def demo_surebet_analysis():
    """Demonstrate surebet analysis on simulated data."""
    
    # Import the analysis functions
    from arbitrage_player_specials import detect_player_surebets, write_player_specials_results
    
    # Get simulated data
    matches = simulate_player_specials_surebets()
    
    print("🎯 PLAYER SPECIALS SUREBET DEMO")
    print("="*50)
    print(f"📊 Analyzing {len(matches)} simulated player specials...")
    
    # Detect surebets with 0% minimum profit
    surebets = detect_player_surebets(matches, min_profit=0.0, total_stake=100.0)
    
    print(f"💰 Found {len(surebets)} surebets!")
    print()
    
    # Display the results
    if surebets:
        print("🎉 SUREBET OPPORTUNITIES:")
        print("-" * 40)
        
        for sb in surebets:
            print(f"Player: {sb['player']} ({sb['stat_type']} {matches[0]['stat_value']})")
            print(f"  ROI: {sb['roi_pct']:.2f}%")
            print(f"  Margin: {sb['margin_pct']:.2f}%")
            print(f"  Under: {sb['odds']['Under']['odd']} -> Stake: ${sb['stakes']['Under']}")
            print(f"  Over: {sb['odds']['Over']['odd']} -> Stake: ${sb['stakes']['Over']}")
            print(f"  Total Investment: ${sb['stakes']['Under'] + sb['stakes']['Over']}")
            
            # Calculate guaranteed profit
            under_return = sb['stakes']['Under'] * sb['odds']['Under']['odd']
            over_return = sb['stakes']['Over'] * sb['odds']['Over']['odd']
            min_return = min(under_return, over_return)
            total_stake = sb['stakes']['Under'] + sb['stakes']['Over']
            profit = min_return - total_stake
            
            print(f"  Guaranteed Profit: ${profit:.2f}")
            print()
    
    # Write to demo file
    write_player_specials_results(matches, surebets, 1)
    print("📝 Demo results written to player_specials_surebets.txt")
    
    return surebets

if __name__ == "__main__":
    demo_surebet_analysis()