"""Tests for the deterministic evidence matcher.

Covers the Phase-3 contracts:
  - fixture JD maps must pass jd_validator.validate against their prose files
  - role-sensitive fact reordering (SWE vs consulting vs ops)
  - unsupported-skill invariants (unverified -> unsupported, missing -> not_in_bank)
  - evidence status preservation (identified $6M is never flattened to realized)
  - the behavioral cap (<= 20% of a fact's final score)
  - determinism (same inputs -> byte-identical output)
  - a checked-in golden file for the data-analytics JD

Run from the repo root:

    python3.12 -m unittest discover -s tests
"""

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jd_validator  # noqa: E402
from evidence_matcher import (  # noqa: E402
    DEFAULT_CONFIG, DEFAULT_EVIDENCE, DEFAULT_RELATIONSHIPS, load_json, match,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / 'tests' / 'fixtures'

_CFG = load_json(DEFAULT_CONFIG)
_RELS = load_json(DEFAULT_RELATIONSHIPS)
_EVIDENCE = load_json(DEFAULT_EVIDENCE)


def load_fixture(name):
    return (load_json(FIXTURES / f'jd_{name}.json'),
            (FIXTURES / f'jd_{name}.txt').read_text(encoding='utf-8'))


def run(name, evidence=None):
    c_map, _ = load_fixture(name)
    return match(c_map, evidence if evidence is not None else _EVIDENCE,
                 _CFG, _RELS)


class TestJdFixturesValidate(unittest.TestCase):
    def test_all_fixtures_pass_jd_validator(self):
        for p in sorted(FIXTURES.glob('jd_*.json')):
            text = p.with_suffix('.txt').read_text(encoding='utf-8')
            data = json.loads(p.read_text(encoding='utf-8'))
            result = jd_validator.validate(text, data)
            if not result.ok:
                self.fail(f'{p.name} failed jd_validator: {result.errors[:5]}')


class TestRoleSensitiveOrdering(unittest.TestCase):
    def test_swe_orders_ai_facts_top(self):
        out = run('software_engineering')
        by_id = {f['fact_id']: f for f in out['fact_scores']}
        self.assertGreater(by_id['siemens_ai_triage']['total_score'],
                           by_id['mock_trial_rag']['total_score'])
        self.assertGreater(by_id['mock_trial_rag']['total_score'],
                           by_id['siemens_sdk_validation']['total_score'])
        self.assertGreater(by_id['siemens_ai_triage']['total_score'],
                           by_id['jlf_data_pipelines']['total_score'])
        self.assertIn(by_id['pubpol_priority_evaluation']['bucket'], ('weak', 'none'))

    def test_econ_orders_financial_facts_top(self):
        out = run('economic_consulting')
        by_id = {f['fact_id']: f for f in out['fact_scores']}
        self.assertGreater(by_id['siemens_savings_analysis']['total_score'],
                           by_id['siemens_allocation_model']['total_score'])
        self.assertGreater(by_id['siemens_allocation_model']['total_score'],
                           by_id['pubpol_priority_evaluation']['total_score'])
        self.assertEqual(by_id['siemens_savings_analysis']['bucket'], 'strong')

    def test_ops_rewards_process_and_budget(self):
        out = run('operations_strategy')
        by_id = {f['fact_id']: f for f in out['fact_scores']}
        self.assertGreater(by_id['siemens_backlog_reduction']['total_score'],
                           by_id['siemens_ai_triage']['total_score'])
        self.assertGreater(by_id['mock_trial_budget']['total_score'],
                           by_id['mock_trial_rag']['total_score'])

    def test_material_reorder_between_roles(self):
        swe = run('software_engineering')
        econ = run('economic_consulting')
        rank_swe = [f['fact_id'] for f in swe['fact_scores']].index('siemens_ai_triage')
        rank_econ = [f['fact_id'] for f in econ['fact_scores']].index('siemens_ai_triage')
        self.assertLess(rank_swe, rank_econ)


class TestSkillIntersection(unittest.TestCase):
    def test_unverified_skill_becomes_unsupported(self):
        out = run('data_analytics')
        rows = {s['canonical_term']: s for s in out['skill_matches']}
        self.assertEqual(rows['SQL']['status'], 'unsupported')
        self.assertEqual(rows['SQL']['verified'], False)
        self.assertEqual(rows['Tableau']['status'], 'not_in_bank')
        self.assertEqual(rows['Python']['status'], 'supported')

    def test_summary_tracks_supported_and_unsupported(self):
        out = run('data_analytics')
        self.assertIn('Python', out['summary']['verified_requested_skills'])
        for term in ('SQL', 'Excel', 'Tableau'):
            self.assertIn(term, out['summary']['unsupported_requested_skills'])

    def test_vacuous_skills_preserved_as_tracked_only(self):
        out = run('software_engineering')
        rows = {s['canonical_term']: s for s in out['skill_matches']}
        self.assertEqual(rows['Kubernetes']['status'], 'not_in_bank')
        self.assertEqual(rows['Git']['status'], 'unsupported')


class TestEvidenceStatusPreservation(unittest.TestCase):
    def test_evidence_bank_is_never_mutated(self):
        snapshot = copy.deepcopy(_EVIDENCE)
        run('economic_consulting')
        self.assertEqual(_EVIDENCE, snapshot)

    def test_identified_metric_not_flattened(self):
        out = run('economic_consulting')
        by_id = {f['fact_id']: f for f in out['fact_scores']}
        savings = by_id['siemens_savings_analysis']
        statuses = {m['metric_id']: m['status'] for m in savings['metrics']}
        self.assertEqual(statuses['siemens_savings'], 'identified')
        expected = round(0.2 * 0.5, 4)  # metric_bonus * identified factor
        self.assertEqual(savings['score_components']['metric'], expected)


class TestBehavioralCap(unittest.TestCase):
    def test_behavioral_share_never_exceeds_20_percent(self):
        out = run('operations_strategy')
        for fr in out['fact_scores']:
            share = fr['score_components']['behavioral']
            if share > 0.0:
                self.assertLessEqual(share, fr['total_score'] * 0.2 + 1e-9,
                                     f'{fr["fact_id"]} breached behavioral cap')


class TestUncovered(unittest.TestCase):
    def test_regulatory_analysis_is_high_priority_uncovered(self):
        out = run('economic_consulting')
        ids = {c['competency_id']: c for c in out['competency_coverage']}
        self.assertEqual(ids['regulatory_analysis']['status'], 'uncovered')
        self.assertIn('regulatory_analysis',
                      out['summary']['high_priority_uncovered_competencies'])
        uncov = {u['competency_id'] for u in out['uncovered']}
        self.assertIn('regulatory_analysis', uncov)


class TestRedundancy(unittest.TestCase):
    def test_overlapping_swe_facts_reported(self):
        out = run('software_engineering')
        ids = {f['fact_id']: f for f in out['fact_scores']}
        self.assertIn('siemens_ai_triage', ids)
        names = [p['fact_a'] for p in out['redundancy']['pairs']]
        names += [p['fact_b'] for p in out['redundancy']['pairs']]
        self.assertIn('siemens_ai_triage', names)

    def test_signature_is_stable_hash(self):
        out = run('data_analytics')
        self.assertEqual(len(out['redundancy']['signature']), 64)


class TestDeterminism(unittest.TestCase):
    def test_same_inputs_produce_byte_identical_output(self):
        c_map, _ = load_fixture('data_analytics')
        first = match(copy.deepcopy(c_map), copy.deepcopy(_EVIDENCE), _CFG, _RELS)
        second = match(copy.deepcopy(c_map), copy.deepcopy(_EVIDENCE), _CFG, _RELS)
        self.assertEqual(first, second)
        dump = lambda d: json.dumps(d, indent=2, sort_keys=True)
        self.assertEqual(dump(first), dump(second))

    def test_input_hash_present(self):
        out = run('data_analytics')
        self.assertEqual(len(out['determinism']['input_hash']), 64)


class TestGolden(unittest.TestCase):
    def test_golden_data_analytics_output(self):
        golden = FIXTURES / 'golden_data_analytics.json'
        if not golden.is_file():
            self.skipTest('golden file not present')
        expected = json.loads(golden.read_text(encoding='utf-8'))
        out = run('data_analytics')
        self.assertEqual(out, expected)


if __name__ == '__main__':
    unittest.main()