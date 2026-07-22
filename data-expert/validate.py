import os
from rich.console import Console

console = Console()
OUTPUT_DIR = "local_library"

def validate_library():
    if not os.path.exists(OUTPUT_DIR):
        console.print(f"[bold red]Directory {OUTPUT_DIR} does not exist.[/bold red]")
        return

    folders = [f for f in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, f))]
    
    with open("urls.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    console.print(f"[bold blue]Validation Report:[/bold blue]")
    console.print(f"Total target lessons in urls.txt: [bold]{len(urls)}[/bold]")
    console.print(f"Total downloaded folders: [bold]{len(folders)}[/bold]\n")

    missing_videos = []
    missing_notes = []

    for folder in folders:
        folder_path = os.path.join(OUTPUT_DIR, folder)
        video_path = os.path.join(folder_path, "video.mp4")
        notes_path = os.path.join(folder_path, "notes.md")

        if not os.path.exists(video_path) or os.path.getsize(video_path) < 1024:
            missing_videos.append(folder)
        
        if not os.path.exists(notes_path):
            missing_notes.append(folder)

    if not missing_videos and not missing_notes:
        console.print("[bold green]✅ All downloaded folders contain a valid video and notes file![/bold green]")
    else:
        if missing_videos:
            console.print("[bold red]❌ Folders missing video.mp4 (or incomplete):[/bold red]")
            for mv in missing_videos:
                console.print(f"  - {mv}")
        if missing_notes:
            console.print("[bold yellow]⚠️ Folders missing notes.md:[/bold yellow]")
            for mn in missing_notes:
                console.print(f"  - {mn}")

    if len(folders) < len(urls):
        console.print("\n[bold yellow]Notice:[/bold yellow] You have fewer downloaded folders than URLs in your list. To fix this, simply rerun `python main.py`. It will skip all the successfully downloaded videos and automatically retry the missing ones!")

if __name__ == "__main__":
    validate_library()
