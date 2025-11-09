"""
Test Selenium with TopTiket - Visible mode to debug
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

def test_selenium():
    print("🧪 Testing Selenium with TopTiket (visible mode)...")
    
    try:
        # Set up Chrome options - NOT headless for debugging
        chrome_options = Options()
        # chrome_options.add_argument("--headless")  # Commented out for debugging
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1200,800")
        
        # Set up the driver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        try:
            print("📱 Opening TopTiket website...")
            driver.get("https://toptiket.rs/odds/football")
            
            print("⏳ Waiting 10 seconds for content to load...")
            time.sleep(10)  # Give it time to load
            
            # Get page title
            print(f"📄 Page title: {driver.title}")
            
            # Get page content
            page_content = driver.page_source
            print(f"📊 Page content size: {len(page_content)} characters")
            
            # Save the content
            with open("selenium_test_output.txt", "w", encoding="utf-8") as f:
                f.write(page_content)
            
            print("✅ Content saved to selenium_test_output.txt")
            
            # Check if we can find any odds-related elements
            try:
                # Look for any elements that might contain odds
                odds_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '.') and string-length(text()) < 10]")
                print(f"🎯 Found {len(odds_elements)} potential odds elements")
                
                if odds_elements:
                    for i, elem in enumerate(odds_elements[:10]):  # Show first 10
                        print(f"  Element {i+1}: '{elem.text}'")
            except:
                print("⚠️ Could not search for odds elements")
            
        finally:
            print("🔄 Closing browser...")
            driver.quit()
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    test_selenium()
