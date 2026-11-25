# Mihir Kale — Canonical Resumes for LLM Tailoring

Upload this whole file to a web LLM. Below are (1) the resume renderer rules
(shaping contract for JSON output) and (2) three canonical resume starting
points: **core software engineering**, **product**, and **consulting/finance**.
Pick the canonical resume matching the target role, tailor it to the job
description, and return only the final JSON per the rules.

---

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

---

# Canonical Resume 1 — Core Software Engineering

Source: `input/mihir_kale_core_swe.json`. Use as the starting point for
software engineering / SWE intern, full-stack, backend, and AI/LLM engineering
roles. Set `output.company` to the target company.

```json
{
  "header": {
    "name": "Mihir Kale",
    "contact": "Charlotte, NC | (704) 957-9236",
    "email": "mpkale@unc.edu",
    "linkedin": "linkedin.com/in/mihirpkale/"
  },
  "education": [
    {
      "institution": "University of North Carolina at Chapel Hill | Kenan-Flagler Business School",
      "location": "Chapel Hill, NC",
      "date": "May 2028",
      "degree": "B.S. Computer Science; B.S.B.A. Business Administration",
      "details": [
        "GPA: 3.7; Dean's List; National Merit Finalist; SAT: 1550",
        "Technical Coursework: Data Structures and Algorithms; Object-Oriented Programming in Java"
      ]
    },
    {
      "institution": "Paris Institute of Political Studies (Sciences Po)",
      "location": "Paris, France",
      "date": "2025",
      "degree": "Certificate in Economics",
      "details": [
        "Coursework: Econometrics, Data Analysis, and Quantitative Modeling"
      ]
    }
  ],
  "experience": [
    {
      "company": "John Locke Foundation",
      "location": "Raleigh, NC",
      "dates": "Fall 2026",
      "title": "Product & Software Intern",
      "bullets": [
        "Develop a full-stack internal workflow platform for JLF Reads using TypeScript, React, Node.js, REST APIs, and PostgreSQL to connect frontend and backend services and automate data processing",
        "Design application and API architectures using object-oriented design, relational schemas, validation controls, and reusable components to deliver secure, maintainable software",
        "Deploy and maintain cloud-based services through GitHub, Jenkins, and CI/CD pipelines while applying code reviews, coding standards, unit testing, and integration testing"
      ]
    },
    {
      "company": "Siemens Digital Industries Software",
      "location": "Charlotte, NC",
      "dates": "Summer 2026",
      "title": "Software Engineering and AI Intern",
      "bullets": [
        "Shipped an LLM-powered issue-triage application by integrating Jira through Atlassian MCP and validating response quality, improving resolution accuracy by 15% and supporting 20+ developers daily; earned the Siemens-wide Intern Impact Award",
        "Resolved 100+ engineering issues across C services and AWS environments through debugging, testing, requirements validation, and implementation, reducing the engineering backlog by 42%",
        "Modeled enterprise AI resource-allocation scenarios in Python using vendor pricing, adoption, and usage data, identifying up to $6M in potential savings"
      ]
    }
  ],
  "leadership": [
    {
      "organization": "App Team Carolina",
      "location": "Chapel Hill, NC",
      "dates": "2025-Present",
      "title": "iOS Development Team Member",
      "bullets": [
        "Build and test Swift and SwiftUI components for the Porch iOS application using Xcode, Git, Agile workflows, and iterative feedback",
        "Translate product and UX requirements into reliable mobile features through collaboration with product managers, designers, and engineers"
      ]
    },
    {
      "organization": "Carolina Mock Trial Team",
      "location": "Chapel Hill, NC",
      "dates": "2025-Present",
      "title": "Team Captain; Lead Attorney; AI Tools Lead",
      "bullets": [
        "Developed a Python retrieval-augmented generation system that structures case records, retrieves relevant evidence, and supports individualized preparation for 30+ members",
        "Direct technical training and team operations while managing a $5,000+ budget; guided the team to first place at the 2025 Invitational"
      ]
    }
  ],
  "additional": {
    "bullets": [
      "Languages: Python, Java, C, C++, C#, JavaScript, TypeScript, Swift, SQL, R",
      "Engineering: Data Structures, Algorithms, Object-Oriented Programming, REST APIs, PostgreSQL, CI/CD, Software Testing, Debugging, Code Reviews, Agile, SDLC",
      "AI & Data: PyTorch, TensorFlow, scikit-learn, pandas, NumPy; LLM integration, Retrieval-Augmented Generation, Prompt Engineering, Model Evaluation, Data Pipelines",
      "Cloud & Delivery: AWS, Azure, Docker, Git, GitHub, Linux, Jira, Confluence, Atlassian MCP"
    ]
  },
  "output": {
    "company": "SoftwareEngineering",
    "job_id": "Core_SWE_Canonical"
  }
}
```

# Canonical Resume 2 — Product

Source: `input/mihir_kale_product.json`. Use as the starting point for product
management / product manager intern, APM, and product operations roles. Set
`output.company` to the target company.

```json
{
  "header": {
    "name": "Mihir Kale",
    "contact": "Charlotte, NC | (704) 957-9236",
    "email": "mpkale@unc.edu",
    "linkedin": "linkedin.com/in/mihirpkale/"
  },
  "education": [
    {
      "institution": "University of North Carolina at Chapel Hill | Kenan-Flagler Business School",
      "location": "Chapel Hill, NC",
      "date": "May 2028",
      "degree": "B.S. Computer Science; B.S.B.A. Business Administration",
      "details": [
        "GPA: 3.7; Dean's List; National Merit Finalist; SAT: 1550"
      ]
    },
    {
      "institution": "Paris Institute of Political Studies (Sciences Po)",
      "location": "Paris, France",
      "date": "2025",
      "degree": "Certificate in Economics",
      "details": [
        "Coursework: Econometrics, Data Analysis, and Quantitative Modeling"
      ]
    }
  ],
  "experience": [
    {
      "company": "John Locke Foundation",
      "location": "Raleigh, NC",
      "dates": "Aug 2026-Present",
      "title": "Product & Software Intern",
      "bullets": [
        "Define the product roadmap, user stories, acceptance criteria, and data models for JLF Reads by converting content-team workflows into requirements spanning intake, database, API, and frontend components",
        "Engineer REST API, PostgreSQL, access-control, and ETL infrastructure that moves editorial recommendations from internal submission through public presentation",
        "Build Power BI and Advanced Excel data products that convert policy and operational data into actionable insights for technical and nontechnical stakeholders"
      ]
    },
    {
      "company": "Siemens Digital Industries Software",
      "location": "Charlotte, NC",
      "dates": "Summer 2026",
      "title": "Software Engineering & AI Intern",
      "bullets": [
        "Launched an LLM-powered issue-triage product by defining requirements, integrating Jira data through Atlassian MCP, and validating responses; improved resolution accuracy by 15%, reached 20+ daily users, and earned the Siemens-wide Intern Impact Award",
        "Reduced the engineering backlog by 42% by resolving 100+ engineering issues using C debugging, AWS testing, and requirements validation",
        "Analyzed vendor pricing, adoption, and usage data through a Python decision-support model, identifying up to $6M in potential savings"
      ]
    }
  ],
  "leadership": [
    {
      "organization": "App Team Carolina",
      "location": "Chapel Hill, NC",
      "dates": "2025-Present",
      "title": "iOS Product Team Member",
      "bullets": [
        "Translate user needs into feature requirements, UX flows, and SwiftUI components for the Porch iOS project, collaborating across product, design, and engineering"
      ]
    },
    {
      "organization": "Carolina Mock Trial Team",
      "location": "Chapel Hill, NC",
      "dates": "2025-Present",
      "title": "Team Captain; Lead Attorney; AI Tools Lead",
      "bullets": [
        "Designed a Python/RAG product using case records, retrieval logic, and individualized workflows to streamline preparation for 30+ members",
        "Managed a $5,000+ budget and directed training leading to a first-place 2025 Invitational win"
      ]
    },
    {
      "organization": "UNC Department of Public Policy",
      "location": "Chapel Hill, NC",
      "dates": "2025-Present",
      "title": "Representative to Faculty and Planning Board",
      "bullets": [
        "Built an advanced Excel prioritization framework comparing grants, scholarships, and departmental investments; balanced competing stakeholder priorities and presented data-driven recommendations to faculty leadership"
      ]
    }
  ],
  "additional": {
    "bullets": [
      "Product & Delivery: Roadmaps, requirements gathering, user stories, prioritization, Agile, UX prototyping; Jira, Confluence, Figma, Airtable, Atlassian MCP",
      "Analytics & Strategy: Python, SQL, Advanced Excel, Power BI, Tableau, pandas, NumPy; adoption and usage analysis, resource-allocation modeling, dashboards",
      "AI & Engineering: Java, C, C++, C#, TypeScript, Swift, PyTorch, TensorFlow, AWS, Git, REST APIs; LLM integration, RAG, prompt engineering, workflow automation"
    ]
  },
  "output": {
    "company": "Product",
    "job_id": "Product_Canonical"
  }
}
```

# Canonical Resume 3 — Consulting / Finance

Source: `input/mihir_kale_consulting_finance.json`. Use as the starting point
for management consulting, strategy, economic consulting, and finance
(banking, investment, corporate finance) roles. Set `output.company` to the
target company.

```json
{
  "header": {
    "name": "Mihir Kale",
    "contact": "Charlotte, NC | (704) 957-9236",
    "email": "mpkale@unc.edu",
    "linkedin": "linkedin.com/in/mihirpkale/"
  },
  "education": [
    {
      "institution": "University of North Carolina at Chapel Hill | Kenan-Flagler Business School",
      "location": "Chapel Hill, NC",
      "date": "June 2028",
      "degree": "Bachelor of Science in Business Administration and Computer Science",
      "details": [
        "GPA: 3.7; SAT: 1550; Dean's List; National Merit Finalist"
      ]
    },
    {
      "institution": "Paris Institute of Political Studies (Sciences Po)",
      "location": "Paris, France",
      "date": "2025",
      "degree": "Certificate in Economics",
      "details": [
        "Coursework in econometrics, data analysis, and quantitative modeling; analyzed cross-country labor-market data using R and Stata"
      ]
    }
  ],
  "experience": [
    {
      "company": "John Locke Foundation",
      "location": "Raleigh, NC",
      "dates": "Fall 2026",
      "title": "Operations Intern",
      "bullets": [
        "Build financial and costing models analyzing organizational spending, donor economics, and resource allocation, translating quantitative findings into recommendations for leadership",
        "Develop data-access and reporting pipelines that source, clean, and structure financial, fundraising, operational, and policy data for quantitative analysis and management reporting",
        "Create data visualizations and reporting workflows that translate financial and operational analysis into decision-ready insights"
      ]
    },
    {
      "company": "Siemens Digital Industries Software",
      "location": "Charlotte, NC",
      "dates": "Summer 2026",
      "title": "Software Engineering and AI Intern",
      "bullets": [
        "Modeled enterprise AI resource-allocation scenarios in a Python decision-support model using vendor pricing, adoption, and usage data, identifying up to $6M in potential savings",
        "Analyzed AI usage and productivity across development and sales teams, identifying 3M tokens in annual usage optimization and 300+ engineering hours in monthly productivity gains; translated findings into executive recommendations",
        "Built an AI-powered issue-triage system integrating Jira data through Atlassian MCP, improving resolution accuracy by 15% and supporting 20+ developers daily; earned the Siemens-wide Intern Impact Award"
      ]
    }
  ],
  "leadership": [
    {
      "organization": "UNC Department of Public Policy",
      "location": "Chapel Hill, NC",
      "dates": "2025-Present",
      "title": "Representative to Faculty and Planning Board",
      "bullets": [
        "Built an advanced Excel prioritization framework comparing grants, scholarships, and departmental investments across cost, stakeholder impact, and growth potential; presented tradeoffs and recommendations to faculty leadership",
        "Conducted quantitative analysis and presented tradeoffs and recommendations to faculty leadership"
      ]
    },
    {
      "organization": "Carolina Mock Trial Team",
      "location": "Chapel Hill, NC",
      "dates": "2025-Present",
      "title": "Team Captain; Lead Attorney; AI Tools Lead",
      "bullets": [
        "Led the team to first place at the 2025 Invitational while training 30+ members, directing preparation strategy, and managing a budget exceeding $5,000",
        "Synthesized case records and testimony into evidence-based arguments"
      ]
    },
    {
      "organization": "Kenan-Flagler Undergraduate Finance Society",
      "location": "Chapel Hill, NC",
      "dates": "2026-Present",
      "title": "Finance Development Team Member",
      "bullets": [
        "Build Excel-based financial models analyzing financial statements, cash flows, valuation, and investment decisions"
      ]
    }
  ],
  "additional": {
    "bullets": [
      "Finance & Analytics: Financial modeling, financial statement analysis, valuation, econometrics, quantitative analysis; Advanced Excel, Python, R, Stata",
      "Consulting & Delivery: Requirements analysis, resource allocation, process mapping, executive presentations, stakeholder engagement; PowerPoint, Word, Jira"
    ]
  },
  "output": {
    "company": "ConsultingFinance",
    "job_id": "Consulting_Finance_Canonical"
  }
}
```