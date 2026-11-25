#!/usr/bin/env python3
"""Render a resume PDF from a JSON content file. No AI, no API keys.

Usage:
    python render.py
    python render.py input/content.json
    python render.py -o some_dir --name My_Resume
    python render.py --jd input/job.txt

With no arguments, reads input/content.json next to render.py and writes
output/<LastName_FirstName_Resume_MM_DD_CompanyName>.pdf. Pass --jd to inject
ATS keywords from a job description in invisible white font (readable by
ATS parsers, invisible to humans).
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from ats_keywords import extract_ats_keywords
from parser import parse_job_description
from pdf_generator import generate_resume_pdf

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / 'input'
OUTPUT_DIR = BASE_DIR / 'output'


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Could not find {path}.")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_') or ''


def name_stem(content: dict) -> str:
    """Build the output filename stem: LastName_FirstName_Resume_MM_DD_CompanyName."""
    parts = [p for p in str(content.get('header', {}).get('name', '')).split() if p]
    if len(parts) >= 2:
        base = f"{parts[-1]}_{parts[0]}"
    elif parts:
        base = parts[0]
    else:
        base = 'resume'

    output = content.get('output', {}) or {}
    stem = _slugify(base)
    company = _slugify(str(output.get('company', '') or ''))
    date_str = datetime.now().strftime('%m_%d')
    stem = f"{stem}_Resume_{date_str}"
    if company:
        company = company.replace('_', '')
        stem = f"{stem}_{company[:1].upper()}{company[1:]}"
    return stem


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog='render.py',
        description='Render a resume PDF from a JSON content file.')
    parser.add_argument('content_json', nargs='?', default=None,
                        help='Resume content file (default: input/content.json)')
    parser.add_argument('--jd', default=None,
                        help='Job description file (TXT/PDF/DOCX) for ATS keyword injection')
    parser.add_argument('-o', '--output-dir', default=None,
                        help='Output directory (default: output/)')
    parser.add_argument('--name', default=None, help='Output filename stem')
    args = parser.parse_args(argv)

    try:
        content_path = args.content_json or str(INPUT_DIR / 'content.json')
        content = load_json(content_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    out_dir = args.output_dir or str(OUTPUT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    stem = args.name or name_stem(content)
    path = os.path.join(out_dir, f"{stem}.pdf")

    ats_keywords = None
    if args.jd:
        jd_text = parse_job_description(args.jd)
        ats_keywords = extract_ats_keywords(jd_text, content)
        print(f"  Injecting {len(ats_keywords)} ATS keywords (invisible, ATS-readable)")

    generate_resume_pdf(content, path, ats_keywords=ats_keywords)
    print(f"Resume PDF: {path}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
