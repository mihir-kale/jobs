# Jobs

Deterministic JSON → PDF resume and cover letter renderer. No AI, no API keys, no build step.

- Paste resume JSON (or cover letter JSON) into the web UI, get a PDF.
- Sections render in the order their keys appear in the JSON; absent sections are skipped.
- Optional `section_titles` renames headings; `future: true` renders an `(Incoming)` prefix.
- Cover letters detected automatically when the JSON has a `body` array.

## Local web UI

```bash
python3.12 server.py        # http://127.0.0.1:5000
python3.12 server.py --port 8080
```

## CLI

```bash
python3.12 render.py input/content.json    # -> output/<LastName_FirstName_Resume_MM_DD>.pdf
python3.12 render.py --jd input/job.txt    # inject ATS keywords (invisible white font)
```

## JSON format

See `json_instructions.md` for the exact schema and renderer rules.

## Deploy

The web UI runs on Vercel from `server.py` (a Flask WSGI app) with `@vercel/python`.

## JD storage and parsing pipeline

Job descriptions are stored in Supabase (hosted) and parsed into structured,
candidate-independent competency maps by a deterministic LLM pipeline.

- `job_descriptions` — raw JD text. `job_competency_maps` — validated structured output, one per JD.
- `jd_parser_prompt.md` — fixed system prompt. `jd_parser_schema.json` — strict output shape.
- `jd_validator.py` — programmatic validation (schema, evidence quotes, ranks, score totals, ordering).
- `jd_pipeline.py` — reads unparsed JDs from Supabase, calls the pinned model at `temperature: 0`, validates, repairs once on failure, stores results.

Both tables are RLS-locked to `service_role` only (see `20260829000003_lockdown_rls.sql`); the public/publishable key has no read or write access. Use `SUPABASE_SERVICE_KEY` for any access.

```bash
pip install -r requirements.txt   # stdlib only for the pipeline; no extra deps
cp .env.example .env              # fill in SUPABASE_URL, SUPABASE_SERVICE_KEY, LLM_API_KEY, LLM_MODEL
python3.12 jd_pipeline.py --dry-run   # list unparsed JDs
python3.12 jd_pipeline.py             # parse, validate, store
python3.12 jd_pipeline.py --jd-id <uuid>
```
