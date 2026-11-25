"""Deterministic ATS keyword extraction for white-font injection.

Shared by the AI pipeline (main.py / app.py) and the no-API renderer
(render.py) so keyword behavior stays identical regardless of entry point.
"""

import re


def extract_ats_keywords(jd_text: str, resume_content: dict) -> list:
    """Extract ATS keywords from JD and resume skills for white-font injection."""
    # Known ATS keyword patterns to look for in JDs
    keyword_patterns = [
        # Tools & platforms
        r'\bJira\b', r'\bConfluence\b', r'\bSharePoint\b', r'\bAirtable\b',
        r'\bPython\b', r'\bJavaScript\b', r'\bJava\b', r'\bSQL\b', r'\bR\b',
        r'\bAWS\b', r'\bAzure\b', r'\bGCP\b', r'\bGit\b', r'\bLinux\b',
        r'\bSwift\b', r'\bSwiftUI\b', r'\bReact\b', r'\bNode\.js\b',
        r'\bDocker\b', r'\bKubernetes\b', r'\bTensorFlow\b', r'\bPyTorch\b',
        # AI/ML terms
        r'\bAI\b', r'\bML\b', r'\bLLM\b', r'\bNLP\b', r'\bGPT\b', r'\bClaude\b',
        r'\bChatGPT\b', r'\bGemini\b', r'\bRAG\b', r'\bvectoriz',
        r'\bprompt engineering\b', r'\bfine-tun', r'\bembedding',
        r'\bmodel\b', r'\btraining\b', r'\binference\b',
        # Product/PM terms
        r'\bPRD\b', r'\buser stor', r'\bepic\b', r'\backceptance criter',
        r'\brequirements traceability\b', r'\bproduct management\b',
        r'\bproduct lifecycle\b', r'\bproduct requirements\b',
        r'\bprocess design\b', r'\binformation architecture\b',
        r'\bknowledge management\b', r'\bdocument analysis\b',
        r'\bdocument processing\b', r'\bsummarization\b',
        r'\bworkflow automation\b', r'\brequirements management\b',
        r'\bproject management\b', r'\bscrum\b', r'\bagile\b',
        # Domain terms
        r'\bretail\b', r'\bcommerce\b', r'\bUX\b', r'\buser experience\b',
        r'\bdata analysis\b', r'\bdata driven\b', r'\bmetrics\b',
        r'\bKPI\b', r'\bstakeholder\b', r'\bcross-functional\b',
    ]

    found = set()
    jd_lower = jd_text.lower()

    for pattern in keyword_patterns:
        matches = re.findall(pattern, jd_text, re.IGNORECASE)
        for m in matches:
            found.add(m.strip())

    # Also grab skills from resume if present
    skills_str = resume_content.get('additional', {}).get('skills', '')
    if skills_str:
        for skill in skills_str.split(','):
            skill = skill.strip()
            if skill and len(skill) > 1:
                found.add(skill)

    # Sort by relevance (longer terms first, as they're more specific)
    return sorted(found, key=lambda x: (-len(x), x))
