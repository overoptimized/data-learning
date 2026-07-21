import os
import re
import json
import subprocess
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Request
from rich.console import Console

console = Console()

OUTPUT_DIR = "local_library"

def clean_title(title: str) -> str:
    """Clean the title to generate a safe folder name."""
    title = title.strip()
    title = re.sub(r'[^\w\s-]', '', title)
    title = re.sub(r'[-\s]+', '_', title)
    return title.strip('_')

def process_url(page, url: str):
    console.print(f"[bold blue]Processing URL:[/bold blue] {url}")
    
    # Storage for intercepted media
    intercepted_m3u8 = None
    intercepted_vtt = None
    
    def handle_request(request: Request):
        nonlocal intercepted_m3u8, intercepted_vtt
        req_url = request.url
        if ".m3u8" in req_url and not intercepted_m3u8:
            intercepted_m3u8 = req_url
        if ("/transcripts" in req_url or ".vtt" in req_url) and not intercepted_vtt:
            intercepted_vtt = req_url
            
    page.on("request", handle_request)
    
    # Navigate to the URL and wait for full hydration
    console.print("Navigating and waiting for network idle...")
    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
    except Exception as e:
        console.print(f"[bold red]Failed to load URL:[/bold red] {e}")
        page.remove_listener("request", handle_request)
        return

    # Scrape DOM for title and notes
    try:
        title_element = page.locator("h1").first
        raw_title = title_element.inner_text() if title_element.count() > 0 else "Untitled Lesson"
    except Exception:
        raw_title = "Untitled Lesson"
        
    folder_name = clean_title(raw_title)
    if not folder_name:
        folder_name = "Untitled_Lesson"
        
    lesson_dir = os.path.join(OUTPUT_DIR, folder_name)
    os.makedirs(lesson_dir, exist_ok=True)
    
    console.print(f"Creating directory: [bold green]{lesson_dir}[/bold green]")
    
    try:
        # Scrape main text content for notes. Adjust the selector to match the site structure.
        main_content = page.locator("main").first
        notes_text = main_content.inner_text() if main_content.count() > 0 else "No notes found."
    except Exception:
        notes_text = "No notes found."
        
    # Attempt to extract badges/topics as YAML frontmatter
    badges = page.locator(".badge, [class*='badge']").all_inner_texts()
    tags = [badge.strip() for badge in badges if badge.strip()]
    
    notes_content = f"---\ntags: {json.dumps(tags)}\n---\n\n# {raw_title}\n\n{notes_text}"
    
    with open(os.path.join(lesson_dir, "notes.md"), "w", encoding="utf-8") as f:
        f.write(notes_content)
        
    # Download Transcript if intercepted
    if intercepted_vtt:
        console.print(f"[bold yellow]Intercepted transcript URL:[/bold yellow] {intercepted_vtt}")
        try:
            # We use the authenticated page context to fetch the transcript
            response = page.request.get(intercepted_vtt)
            with open(os.path.join(lesson_dir, "transcript.vtt"), "wb") as f:
                f.write(response.body())
            console.print("[green]Transcript downloaded.[/green]")
        except Exception as e:
            console.print(f"[bold red]Failed to download transcript:[/bold red] {e}")
    else:
        console.print("[yellow]No transcript intercepted.[/yellow]")

    # Download Media using yt-dlp
    if intercepted_m3u8:
        console.print(f"[bold yellow]Intercepted video manifest:[/bold yellow] {intercepted_m3u8}")
        video_output = os.path.join(lesson_dir, "video.mp4")
        
        # Note: If the stream requires the session cookies, you may need to pass them to yt-dlp.
        # This implementation tries without passing cookies first.
        # To pass cookies to yt-dlp, you might need to extract them from Playwright context.
        yt_dlp_cmd = [
            "yt-dlp",
            intercepted_m3u8,
            "-o", video_output
        ]
        
        console.print("Starting video download via yt-dlp...")
        subprocess.run(yt_dlp_cmd)
        console.print("[green]Video download completed.[/green]")
    else:
        console.print("[yellow]No video stream intercepted.[/yellow]")

    page.remove_listener("request", handle_request)
    console.print(f"[bold green]Finished processing {url}[/bold green]\n")


def main():
    if not os.path.exists("state.json"):
        console.print("[bold red]Error:[/bold red] state.json not found! Please run auth_setup.py first.")
        return
        
    if not os.path.exists("urls.txt"):
        console.print("[bold red]Error:[/bold red] urls.txt not found. Create it and add target URLs.")
        return
        
    with open("urls.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
    if not urls:
        console.print("[yellow]No URLs found in urls.txt[/yellow]")
        return
        
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Load the saved session state
        context = browser.new_context(storage_state="state.json")
        page = context.new_page()
        
        for url in urls:
            process_url(page, url)
            
        browser.close()

if __name__ == "__main__":
    main()
