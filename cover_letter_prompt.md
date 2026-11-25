# Cover Letter JSON Format — Renderer Rules

Produce a cover letter as a JSON object matching the schema and rules below. A
deterministic renderer (`cover_letter_generator.py`) turns this JSON into a
letter PDF. This document is **only** the format contract and the exact rules
the renderer follows. It contains no guidance on writing content.

Return **only** the JSON object — no explanations, no Markdown code fences.

---

## 1. Top-level structure

```json
{
  "header": { "name": "", "contact": "", "email": "", "linkedin": "" },
  "date": "string",
  "recipient": { "name": "", "title": "", "company": "", "address": "" },
  "greeting": "string",
  "body": ["", "", "", ""],
  "closing": "string",
  "output": { "company": "" }
}
```

---

## 2. Field reference

### header (object, required)

| Field      | Type   | Rendered |
|------------|--------|----------|
| `name`     | string | 16pt bold (also used for the filename and the closing signature) |
| `contact`  | string | Right-aligned contact line |
| `email`    | string | Appended to the contact line as `"contact | email"` (mailto link) |
| `linkedin` | string | Right-aligned line (hyperlinked; `https://www.<value>` unless already `http…`) |

### date (string, optional)

Rendered right-aligned beneath the header. Also used in the filename.

### recipient (object, optional)

| Field     | Type   | Rendered |
|-----------|--------|----------|
| `name`    | string | Line |
| `title`   | string | Line |
| `company` | string | Line |
| `address` | string | Line |

Each field renders as a separate line, in the order `name`, `title`,
`company`, `address`. Omit any field that has no value rather than sending an
empty string.

### greeting (string, optional)

Rendered as a line after the recipient block.

### body (array of strings, required)

Exactly four paragraph strings. Each renders as a wrapped paragraph; blank
line between consecutive paragraphs.

### closing (string, optional)

Rendered as a line after the body.

### output (object, used only for the filename)

| Field     | Type   | Purpose |
|-----------|--------|---------|
| `company` | string | Company token in the output filename (see §5) |

---

## 3. Renderer constants (not configurable via JSON)

- US Letter; 0.5" margins.
- Times New Roman (or metric-compatible fallback).
- Name: 16pt bold.
- Body / all other lines: 10.5pt.
- 1.5× paragraph spacing; paragraph wrapping automatic.
- Body is followed by two blank lines, then `closing`, two blank lines, the
  sender `header.name` as signature, a blank line, then the literal line
  `Enclosure: Résumé`.

---

## 4. Type and syntax rules

- All keys and strings use double quotes; valid JSON only. No comments, no
  trailing commas, no Markdown fences.
- `body` must be an array of exactly four strings.
- Omit rather than send empty: any `recipient` sub-field, `date`, `greeting`,
  `closing`, or `output.company`.
- No fields outside this schema are read. Extra fields are ignored.

---

## 5. Output filename

Built by the renderer from `header.name`, `date`, and `output.company`.

- `LastName_FirstName`: from `header.name`, split on whitespace; last token
  first. `"Mihir Kale"` → `Kale_Mihir`; a single-token name is used alone.
- Document type token: `Cover_Letter`.
- Date token: `MM_DD` when `date` parses as `%B %d, %Y`; otherwise omitted.
- `Company`: from `output.company`; punctuation stripped, each word
  capitalized, spaces removed (no underscores). `"Deloitte"` → `Deloitte`,
  `"Capital One"` → `CapitalOne`. Omitted if empty.
- Name and company are proper case (not all-caps, not all-lowercase).

Result:

```
LastName_FirstName_Cover_Letter_MM_DD_Company.pdf
```

---

## 6. Output rule

Return only the final JSON. Do not use Markdown fences or provide
explanations before or after it.
