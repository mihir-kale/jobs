# jobs — Agent Guide

Deterministic JSON → PDF resume and cover letter renderer with a local web UI and a Supabase-backed JD parsing pipeline. No AI at render time; the only LLM usage is the offline JD → competency-map pipeline.

## Environment

- **Use `python3.12`** for every command below. The system `python3` does NOT have the deps installed (`python3.12` does).
- Dependencies live in `requirements.txt` (fpdf2, flask, PyPDF2, python-docx). Install once in the 3.12 env.
- Secrets live in `.env` (gitignored). Never log or commit them. `.env.example` documents every var.

## Layout

### Entries points
- `render.py` — CLI. Renders a resume PDF from a content JSON: `python3.12 render.py [content.json] [--jd job.txt] [-o DIR] [--name STEM]`. Default reads `input/content.json`, writes `output/<stem>.pdf`. `--jd` parses a job description (TXT/PDF/DOCX) and injects ATS keywords in invisible white font.
- `server.py` — Flask web UI at `127.0.0.1:5000`. `POST /render` accepts a content JSON body (`{"content": {...}}`) and returns the PDF. `GET /instructions` and `GET /cover-letter-instructions` serve the prompt files to the UI. `POST /convert-to-json` (optional web-UI step) sends a pasted JD + base resume JSON to the pinned LLM and returns a customized resume JSON.
- `resume_customizer.py` — shared LLM call for `POST /convert-to-json`. Reads LLM config from `.env` (same vars as `jd_pipeline`), uses `json_instructions.md` as the system prompt, defaults the base resume to `input/content.json` (override with `BASE_RESUME_JSON`). CLI: `python3.12 resume_customizer.py job.txt [out.json]`.
- `cover_letter_generator.py` — shared render function for cover letters (content JSON that has a `body` list). Used by the server; no CLI.
- Render internals: `pdf_generator.py`, `sections.py`, `parser.py` (JD text extraction), `ats_keywords.py`.

### JD parsing pipeline (offline, Supabase-backed)
- `jd_pipeline.py` — reads unparsed `job_descriptions` rows, calls a pinned LLM at `temperature: 0`, validates, stores `job_competency_maps`. Flags: `--jd-id UUID`, `--dry-run`, `--no-write`, `--limit N`.
- `jd_validator.py` — programmatic validation (schema, evidence quotes, ranks, score totals, ordering).
- `jd_parser_prompt.md`, `jd_parser_schema.json` — the fixed system prompt and strict output shape.
- `supabase/migrations/` — schema. Both tables are RLS-locked to `service_role`; use `SUPABASE_SERVICE_KEY` for any access.

### Candidate evidence layer (canonical factual source)
- `candidate_evidence.json` — the canonical machine-readable fact bank used by all downstream customization (entries, atomic facts, metrics, skills, education). Takes precedence over prose base documents.
- `candidate_evidence_schema.json` — strict shape for the bank (snake_case IDs, locked metrics, controlled competency-tag vocabulary, `evidence_strength` 1–5).
- `candidate_evidence_validator.py` — deterministic validation + CLI: `python3.12 candidate_evidence_validator.py candidate_evidence.json`. Errors stop; warnings do not.
- Tests: `tests/test_candidate_evidence.py` — run `python3.12 -m unittest discover -s tests`.

### Evidence matching (deterministic JD map → ranked facts)
- `evidence_matcher.py` — deterministic matcher: consumes a Phase-1 competency map (`--competency-map`, jd_parser_schema shape) + the evidence bank (`--evidence`) and writes a match object (`--output`): per-fact scores with decomposed `score_components`, skill intersection, competency coverage, hard-qualification verdicts, uncovered competencies, redundancy signature, input hash. CLI: `python3.12 evidence_matcher.py --competency-map tests/fixtures/jd_software_engineering.json --output /tmp/match.json`. No LLM, no Supabase, no resume assembly. Same inputs MUST produce byte-identical output.
- `matching_config.json` — every weight/threshold/alias/tie-break lives here (nothing hardcoded). Includes `tier1_aliases` (JD term → skill_id) and `behavioral_tag_aliases`.
- `competency_relationships.json` — human-maintained explicit JD `competency_id` → candidate competency-tag links with coefficients (only for non-literal name matches).
- `evidence_match_schema.json` — contract for the match object.
- Facts/metrics are never mutated: `identified`/`potential` metric statuses survive matching. The `metric_status_factors` config preserves them (identified ≠ realized).
- Tests: `tests/test_evidence_matcher.py` + `tests/fixtures/jd_*.{json,txt}` (4 roles: data analytics, economic consulting, software engineering, operations/strategy — each must pass `jd_validator.validate` against its `.txt`) + `tests/fixtures/golden_data_analytics.json`.

### Resume planning (deterministic match → plan IR)
- `resume_planner.py` — deterministic planner: consumes an evidence match (`--matches`) + the evidence bank (`--evidence`) + `--config planner_config.json` and writes a plan object (`--output`): selected entries, bullet slots with target competencies/terms, education/skills/coverage/exclusions/warnings, provenance. CLI: `python3.12 resume_planner.py --matches /tmp/match.json --output /tmp/plan.json`. Same inputs MUST produce byte-identical output (selection iterates ordered lists, never sets). No LLM, no Supabase, no prose.
- `planner_config.json` — every weight/threshold/budget lives here (section budgets, marginal weights, saturation curve, redundancy penalties, swap minimum improvement, tie-break order).
- `resume_plan_schema.json` — strict shape for the plan object.
- Tests: `tests/test_resume_planner.py` + `tests/fixtures/golden_plan_data_analytics.json`.

### Content and docs
- `json_instructions.md` — JSON schema and renderer rules for resumes.
- `resume_customization_prompt.md`, `cover_letter_prompt.md` — editing/prompt guides surfaced by the web UI.
- `constitution.md`, `FEATURES.md`, `README.md` — product specs.
- `docs/` — `mihir_kale_base_document.md` (resume source of truth) and the UBP style guides.
- `fonts/` — Liberation Serif (Times New Roman fallback) used for all renders.
- `templates/index.html` — web UI page.
- `tracker/` — static application tracker (built assets in `tracker/assets/`).

### Data dirs (gitignored, do NOT commit)
- `input/` — resume content JSON + JD text.
- `output/` — generated PDFs.
- `.env`, `.vercel`, `supabase/.temp`, `__pycache__/`, `.DS_Store` — all gitignored.

## Output organization (IMPORTANT)

- **Naming convention**: `Kale_Mihir_Resume_MM_DD_Company.pdf` and `Kale_Mihir_Cover_Letter_MM_DD_Company.pdf`. `MM_DD` = generation day (pulled from `datetime.now()`), `Company` = CamelCase from `output.company` in the JSON. `render.py`, `server.py`, and `cover_letter_generator.py` each implement this stem logic via `_name_stem`/`name_stem`.
- **`output/` is organized into one folder per company** (e.g. `output/Deloitte/`, `output/Hilton/`), never flat. Multiple roles/versions for the same company stay in the same folder, disambiguated by an extra `_Role` suffix in the filename (e.g. `Kale_Mihir_Resume_08_22_Hilton_DisputeResolution.pdf`).
- Resumes and cover letters for a company go in the same folder.
- Files with no identifiable company (generic/networking resumes) go in `output/General/`.
- When you render a new artifact for an application, place the PDF into `output/<Company>/`.

## Workflow reminders

- Before rendering, read `resume_customization_prompt.md` (resume) or `cover_letter_prompt.md` (cover letter) for the tailoring rules.
- Base content lives in `docs/mihir_kale_base_document.md`; keep tailored JSONs in `input/`.
- Verify renders with `python3.12 render.py input/content.json -o /tmp/out --name SmokeTest` — never dump smoke-test PDFs into `output/`.
- Run `python3.12 -m py_compile *.py` after editing Python here.