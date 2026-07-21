# DataExpert Content Extractor

This specification outlines the architecture, data structures, and execution flow for a batch educational content extractor.

## Project Overview
A Python-based CLI tool designed to batch-process a list of lecture URLs from DataExpert.io (or similar authenticated SPA platforms). The tool spins up an authenticated headless browser session, intercepts network traffic to capture fragmented video streams and transcripts, scrapes the DOM for supplementary lesson notes, and packages everything into an offline-ready directory structure.

## Core Objectives
- Bypass active authentication by leveraging a pre-saved browser session state.
- Evade static scraping blocks by executing JavaScript and intercepting background API/Network calls (XHR/Fetch/Media).
- Map and package resources cleanly for local consumption.

## Tech Stack & Dependencies
- **Language:** Python 3.11+
- **Browser Automation:** playwright (Synchronous API for straightforward scripting).
- **Media Processing:** yt-dlp (Python module wrapper for downloading and stitching HLS/m3u8 streams).
- **Environment Management:** python-dotenv (for managing local paths or configurations).
- **CLI UX (Optional):** rich or tqdm (for terminal progress bars during batch processing).

## Target Data Model
For every URL processed, the tool will extract and map the following entities:

| Asset Type | Source | Target Output |
| :--- | :--- | :--- |
| Video | Network intercept (.m3u8 manifest) | video.mp4 |
| Transcript | Network intercept (.vtt or /transcripts API) | transcript.vtt |
| Lesson Title | DOM (h1 tag or title metadata) | Directory Name & Markdown header |
| Lesson Notes | DOM (main content container) | notes.md |
| Tags/Topics | DOM (badge elements) | YAML Frontmatter in notes.md |

## Output Architecture
The scraper will generate a flat, organized library of folders.

```
Plaintext/local_library
├── /01_Databricks_Platform_Overview_Day_1_Lecture
│   ├── video.mp4
│   ├── transcript.vtt
│   └── notes.md
├── /02_Capstone_Project_Brainstorming
│   ├── video.mp4
│   ├── transcript.vtt
│   └── notes.md
└── state.json (Ignored by Git, holds session cookies)
```

## Execution Flow

### Phase 1: Authentication (Manual/One-Time)
Run a dedicated auth script (`auth_setup.py`) that launches a visible Chromium instance. The user logs in manually. Once the login resolves, Playwright dumps the browser's cookies and local storage (specifically handling Clerk authentication tokens) into `state.json`.

### Phase 2: Batch Processing Loop (`main.py`)
For each URL in `urls.txt`:
1. **Initialize Context:** Launch a headless browser injecting `state.json`.
2. **Attach Listeners:** Bind `page.on("request")` to listen for:
   - URLs containing `.m3u8` (Video Stream).
   - URLs containing `/transcripts` or `.vtt` (Subtitles).
3. **Navigate & Wait:** Route to the URL and wait for the networkidle state to ensure all SPAs (React/Next.js) have fully hydrated the DOM.
4. **Scrape DOM:** Extract the `h1` and main text bodies. Clean illegal characters from the title to generate a safe folder name.
5. **Download Media:** Pass the intercepted `.m3u8` URL to `yt-dlp` to fetch and compile the chunks into `.mp4` within the designated folder.
6. **Save Text:** Write the scraped notes and intercepted transcripts to the folder.
