# jobs — JSON → PDF renderer

Deterministic, offline PDF generation for resumes and cover letters. There is no LLM, no
database, no web server, and no CLI: an external Python environment (e.g. ChatGPT's code
interpreter) supplies a content dict and an output path, and this package writes the PDF.

## Install

```bash
python3.12 -m pip install -r requirements.txt   # fpdf2 only
```

## API

```python
from pdf_generator import generate_resume_pdf
from cover_letter_generator import generate_cover_letter_pdf

generate_resume_pdf(content, "/tmp/resume.pdf")
suggested_stem = generate_cover_letter_pdf(content, "/tmp/cover_letter.pdf")
```

Both functions take a plain `dict` and a destination path. They do **not** create parent
directories — the caller must do that. The cover-letter function returns a suggested
filename stem but writes to the path you pass.

## Content JSON

- Resume shape and renderer rules: [`json_instructions.md`](json_instructions.md).
- Body sections are `education`, `experience`, `leadership`, `additional`.
- **Section order follows JSON key insertion order**; absent or empty sections are skipped.
- No schema validation happens at render time — the dict must already be well formed.

## Fonts

The renderer prefers system Times New Roman and metric-compatible substitutes. The bundled
[`fonts/`](fonts/) directory is the last-resort fallback and must stay with the package
(or rendering fails on hosts without a suitable serif font).
