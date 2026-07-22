import os
import re
from rich.console import Console

console = Console()
OUTPUT_DIR = "local_library"

def parse_curriculum(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    lessons = []
    in_lessons_section = False
    
    for line in lines:
        if line == "Lessons":
            in_lessons_section = True
            continue
        elif line == "Assignments" or re.match(r'^\d+$', line) and len(line) <= 2:
            in_lessons_section = False
            continue
            
        if in_lessons_section:
            # Skip duration lines like "20m" or "1h 48m" or "67m"
            if re.match(r'^\d+m$', line) or re.match(r'^\d+h \d+m$', line) or re.match(r'^\d+m$', line):
                continue
            lessons.append(line)
            
    return lessons

def main():
    lessons = parse_curriculum("curriculum.txt")
    console.print(f"[bold blue]Found {len(lessons)} lessons in the curriculum text.[/bold blue]")
    
    existing_folders = [f for f in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, f))]
    
    missing = []
    matched_count = 0
    
    for lesson in lessons:
        clean_lesson = re.sub(r'[\W_]+', '', lesson.lower())
        clean_lesson = re.sub(r'copy$', '', clean_lesson)
        
        matched = False
        for folder in existing_folders:
            clean_folder = re.sub(r'[\W_]+', '', folder.lower())
            clean_folder = re.sub(r'copy$', '', clean_folder)
            
            if clean_lesson == clean_folder or clean_lesson.startswith(clean_folder) or clean_folder.startswith(clean_lesson):
                matched = True
                matched_count += 1
                break
                
        if not matched:
            missing.append(lesson)
            
    console.print(f"Matched [bold green]{matched_count}[/bold green] out of {len(lessons)} lessons.")
    
    if missing:
        console.print("\n[bold red]Missing Lessons:[/bold red]")
        for m in missing:
            console.print(f" - {m}")
    else:
        console.print("\n[bold green]✅ ALL lessons from the curriculum are accounted for in your library![/bold green]")

if __name__ == "__main__":
    main()
