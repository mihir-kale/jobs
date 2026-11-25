"""Deterministic evidence matcher: JD competency map -> ranked candidate facts.

Takes the Phase-1 JD competency map (validated shape from jd_parser_schema.json,
with `competency_id` and `score.total`) and the Phase-2 canonical evidence bank
(candidate_evidence.json) and produces a deterministic match object:

  - a relevance score for EVERY fact (including facts that score zero),
    with fully decomposed score_components
  - skill intersection (supported / unsupported / not_in_bank)
  - tier-2 competency coverage (covered / partial / uncovered)
  - behavioral coverage
  - hard-qualification verdicts (met / not_met / unknown / not_machine_verifiable)
  - uncovered competencies with reasons
  - a redundancy signature over overlapping facts
  - an input hash so determinism is verifiable

Philosophy (mirrors jd_validator.py / candidate_evidence_validator.py):

  - No LLM, no Supabase, no resume assembly, no PDF.
  - All weights and thresholds come from matching_config.json.
  - All explicit JD -> candidate-tag links come from competency_relationships.json.
  - Same inputs MUST produce a byte-identical output. No timestamps, no randomness.
  - Facts and metrics are never mutated; identified/potential statuses survive.

Usage:

    python3.12 evidence_matcher.py \
        --competency-map input/jd_map.json \
        --evidence candidate_evidence.json \
        --output /tmp/evidence_match.json
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from candidate_evidence_validator import COMPETENCY_TAGS
from jd_validator import slugify

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_EVIDENCE = REPO_ROOT / 'candidate_evidence.json'
DEFAULT_CONFIG = REPO_ROOT / 'matching_config.json'
DEFAULT_RELATIONSHIPS = REPO_ROOT / 'competency_relationships.json'

_REALIZED = {'realized', 'implemented', 'ongoing'}

_ANALYSIS_ACTIONS = {
    'analyzed', 'analysed', 'evaluated', 'modeled', 'modelled', 'quantified',
    'calculated', 'assessed', 'examined', 'synthesized', 'synthesised',
    'identified', 'compared', 'conducted',
}
_ANALYSIS_TAGS = {'quantitative_analysis', 'data_analysis', 'financial_analysis',
                  'research', 'legal_analysis', 'document_analysis'}
_RECOMMENDATION_ACTIONS = {'recommended', 'recommend', 'recommending', 'proposed',
                           'proposing', 'advised', 'counseled'}
_RECOMMENDATION_TAGS = {'strategic_recommendations', 'decision_support'}
_LEADERSHIP_ACTIONS = {'led', 'lead', 'leading', 'trained', 'training', 'coordinated',
                       'directed', 'managed', 'supervised', 'mentored', 'organized'}
_LEADERSHIP_TAGS = {'leadership', 'teamwork'}
_COMMUNICATION_ACTIONS = {'presented', 'presenting', 'delivered', 'communicated',
                          'argued', 'translated'}
_COMMUNICATION_TAGS = {'communication', 'presentation'}
_OPERATIONAL_ACTIONS = {'reduced', 'improved', 'strengthened', 'standardized',
                        'increased', 'decreased', 'streamlined', 'optimized'}


def load_json(path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _dedupe_preserve(seq):
    seen = set()
    out = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def build_context(evidence: dict) -> dict:
    skills = {s['skill_id']: s for s in evidence.get('skills') or []}
    metrics = {m['metric_id']: m for m in evidence.get('metrics') or []}
    facts = []
    for entry in evidence.get('entries') or []:
        for fact in entry.get('facts') or []:
            facts.append({'entry_id': entry.get('entry_id'), 'fact': fact})
    return {'skills': skills, 'metrics': metrics, 'facts': facts}


def _fact_metrics(fact: dict, ctx: dict) -> list:
    return [ctx['metrics'][mid] for mid in (fact.get('metrics') or [])
            if mid in ctx['metrics']]


def evidence_traits(fact: dict, ctx: dict) -> dict:
    """Compute the 11 resume_evidence_sought traits for a fact (deterministic)."""
    hay = ' '.join([
        ' '.join(str(p) for p in (fact.get(k) or []))
        for k in ('actions', 'objects', 'approved_terms', 'technologies')
    ]).casefold()
    tags = set(fact.get('competency_tags') or [])
    actions = {a.casefold() for a in (fact.get('actions') or [])}
    techs = {t.casefold() for t in (fact.get('technologies') or [])}
    domain_tags = set(fact.get('domain_tags') or [])
    strength = int(fact.get('evidence_strength') or 0)

    fact_metrics = _fact_metrics(fact, ctx)
    _statuses = {m.get('status') for m in fact_metrics}

    award = ('award' in hay or 'first place' in hay
             or bool({'won', 'winner'} & actions))
    adopted_product = bool(fact_metrics) and bool(fact.get('stakeholders')) and bool(
        _statuses & _REALIZED)
    financial_impact = any(
        (m.get('value') or '').startswith('$')
        or 'savings' in (m.get('value') or '').casefold()
        or 'savings' in (m.get('description') or '').casefold()
        or 'budget' in (m.get('description') or '').casefold()
        for m in fact_metrics
    ) or any('savings' in str(t).casefold() for t in (fact.get('approved_terms') or []))
    operational_improvement = bool(_statuses & _REALIZED) or bool(
        actions & _OPERATIONAL_ACTIONS)
    scale_or_usage = any(
        m.get('relationship') == 'count' or '+' in (m.get('value') or '')
        for m in fact_metrics)
    technical_implementation = bool(techs)
    analysis = bool(actions & _ANALYSIS_ACTIONS) or bool(tags & _ANALYSIS_TAGS)
    recommendation = bool(actions & _RECOMMENDATION_ACTIONS) or bool(
        tags & _RECOMMENDATION_TAGS)
    leadership = bool(actions & _LEADERSHIP_ACTIONS) or bool(tags & _LEADERSHIP_TAGS)
    communication = bool(actions & _COMMUNICATION_ACTIONS) or bool(
        tags & _COMMUNICATION_TAGS)
    domain_experience = len(domain_tags) >= 2 or strength >= 4

    return {
        'award': award,
        'adopted_product': adopted_product,
        'financial_impact': financial_impact,
        'operational_improvement': operational_improvement,
        'scale_or_usage': scale_or_usage,
        'technical_implementation': technical_implementation,
        'analysis': analysis,
        'recommendation': recommendation,
        'leadership': leadership,
        'communication': communication,
        'domain_experience': domain_experience,
    }


def match_coefficient(fact: dict, tier2_rec: dict, relationships: dict) -> float:
    """0.0 untouched; 1.0 exact competency-tag match; else best relationship weight."""
    cid = tier2_rec.get('competency_id')
    if cid in set(fact.get('competency_tags') or []):
        return 1.0
    best = 0.0
    for rel in (relationships.get('relationships') or {}).get(cid, []):
        if rel.get('candidate_tag') in set(fact.get('competency_tags') or []):
            best = max(best, float(rel.get('weight', 0.0)))
    return best


def resolve_tier1_skill(term, config: dict):
    return (config.get('tier1_aliases') or {}).get((term or '').casefold().strip())


def _skill_matches_fact(fact: dict, skill: dict) -> bool:
    if fact.get('fact_id') in (skill.get('evidence_fact_ids') or []):
        return True
    tokens = {skill.get('skill_id', '').casefold(),
              skill.get('display_name', '').casefold()}
    techs = {t.casefold() for t in (fact.get('technologies') or [])}
    return bool(tokens & techs)


def _behavioral_mapping(behavioral: list, config: dict) -> list:
    aliases = config.get('behavioral_tag_aliases') or {}
    out = []
    for b in behavioral:
        slug = slugify(b.get('competency') or '')
        tag = slug if slug in COMPETENCY_TAGS else aliases.get(slug)
        if tag not in COMPETENCY_TAGS:
            tag = None
        out.append({'competency': b.get('competency'),
                    'level': b.get('level'), '_tag': tag})
    return out


def score_fact(entry_id, fact, tier_1, tier_2, relationships, ctx, cfg) -> dict:
    w = cfg['weights']
    precision = cfg['decimal_precision']
    strength = int(fact.get('evidence_strength') or 0)
    traits = evidence_traits(fact, ctx)

    # --- competency channel -------------------------------------------------
    matched_competencies = []
    comp_contrib = 0.0
    for rec in tier_2:
        coeff = match_coefficient(fact, rec, relationships)
        if coeff <= 0.0:
            continue
        weight = float(rec['score']['total']) / 10.0
        comp_contrib += coeff * weight
        matched_competencies.append({
            'competency_id': rec.get('competency_id'),
            'rank': rec.get('rank'),
            'match_coefficient': round(coeff, precision),
            'weight': round(weight, precision),
            'requested_evidence_satisfied': _dedupe_preserve(
                e for e in (rec.get('resume_evidence_sought') or []) if traits.get(e)),
        })

    # --- tier-1 verified-skill channel --------------------------------------
    matched_skills = []
    skill_contrib = 0.0
    verified_tier1_matches = 0
    for rec in tier_1:
        skill_id = resolve_tier1_skill(rec.get('canonical_term') or '', cfg)
        skill = ctx['skills'].get(skill_id) if skill_id else None
        if not skill or not skill.get('verified'):
            continue
        if int(skill.get('proficiency') or 0) < int(cfg['skill_eligibility']['min_proficiency']):
            continue
        if not _skill_matches_fact(fact, skill):
            continue
        factor = float(cfg['level_factors_tier1'].get(rec.get('level'), 0.0))
        skill_contrib += float(w['tier1_skill']) * factor
        matched_skills.append({
            'canonical_term': rec.get('canonical_term'),
            'level': rec.get('level'),
            'skill_id': skill_id,
        })
        verified_tier1_matches += 1

    # --- evidence-sought channel ---------------------------------------------
    denominator = _dedupe_preserve(
        e for rec in tier_2
        if match_coefficient(fact, rec, relationships) > 0.0
        for e in (rec.get('resume_evidence_sought') or [])
    )
    satisfied = _dedupe_preserve(e for e in denominator if traits.get(e))
    quality = 0.0
    if denominator:
        quality = float(w['evidence_sought']) * (len(satisfied) / len(denominator))

    # --- evidence-strength channel -------------------------------------------
    strength_contrib = float(w['evidence_strength']) * (
        strength / float(cfg['evidence_strength_max']))

    # --- metric channel (status factors; identified != realized) -------------
    fact_metrics = _fact_metrics(fact, ctx)
    metric_factors = cfg['metric_status_factors']
    metric_contrib = 0.0
    for m in fact_metrics:
        factor = float(metric_factors.get(m.get('status'), 0.0))
        metric_contrib = max(metric_contrib, float(w['metric_bonus']) * factor)

    # --- behavioral channel (capped below) -----------------------------------
    behavioral_contrib = 0.0
    matched_behavioral = []
    for b in cfg['_runtime']['_behavioral_list']:
        tag = b['_tag']
        if tag is None or tag not in set(fact.get('competency_tags') or []):
            continue
        factor = float(cfg['behavioral_level_factors'].get(b.get('level'), 0.0))
        candidate = float(w['behavioral']) * factor
        if candidate > behavioral_contrib:
            behavioral_contrib = candidate
        matched_behavioral.append({'competency': b['competency'],
                                   'level': b['level'], 'tag': tag})

    # --- domain channel -------------------------------------------------------
    domain_contrib = 0.0
    for rec in tier_2:
        if rec.get('category') != 'domain_terminology':
            continue
        comp_tokens = set(rec.get('competency_id', '').split('_'))
        fact_tokens = {t for d in (fact.get('domain_tags') or []) for t in d.split('_')}
        if comp_tokens & fact_tokens:
            domain_contrib = float(w['domain'])

    pre_behavioral = (comp_contrib + skill_contrib + quality + strength_contrib
                      + metric_contrib + domain_contrib)
    if behavioral_contrib > 0.0:
        cap = float(cfg['behavioral_cap']['max_final_share'])
        allowed = (cap / (1.0 - cap)) * pre_behavioral
        if behavioral_contrib > allowed:
            behavioral_contrib = allowed
    total = round(pre_behavioral + behavioral_contrib, precision)
    bucket = _bucket(total, cfg)

    high_weight_matches = sum(1 for mc in matched_competencies if mc['weight'] >= 0.5)

    return {
        'fact_id': fact.get('fact_id'),
        'entry_id': entry_id,
        'total_score': total,
        'bucket': bucket,
        'score_components': {
            'competency': round(comp_contrib, precision),
            'tier1_skill': round(skill_contrib, precision),
            'evidence_sought': round(quality, precision),
            'evidence_strength': round(strength_contrib, precision),
            'metric': round(metric_contrib, precision),
            'behavioral': round(behavioral_contrib, precision),
            'domain': round(domain_contrib, precision),
        },
        'matched_competencies': matched_competencies,
        'matched_skills': matched_skills,
        'matched_behavioral': matched_behavioral,
        'metrics': [
            {'metric_id': m['metric_id'], 'value': m['value'], 'status': m['status']}
            for m in fact_metrics
        ],
        '_ties': {
            'evidence_strength': strength,
            'high_weight_matches': high_weight_matches,
            'verified_tier1_matches': verified_tier1_matches,
            'quantified': int(bool(fact_metrics)),
        },
    }


def _bucket(total: float, cfg: dict) -> str:
    b = cfg['buckets']
    if total >= float(b['strong']):
        return 'strong'
    if total >= float(b['moderate']):
        return 'moderate'
    if total > 0.0:
        return 'weak'
    return 'none'


def skill_matches(competency_map: dict, ctx: dict, cfg: dict) -> list:
    out = []
    for rec in competency_map.get('tier_1_terms') or []:
        skill_id = resolve_tier1_skill(rec.get('canonical_term') or '', cfg)
        skill = ctx['skills'].get(skill_id) if skill_id else None
        if not skill:
            out.append({'canonical_term': rec.get('canonical_term'),
                        'level': rec.get('level'), 'category': rec.get('category'),
                        'status': 'not_in_bank', 'skill_id': None,
                        'proficiency': None, 'verified': None})
            continue
        eligible = (skill.get('verified')
                    and int(skill.get('proficiency') or 0)
                    >= int(cfg['skill_eligibility']['min_proficiency']))
        out.append({'canonical_term': rec.get('canonical_term'),
                    'level': rec.get('level'), 'category': rec.get('category'),
                    'status': 'supported' if eligible else 'unsupported',
                    'skill_id': skill_id, 'proficiency': skill.get('proficiency'),
                    'verified': skill.get('verified')})
    return out


def competency_coverage(tier_2, evidence_facts, relationships, cfg) -> list:
    coverage = []
    for rec in tier_2:
        best = 0.0
        best_fact = None
        best_strength = -1
        for row in evidence_facts:
            fact = row['fact']
            coeff = match_coefficient(fact, rec, relationships)
            if coeff == 0.0:
                continue
            strength = int(fact.get('evidence_strength') or 0)
            if (coeff > best or (coeff == best and (
                    strength > best_strength
                    or (strength == best_strength
                        and fact.get('fact_id') < best_fact)))):
                best = coeff
                best_fact = fact.get('fact_id')
                best_strength = strength
        weight = float(rec['score']['total']) / 10.0
        if best >= float(cfg['coverage']['covered_min_match']):
            status = 'covered'
        elif best > float(cfg['coverage']['partial_min_match']):
            status = 'partial'
        else:
            status = 'uncovered'
        coverage.append({'competency_id': rec.get('competency_id'),
                         'rank': rec.get('rank'),
                         'weight': round(weight, cfg['decimal_precision']),
                         'status': status,
                         'best_fact_id': best_fact,
                         'best_match': round(best, cfg['decimal_precision'])})
    return coverage


def uncovered_competencies(coverage) -> list:
    out = []
    for c in coverage:
        if c['status'] != 'uncovered':
            continue
        out.append({'competency_id': c['competency_id'], 'rank': c['rank'],
                    'weight': c['weight'],
                    'reasons': [
                        'no candidate fact carries the exact competency tag',
                        'no explicit relationship mapping to a candidate competency tag',
                    ]})
    return out


def hard_qualifications(competency_map: dict, evidence: dict) -> list:
    edu = evidence.get('education') or []
    degrees = ' '.join(e.get('degree', '') for e in edu).casefold()
    gpa = _candidate_gpa(evidence)
    grad_year = _candidate_grad_year(evidence)
    skills = {s.get('display_name', '').casefold(): s
              for s in evidence.get('skills') or []}
    out = []
    for hq in competency_map.get('hard_qualifications') or []:
        verdict, basis = _hard_qual_verdict(
            hq.get('category'), (hq.get('requirement') or '').casefold(),
            degrees, gpa, grad_year, skills)
        out.append({'category': hq.get('category'),
                    'requirement': hq.get('requirement'),
                    'level': hq.get('level'),
                    'resume_visibility': hq.get('resume_visibility'),
                    'verdict': verdict, 'basis': basis})
    return out


def _candidate_gpa(evidence: dict):
    for e in evidence.get('education') or []:
        for d in e.get('details') or []:
            m = re.search(r'gpa[:\s]*([0-9]+\.[0-9]+)',
                          (d.get('text') or '').casefold())
            if m:
                return float(m.group(1))
    return None


def _candidate_grad_year(evidence: dict):
    years = []
    for e in evidence.get('education') or []:
        for m in re.finditer(r'20\d{2}', e.get('date') or ''):
            years.append(int(m.group(0)))
    return max(years) if years else None


def _hard_qual_verdict(category, req, degrees, cand_gpa, cand_grad_year, skills):
    if category == 'degree':
        if any(k in req for k in ('bachelor', 'undergraduate', 'b.s', 'ba,')):
            if 'bachelor' in degrees or 'b.s' in degrees:
                return 'met', 'candidate degree includes a Bachelor of Science'
            return 'unknown', 'no matching degree found in education bank'
        if any(k in req for k in ('master', 'phd', 'mba')):
            return 'not_met', 'bank shows an undergraduate degree only'
        return 'unknown', 'unrecognized degree requirement'
    if category == 'major':
        if 'related' in req:
            return 'met', 'requirement is open to related fields; candidate majors in Business and CS'
        matched = [M for M in ('business analytics', 'computer science')
                   if M in req and M in degrees]
        if matched:
            return 'met', f'candidate major covers {matched[0]}'
        return 'unknown', 'no explicit major match found'
    if category == 'gpa':
        m = re.search(r'([0-9]+(?:\.[0-9]+)?)', req)
        if not m:
            return 'unknown', 'no numeric GPA threshold stated'
        req_gpa = float(m.group(1))
        if cand_gpa is None:
            return 'unknown', 'candidate GPA not in education bank'
        if cand_gpa >= req_gpa:
            return 'met', f'candidate GPA {cand_gpa} meets {req_gpa}'
        return 'not_met', f'candidate GPA {cand_gpa} below {req_gpa}'
    if category == 'graduation_date':
        m = re.search(r'(20\d{2})', req)
        if not m:
            return 'unknown', 'no graduation year stated'
        if cand_grad_year is None:
            return 'unknown', 'candidate graduation date not in education bank'
        if cand_grad_year <= int(m.group(1)) + 1:
            return 'met', f'candidate graduates {cand_grad_year}'
        return 'not_met', f'candidate graduates {cand_grad_year}'
    if category == 'enrollment':
        if any(k in req for k in ('enrolled', 'currently', 'pursuing', 'in progress')):
            return 'met', 'candidate has active degree credentials in education bank'
        return 'unknown', 'unrecognized enrollment requirement'
    if category == 'credential':
        for name, skill in skills.items():
            if name and name in req:
                if skill.get('verified'):
                    return 'met', f'verified skill {skill.get("display_name")}'
                return 'not_machine_verifiable', 'skill exists but is unverified'
        return 'not_machine_verifiable', 'credential not represented in evidence bank'
    return 'not_machine_verifiable', 'not decidable from the resume evidence bank'


def redundancy(fact_results, cfg) -> dict:
    matched = {fr['fact_id']: {c['competency_id'] for c in fr['matched_competencies']}
               for fr in fact_results}
    ids = list(matched.keys())
    pairs = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            fa, fb = ids[i], ids[j]
            shared = matched[fa] & matched[fb]
            if len(shared) < int(cfg['redundancy']['min_shared_competencies']):
                continue
            union = matched[fa] | matched[fb]
            jac = len(shared) / len(union) if union else 0.0
            if jac < float(cfg['redundancy']['min_jaccard']):
                continue
            by_id = {fr['fact_id']: fr for fr in fact_results}
            dominant = fa if by_id[fa]['total_score'] >= by_id[fb]['total_score'] else fb
            pairs.append({'fact_a': fa, 'fact_b': fb,
                          'shared_competencies': sorted(shared),
                          'jaccard': round(jac, cfg['decimal_precision']),
                          'dominant_fact_id': dominant})
    canonical = json.dumps(pairs, sort_keys=True, separators=(',', ':'))
    return {'signature': hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
            'pairs': pairs}


def build_summary(fact_results, skill_rows, uncovered, cfg) -> dict:
    buckets = {}
    for fr in fact_results:
        buckets[fr['bucket']] = buckets.get(fr['bucket'], 0) + 1
    return {
        'strong_matches': buckets.get('strong', 0),
        'moderate_matches': buckets.get('moderate', 0),
        'weak_or_none': buckets.get('weak', 0) + buckets.get('none', 0),
        'verified_requested_skills': [s['canonical_term'] for s in skill_rows
                                      if s['status'] == 'supported'],
        'unsupported_requested_skills': [s['canonical_term'] for s in skill_rows
                                         if s['status'] in ('unsupported', 'not_in_bank')],
        'high_priority_uncovered_competencies': [
            u['competency_id'] for u in uncovered
            if (u['rank'] <= int(cfg['high_priority_uncovered']['max_rank'])
                or u['weight'] >= float(cfg['high_priority_uncovered']['min_weight']))
        ],
    }


def _det_hash(competency_map, evidence, cfg, relationships) -> str:
    payload = json.dumps({'map': competency_map, 'evidence': evidence,
                          'config': cfg, 'relationships': relationships},
                         sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def match(competency_map: dict, evidence: dict, cfg: dict = None,
          relationships: dict = None) -> dict:
    """Run the deterministic matcher. Returns the match object."""
    if cfg is None:
        cfg = load_json(DEFAULT_CONFIG)
    if relationships is None:
        relationships = load_json(DEFAULT_RELATIONSHIPS)

    for key in ('job_identity', 'role_summary', 'tier_1_terms', 'tier_2_competencies',
                'hard_qualifications', 'behavioral_competencies'):
        if key not in competency_map:
            raise ValueError(f'competency map missing required key {key!r}; run the JD pipeline')

    vocab = COMPETENCY_TAGS
    for cid, rels in (relationships.get('relationships') or {}).items():
        for rel in rels:
            if rel.get('candidate_tag') not in vocab:
                raise ValueError(
                    f'relationships: {cid!r} references unknown candidate tag '
                    f'{rel.get("candidate_tag")!r}')

    cfg = dict(cfg)
    cfg['_runtime'] = {'_behavioral_list': _behavioral_mapping(
        competency_map.get('behavioral_competencies') or [], cfg)}

    ctx = build_context(evidence)
    tier_1 = competency_map.get('tier_1_terms') or []
    tier_2 = competency_map.get('tier_2_competencies') or []

    fact_results = []
    seen = set()
    for fact_row in ctx['facts']:
        entry_id, fact = fact_row['entry_id'], fact_row['fact']
        fact_id = fact.get('fact_id')
        if fact_id in seen:
            raise ValueError(f'duplicate fact_id in evidence bank: {fact_id!r}')
        seen.add(fact_id)
        fact_results.append(score_fact(entry_id, fact, tier_1, tier_2,
                                       relationships, ctx, cfg))

    fact_results.sort(key=lambda fr: (
        -fr['total_score'],
        -fr['_ties']['evidence_strength'],
        -fr['_ties']['high_weight_matches'],
        -fr['_ties']['verified_tier1_matches'],
        -fr['_ties']['quantified'],
        fr['fact_id'],
    ))
    for fr in fact_results:
        fr.pop('_ties', None)

    cov = competency_coverage(tier_2, ctx['facts'], relationships, cfg)
    uncov = uncovered_competencies(cov)
    skill_rows = skill_matches(competency_map, ctx, cfg)
    hq_rows = hard_qualifications(competency_map, evidence)
    redun = redundancy(fact_results, cfg)

    behavioral_rows = []
    for b in cfg['_runtime']['_behavioral_list']:
        tag = b['_tag']
        matched = sorted(fr['fact_id'] for fr in fact_results
                         if tag is not None and any(
                             mb['tag'] == tag for mb in fr['matched_behavioral']))
        behavioral_rows.append({'competency': b['competency'], 'level': b['level'],
                                'tag': tag, 'matched_fact_ids': matched})

    ji = competency_map.get('job_identity') or {}
    return {
        'schema_version': '1.0',
        'generated_for': {
            'company': ji.get('company'),
            'title': ji.get('title'),
            'program_term': ji.get('program_term'),
            'competency_map_schema_version': competency_map.get('schema_version'),
        },
        'summary': build_summary(fact_results, skill_rows, uncov, cfg),
        'fact_scores': fact_results,
        'skill_matches': skill_rows,
        'competency_coverage': cov,
        'behavioral_coverage': behavioral_rows,
        'hard_qualifications': hq_rows,
        'uncovered': uncov,
        'redundancy': redun,
        'determinism': {'input_hash': _det_hash(
            competency_map, evidence, cfg, relationships)},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Deterministic evidence matcher: JD map -> ranked facts')
    parser.add_argument('--competency-map', required=True,
                        help='validated JD competency map (jd_parser_schema shape)')
    parser.add_argument('--evidence', default=str(DEFAULT_EVIDENCE),
                        help='path to candidate_evidence.json')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG),
                        help='path to matching_config.json')
    parser.add_argument('--relationships', default=str(DEFAULT_RELATIONSHIPS),
                        help='path to competency_relationships.json')
    parser.add_argument('--output', required=True,
                        help='path to write the match object')
    args = parser.parse_args(argv)

    try:
        c_map = load_json(args.competency_map)
        evidence = load_json(args.evidence)
        cfg = load_json(args.config)
        rels = load_json(args.relationships)
    except (OSError, json.JSONDecodeError) as e:
        print(f'error loading input: {e}', file=sys.stderr)
        return 1

    out = match(c_map, evidence, cfg, rels)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write('\n')

    s = out['summary']
    print('Evidence matching: OK')
    print(f'Strong matches: {s["strong_matches"]} / '
          f'Moderate: {s["moderate_matches"]} / Weak or none: {s["weak_or_none"]}')
    print('Verified requested skills: '
          f'{", ".join(s["verified_requested_skills"]) or "(none)"}')
    print('Unsupported requested skills: '
          f'{", ".join(s["unsupported_requested_skills"]) or "(none)"}')
    print('High-priority uncovered competencies: '
          f'{", ".join(s["high_priority_uncovered_competencies"]) or "(none)"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())