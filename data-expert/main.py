import os
import re
import json
import subprocess
import time
import random
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Request
from playwright_stealth import Stealth
from rich.console import Console

console = Console()

OUTPUT_DIR = "local_library"

def clean_title(title: str) -> str:
    """Clean the title to generate a safe folder name."""
    title = title.strip()
    title = re.sub(r'[^\w\s-]', '', title)
    title = re.sub(r'[-\s]+', '_', title)
    return title

def should_fast_skip(url, existing_folders):
    """
    Fuzzy maps a URL to an existing folder to check if video.mp4 is already downloaded.
    This allows us to skip visiting the page entirely.
    """
    slug = url.rstrip('/').split('/')[-1]
    
    # Try heuristic prefix match (strip known date/id suffixes)
    clean_slug = re.sub(r'-(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\d{4}.*$', '', slug)
    clean_slug = re.sub(r'-\d{4}$', '', clean_slug)
    clean_slug = re.sub(r'-yt-p\d+.*$', '', clean_slug)
    
    # Strip all non-alphanumeric characters for robust fuzzy matching
    clean_slug = re.sub(r'[\W_]+', '', clean_slug.lower())
    
    for folder in existing_folders:
        clean_folder = re.sub(r'[\W_]+', '', folder.lower())
        clean_folder = re.sub(r'copy$', '', clean_folder) # Handle random "_Copy" folder names
        
        if clean_slug == clean_folder or clean_slug.startswith(clean_folder) or clean_folder.startswith(clean_slug):
            video_output = os.path.join(OUTPUT_DIR, folder, "video.mp4")
            if os.path.exists(video_output) and os.path.getsize(video_output) > 1024:
                return True
                
    return False

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
        
        console.print(f"[cyan]Starting stealth video download via Playwright...[/cyan]")
        try:
            # Filter out pseudo-headers that Playwright doesn't allow and forcibly spoof sec-ch-ua
            clean_headers = {}
            for k, v in m3u8_headers.items():
                if k.startswith(':'):
                    continue
                # Strip out any existing sec-ch-ua headers that might be leaking 'HeadlessChrome'
                if k.lower() in ['sec-ch-ua', 'sec-ch-ua-mobile', 'sec-ch-ua-platform']:
                    continue
                clean_headers[k] = v
                
            # Explicitly add the spoofed Chrome headers
            clean_headers['sec-ch-ua'] = '"Google Chrome";v="120", "Chromium";v="120", "Not?A_Brand";v="24"'
            clean_headers['sec-ch-ua-mobile'] = '?0'
            clean_headers['sec-ch-ua-platform'] = '"Windows"'
            
            # 1. Fetch manifest directly through the browser context with retries
            manifest_res = None
            for attempt in range(5):
                try:
                    manifest_res = page.request.get(intercepted_m3u8, headers=clean_headers, timeout=15000)
                    if manifest_res.ok:
                        break
                except Exception as e:
                    time.sleep(1)
            
            if not manifest_res or not manifest_res.ok:
                raise Exception("Failed to fetch primary manifest")
                
            manifest_text = manifest_res.text()
            
            # Extract segment URLs
            lines = manifest_text.splitlines()
            segment_urls = []
            base_url = intercepted_m3u8.rsplit('/', 1)[0] + '/'
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    if line.startswith('http'):
                        segment_urls.append(line)
                    else:
                        segment_urls.append(base_url + line)
                        
            # Handle Master Playlists (if the m3u8 just points to another m3u8)
            if segment_urls and ".m3u8" in segment_urls[0]:
                console.print("[cyan]Master playlist detected. Fetching media playlist...[/cyan]")
                media_m3u8 = segment_urls[0]
                
                manifest_res = None
                for attempt in range(5):
                    try:
                        manifest_res = page.request.get(media_m3u8, headers=clean_headers, timeout=15000)
                        if manifest_res.ok:
                            break
                    except Exception as e:
                        time.sleep(1)
                        
                if not manifest_res or not manifest_res.ok:
                    raise Exception("Failed to fetch media playlist")
                    
                manifest_text = manifest_res.text()
                lines = manifest_text.splitlines()
                segment_urls = []
                base_url = media_m3u8.rsplit('/', 1)[0] + '/'
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if line.startswith('http'):
                            segment_urls.append(line)
                        else:
                            segment_urls.append(base_url + line)
            
            console.print(f"[cyan]Found {len(segment_urls)} video fragments. Downloading...[/cyan]")
            
            # Download segments and append to video.mp4
            total_bytes = 0
            with open(video_output, 'wb') as f:
                for i, seg_url in enumerate(segment_urls):
                    # Retries for individual segments
                    for attempt in range(5):
                        try:
                            seg_res = page.request.get(seg_url, headers=clean_headers, timeout=15000)
                            if seg_res.ok:
                                body = seg_res.body()
                                f.write(body)
                                total_bytes += len(body)
                                if (i + 1) % 10 == 0 or i == len(segment_urls) - 1:
                                    ts = datetime.now().strftime('%H:%M:%S')
                                    mb_so_far = total_bytes / (1024 * 1024)
                                    console.print(f"[{ts}] Downloaded {i + 1}/{len(segment_urls)} fragments... ({mb_so_far:.2f} MB)")
                                break
                            else:
                                time.sleep(1)
                        except Exception as e:
                            time.sleep(1)
                            
            console.print("[green]Video download completed successfully.[/green]")
        except Exception as e:
            console.print(f"[bold red]Download failed: {e}[/bold red]")
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
    
    # Return True if we skipped the video download to allow for a shorter sleep
    return intercepted_m3u8 is None


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
    
    # Fast skip pre-check
    existing_folders = [f for f in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, f))]
    filtered_urls = []
    
    console.print("[cyan]Pre-checking URLs to skip already downloaded videos...[/cyan]")
    for url in urls:
        if should_fast_skip(url, existing_folders):
            console.print(f"[dim]Fast-skipped (already downloaded): {url}[/dim]")
        else:
            filtered_urls.append(url)
            
    if not filtered_urls:
        console.print("[bold green]All URLs have already been downloaded! Nothing to do.[/bold green]")
        return
        
    console.print(f"[bold green]Starting processing for {len(filtered_urls)} remaining URLs...[/bold green]")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        # Load the saved session state, override the user agent, and randomize viewport
        context = browser.new_context(
            storage_state="state.json",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": random.randint(1280, 1920), "height": random.randint(720, 1080)},
            extra_http_headers={
                "sec-ch-ua": '"Google Chrome";v="120", "Chromium";v="120", "Not?A_Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"'
            }
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page) # Apply stealth techniques to the page
        
        previous_was_skipped = False
        
        for idx, url in enumerate(filtered_urls):
            if idx > 0:
                if previous_was_skipped:
                    delay = random.uniform(2.0, 5.0)
                    console.print(f"[cyan]Video was skipped. Short sleeping for {delay:.2f} seconds before next lesson...[/cyan]")
                else:
                    delay = random.uniform(15.0, 35.0)
                    console.print(f"[cyan]Sleeping for {delay:.2f} seconds before next lesson to behave like a human...[/cyan]")
                time.sleep(delay)
                
            previous_was_skipped = process_url(page, url)
            
        browser.close()

if __name__ == "__main__":
    main()
