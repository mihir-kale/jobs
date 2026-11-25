# jobs — Agent Guide

## Purpose

The only capability of this repo is deterministic JSON → PDF rendering (resume and cover
letter). An external Python environment imports the renderer directly. Do **not**
reintroduce LLM calls, Supabase, JD parsing, matching/planning pipelines, a Flask server,
or deployment config.

## Environment

- Use `python3.12`. Dependencies are in `requirements.txt` — **fpdf2 only**.
- Keep the dependency set minimal; adding network/database/UI packages is out of scope.

## Layout

- `pdf_generator.py` — `generate_resume_pdf(content, output_path)` plus shared layout
  helpers and constants. `cover_letter_generator.py` imports private names from here
  (`_Layout`, `_load_fonts`, `_wrap`, `ASCENT`, `BODY_SIZE`, `LINE_FACTOR`, `MARGIN`,
  `NAME_SIZE`, `RIGHT`): preserve those names when editing.
- `sections.py` — section config; imported only by `pdf_generator.py`.
- `cover_letter_generator.py` — `generate_cover_letter_pdf(content, output_path)`.
- `fonts/` — Liberation Serif fallback fonts + license. Keep them; font discovery ends
  here and raises if no usable serif TTF exists on the host.
- `json_instructions.md` — reference doc for the expected content JSON shape.
- `README.md` — public API docs.

## Workflow reminders

- Sections render in content-dict key insertion order; unknown/empty sections are skipped.
- The renderer does no schema validation — callers own the dict shape.
- Neither public function creates parent directories for `output_path`.
- Smoke-test changes by rendering to a temp directory, never into `output/`:

  ```python
  from pdf_generator import generate_resume_pdf
  generate_resume_pdf(content, "/tmp/smoke.pdf")
  ```
