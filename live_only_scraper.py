"""
Live-Only Football Odds Scraper
No static files - only current live data from TopTiket
"""

import requests
import time
import os
from datetime import datetime

def try_selenium_scraping():
    """Try Selenium with different configurations"""
    print("🔧 Attempting Selenium WebDriver setup...")
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
        
        # Try different Chrome configurations
        configurations = [
            {
                "name": "Standard Chrome",
                "options": [
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--window-size=1920,1080"
                ]
            },
            {
                "name": "Chrome with minimal flags",
                "options": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            },
            {
                "name": "Chrome incognito",
                "options": [
                    "--incognito",
                    "--disable-dev-shm-usage",
                    "--no-sandbox"
                ]
            }
        ]
        
        for config in configurations:
            print(f"🧪 Trying: {config['name']}")
            
            try:
                chrome_options = Options()
                for option in config['options']:
                    chrome_options.add_argument(option)
                
                # Try to install and use ChromeDriver
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                print(f"✅ {config['name']} - WebDriver started successfully!")
                
                # Test the connection
                driver.get("https://toptiket.rs/odds/football")
                print("🌐 Successfully opened TopTiket")
                
                # Wait for content
                time.sleep(8)
                
                page_content = driver.page_source
                driver.quit()
                
                if "You need to enable JavaScript" not in page_content and len(page_content) > 5000:
                    print(f"✅ Successfully got content with {config['name']}")
                    return page_content
                else:
                    print(f"⚠️ {config['name']} - Content not fully loaded")
                    
            except Exception as e:
                print(f"❌ {config['name']} failed: {str(e)[:100]}")
                continue
        
        print("❌ All Selenium configurations failed")
        return None
        
    except ImportError:
        print("❌ Selenium not installed")
        return None

def try_requests_with_session():
    """Try advanced requests with session and different headers"""
    print("🔧 Trying advanced HTTP requests...")
    
    session = requests.Session()
    
    headers_configs = [
        {
            "name": "Chrome Windows",
            "headers": {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        },
        {
            "name": "Firefox",
            "headers": {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
        }
    ]
    
    for config in headers_configs:
        print(f"🧪 Trying: {config['name']}")
        
        try:
            response = session.get("https://toptiket.rs/odds/football", 
                                 headers=config['headers'], 
                                 timeout=15)
            
            if response.status_code == 200:
                content = response.text
                if "You need to enable JavaScript" not in content and len(content) > 5000:
                    print(f"✅ Success with {config['name']}!")
                    return content
                else:
                    print(f"⚠️ {config['name']} - JavaScript required or content too small")
            else:
                print(f"❌ {config['name']} - Status: {response.status_code}")
                
        except Exception as e:
            print(f"❌ {config['name']} failed: {str(e)[:50]}")
    
    return None

def parse_live_content(content):
    """Parse live content for football odds"""
    try:
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # Save raw HTML for inspection
        with open("live_raw_content.html", "w", encoding="utf-8") as f:
            f.write(content)
        
        # Extract text
        text_content = soup.get_text(separator='\n', strip=True)
        
        with open("live_text_content.txt", "w", encoding="utf-8") as f:
            f.write(text_content)
        
        print(f"📄 Content saved to live_text_content.txt ({len(text_content)} chars)")
        
        # Look for patterns that might be odds
        lines = text_content.split('\n')
        potential_odds = []
        
        for line in lines:
            line = line.strip()
            # Look for decimal numbers that could be odds
            if line and '.' in line:
                try:
                    # Check if it's a number in betting odds range
                    num = float(line)
                    if 1.1 <= num <= 50.0:  # Typical betting odds range
                        potential_odds.append(line)
                except:
                    pass
        
        print(f"🎯 Found {len(potential_odds)} potential odds values")
        if potential_odds:
            print("📊 Sample odds found:", potential_odds[:10])
        
        return len(potential_odds) > 0
        
    except Exception as e:
        print(f"❌ Parsing error: {str(e)}")
        return False

def main():
    """Main live scraping function"""
    print("🚀 LIVE-ONLY FOOTBALL ODDS SCRAPER")
    print("🎯 No static files - only current TopTiket data")
    print("="*50)
    
    content = None
    
    # Try Selenium first (more reliable for JavaScript sites)
    content = try_selenium_scraping()
    
    # If Selenium fails, try advanced requests
    if not content:
        print("\n" + "-"*30)
        content = try_requests_with_session()
    
    if content:
        print("\n✅ Successfully downloaded live content!")
        print(f"📊 Content size: {len(content)} characters")
        
        # Parse the content
        if parse_live_content(content):
            print("✅ Found potential odds data!")
            print("📄 Check live_text_content.txt for extracted data")
        else:
            print("⚠️ No odds data found - website might need different approach")
            
    else:
        print("\n❌ FAILED TO GET LIVE DATA")
        print("💡 Possible solutions:")
        print("   1. Check internet connection")
        print("   2. Try running as administrator")
        print("   3. Install/update Chrome browser")
        print("   4. Use manual_surebet_analyzer.py instead")
        
        print(f"\n🔄 Alternative: Use manual input tool")
        print(f"   python manual_surebet_analyzer.py")

if __name__ == "__main__":
    main()
