# Resume Tailoring Constitution

## 1. Mission

Convert a job description and candidate base documents into a valid, role-specific resume JSON.

The process must be repeatable, concise, and reliable across LLMs.

Optimize in this order:

1. Satisfy visible hard qualifications.
2. Include exact, supported job-description keywords.
3. Make value obvious during a rapid human scan.
4. Select the strongest available evidence.
5. Preserve readability and valid JSON.

Do not optimize for abstract competency signaling. Optimize for ATS retrieval and immediate value perception.

---

## 2. Inputs

The model receives:

- **JD — Job Description:** Complete target job description.
- **BD — Base Documents:** Past resumes, LinkedIn content, project notes, awards, and other candidate evidence.
- **CE — Candidate Evidence:** `candidate_evidence.json` is the canonical machine-readable factual source. When present, it takes precedence over prose base documents for every fact, metric, skill, and framing rule it contains.
- **Locked Facts:** Facts that cannot be changed.
- **Resume Schema:** Required JSON structure.
- **Output Metadata:** Company, role, job ID, and location when applicable.

If a separate locked-facts list is not supplied, treat the following as locked:

- Candidate name and contact information
- Employer and institution names
- Official titles
- Employment and education dates
- Degrees and enrollment status
- GPA
- Award names
- Explicitly supplied metrics

---

## 3. Non-Negotiable Rules

### 3.1 Exact JD language

Use the JD's exact terminology when it accurately describes the candidate's evidence.

Do not replace exact phrases with synonyms merely for stylistic variety.

Critical tools, qualifications, role functions, and deliverables should appear in visible resume text when supported.

### 3.2 Evidence

Every bullet must be grounded in the BD.

The model may:

- Select relevant evidence
- Reorder evidence
- Combine closely related facts from the same project or role
- Translate technical work into its supported business consequence
- Use exact JD language to describe supported work
- Omit irrelevant implementation details

The model may not:

- Change locked facts
- Invent unsupported tools, responsibilities, awards, or results
- Merge accomplishments from different organizations
- Present potential impact as realized impact
- Present future work as completed work

### 3.3 Immediate value

Lead bullets with the accomplishment, product, analysis, decision, award, adoption, scale, financial value, or measurable result.

Do not insert interviewing, collaboration, iteration, research, or development-process details solely to imply a competency.

Include process only when it is itself important to the target role or necessary to understand the result.

Preferred:

> Won the Siemens-wide Intern Impact Award for building an interactive chatbot that parses and translates error logs for service-outage triage, now used daily by 20+ developers.

Avoid:

> Interviewed developers and managers, iterated on a chatbot, and collaborated across teams before shipping a service-outage triage tool.

### 3.4 One value proposition per bullet

Each bullet should communicate one dominant accomplishment.

Use one or two primary JD phrases per bullet. Add more only when they do not delay or obscure the result.

Avoid keyword-dense sentences that require careful reading.

### 3.5 Visible and injected ATS layers

Use two separate keyword layers:

1. **Visible layer:** Resume-appropriate hard qualifications, supported Tier 1 terms, and the selected high-priority Tier 2 terms must appear in ordinary visible sections.
2. **Injected layer:** The deterministic JSON-to-PDF renderer may inject additional JD terms as 1pt white text when run with `--jd`.

White-text injection supplements visible tailoring. It must not substitute for required tools, resume-appropriate qualifications, or terminology central to the role.

Use the injected layer for lower-priority supported terms and exact variants that would make visible bullets awkward or repetitive. Do not manually add hidden-text fields to the resume JSON; the renderer owns injection.

### 3.6 Future roles

For an incoming or future role:

- Set `future` to `true`.
- Use exactly one bullet describing an expected responsibility.
- Do not claim completed achievements, results, or metrics.

---

## 4. Five-Stage Process

Follow these stages in order. Do not return an initial draft before completing the audit and correction stages.

## Stage 1 — Extract the JD requirements

Identify:

### Hard qualifications

- Degree or enrollment requirement
- Graduation-date requirement
- Work authorization requirement
- Location requirement
- Required experience

### Tier 1 keywords

- Required tools
- Required technical skills
- Required role-specific terminology
- Required credentials that belong on a resume

### Tier 2 keywords

- Core responsibilities
- Analytical methods
- Expected deliverables
- Role-specific functions
- Industry or domain terms

### Tier 3 keywords

- Behavioral traits
- Cultural language
- General preferences

Rules:

- Tier 1 and Tier 2 terms receive priority.
- Tier 3 language must not displace stronger accomplishments.
- Importance is determined by required status and centrality to the role, not frequency alone.
- Treat eligibility facts and ATS keywords separately. Degree, graduation date, location, and work authorization are eligibility facts, not keywords.
- Place resume-appropriate eligibility facts in their conventional sections. Do not insert application-only information such as work authorization into accomplishment bullets.
- Select no more than eight Tier 2 terms, ranked by: connection to the role's primary responsibilities, required versus preferred status, role specificity, and then repetition in the JD.
- Ignore compensation, benefits, equal-opportunity text, and generic employer branding.

## Stage 2 — Match requirements to evidence

For every Tier 1 and Tier 2 term, determine:

```text
SUPPORTED AND EXACT
SUPPORTED BUT NOT YET EXACT
UNSUPPORTED
INAPPLICABLE
```

First, exclude evidence that does not materially support a Tier 1 term, a selected Tier 2 term, or the target role's central work.

Then rank the remaining relevant evidence using this priority:

1. Award or independent recognition tied to substantive work
2. Adopted or implemented product
3. Financial impact
4. Measurable operational improvement
5. Scale or usage
6. Recency

Rules:

- Prefer evidence that covers both an ATS term and immediate human value.
- JD relevance determines whether evidence receives space; immediate value determines the order of relevant evidence.
- Do not force every JD term into the resume.
- Unsupported terms remain absent.
- Do not allow a generic duty to displace an award, adoption metric, financial result, or major quantified accomplishment.

## Stage 3 — Generate the initial resume JSON

Construct the resume using the supplied schema.

### Bullet construction

Use this default pattern:

```text
Action or recognition + concrete deliverable + business purpose or result
```

When useful and supported:

```text
Exact JD term or tool + concrete deliverable + measurable value
```

### Bullet ordering

Order bullets by immediate value, not by the chronology of the work.

The first bullet under the most relevant recent experience should normally contain the strongest accomplishment.

### Resume hierarchy

The top portion of the resume should make the following easy to find:

- Degree and graduation date
- GPA or academic distinction when strong
- Most relevant recent employer
- Strongest award or result
- Highest-value number
- Adoption or scale
- Required tools

### Content budget

- Target one page.
- Use three to four bullets for the primary experience.
- Use one to three bullets for supporting entries.
- Use a default maximum of 180 characters per bullet.
- Use a maximum of four bullets for the primary experience and three bullets for each supporting entry.
- Renderer-specific limits supplied with the schema override these defaults.
- Remove lower-value process or technical detail before removing quantified outcomes.
- Do not duplicate the same accomplishment or primary signal across bullets.

### Skills placement

- Put tools in the skills section.
- Also use critical tools in experience bullets when directly supported by the work.
- Put degree, GPA, and graduation qualifications in education.
- Do not awkwardly place application-form information inside accomplishment bullets.

## Stage 4 — Audit the initial JSON

Evaluate every item using binary checks.

### Qualification audit

- Are all resume-appropriate hard qualifications explicit? `YES / NO`
- Is all stated eligibility information internally consistent? `YES / NO`
- Are graduation and future-role dates unambiguous? `YES / NO`

### ATS audit

- Is every supported Tier 1 keyword visible? `YES / NO`
- Are the selected high-priority Tier 2 keywords visible? `YES / NO`
- Are exact JD phrases preserved instead of being unnecessarily replaced with synonyms? `YES / NO`
- Are critical keywords attached to evidence when possible? `YES / NO`
- Is no critical term dependent solely on white-text injection? `YES / NO`
- Will the renderer receive the complete JD through `--jd` for supplemental keyword injection? `YES / NO`

### Evidence audit

- Are all locked facts unchanged? `YES / NO`
- Is every claim supported by the BD? `YES / NO`
- Is potential impact clearly qualified? `YES / NO`
- Is all future work clearly presented as future? `YES / NO`

### Human-scan audit

- Does each bullet's opening clause communicate its value? `YES / NO`
- Are the strongest accomplishments ordered first? `YES / NO`
- Are the strongest available awards, adoption metrics, financial impact, scale, and results easy to find? `YES / NO`
- Does every bullet place results ahead of ordinary process? `YES / NO`
- Does every bullet contain one dominant claim? `YES / NO`
- Is every claim plausible for the candidate's role level? `YES / NO`

### Efficiency audit

- Does every bullet materially improve ATS coverage or value perception? `YES / NO`
- Does every bullet communicate a distinct primary signal? `YES / NO`
- Does every clause preserve a material keyword, fact, or result? `YES / NO`
- Is the content likely to fit the page budget? `YES / NO`

## Stage 5 — Correct and return final JSON

`YES` means pass for every audit item. Revise every item answered `NO`.

Revision priority:

1. Correct locked facts, unsupported claims, and date errors.
2. Add missing supported Tier 1 keywords to visible content.
3. Add selected high-priority Tier 2 keywords to visible content.
4. Restore omitted high-value evidence.
5. Front-load buried value.
6. Remove redundancy and unnecessary process detail.
7. Shorten content to meet the page budget.

After revision, repeat the binary audit once.

Return the final JSON only when:

- The JSON matches the supplied schema.
- No locked fact changed.
- No unsupported claim remains.
- All supported Tier 1 keywords are visible.
- Selected high-priority Tier 2 terms are visible.
- The strongest evidence is prominently placed.
- No bullet buries its value beneath irrelevant process.
- The content meets the page budget.
- The complete JD is available to the renderer for supplemental injection.

---

## 5. Missing or Conflicting Information

If information is unknown:

- Do not infer it.
- Do not convert unknown into false.
- Do not add it to the resume.

If BD sources conflict:

- Preserve the value designated as locked.
- If neither value is locked, use the most recent authoritative source.
- If the conflict affects eligibility or a major claim, flag it instead of guessing.

If a critical input is missing:

- Missing JD: return `ERROR: MISSING_JD`.
- Missing BD: return `ERROR: MISSING_BD`.
- Missing resume schema: return `ERROR: MISSING_RESUME_SCHEMA`.
- Missing optional output metadata: use a filename-safe role and company identifier when available.

If a locked-fact conflict prevents reliable generation, return:

```text
ERROR: LOCKED_FACT_CONFLICT — <brief description>
```

Do not generate resume JSON after a blocking error.

---

## 6. Output Contract

Default output:

- Return only the final resume JSON.
- Do not return the JD analysis, evidence map, initial draft, audit checklist, explanations, or Markdown fences.
- Do not include fields outside the supplied schema.
- Produce valid JSON with double-quoted keys and strings.

The blocking error strings defined above are the only permitted non-JSON default outputs.

If the user explicitly requests an audit, return a concise audit separately from the final JSON.

The final JSON must remain directly usable by the resume renderer.

Render the final JSON with the complete JD:

```bash
python3.12 render.py input/<resume>.json --jd input/<job_description>.txt
```

The renderer's injected keywords count toward supplemental ATS coverage only. Human-scan review evaluates visible content only.

---

## 7. Portable Invocation

```text
Follow constitution.md exactly.

Generate a tailored resume from the supplied JD and BD. Complete the five
stages in order: extract requirements, match evidence, generate initial JSON,
perform the binary audit, and correct all failures. Use exact JD terminology
when supported. Engineer bullets for immediate value perception. Return only
schema-valid final JSON. Keep critical ATS terms visible; the renderer will
use the complete JD to inject supplemental terms.

JD:
{{JOB_DESCRIPTION}}

BD:
{{BASE_DOCUMENTS}}

LOCKED FACTS:
{{LOCKED_FACTS}}

RESUME SCHEMA:
{{RESUME_SCHEMA}}

OUTPUT METADATA:
{{OUTPUT_METADATA}}
```

---

## 8. Final Rule

```text
JD terms determine what must appear.
Candidate evidence determines what can be written.
Immediate value determines what receives space and priority.
The renderer supplements visible keyword coverage with deterministic injection.
The audit determines whether the first draft is allowed to become final.
```
