# Resume JSON Format — Renderer Rules

Produce a resume as a JSON object matching the schema and rules below. A
deterministic renderer (`pdf_generator.py` + `sections.py`) turns this JSON
into a PDF. This document is **only** the format contract and the exact rules
the renderer follows. It contains no guidance on writing content.

Return **only** the JSON object — no explanations, no Markdown code fences.

---

## 1. Top-level structure

The renderer iterates the top-level object keys in their JSON order and renders
the known body-section keys it finds (`education`, `experience`, `leadership`,
`additional`). Unknown keys, and any known key that is absent or empty, are
ignored/skipped. No section is required.

```json
{
  "header": { "name": "", "contact": "", "email": "", "linkedin": "" },
  "education": [],
  "experience": [],
  "leadership": [],
  "additional": { "bullets": [] },
  "section_titles": {},
  "output": { "company": "" }
}
```

Rules:
- Sections render **in the order their keys appear** in the JSON object.
  Reorder the keys to reorder the sections.
- An absent or empty section renders nothing — omit unused keys entirely.
  Never emit empty arrays or empty objects for an unused section.
- No fields outside the schema below are read. Extra fields are ignored.

---

## 2. Field reference

### header (object, required)

| Field      | Type   | Rendered |
|------------|--------|----------|
| `name`     | string | Uppercased, 16pt bold |
| `contact`  | string | Right-aligned contact line |
| `email`    | string | Appended to the right-aligned line as `"contact | email"` (mailto link) |
| `linkedin` | string | Right-aligned line (hyperlinked to `https://www.<value>` unless already `http…`) |

None of the `header` fields are mandatory keys; each renders only if present.
`name` is also used for the output filename (see §5).

### education (array of entry objects)

| Field         | Type     | Rendered |
|---------------|----------|----------|
| `institution` | string   | Bold org, left |
| `location`    | string   | Regular, appended after ` – ` |
| `date`        | string   | Right-aligned |
| `degree`      | string   | Dedicated italic title line |
| `details`     | string[] | Bullet list |

### experience (array of entry objects)

| Field      | Type     | Rendered |
|------------|----------|----------|
| `company`  | string   | Bold org, left |
| `location` | string   | Regular, appended after ` – ` |
| `dates`    | string   | Right-aligned |
| `title`    | string   | Dedicated italic title line |
| `bullets`  | string[] | Bullet list |
| `future`   | boolean  | When `true`, `(Incoming) ` is prepended to the rendered title |

### leadership (array of entry objects)

Identical shape to `experience`, but the org field key is `organization`
(instead of `company`) and the title field key is `title`.

| Field          | Type     | Rendered |
|----------------|----------|----------|
| `organization` | string   | Bold org, left |
| `location`     | string   | Regular, appended after ` – ` |
| `dates`        | string   | Right-aligned |
| `title`        | string   | Dedicated italic title line |
| `bullets`      | string[] | Bullet list |
| `future`       | boolean  | When `true`, `(Incoming) ` is prepended to the rendered title |

### Entry rendering (education / experience / leadership)

Each entry renders as:
1. Org line: **bold** org + ` – location` (regular), date right-aligned.
2. Title line: italic (degree for education; title for experience/leadership).
3. Bullet list.

#### `future` / `(Incoming)`

- Only supported on `experience` and `leadership` entries.
- If `future` is `true` and the title does **not** already start with
  `(incoming` (case-insensitive), the renderer prepends `(Incoming) `.
- If the title already starts with `(Incoming)`, it is left unchanged (no
  duplicate prefix).
- `future` is optional; treat absent as `false`.

### additional (object)

| Field     | Type     | Rendered |
|-----------|----------|----------|
| `bullets` | string[] | A flat bullet list under the heading, no entry/title lines |

### section_titles (object, optional)

Maps a body-section key to a replacement heading. Keys are
`education`, `experience`, `leadership`, `additional`. Keys not listed keep
their defaults. The renderer does not transform case — write values exactly as
they should print.

Defaults (used when a key is absent from `section_titles`):
- education → `EDUCATION`
- experience → `EXPERIENCE`
- leadership → `LEADERSHIP AND COMMUNITY INVOLVEMENT`
- additional → `ADDITIONAL INFORMATION`

### output (object, used only for the filename)

| Field     | Type   | Purpose |
|-----------|--------|---------|
| `company` | string | Company token in the output filename (see §5) |

---

## 3. Renderer constants (not configurable via JSON)

These are fixed and cannot be changed through the JSON:

- US Letter; 0.5" margins all sides.
- Font: Times New Roman (or metric-compatible fallback).
- Name: 16pt bold, rendered UPPERCASE.
- Section heading: 12pt bold, full-width bottom rule.
- Body: 10.5pt; single line spacing (1.15×); no paragraph spacing.
- Bullets hang with a `•` glyph.
- `(Incoming)` prefix for `future: true` entries (see §2).

---

## 4. Type and syntax rules

- All keys and strings use double quotes; valid JSON only. No comments, no
  trailing commas, no Markdown fences.
- `bullets` and `details`: arrays of strings.
- `future`: boolean (`true` / `false`) — never a string.
- Body-section values that are arrays must be arrays of entry objects.
- `additional` must be an object with a `bullets` array.
- Omit rather than send empty: any unused body-section key, `section_titles`
  when no rename is needed, `recipient`/optional fields per the rules above.

---

## 5. Output filename

Built by the renderer from `header.name` and `output.company`.

- `LastName_FirstName`: from `header.name`, split on whitespace; last token
  first. `"Mihir Kale"` → `Kale_Mihir`; a single-token name is used alone.
- Document type token: `Resume` (or `Cover_Letter` when the JSON has a `body`
  array).
- Date token: `MM_DD` (current date).
- `Company`: from `output.company`; punctuation stripped, each word
  capitalized, spaces removed (no underscores). `"Deloitte"` → `Deloitte`,
  `"Capital One"` → `CapitalOne`, `"J.P. Morgan & Co."` → `JPMorganCo`.
  Omitted if empty.
- Name and company are proper case (not all-caps, not all-lowercase).

Result:

```
LastName_FirstName_Resume_MM_DD_Company.pdf
```

Example: name `Mihir Kale`, company `Deloitte` →
`Kale_Mihir_Resume_08_29_Deloitte.pdf`.

---

## 6. Output rule

Return only the final JSON. Do not use Markdown fences or provide
explanations before or after it.
