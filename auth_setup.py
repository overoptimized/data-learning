import os
from playwright.sync_api import sync_playwright

def run():
    print("=====================================================")
    print("Launching browser for authentication...")
    print("Please log in manually in the opened browser window.")
    print("=====================================================")
    
    with sync_playwright() as p:
        # Launch visible browser for manual login
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Navigate to the target platform (DataExpert.io used as placeholder)
        print("Navigating to https://www.dataexpert.io ...")
        page.goto("https://www.dataexpert.io")
        
        # Wait for the user to manually log in
        input("\n>>> Press Enter here in the terminal once you have successfully logged in... <<<\n")
        
        print("Saving session state to state.json...")
        context.storage_state(path="state.json")
        print("Session state saved! You can now run main.py for batch processing.")
        
        browser.close()

if __name__ == "__main__":
    run()
