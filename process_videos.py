#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path
import time

# Attempt to import the translation logic from the existing script
try:
    import local_translate_srt
except ImportError:
    # If the script is run from a different directory, add the directory to sys.path
    current_dir = Path(__file__).parent.resolve()
    sys.path.append(str(current_dir))
    import local_translate_srt

def check_whisper_installed():
    """Check if whisper is available in the path."""
    whisper_bin = shutil.which("whisper")
    if not whisper_bin:
        # Fallback to the venv location mentioned in README if not found in path
        venv_whisper = Path.home() / "venvs" / "whisper" / "bin" / "whisper"
        if venv_whisper.exists():
            return str(venv_whisper)
        else:
            print("Error: 'whisper' command not found. Please ensure it is installed and in your PATH, or in ~/venvs/whisper/bin/whisper")
            sys.exit(1)
    return whisper_bin

def generate_english_subtitle(video_path, whisper_bin):
    """Generates English subtitle using Whisper."""
    print(f"🎤 Generating English subtitles for: {video_path.name}")
    
    # Whisper command
    # whisper "video.mp4" --task transcribe --language en --model small --fp16 False --output_format srt
    cmd = [
        whisper_bin,
        str(video_path),
        "--task", "transcribe",
        "--language", "en",
        "--model", "small",
        "--fp16", "False",
        "--output_format", "srt",
        "--output_dir", str(video_path.parent) # Ensure output is in the same directory
    ]
    
    try:
        subprocess.run(cmd, check=True)
        # Whisper generates [filename].srt by default if we don't verify filename logic manually, 
        # but with --output_format srt it usually appends .srt
        # However, Whisper's behavior on filenames can vary. 
        # Usually: video.mp4 -> video.srt (if no lang specified) or video.en.srt? 
        # Let's check the output file. 
        # With --language en, it might produce `video.srt` or `video.en.srt` depending on version.
        # We will look for the most recently created .srt file matching the video name.
        
        expected_srt = video_path.with_suffix(".srt")
        
        # If whisper included language code in filename (e.g. video.en.srt)
        expected_srt_lang = video_path.with_suffix(".en.srt")
        
        if expected_srt_lang.exists():
            return expected_srt_lang
        elif expected_srt.exists():
             # Rename to ensure it has .en.srt for our internal processing before translation
             expected_srt.rename(expected_srt_lang)
             return expected_srt_lang
        else:
            # Fallback scan
            possible_files = list(video_path.parent.glob(f"{video_path.stem}*.srt"))
            if possible_files:
                # return the most recent one
                latest = max(possible_files, key=os.path.getctime)
                if latest.name != expected_srt_lang.name:
                    latest.rename(expected_srt_lang)
                return expected_srt_lang
            
        print(f"⚠️  Could not locate generated SRT for {video_path.name}")
        return None
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Whisper failed for {video_path.name}: {e}")
        return None

def translate_to_spanish(en_srt_path, es_srt_path):
    """Translates English SRT to Spanish using local_translate_srt logic."""
    print(f"🌍 Translating to Spanish: {en_srt_path.name} -> {es_srt_path.name}")
    
    try:
        # Initialize translator (Google backend as default/free)
        # We need to set the internal TranslatorImpl in the imported module if it's not set
        local_translate_srt.load_translator(backend="google", src="en", tgt="es")
        
        content = en_srt_path.read_text(encoding="utf-8", errors="ignore")
        translated_content = local_translate_srt.translate_srt(content)
        
        es_srt_path.write_text(translated_content, encoding="utf-8")
        print(f"✅ Translation saved: {es_srt_path.name}")
        return True
    except Exception as e:
        print(f"❌ Translation failed for {en_srt_path.name}: {e}")
        return False

import re

def normalize_path(path_str):
    """
    Unescapes backslashes from a path string (common in macOS terminal drag & drop).
    Converts '/path\ with\ spaces' -> '/path with spaces'
    """
    # If the path exists as-is, return it (it might actually contain backslashes)
    if os.path.exists(path_str):
        return path_str
        
    # Regex to replace '\c' with 'c' (unescape)
    unescaped = re.sub(r'\\(.)', r'\1', path_str)
    return unescaped

def process_directory(directory_path, force=False):
    # Sanitize inputs from shell
    raw_path = directory_path.strip()
    
    # Try to clean up shell escaping (e.g. backslashes from drag-and-drop)
    clean_path_str = normalize_path(raw_path)
    
    root_dir = Path(clean_path_str).resolve()
    
    if not root_dir.exists():
        print(f"Error: Directory does not exist: {root_dir}")
        print(f"       (Original input: {directory_path})")
        return

    whisper_bin = check_whisper_installed()
    
    # 1. Create or verify 'sub_en' directory
    sub_en_dir = root_dir / "sub_en"
    sub_en_dir.mkdir(exist_ok=True)
    
    print(f"📂 Scanning directory: {root_dir}")
    
    # Support both lowercase and uppercase extension
    videos = sorted(list(root_dir.glob("*.mp4")) + list(root_dir.glob("*.MP4")))
    
    # Remove duplicates just in case (e.g. case-insensitive FS)
    videos = sorted(list(set(videos)))
    
    if not videos:
        print(f"❌ No .mp4 videos found in: {root_dir}")
        print("   If your videos are elsewhere, please provide the full path in the menu.")
        return

    print(f"Found {len(videos)} videos. Starting process...\n")
    
    total_videos = len(videos)
    start_time = time.time()
    processed_count = 0
    
    for i, video in enumerate(videos, 1):
        # Calculate ETA (Estimated Time of Arrival)
        if processed_count > 0:
            elapsed = time.time() - start_time
            avg_time = elapsed / processed_count
            remaining = total_videos - (i - 1)
            eta_seconds = avg_time * remaining
            eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
            progress_msg = f"[{i}/{total_videos}] 🎬 Processing: {video.name} | ETA: {eta_str}"
        else:
             progress_msg = f"[{i}/{total_videos}] 🎬 Processing: {video.name} | ETA: Calculating..."
             
        print("="*60)
        print(progress_msg)
        print("="*60)
        
        # Desired file paths
        # Spanish subtitle (alongside video) -> VideoName.srt
        final_es_srt = video.with_suffix(".srt")
        # English subtitle (in sub_en) -> VideoName.en.srt
        final_en_srt_in_subdir = sub_en_dir / f"{video.stem}.en.srt"
        
        # Check if work is already done
        if final_es_srt.exists() and final_en_srt_in_subdir.exists() and not force:
            print(f"⏭️  Skipping {video.name} (files already exist).")
            # Even if skipped, we count it for progress (it was fast)
            processed_count += 1
            continue
            
        # 1. Generate English Subtitle (tmp location in root first)
        temp_en_srt = video.with_suffix(".en.srt")
        
        # Check if we already have the English sub in sub_en or root
        english_source = None
        if final_en_srt_in_subdir.exists():
             english_source = final_en_srt_in_subdir
             print(f"   ℹ️  Found existing English subtitle in 'sub_en/'. Skipping Whisper generation.")
        elif temp_en_srt.exists():
             english_source = temp_en_srt
             print(f"   ℹ️  Found existing English subtitle in root. Skipping Whisper generation.")
        else:
             # Run Whisper
             english_source = generate_english_subtitle(video, whisper_bin)
        
        if not english_source or not english_source.exists():
            print("   - Skipping translation (no English source).")
            continue
            
        # 2. Translate to Spanish if needed
        if not final_es_srt.exists() or force:
            translate_to_spanish(english_source, final_es_srt)
        else:
            print("   - Spanish subtitle already exists.")

        # 3. Organize English Subtitle
        # Move English subtitle to sub_en/ folder if it's not already there
        if english_source != final_en_srt_in_subdir:
            try:
                shutil.move(str(english_source), str(final_en_srt_in_subdir))
                print(f"📂 Moved English subtitle to: {final_en_srt_in_subdir.name}")
            except Exception as e:
                print(f"⚠️  Failed to move English subtitle: {e}")

        processed_count += 1
        print("-" * 40)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automate subtitle generation, translation, and organization.")
    parser.add_argument("directory", nargs="?", default=".", help="Directory containing videos")
    parser.add_argument("--force", action="store_true", help="Force regeneration of subtitles")
    
    args = parser.parse_args()
    
    process_directory(args.directory, args.force)
