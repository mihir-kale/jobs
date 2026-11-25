"""Tests for the candidate evidence validator.

Covers the dangerous cases: duplicate IDs, broken references, invalid slugs,
invalid evidence strength, duplicate competency tags, malformed metrics, and
representation-valid entries/education. Also verifies the real evidence bank.

Run from the repo root:

    python3.12 -m unittest discover -s tests
"""

import copy
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from candidate_evidence_validator import validate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_fact(**overrides):
    fact = {
        'fact_id': 'test_fact',
        'canonical_description': 'Built a thing that did something.',
        'actions': ['built'],
        'objects': ['a thing'],
        'technologies': ['Python'],
        'stakeholders': [],
        'competency_tags': ['software_engineering'],
        'domain_tags': ['software'],
        'metrics': ['test_metric'],
        'approved_terms': [],
        'forbidden_inferences': [],
        'evidence_strength': 4,
    }
    fact.update(overrides)
    return fact


def make_metric(**overrides):
    metric = {
        'metric_id': 'test_metric',
        'value': '10%',
        'status': 'realized',
        'relationship': 'increase',
        'description': 'improvement',
        'locked': True,
    }
    metric.update(overrides)
    return metric


def make_bank(**overrides):
    bank = {
        'schema_version': '1.0',
        'candidate': {'name': 'Test Candidate'},
        'education': [
            {
                'education_id': 'test_uni',
                'institution': 'Test University',
                'location': 'Test City, ST',
                'date': 'June 2030',
                'degree': 'Bachelor of Testing',
                'details': [
                    {
                        'detail_id': 'test_course',
                        'text': 'Coursework: Testing methods',
                        'locked': True,
                    }
                ],
            }
        ],
        'entries': [
            {
                'entry_id': 'test_entry',
                'section': 'experience',
                'organization': 'Test Co',
                'location': 'Test City, ST',
                'title': 'Test Intern',
                'dates': 'Summer 2030',
                'facts': [make_fact()],
            }
        ],
        'metrics': [make_metric()],
        'skills': [
            {
                'skill_id': 'python',
                'display_name': 'Python',
                'category': 'technical',
                'verified': True,
                'proficiency': 3,
                'evidence_fact_ids': ['test_fact'],
                'education_evidence_ids': [],
            }
        ],
    }
    bank.update(overrides)
    return bank


class TestCandidateEvidenceValidator(unittest.TestCase):
    def test_duplicate_fact_id_fails(self):
        bank = make_bank()
        dup = make_fact(fact_id='test_fact', canonical_description='Duplicate fact.')
        bank['entries'][0]['facts'].append(dup)
        report = validate(bank)
        self.assertFalse(report.ok)
        self.assertTrue(any('duplicate fact_id' in e for e in report.errors))

    def test_broken_skill_fact_reference_fails(self):
        bank = make_bank()
        bank['skills'][0]['evidence_fact_ids'] = ['does_not_exist']
        report = validate(bank)
        self.assertFalse(report.ok)
        self.assertTrue(any('unresolved fact_id' in e for e in report.errors))

    def test_invalid_slug_fails(self):
        bank = make_bank()
        bank['entries'][0]['facts'][0]['fact_id'] = 'Bad Fact ID'
        report = validate(bank)
        self.assertFalse(report.ok)
        self.assertTrue(any('not a valid snake_case slug' in e for e in report.errors))

    def test_invalid_evidence_strength_fails(self):
        bank = make_bank()
        bank['entries'][0]['facts'][0]['evidence_strength'] = 7
        report = validate(bank)
        self.assertFalse(report.ok)
        self.assertTrue(any('outside 1..5' in e for e in report.errors))

    def test_duplicate_competency_tag_fails(self):
        bank = make_bank()
        bank['entries'][0]['facts'][0]['competency_tags'] = ['ai_llm', 'ai_llm']
        report = validate(bank)
        self.assertFalse(report.ok)
        self.assertTrue(any('duplicate tag' in e for e in report.errors))

    def test_metric_lacking_status_fails(self):
        bank = make_bank()
        del bank['metrics'][0]['status']
        report = validate(bank)
        self.assertFalse(report.ok)
        self.assertTrue(any('missing required key' in e and 'status' in e for e in report.errors))

    def test_locked_metric_malformed_fails(self):
        bank = make_bank()
        bank['metrics'][0]['locked'] = 'yes'
        report = validate(bank)
        self.assertFalse(report.ok)
        self.assertTrue(any('metrics[0].locked' in e and 'expected bool' in e for e in report.errors))

    def test_valid_siemens_entry_passes(self):
        bank = make_bank(
            entries=[{
                'entry_id': 'siemens_2026',
                'section': 'experience',
                'organization': 'Siemens Digital Industries Software',
                'location': 'Charlotte, NC',
                'title': 'Software Engineering and AI Intern',
                'dates': 'Summer 2026',
                'facts': [make_fact(
                    fact_id='siemens_ai_triage',
                    canonical_description='Built a chatbot for service-outage triage.',
                    competency_tags=['ai_llm', 'software_engineering'],
                    metrics=['test_metric'],
                )],
            }]
        )
        bank['skills'][0]['evidence_fact_ids'] = ['siemens_ai_triage']
        report = validate(bank)
        if not report.ok:
            self.fail(f'expected valid Siemens entry, got errors: {report.errors}')

    def test_valid_education_passes(self):
        bank = make_bank()
        del bank['entries'][0]['facts'][0]['metrics'][:]
        bank['skills'][0]['verified'] = False
        bank['skills'][0]['evidence_fact_ids'] = []
        report = validate(bank)
        if not report.ok:
            self.fail(f'expected valid education data, got errors: {report.errors}')

    def test_future_entry_with_realized_metric_fails(self):
        bank = make_bank()
        bank['entries'][0]['future'] = True
        report = validate(bank)
        self.assertFalse(report.ok)
        self.assertTrue(any('references realized metric' in e for e in report.errors))

    def test_tag_outside_vocabulary_fails(self):
        bank = make_bank()
        bank['entries'][0]['facts'][0]['competency_tags'] = ['synergy']
        report = validate(bank)
        self.assertFalse(report.ok)
        self.assertTrue(any('not in controlled competency vocabulary' in e for e in report.errors))

    def test_verified_skill_without_evidence_fails(self):
        bank = make_bank()
        bank['skills'][0]['evidence_fact_ids'] = []
        bank['skills'][0]['education_evidence_ids'] = []
        report = validate(bank)
        self.assertFalse(report.ok)
        self.assertTrue(any('verified skill has no evidence references' in e for e in report.errors))

    def test_real_evidence_bank_validates(self):
        path = REPO_ROOT / 'candidate_evidence.json'
        if not path.is_file():
            self.skipTest('candidate_evidence.json not present')
        data = json.loads(path.read_text(encoding='utf-8'))
        report = validate(data)
        if not report.ok:
            self.fail(f'real evidence bank should validate, got errors: {report.errors[:5]}')


if __name__ == '__main__':
    unittest.main()