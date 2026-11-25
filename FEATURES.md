# resume_engine — FEATURES

Deterministic JSON → PDF resume renderer. No AI, no API keys, no build step.

## Usage

```bash
python3.12 render.py                    # input/content.json -> output/<name>.pdf
python3.12 render.py path/to/content.json
python3.12 render.py -o out_dir --name My_Resume
python3.12 render.py --jd input/job.txt # inject ATS keywords from a job description
```

## What it does

- Reads resume content from `input/content.json`
- Renders a US Letter PDF (Times New Roman, 0.5" margins, single-spaced)
- Derives output filename from `header.name` + `output.company` → `LastName_FirstName_Resume_MM_DD_Company.pdf`
- `--jd FILE` parses a job description (TXT/PDF/DOCX/MD) and injects matched ATS keywords in 1pt white font — invisible to humans, readable by ATS parsers

## Content schema

| Section | Fields |
|---|---|
| `header` | `name`, `contact`, `email`, `linkedin` |
| `education[]` | `institution`, `location`, `date`, `degree`, `details[]` |
| `experience[]` | `company`, `location`, `dates`, `title`, `bullets[]`, `future` |
| `leadership[]` | `organization`, `location`, `dates`, `title`, `bullets[]`, `future` |
| `additional` | `bullets[]` |
| `output` | `company` (filename only) |

## Layout rules

- Name 16pt bold, section headings 12pt bold with bottom rule, body 10.5pt
- Org lines: bold org, regular "– location", date right-aligned
- Hanging bullets; italic titles; `future: true` titles get an "(Incoming)" prefix
- Sections render in content-JSON key order (e.g. put `experience` before `education` for mid-career resumes); absent or empty sections are skipped — no section is required; extra entries flow onto page 2 automatically
- ATS keywords: `extract_ats_keywords()` matches JD terms against a curated pattern list plus resume `additional.skills`; injected as one white-font line at 1pt

## What it does NOT do

- No AI, prompts, or API keys
- No DOCX
- No job-description tailoring — edit the JSON directly
