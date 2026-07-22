import os
import re
import json
import subprocess
import time
import random
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Request
from playwright_stealth import stealth_sync
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
    m3u8_headers = {}
    intercepted_vtt = None
    intercepted_pdfs = set()
    
    def handle_request(request: Request):
        nonlocal intercepted_m3u8, m3u8_headers, intercepted_vtt, intercepted_pdfs
        req_url = request.url
        if ".m3u8" in req_url and not intercepted_m3u8:
            intercepted_m3u8 = req_url
            m3u8_headers = request.all_headers()
        if ("/transcripts" in req_url or ".vtt" in req_url) and not intercepted_vtt:
            intercepted_vtt = req_url
        if (".pdf" in req_url) and req_url not in intercepted_pdfs:
            intercepted_pdfs.add(req_url)
            
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

    # Download Media using yt-dlp (checking for redownloads first)
    video_output = os.path.join(lesson_dir, "video.mp4")
    if os.path.exists(video_output) and os.path.getsize(video_output) > 1024:
        console.print("[green]Video already exists locally. Skipping download to save time.[/green]")
        intercepted_m3u8 = None  # Clear to prevent download
        
    if intercepted_m3u8:
        console.print(f"[bold yellow]Intercepted video manifest:[/bold yellow] {intercepted_m3u8}")
        
        # Pass the captured headers (including cookies and auth tokens) from Playwright to yt-dlp
        yt_dlp_cmd = [
            "yt-dlp",
            intercepted_m3u8,
            "-o", video_output,
            "--limit-rate", "1M",            # Limit download to 1 MB/s to prevent flooding
            "--sleep-requests", "0.5",       # Sleep 0.5 seconds between fragment requests
            "--concurrent-fragments", "1",   # Only download 1 fragment at a time
            "--retries", "10",               # Automatically retry failed fragments
        ]
        
        for key, value in m3u8_headers.items():
            # Skip pseudo-headers like :authority, :method, etc. that yt-dlp doesn't like
            if not key.startswith(':'):
                yt_dlp_cmd.extend(["--add-header", f"{key}:{value}"])
        
        console.print("Starting video download via yt-dlp...")
        subprocess.run(yt_dlp_cmd)
        console.print("[green]Video download completed.[/green]")
    else:
        console.print("[yellow]No video stream intercepted or download skipped.[/yellow]")

    # Download PDFs from DOM anchor tags
    pdf_links = page.locator("a[href*='.pdf']").element_handles()
    for link in pdf_links:
        pdf_href = link.get_attribute("href")
        if pdf_href:
            full_pdf_url = urlparse(pdf_href)._replace(netloc=urlparse(url).netloc).geturl() if pdf_href.startswith("/") else pdf_href
            intercepted_pdfs.add(full_pdf_url)
            
    # Process all collected PDFs
    for idx, pdf_url in enumerate(intercepted_pdfs):
        pdf_name = pdf_url.split("/")[-1].split("?")[0]
        if not pdf_name.endswith(".pdf"):
            pdf_name = f"slide_or_doc_{idx+1}.pdf"
        
        pdf_output = os.path.join(lesson_dir, pdf_name)
        if os.path.exists(pdf_output) and os.path.getsize(pdf_output) > 0:
            console.print(f"[green]PDF {pdf_name} already exists. Skipping.[/green]")
            continue
            
        console.print(f"[bold yellow]Downloading PDF:[/bold yellow] {pdf_url}")
        try:
            pdf_res = page.request.get(pdf_url)
            with open(pdf_output, "wb") as f:
                f.write(pdf_res.body())
            console.print(f"[green]Saved {pdf_name}[/green]")
        except Exception as e:
            console.print(f"[red]Failed to download PDF {pdf_url}: {e}[/red]")

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
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        # Load the saved session state, override the user agent, and randomize viewport
        context = browser.new_context(
            storage_state="state.json",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": random.randint(1280, 1920), "height": random.randint(720, 1080)}
        )
        page = context.new_page()
        stealth_sync(page) # Apply stealth techniques to the page
        
        for idx, url in enumerate(urls):
            if idx > 0:
                delay = random.uniform(15.0, 35.0)
                console.print(f"[cyan]Sleeping for {delay:.2f} seconds before next lesson to behave like a human...[/cyan]")
                time.sleep(delay)
                
            process_url(page, url)
            
        browser.close()

if __name__ == "__main__":
    main()
