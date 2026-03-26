import os
from driver_utils import setup_chrome_driver, kill_chrome_processes

def debug_driver():
    kill_chrome_processes()
    print("Testing setup_chrome_driver...")
    driver, status = setup_chrome_driver(headless=False, use_profile=False)
    if driver:
        print(f"Success! Status: {status}")
        print(f"URL: {driver.current_url}")
        driver.quit()
    else:
        print(f"Failed! Status: {status}")

if __name__ == "__main__":
    debug_driver()
