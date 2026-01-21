#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch-translate .srt subtitles to Spanish **locally** (no website automation).

Usage:
  python3 local_translate_srt.py /path/to/input_dir /path/to/output_dir --src en --tgt es --backend google

Backends supported (pick one with --backend):
  - google  : uses deep-translator's GoogleTranslator (no API key; may rate-limit)
  - libre   : uses LibreTranslate (needs --libre-url, optionally --libre-api-key)
  - deepl   : uses DeepL API (needs env DEEPL_API_KEY or --deepl-api-key)
  
Notes:
  * Preserves timing and formatting. Only subtitle text is translated.
  * Skips files already translated if the exact output file exists.
  * Safe for macOS; create and use a virtualenv if you prefer.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

# Optional imports handled lazily
TranslatorImpl = None

SRT_BLOCK_RE = re.compile(r"""(?mx)
    (\d+)\s*\n          # index
    (\d\d:\d\d:\d\d,\d{3})\s+-->\s+(\d\d:\d\d:\d\d,\d{3})\s*\n  # timestamp
    (.*?)                  # text (can be multi-line)
    (?=\n\n|\Z)         # until blank line or EOF
""")

def parse_args():
    ap = argparse.ArgumentParser(description="Batch-translate SRT files to another language while preserving timestamps.")
    ap.add_argument("input_dir", help="Directory containing .srt files in source language (e.g., English)." )
    ap.add_argument("output_dir", help="Directory where translated .srt files will be written.")
    ap.add_argument("--src", default="en", help="Source language code (default: en)." )
    ap.add_argument("--tgt", default="es", help="Target language code (default: es for Spanish)." )
    ap.add_argument("--backend", choices=["google","libre","deepl"], default="google", help="Translation backend.")
    ap.add_argument("--sleep", type=float, default=0.4, help="Seconds to wait between requests (avoid rate-limits)." )
    ap.add_argument("--libre-url", default=None, help="LibreTranslate endpoint URL, e.g., https://translate.argosopentech.com/" )
    ap.add_argument("--libre-api-key", default=None, help="LibreTranslate API key if your server requires one." )
    ap.add_argument("--deepl-api-key", default=None, help="DeepL API key (or set DEEPL_API_KEY env var)." )
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs.")
    return ap.parse_args()

def load_translator(backend, src, tgt, libre_url=None, libre_api_key=None, deepl_api_key=None):
    global TranslatorImpl
    if backend == "google":
        from deep_translator import GoogleTranslator
        class GT:
            def translate(self, text):
                # deep_translator handles \n fine; for long lines we do small chunks
                return GoogleTranslator(source=src, target=tgt).translate(text)
        TranslatorImpl = GT()
    elif backend == "libre":
        # pip install libretranslatepy
        from libretranslatepy import LibreTranslateAPI
        if not libre_url:
            raise SystemExit("--libre-url is required for backend=libre (e.g., https://translate.astian.org/)")
        lt = LibreTranslateAPI(libre_url, api_key=libre_api_key)
        class LT:
            def translate(self, text):
                return lt.translate(text, source=src, target=tgt)
        TranslatorImpl = LT()
    elif backend == "deepl":
        import deepl
        key = deepl_api_key or os.environ.get("DEEPL_API_KEY")
        if not key:
            raise SystemExit("DeepL backend selected but no API key provided. Set DEEPL_API_KEY or use --deepl-api-key.")
        translator = deepl.Translator(key)
        class DL:
            def translate(self, text):
                res = translator.translate_text(text, source_lang=src.upper(), target_lang=tgt.upper())
                return res.text
        TranslatorImpl = DL()
    else:
        raise ValueError("Unknown backend")


def translate_text_preserving_newlines(text, sleep_duration=0.4):
    # Split on lines to avoid very long requests; keep empty lines.
    lines = text.split("\n")
    out_lines = []
    for ln in lines:
        if ln.strip() == "":
            out_lines.append(ln)
            continue
        # Retry logic
        for attempt in range(5):
            try:
                translated = TranslatorImpl.translate(ln)
                out_lines.append(translated)
                break
            except Exception as e:
                if attempt == 4:
                    raise
                time.sleep(0.8 * (attempt + 1))
        # Use provided sleep duration instead of global args
        time.sleep(sleep_duration)
    return "\n".join(out_lines)


def translate_srt(content, sleep_duration=0.4):
    # Walk blocks, translate only the text part.
    out_parts = []
    pos = 0
    for m in SRT_BLOCK_RE.finditer(content):
        start, end = m.span()
        out_parts.append(content[pos:start])  # anything before the block (usually nothing)
        idx = m.group(1)
        t1 = m.group(2)
        t2 = m.group(3)
        txt = m.group(4)
        translated_txt = translate_text_preserving_newlines(txt, sleep_duration=sleep_duration)
        block = f"{idx}\n{t1} --> {t2}\n{translated_txt}\n\n"
        out_parts.append(block)
        pos = end
    out_parts.append(content[pos:])  # tail
    return "".join(out_parts)


def main():
    global args
    args = parse_args()
    in_dir = Path(args.input_dir).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    load_translator(args.backend, args.src, args.tgt, args.libre_url, args.libre_api_key, args.deepl_api_key)

    srt_files = sorted([p for p in in_dir.iterdir() if p.suffix.lower() == ".srt"])  # only .srt
    if not srt_files:
        print("No .srt files found in", in_dir)
        return 0

    total = len(srt_files)
    done = 0
    for p in srt_files:
        out_path = out_dir / p.name  # keep same filename
        if out_path.exists() and not args.overwrite:
            print(f"⏭️  Skipping existing: {out_path.name}")
            done += 1
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            translated = translate_srt(content)
            out_path.write_text(translated, encoding="utf-8")
            print(f"✅ Translated: {p.name} -> {out_path}")
            done += 1
        except Exception as e:
            print(f"❌ Failed: {p.name}: {{e}}", file=sys.stderr)
    print(f"\nDone {done}/{total} files. Output: {{out_dir}}" )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
