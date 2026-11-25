"""Deterministic resume planner: evidence_match + candidate evidence -> plan IR.

Consumes the Phase-3 evidence match object (validated shape from
evidence_match_schema.json) and the Phase-2 canonical candidate evidence bank
(candidate_evidence.json) and produces a deterministic resume plan IR:

  - entry selection (separate from fact selection) with a decomposed score
    (top/second/third facts + quality + role-family + unique-coverage bonuses)
  - greedy marginal fact selection per section budget (min-bullet allocation,
    remaining-slot optimization, then a local same-entry swap-improvement pass)
    where the marginal score is fully decomposed and reproducible
  - bullet slots with a primary fact, optional supporting facts (recognition),
    primary/secondary target competencies, target terms, and targeted metrics
  - verified-only skill ranking (requested-supported above differentiators),
    never surfacing unsupported requested skills into selected_skills
  - education planning (locked details always selected; optional details only
    when the JD calls for them; coursework tagged against JD competencies)
  - coverage analysis with coverage-loss and a high-weight guard, exclusions
    with reason codes, warnings, and provenance (input/config hashes)

Philosophy (mirrors evidence_matcher.py / jd_validator.py):

  - No LLM, no Supabase, no renderer JSON, no PDF.
  - All weights, budgets, and tie-breaks come from planner_config.json.
  - Facts and metrics are never mutated; identified/potential statuses survive.
  - Same inputs MUST produce a byte-identical plan. No timestamps, no randomness.
  - The planned "future" (incoming) internship is represented via
    entry_status/fact_status; planned facts cannot displace completed facts
    solely because of recency.

Usage:

    python3.12 resume_planner.py \
        --matches /tmp/data_match.json \
        --evidence candidate_evidence.json \
        --config planner_config.json \
        --output /tmp/data_plan.json
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_EVIDENCE = REPO_ROOT / 'candidate_evidence.json'
DEFAULT_CONFIG = REPO_ROOT / 'planner_config.json'

_MATCH_REQUIRED = [
    'schema_version', 'generated_for', 'summary', 'fact_scores', 'skill_matches',
    'competency_coverage', 'behavioral_coverage', 'hard_qualifications',
    'uncovered', 'redundancy', 'determinism',
]


def load_json(path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'))


def _hash(obj) -> str:
    return hashlib.sha256(_canonical_json(obj).encode('utf-8')).hexdigest()


def _dedupe_preserve(seq):
    seen = set()
    out = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


class _Ledger:
    """State of selected facts: coverage, skills, domains, metrics, entry counts."""

    def __init__(self, planner):
        self.p = planner
        self.selected_facts = []
        self.selected_set = set()
        self.entry_primary = {}
        self.comp_best = {}
        self.comp_strong_count = {}
        self.skill_covered = set()
        self.domains_seen = set()
        self.metrics_seen = set()

    def _apply(self, fid):
        fr = self.p.fact_scores[fid]
        strong_th = self.p.coverage_level_thresholds['strong']
        for mc in fr.get('matched_competencies') or []:
            cid = mc['competency_id']
            coeff = mc['match_coefficient']
            if coeff <= 0.0:
                continue
            prev = self.comp_best.get(cid, 0.0)
            if coeff > prev:
                self.comp_best[cid] = coeff
            if coeff >= strong_th:
                self.comp_strong_count[cid] = self.comp_strong_count.get(cid, 0) + 1
        eid = self.p.fact_entry[fid]
        self.entry_primary.setdefault(eid, []).append(fid)
        for ms in fr.get('matched_skills') or []:
            if ms.get('skill_id'):
                self.skill_covered.add(ms['skill_id'])
        fact = self.p.facts_by_id[fid]
        self.domains_seen.update(fact.get('domain_tags') or [])
        for m in fr.get('metrics') or []:
            self.metrics_seen.add(m.get('metric_id'))

    def _rebuild(self):
        self.entry_primary = {}
        self.comp_best = {}
        self.comp_strong_count = {}
        self.skill_covered = set()
        self.domains_seen = set()
        self.metrics_seen = set()
        for fid in self.selected_facts:
            self._apply(fid)

    def add(self, fid):
        if fid in self.selected_set:
            return
        self.selected_set.add(fid)
        self.selected_facts.append(fid)
        self._apply(fid)

    def remove(self, fid):
        self.selected_set.discard(fid)
        self.selected_facts = [x for x in self.selected_facts if x != fid]
        self._rebuild()

    def comp_level(self, cid):
        coeff = self.comp_best.get(cid, 0.0)
        strong_th = self.p.coverage_level_thresholds['strong']
        if coeff >= strong_th:
            if self.comp_strong_count.get(cid, 0) >= 2:
                return 'saturated'
            return 'strong'
        moderate_th = self.p.coverage_level_thresholds['moderate']
        if coeff >= moderate_th:
            return 'moderate'
        if coeff > 0.0:
            return 'weak'
        return 'none'

    def count_for_entry(self, eid):
        return len(self.entry_primary.get(eid, []))

    def coverage_for_competency(self, cid):
        """Final (selected) coverage level restricted to plain levels."""
        lvl = self.comp_level(cid)
        return 'strong' if lvl == 'saturated' else lvl


class ResumePlanner:
    def __init__(self, evidence: dict, match_obj: dict, cfg: dict):
        for key in _MATCH_REQUIRED:
            if key not in match_obj:
                raise ValueError(f'evidence match missing required key {key!r}')
        self.evidence = evidence
        self.match_obj = match_obj
        self.cfg = cfg
        self.precision = int(cfg['decimal_precision'])
        self.level_rank = {'none': 0, 'weak': 1, 'moderate': 2, 'strong': 3,
                           'saturated': 4}
        for key in ('none', 'weak', 'moderate', 'strong', 'saturated'):
            if key not in cfg['marginal_selection']['coverage_saturation']:
                raise ValueError(f'planner_config missing saturation level {key!r}')
        self.coverage_saturation = cfg['marginal_selection']['coverage_saturation']
        cov_th = cfg['marginal_selection']['coverage_level_thresholds']
        for key in ('strong', 'moderate', 'weak'):
            if key not in cov_th:
                raise ValueError(f'planner_config missing coverage threshold {key!r}')
        self.coverage_level_thresholds = cov_th
        self.tier1_level_factors = cfg['tier1_level_factors']
        self.metric_status_factors = cfg['metric_status_factors']
        self.sections_cfg = cfg['sections']
        self.entry_scoring_cfg = cfg['entry_scoring']
        self.marg_cfg = cfg['marginal_selection']
        self.future_tie = cfg['future_fact']['tie_priority']
        self.tiebreak = cfg['tiebreak']

        self._build_indexes()

    # ------------------------------------------------------------------ index
    def _build_indexes(self):
        self.skills = {s.get('skill_id'): s for s in (self.evidence.get('skills') or [])}
        self.facts_by_id = {}
        self.fact_entry = {}
        self.entry_fact_ids = {}
        self.entries = {}
        for entry in self.evidence.get('entries') or []:
            eid = entry.get('entry_id')
            self.entries[eid] = entry
            self.entry_fact_ids.setdefault(eid, [])
            for fact in entry.get('facts') or []:
                fid = fact.get('fact_id')
                if fid in self.facts_by_id:
                    raise ValueError(f'duplicate fact_id in evidence bank: {fid!r}')
                self.facts_by_id[fid] = fact
                self.fact_entry[fid] = eid
                self.entry_fact_ids[eid].append(fid)

        self.fact_scores = {}
        for fr in self.match_obj.get('fact_scores') or []:
            self.fact_scores[fr['fact_id']] = fr

        self.comp_rows = {}
        for row in self.match_obj.get('competency_coverage') or []:
            self.comp_rows[row['competency_id']] = row

        self.pair_jaccard = {}
        for pair in (self.match_obj.get('redundancy') or {}).get('pairs') or []:
            a, b = pair['fact_a'], pair['fact_b']
            key = (a, b) if a < b else (b, a)
            self.pair_jaccard[key] = pair['jaccard']

        self.skill_matches_rows = self.match_obj.get('skill_matches') or []
        self.entry_status = {}
        self.fact_status = {}
        for entry in (self.evidence.get('entries') or []):
            eid = entry.get('entry_id')
            es = entry.get('entry_status')
            if not es:
                if entry.get('future') is True:
                    es = 'incoming'
                elif 'present' in (entry.get('dates') or '').casefold():
                    es = 'current'
                else:
                    es = 'past'
            self.entry_status[eid] = es
            default_fact = {'incoming': 'planned', 'current': 'in_progress',
                            'past': 'completed'}[es]
            for fact in entry.get('facts') or []:
                fs = fact.get('fact_status') or default_fact
                self.fact_status[fact['fact_id']] = fs

    # ------------------------------------------------------------- helpers
    def _is_recognition(self, fid):
        fact = self.facts_by_id[fid]
        text = fact.get('canonical_description') or ''
        actions = {str(a).casefold() for a in (fact.get('actions') or [])}
        return bool('award' in text.casefold() or actions & {'won', 'winner'})

    def _penalty_for(self, jac):
        red = self.marg_cfg['redundancy_penalties']
        if jac >= red['strong']['min_jaccard']:
            return red['strong']['penalty']
        if jac >= red['moderate']['min_jaccard']:
            return red['moderate']['penalty']
        return 0.0

    def _status_priority(self, fid):
        fs = self.fact_status.get(fid, 'in_progress')
        try:
            return self.future_tie.index(fs)
        except ValueError:
            return len(self.future_tie)

    def _tie_key(self, fid):
        fr = self.fact_scores.get(fid, {})
        fact = self.facts_by_id.get(fid, {})
        keys = {
            'marginal_score': lambda: self._last_marginal.get(fid, 0.0),
            'phase3_score': lambda: fr.get('total_score', 0.0),
            'fact_status': lambda: self._status_priority(fid),
            'evidence_strength': lambda: int(fact.get('evidence_strength') or 0),
            'quantified': lambda: int(bool(fr.get('metrics'))),
            'fact_id': lambda: fid,
        }
        descending = {
            'marginal_score', 'phase3_score', 'evidence_strength', 'quantified',
        }
        parts = []
        for k in self.tiebreak:
            if k not in keys:
                continue
            val = keys[k]()
            if k in descending and isinstance(val, (int, float)) \
                    and not isinstance(val, bool):
                val = -val
            parts.append(val)
        return parts

    def _best_fact(self, candidates, ledger):
        best = None
        best_key = None
        self._last_marginal = {}
        for fid in candidates:
            if fid in ledger.selected_set:
                continue
            score, _ = self.marginal(ledger, fid)
            self._last_marginal[fid] = score
        for fid in candidates:
            if fid in ledger.selected_set:
                continue
            fr = self.fact_scores.get(fid, {})
            score = self._last_marginal.get(fid, 0.0)
            if score <= float(self.marg_cfg['min_positive_marginal']):
                continue
            key = self._tie_key(fid)
            if best is None or key < best_key:
                best, best_key = fid, key
            elif key == best_key:
                best = min(best, fid, key=lambda x: x)
        return best

    # ----------------------------------------------------------- marginaling
    def marginal(self, ledger, fid):
        """Full decomposed marginal utility of adding `fid` to `ledger` (no mutation)."""
        w = self.marg_cfg['weights']
        sat = self.coverage_saturation
        strong_th = self.coverage_level_thresholds['strong']
        moderate_th = self.coverage_level_thresholds['moderate']
        fr = self.fact_scores[fid]
        fact = self.facts_by_id[fid]

        cov = 0.0
        for mc in fr.get('matched_competencies') or []:
            cid = mc['competency_id']
            coeff = mc['match_coefficient']
            if coeff <= 0.0:
                continue
            before = ledger.comp_level(cid)
            before_val = sat[before]
            if coeff >= strong_th:
                cnt = ledger.comp_strong_count.get(cid, 0) + 1
                after = 'saturated' if cnt >= 2 else 'strong'
            elif coeff >= moderate_th:
                after = 'moderate'
            elif coeff > 0.0:
                after = 'weak'
            else:
                after = 'none'
            after_rank = self.level_rank[after]
            before_rank = self.level_rank[before]
            if after_rank <= before_rank:
                continue
            gain = sat[after] - before_val
            if gain > 0.0:
                cov += gain * mc.get('weight', 0.0)
        cov = round(cov * w['competency_coverage'], self.precision)

        skill = 0.0
        for ms in fr.get('matched_skills') or []:
            sid = ms.get('skill_id')
            if sid and sid not in ledger.skill_covered:
                factor = self.tier1_level_factors.get(ms.get('level'), 0.0)
                skill += w['skill_coverage'] * factor
        skill = round(skill, self.precision)

        strength = int(fact.get('evidence_strength') or 0)
        eq = round(w['evidence_quality'] * (strength / float(self.cfg['evidence_strength_max'])),
                   self.precision)

        metric = 0.0
        for m in fr.get('metrics') or []:
            factor = self.metric_status_factors.get(m.get('status'), 0.0)
            metric = max(metric, w['metric'] * factor)
        metric = round(metric, self.precision)

        diff_cfg = self.marg_cfg['differentiation']
        new_domains = [d for d in (fact.get('domain_tags') or [])
                       if d not in ledger.domains_seen]
        diff = diff_cfg['distinct_domain_bonus'] * len(new_domains)
        if any(m.get('metric_id') not in ledger.metrics_seen for m in fr.get('metrics') or []):
            diff += diff_cfg['distinct_metric_bonus']
        diff = round(diff * w['differentiation'], self.precision)

        pen = 0.0
        for other in ledger.selected_facts:
            a, b = (fid, other) if fid < other else (other, fid)
            jac = self.pair_jaccard.get((a, b), 0.0)
            if jac > 0.0:
                pen += self._penalty_for(jac)
        pen = round(pen, self.precision)

        eid = self.fact_entry[fid]
        prior = self.sections_cfg[self.entries[eid]['section']]['prior']
        subtotal = cov + skill + eq + metric + diff - pen
        score = round(prior * subtotal, self.precision)
        components = {
            'new_competency_coverage': cov,
            'skill_support': skill,
            'evidence_quality': eq,
            'metric_bonus': metric,
            'differentiation': diff,
            'redundancy_penalty': -pen,
            'section_prior': prior,
        }
        return score, components

    # ---------------------------------------------------------- entry scores
    def _unique_strong_entries(self):
        strong_th = self.entry_scoring_cfg['strong_coefficient']
        out = {}
        for cid in self.comp_rows:
            strong_entries = set()
            for eid, ids in self.entry_fact_ids.items():
                for fid in ids:
                    for mc in self.fact_scores.get(fid, {}).get('matched_competencies') or []:
                        if (mc['competency_id'] == cid
                                and mc['match_coefficient'] >= strong_th):
                            strong_entries.add(eid)
                            break
                    if len(strong_entries) > 1:
                        break
                if len(strong_entries) > 1:
                    break
            out[cid] = strong_entries
        return out

    def entry_score(self, eid, unique_strong):
        es = self.entry_scoring_cfg
        frs = sorted((self.fact_scores[fid] for fid in self.entry_fact_ids[eid]),
                     key=lambda f: -f['total_score'])
        vals = [f['total_score'] for f in frs[:3]]
        top = vals[0] if vals else 0.0
        second = vals[1] if len(vals) > 1 else 0.0
        third = vals[2] if len(vals) > 2 else 0.0

        n_q = sum(1 for f in frs if f.get('metrics'))
        quality = es['quality_bonus_per_quantified_fact'] * min(
            n_q, es['quality_bonus_quantified_cap'])
        if any(self._is_recognition(fid) for fid in self.entry_fact_ids[eid]):
            quality += es['award_bonus']

        high_min = es['high_priority_min_weight']
        strong_th = es['strong_coefficient']
        strong_comps = set()
        for fid in self.entry_fact_ids[eid]:
            for mc in self.fact_scores.get(fid, {}).get('matched_competencies') or []:
                if (mc['weight'] >= high_min
                        and mc['match_coefficient'] >= strong_th):
                    strong_comps.add(mc['competency_id'])
        role_family = es['role_family_bonus_per_high_priority'] * len(strong_comps)

        unique = 0
        for cid, entries in unique_strong.items():
            if entries == {eid}:
                best_fact = self.comp_rows[cid].get('best_fact_id')
                if best_fact in self.entry_fact_ids[eid]:
                    unique += 1
        unique = es['unique_coverage_bonus_per_competency'] * unique

        total = round(top + es['second_fact'] * second + es['third_fact'] * third
                      + quality + role_family + unique, self.precision)
        return {
            'top_fact': round(top, self.precision),
            'second_fact': round(second, self.precision),
            'third_fact': round(third, self.precision),
            'quality_bonus': round(quality, self.precision),
            'role_family_bonus': round(role_family, self.precision),
            'unique_coverage_bonus': round(unique, self.precision),
            'total': total,
        }

    # ---------------------------------------------------------------- select
    def run(self):
        unique_strong = self._unique_strong_entries()

        scores = {}
        for eid in self.entries:
            scores[eid] = self.entry_score(eid, unique_strong)

        chosen = {'experience': [], 'leadership': []}
        for section in ('experience', 'leadership'):
            sess_ids = [eid for eid, e in self.entries.items()
                        if e['section'] == section]
            sess_ids.sort(key=lambda eid: (
                -scores[eid]['total'],
                -scores[eid]['top_fact'],
                eid,
            ))
            min_score = float(self.entry_scoring_cfg['min_entry_score'])
            keep = [eid for eid in sess_ids
                    if scores[eid]['total'] >= min_score]
            keep = keep[:self.sections_cfg[section]['max_entries']]
            chosen[section] = keep

        ledger = _Ledger(self)
        dropped = set()

        # Phase A: minimum-bullet allocation per chosen entry.
        for section in ('experience', 'leadership'):
            minb = self.sections_cfg[section]['min_bullets_per_entry']
            for eid in chosen[section]:
                placed = 0
                while placed < minb:
                    pool = [fid for fid in self.entry_fact_ids[eid]
                            if fid not in ledger.selected_set]
                    best = self._best_fact(pool, ledger)
                    if best is None:
                        break
                    score, _ = self.marginal(ledger, best)
                    if score <= float(self.marg_cfg['min_positive_marginal']):
                        break
                    ledger.add(best)
                    placed += 1
                if placed == 0:
                    dropped.add(eid)

        # Phase B: remaining-slot optimization across both sections.
        while True:
            best_global = None
            best_key = None
            for section in ('experience', 'leadership'):
                sect = self.sections_cfg[section]
                total = sum(ledger.count_for_entry(eid) for eid in chosen[section])
                if total >= sect['max_total_bullets']:
                    continue
                for eid in chosen[section]:
                    if eid in dropped:
                        continue
                    if ledger.count_for_entry(eid) >= sect['max_bullets_per_entry']:
                        continue
                    pool = [fid for fid in self.entry_fact_ids[eid]
                            if fid not in ledger.selected_set]
                    cand = self._best_fact(pool, ledger)
                    if cand is None:
                        continue
                    key = self._tie_key(cand)
                    cand_pack = (cand, eid, section)
                    if best_global is None or key < best_key:
                        best_global, best_key = cand_pack, key
            if best_global is None:
                break
            ledger.add(best_global[0])

        # Phase C: local same-entry swap-improvement pass.
        for _ in range(int(self.marg_cfg['swap_passes'])):
            changed = False
            for fid in list(ledger.selected_facts):
                eid = self.fact_entry[fid]
                pool = [c for c in self.entry_fact_ids[eid]
                        if c not in ledger.selected_set and c != fid]
                if not pool:
                    continue
                ledger.remove(fid)
                score_f, _ = self.marginal(ledger, fid)
                best_c = self._best_fact(pool, ledger)
                if best_c is not None:
                    score_c, _ = self.marginal(ledger, best_c)
                else:
                    score_c = -1.0
                if score_c - score_f >= float(
                        self.marg_cfg['swap_min_improvement']):
                    ledger.add(best_c)
                    changed = True
                else:
                    ledger.add(fid)
            if not changed:
                break

        # Entries that never earned a primary bullet are dropped.
        final_entry_order = {'experience': [], 'leadership': []}
        for section in ('experience', 'leadership'):
            rows = []
            for eid in chosen[section]:
                if eid in dropped or ledger.count_for_entry(eid) == 0:
                    continue
                rows.append(eid)
            rows.sort(key=lambda eid: (-self._aggregate_relevance(eid, ledger), eid))
            final_entry_order[section] = rows

        return self._assemble(ledger, scores, final_entry_order, dropped)

    def _recognition_partner(self, fid, ledger):
        """Best same-entry selected fact to attach a recognition fact to."""
        eid = self.fact_entry[fid]
        tags = set(self.facts_by_id[fid].get('competency_tags') or [])
        best = None
        best_overlap = -1
        for other in ledger.entry_primary.get(eid, []):
            if other == fid:
                continue
            overlap = len(tags & set(self.facts_by_id[other].get('competency_tags') or []))
            if overlap > best_overlap or (
                    overlap == best_overlap and best is not None and other < best):
                best, best_overlap = other, overlap
        return best if best_overlap > 0 else None

    def _aggregate_relevance(self, eid, ledger):
        agg = 0.0
        for fid in ledger.entry_primary.get(eid, []):
            if self._is_recognition(fid) and self._recognition_partner(fid, ledger):
                continue
            agg += self._recompute_marginal(ledger, fid)[0]
        return round(agg, self.precision)

    def _recompute_marginal(self, ledger, fid):
        """Marginal contribution of `fid` against the final set minus itself."""
        score, components = self.marginal(ledger, fid)
        return score, components

    # -------------------------------------------------------------- assemble
    def _assemble(self, ledger, scores, final_entry_order, dropped):
        p = self
        precision = p.precision
        self.supporting_pairs = []

        experience = []
        leadership = []
        slot_count = 0
        for section in ('experience', 'leadership'):
            for eid in final_entry_order[section]:
                entry = self.entries[eid]
                primaries = [fid for fid in ledger.entry_primary.get(eid, [])
                             if not (self._is_recognition(fid)
                                     and self._recognition_partner(fid, ledger))]
                primaries.sort(key=lambda fid: self._bullet_order_key(
                    fid, primaries), reverse=True)
                slots = []
                supporting = []
                for pos, fid in enumerate(primaries, start=1):
                    partner = self._recognition_partner(fid, ledger)
                    if self._is_recognition(fid) and partner:
                        supporting.append((fid, partner))
                        continue
                    score, components = self._recompute_marginal(ledger, fid)
                    slots.append(self._build_slot(eid, fid, pos, score, components))
                for sup_fid, partner in supporting:
                    self.supporting_pairs.append({
                        'fact_id': sup_fid,
                        'primary_fact_id': partner,
                        'entry_id': eid,
                        'relation': 'recognition',
                    })
                slot_count += len(slots)
                entry_plan = {
                    'entry_id': eid,
                    'section': entry['section'],
                    'organization': entry.get('organization'),
                    'location': entry.get('location'),
                    'title': entry.get('title'),
                    'dates': entry.get('dates'),
                    'entry_status': self.entry_status[eid],
                    'aggregate_relevance': round(sum(
                        s['marginal_score'] for s in slots), precision),
                    'entry_score': scores[eid],
                    'bullet_slots': slots,
                }
                if section == 'experience':
                    experience.append(entry_plan)
                else:
                    leadership.append(entry_plan)

        education = self._build_education()
        skills_plan = self._build_skills(ledger)
        coverage = self._build_coverage(ledger)
        excluded, redundant_rejected = self._build_excluded(ledger, final_entry_order,
                                                            dropped)
        warnings = self._build_warnings(coverage, excluded)
        additional = {
            'budget_lines': int(self.cfg['additional']['max_lines']),
            'skills_line_skill_ids': [s['skill_id'] for s in skills_plan['selected_skills']],
            'coursework_line_competency_ids': _dedupe_preserve(
                tag for edu in education for tag in edu['selected_coursework_tags']),
        }
        summary = {
            'selected_experience_entries': [e['entry_id'] for e in experience],
            'selected_leadership_entries': [e['entry_id'] for e in leadership],
            'bullet_slots': slot_count,
            'competencies_covered_strong': coverage['selected']['strong'],
            'competencies_covered_moderate': coverage['selected']['moderate'],
            'high_priority_supported_omitted': [
                c['competency_id'] for c in coverage['competencies']
                if c['gap'] == 'under_selected'
                and c['target_level'] == 'strong'
            ],
            'unsupported_skills_excluded': [
                r['canonical_term'] for r in skills_plan['unsupported_requested']
            ],
            'redundant_facts_rejected': redundant_rejected,
            'future_facts_selected': [
                fid for fid in ledger.selected_facts
                if self.fact_status.get(fid) == 'planned'
            ],
        }

        plan = {
            'schema_version': '1.0',
            'generated_for': self.match_obj.get('generated_for'),
            'summary': summary,
            'education': education,
            'experience': experience,
            'leadership': leadership,
            'additional': additional,
            'skills': skills_plan,
            'coverage': coverage,
            'excluded_evidence': excluded,
            'supporting_facts': self.supporting_pairs,
            'warnings': warnings,
        }

        ev_hash = _hash(self.evidence)
        cfg_hash = _hash(self.cfg)
        plan_hash = _hash(plan)
        plan['provenance'] = {
            'planner_version': self.cfg.get('planner_version'),
            'candidate_evidence_hash': ev_hash,
            'evidence_match_hash': self.match_obj['determinism']['input_hash'],
            'planner_config_hash': cfg_hash,
            'plan_hash': plan_hash,
        }
        return plan

    # ----------------------------------------------------------- bullet slot
    def _matched_comp_rank(self, fid):
        out = []
        for mc in self.fact_scores.get(fid, {}).get('matched_competencies') or []:
            if mc['match_coefficient'] > 0.0:
                out.append((mc['competency_id'],
                            mc['weight'] * mc['match_coefficient']))
        out.sort(key=lambda x: (-x[1], x[0]))
        return [cid for cid, _ in out]

    def _bullet_order_key(self, fid, primaries):
        fr = self.fact_scores.get(fid, {})
        fact = self.facts_by_id[fid]
        job_rel = sum(mc['weight'] * mc['match_coefficient']
                      for mc in fr.get('matched_competencies') or [])
        strength = int(fact.get('evidence_strength') or 0)
        quantified = 1 if fr.get('metrics') else 0
        coeff_by_comp = {}
        for mc in fr.get('matched_competencies') or []:
            coeff_by_comp.setdefault(mc['competency_id'], mc['match_coefficient'])
        diff = 0
        for other in primaries:
            if other == fid:
                continue
            for omc in self.fact_scores.get(other, {}).get('matched_competencies') or []:
                cid = omc['competency_id']
                if coeff_by_comp.get(cid, 0.0) > omc['match_coefficient']:
                    diff += 1
        recognition = 1 if self._is_recognition(fid) else 0
        return (job_rel, strength, quantified, diff, recognition,
                fr.get('total_score', 0.0), fid)

    def _build_slot(self, eid, fid, pos, score, components):
        fact = self.facts_by_id[fid]
        fr = self.fact_scores[fid]
        comps = self._matched_comp_rank(fid)
        primary = comps[:self.cfg['bullet']['max_primary_competencies']]
        secondary = comps[len(primary):len(primary) + self.cfg['bullet']['max_secondary_competencies']]
        terms = _dedupe_preserve(
            list(fact.get('approved_terms') or []) + list(fact.get('technologies') or []))
        terms = terms[:self.cfg['bullet']['max_target_terms']]
        top = ''
        if primary:
            top_fact = self.facts_by_id[fid]
            top_bits = [f'{cid}'
                        for cid in primary]
            top = f'{fid}: targets {", ".join(top_bits)}'
        else:
            top = f'{fid}: no primary JD competency match'
        if fr.get('metrics'):
            top += '; carries metrics'
        if components['redundancy_penalty'] < 0.0:
            top += '; redundancy penalized'
        return {
            'slot_id': f'{eid}#{pos}',
            'priority': pos,
            'primary_fact_id': fid,
            'supporting_fact_ids': [],
            'primary_competency_ids': primary,
            'secondary_competency_ids': secondary,
            'target_terms': terms,
            'targeted_metrics': list(fr.get('metrics') or [])[:2],
            'marginal_score': score,
            'components': components,
            'rationale': top,
        }

    # ------------------------------------------------------------- education
    def _build_education(self):
        edu_plan = []
        comp_ids = set(self.comp_rows.keys())
        hard_reqs = [str(h.get('requirement') or '') for h in
                     self.match_obj.get('hard_qualifications') or []]
        tier_terms = []
        for row in self.skill_matches_rows:
            tier_terms.append(str(row.get('canonical_term') or ''))
        opt_cfg = self.cfg['education']['optional_detail_relevance']
        for edu in (self.evidence.get('education') or [])[:self.cfg['education']['max_entries']]:
            selected = []
            excluded = []
            coursework = []
            for d in edu.get('details') or []:
                did = d.get('detail_id')
                text = (d.get('text') or '').casefold()
                if d.get('locked') and not d.get('optional'):
                    selected.append(did)
                    continue
                if d.get('optional'):
                    relevant = False
                    if opt_cfg.get('enabled'):
                        hay = ' '.join(hard_reqs + tier_terms).casefold()
                        if text and hay and any(
                                tok and (tok in text or text in tok)
                                for tok in hay.replace('-', ' ').split()):
                            relevant = True
                    (selected if relevant else excluded).append(did)
                    continue
                selected.append(did)
            tags = _dedupe_preserve(
                t for d in edu.get('details') or [] for t in (d.get('detail_tags') or [])
                if t in comp_ids)
            coursework = tags
            rationale = 'locked details included; optional details only when the JD requests them' if excluded else 'all details selected'
            if coursework:
                rationale += '; coursework tagged to JD competencies'
            edu_plan.append({
                'education_id': edu.get('education_id'),
                'institution': edu.get('institution'),
                'degree': edu.get('degree'),
                'location': edu.get('location'),
                'date': edu.get('date'),
                'selected_detail_ids': selected,
                'excluded_detail_ids': excluded,
                'selected_coursework_tags': coursework,
                'rationale': rationale,
            })
        return edu_plan

    # ---------------------------------------------------------------- skills
    def _build_skills(self, ledger):
        requested = {}
        unsupported_req = []
        for row in self.skill_matches_rows:
            if row.get('status') == 'supported' and row.get('skill_id'):
                requested[row['skill_id']] = row['level']
            elif row.get('status') in ('unsupported', 'not_in_bank'):
                unsupported_req.append({
                    'canonical_term': row.get('canonical_term'),
                    'skill_id': row.get('skill_id'),
                    'status': row.get('status'),
                })
        scfg = self.cfg['skills']
        category_order = scfg['category_order']
        selected_set = set(ledger.selected_set)
        rows = []
        for skill in self.evidence.get('skills') or []:
            sid = skill.get('skill_id')
            if not skill.get('verified'):
                continue
            jd_level = requested.get(sid)
            if jd_level is None:
                if sid in {r['skill_id'] for r in unsupported_req if r['skill_id']}:
                    continue
                mult = scfg['differentiator_multiplier']
                jd_factor = 1.0
            else:
                mult = scfg['requested_supported_multiplier']
                jd_factor = self.tier1_level_factors.get(jd_level, 0.0)
            ev_count = len(skill.get('evidence_fact_ids') or []) + len(
                skill.get('education_evidence_ids') or [])
            ev = min(ev_count, int(scfg['evidence_cap']))
            selected_support = any(fid in selected_set
                                   for fid in (skill.get('evidence_fact_ids') or []))
            boost = scfg['selected_fact_boost'] if selected_support else 1.0
            score = round(mult * jd_factor * (1.0 + scfg['evidence_weight'] * ev) * boost,
                          self.precision)
            cat_rank = category_order.index(skill.get('category')) \
                if skill.get('category') in category_order else len(category_order)
            rows.append({
                'skill_id': sid,
                'display_name': skill.get('display_name'),
                'category': skill.get('category'),
                'verified': True,
                'jd_level': jd_level,
                'evidence_count': ev_count,
                'selected_fact_support': selected_support,
                'score': score,
                '_sort': (-score, cat_rank, -int(skill.get('proficiency') or 0),
                          str(skill.get('display_name'))),
            })
        rows.sort(key=lambda r: r['_sort'])
        picked = rows[:int(scfg['max_selected'])]
        for r in picked:
            r.pop('_sort', None)
        for r in rows[int(scfg['max_selected']):]:
            r.pop('_sort', None)
        excluded = [{'skill_id': r['skill_id'],
                     'display_name': r['display_name'],
                     'reason': 'NOT_SELECTED_WITHIN_CAP'} for r in
                    rows[int(scfg['max_selected']):]]
        for r in rows:
            r.setdefault('rationale', self._skill_rationale(r, ledger))
        return {
            'selected_skills': picked,
            'excluded': excluded,
            'unsupported_requested': unsupported_req,
        }

    def _skill_rationale(self, row, ledger):
        if row.get('jd_level'):
            return f'requested tier-1 skill ({row["jd_level"]}); verified evidence={row["evidence_count"]}'
        return f'verified differentiator; evidence={row["evidence_count"]}'

    # -------------------------------------------------------------- coverage
    def _level_from_coeff(self, coeff):
        strong_th = self.coverage_level_thresholds['strong']
        moderate_th = self.coverage_level_thresholds['moderate']
        if coeff >= strong_th:
            return 'strong'
        if coeff >= moderate_th:
            return 'moderate'
        if coeff > 0.0:
            return 'weak'
        return 'none'

    def _coverage_target(self, weight):
        ts = self.cfg['coverage_targets']
        if weight >= ts['high']['min_weight']:
            return 'strong'
        if weight >= ts['medium']['min_weight']:
            return 'moderate'
        return 'none'

    def _build_coverage(self, ledger):
        rows = self.comp_rows
        competencies = []
        cand = {'strong': [], 'moderate': [], 'weak': [], 'none': []}
        sel = {'strong': [], 'moderate': [], 'weak': [], 'none': []}
        loss = []
        for cid in sorted(rows, key=lambda c: rows[c]['rank']):
            row = rows[cid]
            candidate_level = self._level_from_coeff(row['best_match'])
            selected_level = ledger.coverage_for_competency(cid)
            target = self._coverage_target(row['weight'])
            selected_facts = [fid for fid in ledger.selected_set
                              if any(mc['competency_id'] == cid
                                     for mc in self.fact_scores[fid].get(
                                         'matched_competencies') or [])]
            selected_facts.sort()
            cand[candidate_level].append(cid)
            sel[selected_level].append(cid)
            gap = 'none'
            if candidate_level == 'none' and row['weight'] >= float(
                    self.cfg['unsupported_gap_min_weight']):
                gap = 'unsupported'
            elif target != 'none' and self.level_rank[selected_level] < self.level_rank[target]:
                gap = 'under_selected'
            competencies.append({
                'competency_id': cid,
                'rank': row['rank'],
                'weight': row['weight'],
                'target_level': target,
                'candidate_level': candidate_level,
                'candidate_best_fact_id': row['best_fact_id'],
                'selected_level': selected_level,
                'selected_facts': selected_facts,
                'gap': gap,
            })
            if (self.level_rank[candidate_level] > self.level_rank['none']
                    and self.level_rank[candidate_level] > self.level_rank[selected_level]):
                reason = f'candidate {candidate_level}, selected {selected_level}'
                if target != 'none' and self.level_rank[selected_level] < self.level_rank[target]:
                    reason = f'target {target} unmet; candidate {candidate_level}, selected {selected_level}'
                loss.append({
                    'competency_id': cid,
                    'rank': row['rank'],
                    'weight': row['weight'],
                    'candidate_level': candidate_level,
                    'selected_level': selected_level,
                    'reason': reason,
                })
        guard = self.cfg['coverage_loss_guard']
        return {
            'competencies': competencies,
            'candidate_possible': cand,
            'selected': sel,
            'coverage_loss': loss,
            '_guard': guard,
        }

    # --------------------------------------------------------------- exclusions
    def _build_excluded(self, ledger, final_entry_order, dropped):
        selected = set(ledger.selected_set)
        supporting = {s['fact_id'] for s in self.supporting_pairs}
        out_entries = {eid for section in final_entry_order.values() for eid in section}
        reason_order = self.cfg['excluded_reason_order']
        redundant_rejected = []
        out = []
        for fid in sorted(selected | set(self.facts_by_id.keys())):
            if fid in selected or fid in supporting:
                continue
            eid = self.fact_entry[fid]
            reason, explanation = self._reason_for(fid, eid, ledger, out_entries,
                                                   reason_order)
            out.append({'fact_id': fid, 'entry_id': eid, 'reason': reason,
                        'explanation': explanation})
            if reason == 'REDUNDANT':
                redundant_rejected.append(fid)
        return out, redundant_rejected

    def _reason_for(self, fid, eid, ledger, out_entries, reason_order):
        fr = self.fact_scores.get(fid, {})
        if eid not in out_entries:
            return ('ENTRY_NOT_SELECTED',
                    f'entry {eid!r} not selected for the role')
        # redundancy vs selected facts
        strong_th = self.marg_cfg['redundancy_penalties']['moderate']['min_jaccard']
        for other in sorted(ledger.selected_set):
            a, b = (fid, other) if fid < other else (other, fid)
            jac = self.pair_jaccard.get((a, b), 0.0)
            if jac >= strong_th:
                return ('REDUNDANT',
                        f'overlaps selected fact {other!r} (jaccard {jac})')
        if self.fact_status.get(fid) == 'planned':
            my_score = fr.get('total_score', 0.0)
            for other in ledger.entry_primary.get(eid, []):
                pull = self.fact_scores.get(other, {}).get('total_score', 0.0)
                if (other != fid and pull == my_score
                        and self.fact_status.get(other) == 'completed'):
                    return ('FUTURE_FACT_RESTRICTION',
                            'planned fact tied with a completed fact; completed wins')
        if fr.get('total_score', 0.0) < float(self.cfg['min_relevance_threshold']):
            return ('LOW_RELEVANCE', f'total_score below relevance threshold')
        for other in sorted(ledger.entry_primary.get(eid, [])):
            pull = self.fact_scores.get(other, {}).get('total_score', 0.0)
            if pull > fr.get('total_score', 0.0):
                return ('WEAKER_ALTERNATIVE',
                        f'bested by selected fact {other!r} in the same entry')
        return ('SPACE_CONSTRAINT', 'section bullet budget reached')

    # ---------------------------------------------------------------- warnings
    def _build_warnings(self, coverage, excluded):
        warnings = []
        guard = coverage.get('_guard', {})
        for row in coverage['competencies']:
            if row['gap'] == 'unsupported':
                warnings.append({
                    'code': 'UNSUPPORTED_GAP',
                    'message': (f'{row["competency_id"]} (w={row["weight"]}) has no '
                                'candidate evidence; not fabricated at plan time'),
                })
            if row['target_level'] != 'none' and row['gap'] == 'under_selected':
                warnings.append({
                    'code': 'COVERAGE_TARGET_UNMET',
                    'message': (f'{row["competency_id"]} target {row["target_level"]} '
                                f'but selected {row["selected_level"]}'),
                })
            weight = row['weight']
            if (weight >= float(guard.get('min_weight', 0.4))
                    and row['candidate_level'] in ('strong', 'saturated')
                    and row['selected_level'] in ('none', 'weak')):
                warnings.append({
                    'code': 'COVERAGE_LOSS',
                    'message': (f'{row["competency_id"]} (w={weight}) reachable at '
                                f'{row["candidate_level"]} but selected '
                                f'{row["selected_level"]}'),
                })
        return warnings

    # ------------------------------------------------------------------ main
    def main_flow(self):
        return self.run()


def plan(evidence: dict, match_obj: dict, cfg: dict = None) -> dict:
    """Produce a deterministic resume plan. Same inputs -> same output."""
    if cfg is None:
        cfg = load_json(DEFAULT_CONFIG)
    p = ResumePlanner(evidence, match_obj, cfg)
    return p.run()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Deterministic resume planner: match -> plan IR')
    parser.add_argument('--matches', required=True,
                        help='path to the evidence match object (evidence_match_schema shape)')
    parser.add_argument('--evidence', default=str(DEFAULT_EVIDENCE),
                        help='path to candidate_evidence.json')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG),
                        help='path to planner_config.json')
    parser.add_argument('--output', required=True,
                        help='path to write the plan object')
    args = parser.parse_args(argv)

    try:
        match_obj = load_json(args.matches)
        evidence = load_json(args.evidence)
        cfg = load_json(args.config)
    except (OSError, json.JSONDecodeError) as e:
        print(f'error loading input: {e}', file=sys.stderr)
        return 1

    out = plan(evidence, match_obj, cfg)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write('\n')

    s = out['summary']
    print('Resume planning: OK')
    print('Selected experience entries: '
          f'{", ".join(s["selected_experience_entries"]) or "(none)"}')
    print('Selected leadership entries: '
          f'{", ".join(s["selected_leadership_entries"]) or "(none)"}')
    print(f'Bullet slots: {s["bullet_slots"]}')
    print('Competencies covered strongly: '
          f'{", ".join(s["competencies_covered_strong"]) or "(none)"}')
    print('Competencies covered moderately: '
          f'{", ".join(s["competencies_covered_moderate"]) or "(none)"}')
    print('High-priority supported competencies omitted: '
          f'{", ".join(s["high_priority_supported_omitted"]) or "(none)"}')
    print('Unsupported JD skills excluded: '
          f'{", ".join(s["unsupported_skills_excluded"]) or "(none)"}')
    print('Redundant facts rejected: '
          f'{", ".join(s["redundant_facts_rejected"]) or "(none)"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())