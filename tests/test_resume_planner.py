"""Tests for the deterministic resume planner.

Covers the Phase-4 contracts:
  - a fixture JD map must first pass the matcher, then the planner
  - deterministic, re-entrant output (same inputs -> byte-identical plan)
  - provenance hashes (evidence, match, config, plan) are present and stable
  - per-role coverage: the target strong competencies are reached for each of
    the four fixture roles, and no high-priority supported competency is
    silently omitted
  - section/bullet budgets are respected (experience <= 6, leadership <= 5,
    per-entry caps)
  - bullet slots carry primary/secondary competency IDs, target terms, and a
    full marginal-score decomposition
  - skills: verified tools are selected, unsupported requested skills excluded
  - exclusions carry a valid reason enum and match the summary counters
  - evidence bank is never mutated; identified metric statuses survive
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

from evidence_matcher import (  # noqa: E402
    DEFAULT_CONFIG as MATCHER_CONFIG, DEFAULT_EVIDENCE, DEFAULT_RELATIONSHIPS,
    load_json, match,
)
from resume_planner import DEFAULT_CONFIG as PLANNER_CONFIG, plan  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / 'tests' / 'fixtures'

_EVIDENCE = load_json(DEFAULT_EVIDENCE)
_PLANNER_CFG = load_json(PLANNER_CONFIG)
_MATCHER_CFG = load_json(MATCHER_CONFIG)
_RELS = load_json(DEFAULT_RELATIONSHIPS)

REASONS = {
    'ENTRY_NOT_SELECTED', 'REDUNDANT', 'SPACE_CONSTRAINT', 'LOW_RELEVANCE',
    'WEAKER_ALTERNATIVE', 'UNSUPPORTED_FOR_ROLE', 'FUTURE_FACT_RESTRICTION',
}
SLOT_COMPONENTS = {
    'new_competency_coverage', 'skill_support', 'evidence_quality',
    'metric_bonus', 'differentiation', 'redundancy_penalty', 'section_prior',
}


def load_competency_map(name):
    return load_json(FIXTURES / f'jd_{name}.json')


def run(name, evidence=None):
    c_map = load_competency_map(name)
    m = match(c_map, evidence if evidence is not None else _EVIDENCE,
              _MATCHER_CFG, _RELS)
    return plan(evidence if evidence is not None else _EVIDENCE, m,
                _PLANNER_CFG)


def entries(plan_out):
    return plan_out['experience'] + plan_out['leadership']


def all_bullets(plan_out):
    return [s for e in entries(plan_out) for s in e['bullet_slots']]


class TestPlannerTopLevelShape(unittest.TestCase):
    def test_plan_has_schema_and_provenance(self):
        out = run('software_engineering')
        self.assertEqual(out['schema_version'], '1.0')
        self.assertEqual(set(out.keys()),
                         {'schema_version', 'generated_for', 'summary',
                          'education', 'experience', 'leadership',
                          'additional', 'skills', 'coverage',
                          'excluded_evidence', 'supporting_facts',
                          'warnings', 'provenance'})

    def test_generated_for_mirrors_match(self):
        out = run('software_engineering')
        gf = out['generated_for']
        self.assertIn('company', gf)
        self.assertIn('title', gf)
        self.assertIn('program_term', gf)
        self.assertEqual(gf['competency_map_schema_version'], '1.1')

    def test_provenance_hashes_are_64_hex(self):
        out = run('data_analytics')
        prov = out['provenance']
        for key in ('candidate_evidence_hash', 'evidence_match_hash',
                    'planner_config_hash', 'plan_hash'):
            self.assertEqual(len(prov[key]), 64, key)
        self.assertEqual(prov['planner_version'], _PLANNER_CFG['planner_version'])

    def test_evidence_bank_is_never_mutated(self):
        snapshot = copy.deepcopy(_EVIDENCE)
        run('economic_consulting')
        self.assertEqual(_EVIDENCE, snapshot)


class TestRoleCoverage(unittest.TestCase):
    def test_analytics_reaches_target_strong_set(self):
        out = run('data_analytics')
        self.assertEqual(
            set(out['summary']['competencies_covered_strong']),
            {'data_analysis', 'data_cleaning', 'data_visualization',
             'sql_querying', 'presenting_to_stakeholders',
             'financial_reporting'})

    def test_econ_reaches_target_strong_set(self):
        out = run('economic_consulting')
        self.assertEqual(
            set(out['summary']['competencies_covered_strong']),
            {'quantitative_analysis', 'financial_modeling',
             'document_synthesis', 'expert_presentations',
             'economic_research'})

    def test_sweng_reaches_target_strong_set(self):
        out = run('software_engineering')
        self.assertEqual(
            set(out['summary']['competencies_covered_strong']),
            {'software_engineering', 'ai_llm', 'testing',
             'cross_platform_debugging', 'requirements_validation'})

    def test_ops_reaches_target_strong_set(self):
        out = run('operations_strategy')
        self.assertEqual(
            set(out['summary']['competencies_covered_strong']),
            {'process_improvement', 'data_analysis', 'budget_management',
             'strategic_recommendations', 'stakeholder_management'})

    def test_no_high_priority_supported_competency_omitted(self):
        for role in ('data_analytics', 'economic_consulting',
                     'software_engineering', 'operations_strategy'):
            out = run(role)
            self.assertEqual(
                out['summary']['high_priority_supported_omitted'], [], role)
            for row in out['coverage']['competencies']:
                if row['weight'] >= 0.4 and row['candidate_level'] == 'strong':
                    self.assertNotEqual(row['selected_level'], 'none', row)
                    self.assertEqual(row['gap'], 'none', row)

    def test_selected_buckets_match_summary(self):
        out = run('economic_consulting')
        self.assertEqual(
            set(out['coverage']['selected']['strong']),
            set(out['summary']['competencies_covered_strong']))
        self.assertEqual(
            set(out['coverage']['selected']['moderate']),
            set(out['summary']['competencies_covered_moderate']))

    def test_coverage_guard_present(self):
        out = run('data_analytics')
        guard = out['coverage']['_guard']
        self.assertIn('min_weight', guard)
        self.assertIn('candidate_min_level', guard)
        self.assertIn('max_acceptable_selected_level', guard)
        for c in out['coverage']['competencies']:
            self.assertIn(c['gap'], {'unsupported', 'under_selected', 'none'})


class TestEntryAndBulletBudgets(unittest.TestCase):
    def test_section_budgets_respected(self):
        for role in ('data_analytics', 'economic_consulting',
                     'software_engineering', 'operations_strategy'):
            out = run(role)
            cfg = _PLANNER_CFG['sections']
            exp_total = sum(len(e['bullet_slots'])
                            for e in out['experience'])
            lead_total = sum(len(e['bullet_slots'])
                             for e in out['leadership'])
            self.assertLessEqual(len(out['experience']),
                                 cfg['experience']['max_entries'], role)
            self.assertLessEqual(len(out['leadership']),
                                 cfg['leadership']['max_entries'], role)
            self.assertLessEqual(exp_total,
                                 cfg['experience']['max_total_bullets'], role)
            self.assertLessEqual(lead_total,
                                 cfg['leadership']['max_total_bullets'], role)
            for sec_name, sec_out in (('experience', out['experience']),
                                      ('leadership', out['leadership'])):
                for e in sec_out:
                    cap = cfg[sec_name]['max_bullets_per_entry']
                    self.assertLessEqual(len(e['bullet_slots']), cap,
                                         (role, e['entry_id']))
                    self.assertGreaterEqual(len(e['bullet_slots']),
                                            cfg[sec_name]['min_bullets_per_entry'],
                                            (role, e['entry_id']))

    def test_entry_plan_required_keys(self):
        out = run('software_engineering')
        for e in entries(out):
            for key in ('entry_id', 'section', 'organization', 'location',
                        'title', 'dates', 'entry_status',
                        'aggregate_relevance', 'entry_score', 'bullet_slots'):
                self.assertIn(key, e, e['entry_id'])
            self.assertIn(e['section'], ('experience', 'leadership'))
            self.assertIn(e['entry_status'], ('incoming', 'current', 'past'))

    def test_bullet_slots_sequential_and_well_formed(self):
        out = run('data_analytics')
        for e in entries(out):
            for idx, s in enumerate(e['bullet_slots'], start=1):
                self.assertEqual(s['priority'], idx)
                self.assertEqual(s['slot_id'], f"{e['entry_id']}#{idx}")
                self.assertEqual(s['primary_fact_id'], s['primary_fact_id'])
                self.assertIsInstance(s['primary_competency_ids'], list)
                self.assertLessEqual(
                    len(s['target_terms']),
                    _PLANNER_CFG['bullet']['max_target_terms'])
                self.assertGreaterEqual(s['marginal_score'], 0.0)
                self.assertEqual(set(s['components']), SLOT_COMPONENTS)
        # a fact is never used as a primary twice
        primaries = [s['primary_fact_id'] for s in all_bullets(out)]
        self.assertEqual(len(primaries), len(set(primaries)))


class TestSkills(unittest.TestCase):
    def test_selected_skills_are_verified(self):
        out = run('data_analytics')
        for s in out['skills']['selected_skills']:
            self.assertTrue(s['verified'], s['skill_id'])
            for key in ('skill_id', 'display_name', 'category', 'jd_level',
                        'evidence_count', 'selected_fact_support', 'score',
                        'rationale'):
                self.assertIn(key, s)

    def test_unsupported_requested_skills_excluded(self):
        cases = {
            'data_analytics': {'SQL', 'Excel', 'Tableau'},
            'economic_consulting': {'Excel'},
            'software_engineering': {'Git', 'Linux', 'C++', 'Kubernetes'},
            'operations_strategy': {'Excel', 'SQL'},
        }
        for role, expected in cases.items():
            out = run(role)
            got = {u['canonical_term']
                   for u in out['skills']['unsupported_requested']}
            self.assertEqual(got, expected, role)
            self.assertEqual(
                set(out['summary']['unsupported_skills_excluded']), expected,
                role)

    def test_skills_line_tracks_selected(self):
        out = run('software_engineering')
        selected = {s['skill_id'] for s in out['skills']['selected_skills']}
        self.assertEqual(set(out['additional']['skills_line_skill_ids']),
                         selected)


class TestExclusions(unittest.TestCase):
    def test_exclusion_reasons_are_valid_enum(self):
        out = run('operations_strategy')
        for x in out['excluded_evidence']:
            self.assertIn(x['reason'], REASONS, x['fact_id'])
            self.assertIsInstance(x['explanation'], str)

    def test_redundant_rejected_matches_exclusions(self):
        out = run('economic_consulting')
        redundant = [x['fact_id'] for x in out['excluded_evidence']
                     if x['reason'] == 'REDUNDANT']
        self.assertEqual(
            set(out['summary']['redundant_facts_rejected']), set(redundant))

    def test_selected_facts_never_excluded(self):
        out = run('data_analytics')
        selected = {s['primary_fact_id'] for s in all_bullets(out)}
        excluded = {x['fact_id'] for x in out['excluded_evidence']}
        for supporting in out['supporting_facts']:
            selected.add(supporting['fact_id'])
        self.assertTrue(selected.isdisjoint(excluded))


class TestSupportingFacts(unittest.TestCase):
    def test_recognition_pair_is_consistent(self):
        for role in ('data_analytics', 'economic_consulting',
                     'software_engineering', 'operations_strategy'):
            out = run(role)
            selected = {s['primary_fact_id'] for s in all_bullets(out)}
            for sf in out['supporting_facts']:
                self.assertEqual(sf['relation'], 'recognition')
                self.assertIn(sf['entry_id'],
                              out['summary']['selected_experience_entries']
                              + out['summary']['selected_leadership_entries'])
                self.assertIn(sf['primary_fact_id'], selected)
                self.assertNotIn(sf['fact_id'], selected)


class TestDeterminism(unittest.TestCase):
    def test_same_inputs_produce_byte_identical_plan(self):
        c_map = load_competency_map('data_analytics')
        ev = copy.deepcopy(_EVIDENCE)
        m = match(copy.deepcopy(c_map), ev, _MATCHER_CFG, _RELS)
        first = plan(ev, m, _PLANNER_CFG)
        second = plan(ev, m, _PLANNER_CFG)
        self.assertEqual(first, second)
        dump = lambda d: json.dumps(d, indent=2, sort_keys=True)
        self.assertEqual(dump(first), dump(second))

    def test_re_entrant_plan_calls_are_stable(self):
        m = match(load_competency_map('software_engineering'), _EVIDENCE,
                  _MATCHER_CFG, _RELS)
        plans = [plan(_EVIDENCE, m, _PLANNER_CFG) for _ in range(2)]
        self.assertEqual(plans[0], plans[1])
        self.assertEqual(plans[0]['provenance']['plan_hash'],
                         plans[1]['provenance']['plan_hash'])

    def test_evidence_match_hash_follows_match_object(self):
        m = match(load_competency_map('data_analytics'), _EVIDENCE,
                  _MATCHER_CFG, _RELS)
        out = plan(_EVIDENCE, m, _PLANNER_CFG)
        self.assertEqual(out['provenance']['evidence_match_hash'],
                         m['determinism']['input_hash'])


class TestGolden(unittest.TestCase):
    def test_golden_plan_data_analytics_output(self):
        golden = FIXTURES / 'golden_plan_data_analytics.json'
        if not golden.is_file():
            self.skipTest('golden file not present')
        expected = json.loads(golden.read_text(encoding='utf-8'))
        out = run('data_analytics')
        self.assertEqual(out, expected)


if __name__ == '__main__':
    unittest.main()