"""Deterministic validation for the canonical candidate evidence bank.

Enforces the contract in candidate_evidence_schema.json against
candidate_evidence.json, following the same philosophy as jd_validator.py:

  - structural checks (required keys, types, enums, no extra properties)
  - stable snake_case IDs unique within each namespace
  - referential integrity (fact -> metric, skill -> fact / education detail)
  - controlled competency-tag vocabulary, no duplicate tags per fact
  - metrics structurally locked (value/status/relationship/description/locked)
  - future entries may not reference realized metrics
  - evidence_strength is an integer 1..5

Errors stop the process; warnings do not.

Usage:

    python3.12 candidate_evidence_validator.py candidate_evidence.json
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PATH = BASE_DIR / 'candidate_evidence.json'

_SLUG_PATTERN = re.compile(r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$')

SECTIONS = {'experience', 'leadership', 'activity', 'other'}
STATUS_ENUM = {'realized', 'identified', 'estimated', 'potential', 'recommended',
               'implemented', 'ongoing'}
ENTRY_STATUS_ENUM = {'incoming', 'current', 'past'}
FACT_STATUS_ENUM = {'planned', 'in_progress', 'completed'}
RELATIONSHIP_ENUM = {'exact', 'up_to', 'exceeding', 'increase', 'decrease',
                     'count', 'annual', 'monthly'}
SKILL_CATEGORY = {'technical', 'business', 'communication', 'methodology',
                  'platform', 'tool', 'analytical'}

REALIZED_STATUSES = {'realized', 'implemented', 'ongoing'}

COMPETENCY_TAGS = {
    'quantitative_analysis', 'data_analysis', 'data_sourcing', 'data_cleaning',
    'data_structuring', 'data_modeling', 'data_visualization', 'financial_analysis',
    'financial_modeling', 'resource_allocation', 'decision_support',
    'workflow_automation', 'software_engineering', 'ai_llm', 'requirements_validation',
    'testing', 'implementation', 'research', 'document_analysis', 'legal_analysis',
    'presentation', 'communication', 'leadership', 'teamwork', 'stakeholder_management',
    'budget_management', 'strategic_recommendations', 'process_improvement',
}

FACT_REQUIRED = [
    'fact_id', 'canonical_description', 'actions', 'objects', 'technologies',
    'stakeholders', 'competency_tags', 'domain_tags', 'metrics',
    'approved_terms', 'forbidden_inferences', 'evidence_strength',
]
METRIC_REQUIRED = ['metric_id', 'value', 'status', 'relationship', 'description', 'locked']
SKILL_REQUIRED = [
    'skill_id', 'display_name', 'category', 'verified', 'proficiency',
    'evidence_fact_ids', 'education_evidence_ids',
]
ENTRY_REQUIRED = ['entry_id', 'section', 'organization', 'location', 'title', 'dates', 'facts']
EDUCATION_REQUIRED = ['education_id', 'institution', 'location', 'date', 'degree', 'details']


@dataclass
class ValidationReport:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, path: str, msg: str) -> None:
        self.errors.append(f'{path}: {msg}')

    def add_warning(self, path: str, msg: str) -> None:
        self.warnings.append(f'{path}: {msg}')


def _require_type(report: ValidationReport, path: str, value, types) -> None:
    if value is None:
        report.add_error(path, 'missing value')
        return
    if not isinstance(value, types):
        report.add_error(path, f'expected {types.__name__}, got {type(value).__name__}')


def _expect_keys(report: ValidationReport, path: str, obj, required: list, optional: list = None) -> None:
    optional = optional or []
    if not isinstance(obj, dict):
        report.add_error(path, 'expected object')
        return
    for k in obj:
        if k not in set(required) | set(optional):
            report.add_error(f'{path}.{k}', 'unexpected property')
    for k in required:
        if k not in obj:
            report.add_error(path, f'missing required key {k!r}')


def _check_slug(report: ValidationReport, path: str, value) -> None:
    if value is None:
        report.add_error(path, 'missing id')
    elif not isinstance(value, str):
        report.add_error(path, f'expected string id, got {type(value).__name__}')
    elif not _SLUG_PATTERN.match(value):
        report.add_error(path, f'not a valid snake_case slug: {value!r}')


def _check_string_list(report: ValidationReport, path: str, value) -> None:
    if value is None:
        return
    _require_type(report, path, value, list)
    if isinstance(value, list):
        for i, item in enumerate(value):
            _require_type(report, f'{path}[{i}]', item, str)
            if isinstance(item, str) and not item:
                report.add_error(f'{path}[{i}]', 'empty string')


def _check_top(report: ValidationReport, data) -> None:
    _expect_keys(report, 'root', data,
                 ['schema_version', 'candidate', 'education', 'entries', 'metrics', 'skills'])
    sv = data.get('schema_version')
    if sv is not None:
        _require_type(report, 'schema_version', sv, str)
        if isinstance(sv, str) and not sv:
            report.add_error('schema_version', 'empty string')


def _check_candidate(report: ValidationReport, data) -> None:
    cand = data.get('candidate')
    if cand is None:
        report.add_error('candidate', 'missing')
        return
    _expect_keys(report, 'candidate', cand, ['name'], ['email', 'phone', 'location', 'linkedin'])
    name = cand.get('name')
    _require_type(report, 'candidate.name', name, str)
    if isinstance(name, str) and not name.strip():
        report.add_error('candidate.name', 'empty string')


def _check_education(report: ValidationReport, data) -> dict:
    edu_ids = set()
    detail_ids = set()
    edu = data.get('education')
    if edu is None:
        report.add_error('education', 'missing')
        return {'detail_ids': detail_ids}
    _require_type(report, 'education', edu, list)
    if not isinstance(edu, list):
        return {'detail_ids': detail_ids}
    for i, rec in enumerate(edu):
        p = f'education[{i}]'
        _expect_keys(report, p, rec, EDUCATION_REQUIRED)
        eid = rec.get('education_id')
        _check_slug(report, f'{p}.education_id', eid)
        if isinstance(eid, str):
            if eid in edu_ids:
                report.add_error(f'{p}.education_id', f'duplicate education_id {eid!r}')
            edu_ids.add(eid)
        for k in ('institution', 'location', 'date', 'degree'):
            v = rec.get(k)
            _check_nonempty_string(report, f'{p}.{k}', v)
        details = rec.get('details')
        if details is None:
            report.add_error(f'{p}.details', 'missing')
            continue
        _require_type(report, f'{p}.details', details, list)
        if not isinstance(details, list):
            continue
        for j, d in enumerate(details):
            dp = f'{p}.details[{j}]'
            _expect_keys(report, dp, d, ['detail_id', 'text', 'locked'],
                         ['optional', 'detail_tags'])
            did = d.get('detail_id')
            _check_slug(report, f'{dp}.detail_id', did)
            if isinstance(did, str):
                if did in detail_ids:
                    report.add_error(f'{dp}.detail_id', f'duplicate detail_id {did!r}')
                detail_ids.add(did)
            _check_nonempty_string(report, f'{dp}.text', d.get('text'))
            if 'locked' in d:
                _require_type(report, f'{dp}.locked', d['locked'], bool)
            if 'optional' in d:
                _require_type(report, f'{dp}.optional', d['optional'], bool)
            if 'detail_tags' in d:
                _check_tag_list(report, f'{dp}.detail_tags', d['detail_tags'],
                                controlled=True)
    return {'detail_ids': detail_ids, 'education_ids': edu_ids}


def _check_nonempty_string(report: ValidationReport, path: str, value) -> None:
    if value is None:
        report.add_error(path, 'missing')
        return
    _require_type(report, path, value, str)
    if isinstance(value, str) and not value.strip():
        report.add_error(path, 'empty string')


def _check_entries(report: ValidationReport, data) -> dict:
    entry_ids = set()
    fact_ids = set()
    future_entries = []
    entries = data.get('entries')
    if entries is None:
        report.add_error('entries', 'missing')
        return {'fact_ids': fact_ids, 'future_entries': future_entries}
    _require_type(report, 'entries', entries, list)
    if not isinstance(entries, list):
        return {'fact_ids': fact_ids, 'future_entries': future_entries}
    for i, entry in enumerate(entries):
        p = f'entries[{i}]'
        _expect_keys(report, p, entry, ENTRY_REQUIRED, ['future', 'entry_status'])
        eid = entry.get('entry_id')
        _check_slug(report, f'{p}.entry_id', eid)
        if isinstance(eid, str):
            if eid in entry_ids:
                report.add_error(f'{p}.entry_id', f'duplicate entry_id {eid!r}')
            entry_ids.add(eid)
        section = entry.get('section')
        if section is not None:
            _require_type(report, f'{p}.section', section, str)
            if isinstance(section, str) and section not in SECTIONS:
                report.add_error(f'{p}.section', f'invalid section {section!r}')
        for k in ('organization', 'location', 'title', 'dates'):
            _check_nonempty_string(report, f'{p}.{k}', entry.get(k))
        future = entry.get('future')
        if future is not None:
            _require_type(report, f'{p}.future', future, bool)
        entry_status = entry.get('entry_status')
        if entry_status is not None:
            _require_type(report, f'{p}.entry_status', entry_status, str)
            if isinstance(entry_status, str) and entry_status not in ENTRY_STATUS_ENUM:
                report.add_error(f'{p}.entry_status',
                                 f'invalid entry_status {entry_status!r}')
        if isinstance(entry_status, str) and isinstance(future, bool):
            if future and entry_status != 'incoming':
                report.add_warning(f'{p}.entry_status',
                                   f'future={future} but entry_status={entry_status!r}')
            if not future and entry_status == 'incoming':
                report.add_warning(f'{p}.entry_status',
                                   f'future={future} but entry_status={entry_status!r}')
        facts = entry.get('facts')
        if facts is None:
            report.add_error(f'{p}.facts', 'missing')
            continue
        _require_type(report, f'{p}.facts', facts, list)
        if not isinstance(facts, list):
            continue
        for j, fact in enumerate(facts):
            fp = f'{p}.facts[{j}]'
            _check_fact(report, fp, fact, fact_ids, future_entry=(future is True))
            if future is True:
                future_entries.append((entry, facts))
    return {'fact_ids': fact_ids, 'future_entries': future_entries}


def _check_fact(report: ValidationReport, path: str, fact, fact_ids: set, future_entry: bool = False) -> None:
    _expect_keys(report, path, fact, FACT_REQUIRED, ['fact_status'])
    fid = fact.get('fact_id')
    _check_slug(report, f'{path}.fact_id', fid)
    if isinstance(fid, str):
        if fid in fact_ids:
            report.add_error(f'{path}.fact_id', f'duplicate fact_id {fid!r}')
        fact_ids.add(fid)
    _check_nonempty_string(report, f'{path}.canonical_description', fact.get('canonical_description'))
    for k in ('actions', 'objects', 'technologies', 'stakeholders', 'approved_terms',
              'forbidden_inferences'):
        _check_string_list(report, f'{path}.{k}', fact.get(k))
    for k in ('competency_tags', 'domain_tags'):
        _check_tag_list(report, f'{path}.{k}', fact.get(k), controlled=(k == 'competency_tags'))
    _check_string_list(report, f'{path}.metrics', fact.get('metrics'))
    fact_status = fact.get('fact_status')
    if fact_status is not None:
        _require_type(report, f'{path}.fact_status', fact_status, str)
        if isinstance(fact_status, str) and fact_status not in FACT_STATUS_ENUM:
            report.add_error(f'{path}.fact_status',
                             f'invalid fact_status {fact_status!r}')
    if future_entry and isinstance(fact_status, str) and fact_status != 'planned':
        report.add_warning(f'{path}.fact_status',
                           'incoming entry but fact_status is not planned')
    strength = fact.get('evidence_strength')
    _require_type(report, f'{path}.evidence_strength', strength, int)
    if isinstance(strength, bool):
        report.add_error(f'{path}.evidence_strength', 'expected integer, got bool')
    elif isinstance(strength, int) and not 1 <= strength <= 5:
        report.add_error(f'{path}.evidence_strength', f'{strength} outside 1..5')
    metrics = fact.get('metrics')
    if isinstance(metrics, list) and not metrics:
        report.add_warning(path, 'fact has no metrics')
    approved = fact.get('approved_terms')
    if isinstance(approved, list) and not approved:
        report.add_warning(path, 'fact has no approved terms')


def _check_tag_list(report: ValidationReport, path: str, value, controlled: bool) -> None:
    if value is None:
        return
    _require_type(report, path, value, list)
    if not isinstance(value, list):
        return
    seen = set()
    for i, tag in enumerate(value):
        tp = f'{path}[{i}]'
        if not isinstance(tag, str):
            report.add_error(tp, f'expected string tag, got {type(tag).__name__}')
            continue
        if not _SLUG_PATTERN.match(tag):
            report.add_error(tp, f'not a valid snake_case tag: {tag!r}')
        if controlled and tag not in COMPETENCY_TAGS:
            report.add_error(tp, f'not in controlled competency vocabulary: {tag!r}')
        if tag in seen:
            report.add_error(tp, f'duplicate tag {tag!r}')
        seen.add(tag)


def _check_metrics(report: ValidationReport, data) -> dict:
    metric_ids = set()
    metric_status = {}
    metrics = data.get('metrics')
    if metrics is None:
        report.add_error('metrics', 'missing')
        return {'metric_ids': metric_ids, 'metric_status': metric_status}
    _require_type(report, 'metrics', metrics, list)
    if not isinstance(metrics, list):
        return {'metric_ids': metric_ids, 'metric_status': metric_status}
    for i, m in enumerate(metrics):
        p = f'metrics[{i}]'
        _expect_keys(report, p, m, METRIC_REQUIRED)
        mid = m.get('metric_id')
        _check_slug(report, f'{p}.metric_id', mid)
        if isinstance(mid, str):
            if mid in metric_ids:
                report.add_error(f'{p}.metric_id', f'duplicate metric_id {mid!r}')
            metric_ids.add(mid)
        _check_nonempty_string(report, f'{p}.value', m.get('value'))
        _check_nonempty_string(report, f'{p}.description', m.get('description'))
        status = m.get('status')
        if status is not None:
            _require_type(report, f'{p}.status', status, str)
            if isinstance(status, str) and status not in STATUS_ENUM:
                report.add_error(f'{p}.status', f'invalid status {status!r}')
            if isinstance(mid, str):
                metric_status[mid] = status
        rel = m.get('relationship')
        if rel is not None:
            _require_type(report, f'{p}.relationship', rel, str)
            if isinstance(rel, str) and rel not in RELATIONSHIP_ENUM:
                report.add_error(f'{p}.relationship', f'invalid relationship {rel!r}')
        if 'locked' in m:
            _require_type(report, f'{p}.locked', m['locked'], bool)
    return {'metric_ids': metric_ids, 'metric_status': metric_status}


def _check_references(report: ValidationReport, data, fact_ids: set,
                      metric_ids: set, detail_ids: set) -> dict:
    metrics_by_fact = {}
    entries = data.get('entries') or []
    for i, entry in enumerate(entries):
        facts = entry.get('facts') or [] if isinstance(entry, dict) else []
        for j, fact in enumerate(facts):
            if not isinstance(fact, dict):
                continue
            fid = fact.get('fact_id')
            fp = f'entries[{i}].facts[{j}]'
            for k, mid in enumerate(fact.get('metrics') or []):
                if not isinstance(mid, str):
                    continue
                if mid not in metric_ids:
                    report.add_error(f'{fp}.metrics[{k}]', f'unresolved metric_id {mid!r}')
                metrics_by_fact.setdefault(fid, []).append(mid)
    skills = data.get('skills') or []
    if not isinstance(skills, list):
        return {'metrics_by_fact': metrics_by_fact}
    verified = 0
    unverified = 0
    for i, skill in enumerate(skills):
        if not isinstance(skill, dict):
            continue
        sp = f'skills[{i}]'
        for k, ref in enumerate(skill.get('evidence_fact_ids') or []):
            if isinstance(ref, str) and ref not in fact_ids:
                report.add_error(f'{sp}.evidence_fact_ids[{k}]', f'unresolved fact_id {ref!r}')
        for k, ref in enumerate(skill.get('education_evidence_ids') or []):
            if isinstance(ref, str) and ref not in detail_ids:
                report.add_error(f'{sp}.education_evidence_ids[{k}]', f'unresolved education detail_id {ref!r}')
        is_verified = skill.get('verified')
        if is_verified is True:
            verified += 1
            facts = skill.get('evidence_fact_ids') or []
            coursework = skill.get('education_evidence_ids') or []
            if not facts and not coursework:
                report.add_error(sp, f'verified skill has no evidence references')
            elif facts and coursework:
                report.add_warning(sp, 'verified skill supported by facts and coursework')
            elif not facts and coursework:
                report.add_warning(sp, 'verified skill supported by coursework only')
        elif is_verified is False:
            unverified += 1
    return {'verified_skills': verified, 'unverified_skills': unverified,
            'metrics_by_fact': metrics_by_fact}


def _check_future_entries(report: ValidationReport, future_entries, metric_status: dict) -> None:
    for entry, facts in future_entries:
        eid = entry.get('entry_id') if isinstance(entry, dict) else None
        label = f'future entry {eid!r}' if isinstance(eid, str) else 'future entry'
        for j, fact in enumerate(facts):
            if not isinstance(fact, dict):
                continue
            for mid in fact.get('metrics') or []:
                if mid in metric_status and metric_status[mid] in REALIZED_STATUSES:
                    report.add_error(
                        f'{label} fact {fact.get("fact_id")!r}',
                        f'references realized metric {mid!r}')


def validate(data) -> ValidationReport:
    """Validate the evidence bank. Returns a report; empty errors means valid."""
    report = ValidationReport()
    if not isinstance(data, dict):
        report.add_error('root', f'expected JSON object, got {type(data).__name__}')
        return report
    _check_top(report, data)
    _check_candidate(report, data)
    edu = _check_education(report, data)
    entries = _check_entries(report, data)
    metrics = _check_metrics(report, data)
    refs = _check_references(report, data, entries['fact_ids'], metrics['metric_ids'],
                             edu['detail_ids'])
    _check_future_entries(report, entries['future_entries'], metrics['metric_status'])

    n_entries = len(data.get('entries') or [])
    n_facts = len(entries['fact_ids'])
    n_metrics = len(metrics['metric_ids'])
    report.counts = {
        'entries': n_entries,
        'facts': n_facts,
        'metrics': n_metrics,
        'verified_skills': refs.get('verified_skills', 0),
        'unverified_skills': refs.get('unverified_skills', 0),
    }
    return report


def load_data(path=None) -> dict:
    p = Path(path) if path else DEFAULT_PATH
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_report(report: ValidationReport) -> str:
    status = 'OK' if report.ok else f'FAILED ({len(report.errors)} error'
    if not report.ok:
        status += 's' if len(report.errors) != 1 else ''
        status += ')'
    lines = [f'Candidate evidence validation: {status}', '']
    if not report.ok:
        for err in report.errors:
            lines.append(f'  ERROR  {err}')
        lines.append('')
    c = report.counts
    lines.append(f'Entries: {c.get("entries", 0)}')
    lines.append(f'Facts: {c.get("facts", 0)}')
    lines.append(f'Metrics: {c.get("metrics", 0)}')
    lines.append(f'Verified skills: {c.get("verified_skills", 0)}')
    lines.append(f'Unverified skills: {c.get("unverified_skills", 0)}')
    lines.append(f'Warnings: {len(report.warnings)}')
    for w in report.warnings:
        lines.append(f'  WARN  {w}')
    return '\n'.join(lines)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Validate the candidate evidence bank')
    parser.add_argument('file', nargs='?', default=None,
                        help='path to candidate_evidence.json (default: repo default)')
    args = parser.parse_args(argv)
    try:
        data = load_data(args.file)
    except (OSError, json.JSONDecodeError) as e:
        print(f'error loading evidence bank: {e}', file=sys.stderr)
        return 1
    report = validate(data)
    print(format_report(report))
    return 0 if report.ok else 1


if __name__ == '__main__':
    sys.exit(main())