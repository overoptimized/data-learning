import os
import json
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
from rich.console import Console
import sys

console = Console()

def fetch_course_urls(course_slug):
    course_url = f"https://www.dataexpert.io/program/{course_slug}/details"
    console.print(f"Navigating to {course_url} to extract lesson URLs...")

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
            page.goto(course_url, wait_until="networkidle", timeout=60000)
            console.print(f"[green]Page loaded for {course_slug}. Extracting links...[/green]")
            
            # Find all anchor tags
            links = page.locator("a").element_handles()
            
            lesson_urls = set()
            for link in links:
                href = link.get_attribute("href")
                if href and "/lesson/" in href:
                    # Resolve relative URLs just in case
                    full_url = urljoin(course_url, href)
                    lesson_urls.add(full_url)
            
            if not lesson_urls:
                console.print(f"[yellow]No lesson URLs found for {course_slug}.[/yellow]")
                return
                
            # Write unique URLs to urls_{slug}.txt
            filename = f"urls_{course_slug}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                for url in sorted(lesson_urls):
                    f.write(url + "\n")
                    
            console.print(f"[bold green]Successfully extracted {len(lesson_urls)} lesson URLs and saved to {filename}![/bold green]")
            
        except Exception as e:
            console.print(f"[bold red]Failed to extract URLs for {course_slug}:[/bold red] {e}")
        finally:
            browser.close()

def main():
    if not os.path.exists("state.json"):
        console.print("[bold red]Error:[/bold red] state.json not found! Please run auth_setup.py first.")
        return

    # Can pass course slugs as arguments, otherwise runs on all
    courses = sys.argv[1:]
    if not courses:
        courses = [
            "data-engineer-interview-skills",
            "linkedin-expert",
            "fullstack-expert",
            "analytics-expert",
            "ai-expert",
            "interview-expert"
        ]

    for course in courses:
        fetch_course_urls(course)

if __name__ == "__main__":
    main()
