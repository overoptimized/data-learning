import os
import json
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
from rich.console import Console

console = Console()

COURSE_URL = "https://www.dataexpert.io/program/data-expert/details"

def main():
    if not os.path.exists("state.json"):
        console.print("[bold red]Error:[/bold red] state.json not found! Please run auth_setup.py first.")
        return

    console.print(f"Navigating to {COURSE_URL} to extract lesson URLs...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Load the saved session state to bypass login
        context = browser.new_context(
            storage_state="state.json",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # Go to the curriculum page
            page.goto(COURSE_URL, wait_until="networkidle", timeout=60000)
            console.print("[green]Page loaded. Extracting links...[/green]")
            
            # Find all anchor tags
            links = page.locator("a").element_handles()
            
            lesson_urls = set()
            for link in links:
                href = link.get_attribute("href")
                if href and "/lesson/" in href:
                    # Resolve relative URLs just in case
                    full_url = urljoin(COURSE_URL, href)
                    lesson_urls.add(full_url)
            
            if not lesson_urls:
                console.print("[yellow]No lesson URLs found. The page structure might be different, or the content requires scrolling/clicks to load.[/yellow]")
                return
                
            # Write unique URLs to urls.txt
            with open("urls.txt", "w", encoding="utf-8") as f:
                for url in sorted(lesson_urls):
                    f.write(url + "\n")
                    
            console.print(f"[bold green]Successfully extracted {len(lesson_urls)} lesson URLs and saved to urls.txt![/bold green]")
            
        except Exception as e:
            console.print(f"[bold red]Failed to extract URLs:[/bold red] {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    main()
