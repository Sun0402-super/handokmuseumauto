from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

def diagnose():
    options = Options()
    options.add_argument('--start-maximized')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    # Try with many flags
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    print("Attempting to start Chrome...")
    try:
        driver = webdriver.Chrome(options=options)
        print("Successfully started Chrome!")
        print(f"Browser version: {driver.capabilities['browserVersion']}")
        print(f"ChromeDriver version: {driver.capabilities['chrome']['chromedriverVersion']}")
        time.sleep(3)
        driver.quit()
    except Exception as e:
        print(f"Failed to start Chrome: {e}")

if __name__ == "__main__":
    diagnose()
