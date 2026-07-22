import os
import re
from collections import defaultdict

OUTPUT_DIR = "local_library"
MASTER_DIR = os.path.join(OUTPUT_DIR, "Master_Transcripts")

def get_course_name(folder_name):
    # No longer needed, we use the actual course folder name
    return folder_name

def natural_sort_key(s):
    """Sort strings that contain numbers naturally (e.g. Day 2 comes before Day 10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def strip_vtt(content):
    """Strip WEBVTT metadata and timestamps to produce clean text."""
    lines = content.splitlines()
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == "WEBVTT":
            continue
        if "-->" in line:
            continue
        if line.startswith("Kind:") or line.startswith("Language:"):
            continue
        text_lines.append(line)
        
    return " ".join(text_lines)

def generate_toc_anchor(title):
    """Generate GitHub-style markdown anchor links from titles."""
    anchor = title.replace('_', ' ').lower()
    anchor = re.sub(r'[^\w\s-]', '', anchor)
    anchor = re.sub(r'[-\s]+', '-', anchor)
    return anchor

def main():
    if not os.path.exists(OUTPUT_DIR):
        print(f"Error: Directory {OUTPUT_DIR} does not exist.")
        return
        
    os.makedirs(MASTER_DIR, exist_ok=True)
    
    # Map courses to a list of (lesson_name, transcript_text)
    courses = defaultdict(list)
    
    # Read all transcripts
    for course_folder in os.listdir(OUTPUT_DIR):
        course_path = os.path.join(OUTPUT_DIR, course_folder)
        if not os.path.isdir(course_path) or course_folder == "Master_Transcripts":
            continue
            
        for lesson_folder in os.listdir(course_path):
            lesson_path = os.path.join(course_path, lesson_folder)
            if not os.path.isdir(lesson_path):
                continue
                
            transcript_path = os.path.join(lesson_path, "transcript.vtt")
            if os.path.exists(transcript_path):
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                clean_text = strip_vtt(content)
                if clean_text:
                    courses[course_folder].append((lesson_folder, clean_text))
                
    # Generate Markdown files
    for course, lessons in courses.items():
        # Sort lessons naturally
        lessons.sort(key=lambda x: natural_sort_key(x[0]))
        
        md_file = os.path.join(MASTER_DIR, f"{course}_Transcripts.md")
        with open(md_file, 'w', encoding='utf-8') as f:
            course_title = course.replace('_', ' ')
            f.write(f"# {course_title} Master Transcripts\n\n")
            f.write("## Table of Contents\n")
            
            # Write TOC
            for lesson_name, _ in lessons:
                lesson_title = lesson_name.replace('_', ' ')
                anchor = generate_toc_anchor(lesson_title)
                f.write(f"- [{lesson_title}](#{anchor})\n")
                
            f.write("\n---\n\n")
            
            # Write Body
            for lesson_name, text in lessons:
                lesson_title = lesson_name.replace('_', ' ')
                f.write(f"## {lesson_title}\n\n")
                f.write(text + "\n\n")
                f.write("---\n\n")
                
    print(f"Successfully generated {len(courses)} Master Transcripts in '{MASTER_DIR}'")

if __name__ == "__main__":
    main()
