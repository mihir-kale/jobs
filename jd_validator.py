"""Programmatic validation for JD parser LLM output.

Implements every post-generation check specified in jd_parser_prompt.md against
the raw job description and the strict output shape in jd_parser_schema.json:

  - schema compliance (types, enums, required keys, no extra properties)
  - evidence quotes are literal substrings of the JD
  - <= 8 Tier 2 records, <= 4 behavioral records
  - contiguous Tier 2 ranks
  - score totals equal their component sums
  - unique normalized Tier 1 terms
  - stable array ordering (appearance order, level-group order, score order)

Returns a list of human-readable errors; an empty list means the output is valid.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / 'jd_parser_schema.json'

_REQUIRED_KEYS = {
    'top': ('schema_version', 'job_identity', 'role_summary', 'hard_qualifications',
            'tier_1_terms', 'tier_2_competencies', 'behavioral_competencies', 'ambiguities'),
}
_LEVEL_ORDER = {'required': 0, 'preferred': 1, 'responsibility': 2, 'mentioned': 3}

_SLUG_PATTERN = re.compile(r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$')


def slugify(name) -> str:
    return re.sub(r'[^a-z0-9]+', '_', (name or '').casefold()).strip('_')


@dataclass
class ValidationResult:
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, path: str, msg: str) -> None:
        self.errors.append(f'{path}: {msg}')

    def lines(self) -> list:
        return self.errors


def load_schema() -> dict:
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _require_type(result: ValidationResult, path: str, value, types) -> None:
    if value is None and 'null' in types:
        return
    if not isinstance(value, types):
        result.add(path, f'expected {_friendly(types)}, got {type(value).__name__}')


def _friendly(types) -> str:
    names = []
    for t in types:
        if t is str:
            names.append('string')
        elif t is int:
            names.append('integer')
        elif t is float:
            names.append('number')
        elif t is list:
            names.append('array')
        elif t is dict:
            names.append('object')
        elif t is bool:
            names.append('boolean')
        else:
            names.append(t.__name__)
    return ' or '.join(names)


def _expect_keys(result: ValidationResult, path: str, obj: dict, required: list, optional: list) -> None:
    if not isinstance(obj, dict):
        result.add(path, 'expected object')
        return
    allowed = set(required) | set(optional)
    for k in obj:
        if k not in allowed:
            result.add(f'{path}.{k}', 'unexpected property (schema does not allow it)')
    for k in required:
        if k not in obj:
            result.add(f'{path}', f'missing required key {k!r}')


def _check_top(result: ValidationResult, data) -> None:
    _expect_keys(result, 'root', data, list(_REQUIRED_KEYS['top']), [])
    if isinstance(data, dict):
        v = data.get('schema_version')
        if v is not None:
            _require_type(result, 'schema_version', v, str)


def _check_job_identity(result: ValidationResult, data) -> None:
    ji = data.get('job_identity') if isinstance(data, dict) else None
    if ji is None:
        result.add('job_identity', 'missing')
        return
    _expect_keys(result, 'job_identity', ji,
                 ['company', 'title', 'locations', 'employment_type', 'program_term', 'seniority'], [])
    for k in ('company', 'title', 'employment_type', 'program_term'):
        if k in ji and ji[k] is not None:
            _require_type(result, f'job_identity.{k}', ji[k], str)
    if 'locations' in ji:
        _require_type(result, 'job_identity.locations', ji['locations'], list)
        for i, loc in enumerate(ji['locations']):
            _require_type(result, f'job_identity.locations[{i}]', loc, str)
    if 'seniority' in ji:
        _require_type(result, 'job_identity.seniority', ji['seniority'], str)
        if ji['seniority'] not in ('internship', 'entry_level', 'experienced', 'leadership', 'unspecified'):
            result.add('job_identity.seniority', f"invalid value {ji['seniority']!r}")


def _check_role_summary(result: ValidationResult, data) -> None:
    rs = data.get('role_summary') if isinstance(data, dict) else None
    if rs is None:
        result.add('role_summary', 'missing')
        return
    _expect_keys(result, 'role_summary', rs, ['primary_mandate', 'business_outcomes'], [])
    pm = rs.get('primary_mandate')
    if pm is not None:
        _require_type(result, 'role_summary.primary_mandate', pm, str)
        if isinstance(pm, str) and len(pm.split()) > 35:
            result.add('role_summary.primary_mandate', 'more than 35 words')
    bo = rs.get('business_outcomes')
    if bo is None:
        result.add('role_summary.business_outcomes', 'missing')
        return
    _require_type(result, 'role_summary.business_outcomes', bo, list)
    if len(bo) > 3:
        result.add('role_summary.business_outcomes', 'more than 3 outcomes')
    for i, o in enumerate(bo):
        _require_type(result, f'role_summary.business_outcomes[{i}]', o, str)
        if isinstance(o, str) and len(o.split()) > 16:
            result.add(f'role_summary.business_outcomes[{i}]', 'more than 16 words')


def _check_hard_qualifications(result: ValidationResult, data) -> None:
    hq = data.get('hard_qualifications') if isinstance(data, dict) else None
    if hq is None:
        result.add('hard_qualifications', 'missing')
        return
    _require_type(result, 'hard_qualifications', hq, list)
    for i, rec in enumerate(hq):
        p = f'hard_qualifications[{i}]'
        _expect_keys(result, p, rec,
                     ['category', 'requirement', 'level', 'resume_visibility', 'evidence_quote'], [])
        if rec.get('category') not in ('enrollment', 'degree', 'major', 'graduation_date', 'gpa',
                                       'work_authorization', 'location', 'travel', 'clearance', 'age',
                                       'availability', 'experience', 'credential', 'other'):
            result.add(f'{p}.category', f"invalid value {rec.get('category')!r}")
        if rec.get('level') not in ('required', 'preferred'):
            result.add(f'{p}.level', f"invalid value {rec.get('level')!r}")
        if rec.get('resume_visibility') not in ('must_show_if_supported', 'helpful_if_supported', 'application_only'):
            result.add(f'{p}.resume_visibility', f"invalid value {rec.get('resume_visibility')!r}")
        for k in ('requirement', 'evidence_quote'):
            v = rec.get(k)
            if v is None:
                continue
            _require_type(result, f'{p}.{k}', v, str)
            if isinstance(v, str) and not v.strip():
                result.add(f'{p}.{k}', 'empty string')


def _check_tier_1(result: ValidationResult, data) -> None:
    t1 = data.get('tier_1_terms') if isinstance(data, dict) else None
    if t1 is None:
        result.add('tier_1_terms', 'missing')
        return
    _require_type(result, 'tier_1_terms', t1, list)
    seen = set()
    for i, rec in enumerate(t1):
        p = f'tier_1_terms[{i}]'
        _expect_keys(result, p, rec,
                     ['canonical_term', 'exact_terms', 'category', 'level', 'evidence_quotes'], [])
        if rec.get('category') not in ('programming_language', 'framework_library', 'ai_data', 'cloud',
                                       'database', 'development_tool', 'analytical_tool', 'software_platform',
                                       'methodology', 'credential', 'technical_terminology', 'other'):
            result.add(f'{p}.category', f"invalid value {rec.get('category')!r}")
        if rec.get('level') not in ('required', 'preferred', 'responsibility', 'mentioned'):
            result.add(f'{p}.level', f"invalid value {rec.get('level')!r}")
        ct = rec.get('canonical_term')
        if ct is not None:
            _require_type(result, f'{p}.canonical_term', ct, str)
            if isinstance(ct, str):
                norm = ct.casefold().strip()
                if norm in seen:
                    result.add(f'{p}.canonical_term', f'duplicate Tier 1 term {ct!r}')
                seen.add(norm)
        et = rec.get('exact_terms')
        _require_type(result, f'{p}.exact_terms', et, list)
        if isinstance(et, list) and not et:
            result.add(f'{p}.exact_terms', 'must contain at least one term')
        eq = rec.get('evidence_quotes')
        if eq is not None:
            _require_type(result, f'{p}.evidence_quotes', eq, list)


def _check_tier_2(result: ValidationResult, data) -> None:
    t2 = data.get('tier_2_competencies') if isinstance(data, dict) else None
    if t2 is None:
        result.add('tier_2_competencies', 'missing')
        return
    _require_type(result, 'tier_2_competencies', t2, list)
    if len(t2) > 8:
        result.add('tier_2_competencies', 'more than 8 records')
    ranks = []
    ids = set()
    for i, rec in enumerate(t2):
        p = f'tier_2_competencies[{i}]'
        _expect_keys(result, p, rec,
                     ['competency_id', 'rank', 'competency', 'category', 'score', 'exact_jd_phrases',
                      'evidence_quotes', 'resume_evidence_sought'], [])
        cid = rec.get('competency_id')
        if cid is None:
            result.add(f'{p}.competency_id', 'missing')
        elif not isinstance(cid, str):
            result.add(f'{p}.competency_id', f'expected string, got {type(cid).__name__}')
        elif not _SLUG_PATTERN.match(cid):
            result.add(f'{p}.competency_id', f'not a valid snake_case slug: {cid!r}')
        else:
            if cid in ids:
                result.add(f'{p}.competency_id', f'duplicate competency_id {cid!r}')
            ids.add(cid)
            name = rec.get('competency')
            if isinstance(name, str) and slugify(name) != cid:
                result.add(f'{p}.competency_id', f"does not match slug of competency name {name!r}; expected {slugify(name)!r}")
        _require_type(result, f'{p}.rank', rec.get('rank'), int)
        if isinstance(rec.get('rank'), int):
            ranks.append(rec['rank'])
        if rec.get('category') not in ('responsibility', 'method', 'deliverable', 'role_function',
                                       'stakeholder_activity', 'domain_terminology'):
            result.add(f'{p}.category', f"invalid value {rec.get('category')!r}")
        res = rec.get('resume_evidence_sought')
        _require_type(result, f'{p}.resume_evidence_sought', res, list)
        if isinstance(res, list):
            if not res or len(res) > 3:
                result.add(f'{p}.resume_evidence_sought', 'expected 1 to 3 evidence types')
            for e in res:
                if e not in ('award', 'adopted_product', 'financial_impact', 'operational_improvement',
                             'scale_or_usage', 'technical_implementation', 'analysis', 'recommendation',
                             'leadership', 'communication', 'domain_experience'):
                    result.add(f'{p}.resume_evidence_sought', f'invalid evidence type {e!r}')
        score = rec.get('score')
        if score is None:
            result.add(f'{p}.score', 'missing')
            continue
        _expect_keys(result, f'{p}.score', score,
                     ['required_status', 'repetition', 'centrality', 'specificity', 'total'], [])
        comps = {}
        for k in ('required_status', 'repetition', 'centrality', 'specificity'):
            v = score.get(k)
            _require_type(result, f'{p}.score.{k}', v, int)
            if isinstance(v, int):
                comps[k] = v
        lo = {'required_status': 3, 'repetition': 2, 'centrality': 3, 'specificity': 2}
        for k, hi in lo.items():
            if comps.get(k, 0) > hi:
                result.add(f'{p}.score.{k}', f'value {comps[k]} exceeds max {hi}')
        total = score.get('total')
        _require_type(result, f'{p}.score.total', total, int)
        if isinstance(total, int):
            expected = sum(comps.values())
            if total != expected:
                result.add(f'{p}.score.total', f'{total} != component sum {expected}')
    if ranks:
        if sorted(set(ranks)) != ranks or len(set(ranks)) != len(ranks):
            result.add('tier_2_competencies', 'ranks are not unique')
        if ranks != list(range(1, len(ranks) + 1)):
            result.add('tier_2_competencies', 'ranks are not contiguous from 1')
        totals = []
        for rec in t2:
            sc = rec.get('score') or {}
            totals.append(sc.get('total') if isinstance(sc, dict) else None)
        if any(t is None for t in totals):
            result.add('tier_2_competencies', 'cannot verify score order for all records')
        elif any(a < b for a, b in zip(totals, totals[1:])):
            result.add('tier_2_competencies', 'total scores are not in descending rank order')


def _check_behavioral(result: ValidationResult, data) -> None:
    bc = data.get('behavioral_competencies') if isinstance(data, dict) else None
    if bc is None:
        result.add('behavioral_competencies', 'missing')
        return
    _require_type(result, 'behavioral_competencies', bc, list)
    if len(bc) > 4:
        result.add('behavioral_competencies', 'more than 4 records')
    for i, rec in enumerate(bc):
        p = f'behavioral_competencies[{i}]'
        _expect_keys(result, p, rec, ['competency', 'level', 'evidence_quote'], [])
        if rec.get('level') not in ('required', 'preferred', 'emphasized', 'mentioned'):
            result.add(f'{p}.level', f"invalid value {rec.get('level')!r}")


def _check_ambiguities(result: ValidationResult, data) -> None:
    am = data.get('ambiguities') if isinstance(data, dict) else None
    if am is None:
        result.add('ambiguities', 'missing')
        return
    _require_type(result, 'ambiguities', am, list)
    for i, rec in enumerate(am):
        p = f'ambiguities[{i}]'
        _expect_keys(result, p, rec, ['issue', 'evidence_quotes'], [])
        if 'issue' in rec:
            _require_type(result, f'{p}.issue', rec['issue'], str)
        if 'evidence_quotes' in rec:
            _require_type(result, f'{p}.evidence_quotes', rec['evidence_quotes'], list)


def _collect_evidence(data: dict) -> list:
    items = []
    for i, rec in enumerate(data.get('hard_qualifications') or []):
        if isinstance(rec, dict) and rec.get('evidence_quote'):
            items.append((f'hard_qualifications[{i}].evidence_quote', rec['evidence_quote']))
    for i, rec in enumerate(data.get('tier_1_terms') or []):
        if not isinstance(rec, dict):
            continue
        for j, t in enumerate(rec.get('exact_terms') or []):
            items.append((f'tier_1_terms[{i}].exact_terms[{j}]', t))
        for j, q in enumerate(rec.get('evidence_quotes') or []):
            items.append((f'tier_1_terms[{i}].evidence_quotes[{j}]', q))
    for i, rec in enumerate(data.get('tier_2_competencies') or []):
        if not isinstance(rec, dict):
            continue
        for j, p in enumerate(rec.get('exact_jd_phrases') or []):
            items.append((f'tier_2_competencies[{i}].exact_jd_phrases[{j}]', p))
        for j, q in enumerate(rec.get('evidence_quotes') or []):
            items.append((f'tier_2_competencies[{i}].evidence_quotes[{j}]', q))
    for i, rec in enumerate(data.get('behavioral_competencies') or []):
        if isinstance(rec, dict) and rec.get('evidence_quote'):
            items.append((f'behavioral_competencies[{i}].evidence_quote', rec['evidence_quote']))
    for i, rec in enumerate(data.get('ambiguities') or []):
        if not isinstance(rec, dict):
            continue
        for j, q in enumerate(rec.get('evidence_quotes') or []):
            items.append((f'ambiguities[{i}].evidence_quotes[{j}]', q))
    return items


def _check_quotes(result: ValidationResult, jd_text: str, data: dict) -> None:
    for path, quote in _collect_evidence(data):
        _require_type(result, path, quote, str)
        if isinstance(quote, str) and jd_text.find(quote) == -1:
            result.add(path, f'not a contiguous substring of the job description: {quote[:80]!r}')


def _check_ordering(result: ValidationResult, jd_text: str, data: dict) -> None:
    def pos(s: str) -> int:
        return jd_text.find(s)

    hq = data.get('hard_qualifications') or []
    current = -1
    seen_preferred = False
    for i, rec in enumerate(hq):
        if not isinstance(rec, dict):
            continue
        q = rec.get('evidence_quote')
        p = pos(q) if isinstance(q, str) else -1
        level = rec.get('level')
        if level == 'preferred':
            seen_preferred = True
        elif seen_preferred:
            result.add(f'hard_qualifications[{i}]', 'required item appears after a preferred item')
        if p == -1:
            continue
        if p < current:
            result.add(f'hard_qualifications[{i}]', 'evidence quote out of appearance order')
        current = p

    t1 = data.get('tier_1_terms') or []
    level_pos = {lvl: -1 for lvl in ('required', 'preferred', 'responsibility', 'mentioned')}
    for i, rec in enumerate(t1):
        if not isinstance(rec, dict):
            continue
        quotes = [q for q in (rec.get('evidence_quotes') or []) if isinstance(q, str)]
        if not quotes:
            continue
        first = min(pos(q) for q in quotes)
        level = rec.get('level')
        if level in level_pos:
            if first < level_pos[level]:
                result.add(f'tier_1_terms[{i}]', 'evidence quote out of appearance order within its level')
            level_pos[level] = max(level_pos[level], first)
    order = [lvl for lvl in ('required', 'preferred', 'responsibility', 'mentioned') if level_pos[lvl] != -1]
    for a, b in zip(order, order[1:]):
        if level_pos[a] > level_pos[b]:
            result.add('tier_1_terms', f'level group {a!r} appears after {b!r}')

    bc = data.get('behavioral_competencies') or []
    current = -1
    for i, rec in enumerate(bc):
        if not isinstance(rec, dict):
            continue
        q = rec.get('evidence_quote')
        p = pos(q) if isinstance(q, str) else -1
        if p == -1:
            continue
        if p < current:
            result.add(f'behavioral_competencies[{i}]', 'evidence quote out of employer-emphasis order')
        current = p


def validate(jd_text: str, data) -> ValidationResult:
    """Validate parsed output against the schema and the raw JD text."""
    result = ValidationResult()
    if not isinstance(data, dict):
        result.add('root', f'expected JSON object, got {type(data).__name__}')
        return result
    _check_top(result, data)
    _check_job_identity(result, data)
    _check_role_summary(result, data)
    _check_hard_qualifications(result, data)
    _check_tier_1(result, data)
    _check_tier_2(result, data)
    _check_behavioral(result, data)
    _check_ambiguities(result, data)
    _check_quotes(result, jd_text, data)
    _check_ordering(result, jd_text, data)
    return result


def repair_prompt(jd_text: str, raw_output: str, errors: list) -> str:
    err_lines = '\n'.join(f'- {e}' for e in errors)
    return (
        'A model-generated JSON object for the job description below failed programmatic validation.\n'
        'Correct ONLY the listed validation errors. Keep every other value unchanged, preserve the '
        'employer\'s exact terminology, and keep every new evidence quote an exact, contiguous substring '
        'of the supplied job description. Return only the corrected JSON object conforming to the schema.\n\n'
        '<job_description>\n'
        f'{jd_text}\n'
        '</job_description>\n\n'
        'INVALID JSON:\n'
        f'```json\n{raw_output}\n```\n\n'
        'VALIDATION ERRORS:\n'
        f'{err_lines}\n'
    )