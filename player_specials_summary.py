"""Quick Player Specials Summary

Shows the latest player specials analysis results without re-scraping.
"""

import os
from datetime import datetime

def show_latest_results():
    """Display the latest player specials surebet results."""
    
    # Check if results file exists
    results_file = "player_specials_surebets.txt"
    if not os.path.exists(results_file):
        print("❌ No player specials results found. Run arbitrage_player_specials.py first.")
        return
    
    # Read and display results
    with open(results_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("🎯 LATEST PLAYER SPECIALS ANALYSIS")
    print("=" * 50)
    print(content)
    
    # Check file modification time
    mod_time = os.path.getmtime(results_file)
    mod_datetime = datetime.fromtimestamp(mod_time)
    time_diff = datetime.now() - mod_datetime
    
    if time_diff.total_seconds() < 300:  # Less than 5 minutes
        print(f"📅 Results are fresh (generated {time_diff.seconds} seconds ago)")
    elif time_diff.total_seconds() < 3600:  # Less than 1 hour
        print(f"📅 Results are recent (generated {int(time_diff.total_seconds()//60)} minutes ago)")
    else:
        print(f"📅 Results may be outdated (generated {mod_datetime.strftime('%Y-%m-%d %H:%M:%S')})")
        print("💡 Consider running: python arbitrage_player_specials.py --pages 4")

def quick_surebet_check():
    """Quick check for current surebets from the latest data."""
    
    results_file = "player_specials_surebets.txt"
    if not os.path.exists(results_file):
        print("❌ No results file found.")
        return
    
    with open(results_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Extract key info
    total_specials = 0
    surebets_found = 0
    pages_scraped = 0
    
    for line in lines:
        if line.startswith("Total player specials:"):
            total_specials = int(line.split(":")[1].strip())
        elif line.startswith("Surebets found:"):
            surebets_found = int(line.split(":")[1].strip())
        elif line.startswith("Pages scraped:"):
            pages_scraped = int(line.split(":")[1].strip())
    
    print(f"📊 Quick Summary:")
    print(f"   • Player specials analyzed: {total_specials}")
    print(f"   • Pages scraped: {pages_scraped}")
    print(f"   • Surebets found: {surebets_found}")
    
    if surebets_found > 0:
        print(f"   • Potential profit opportunities: {surebets_found}")
        print("💰 Check the full results above for details!")
    else:
        print("   • No current surebets (consider checking other pages/bookmakers)")

if __name__ == "__main__":
    show_latest_results()
    print()
    quick_surebet_check()