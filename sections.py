"""Section schema for the PDF generator.

Every body section -- education, experience, leadership, additional --
follows one of two shapes:

``entries``  a list of entry dicts, each rendered as
             org line:   bold org (company / organization / institution)
                         + location, date right-aligned
             title line: italic (job title / degree)
             bullets:    hanging-list items (bullets / details)

``bullets``  a flat bullet list under the heading (the additional section).

Only the field names in the AI-produced content dict differ between the
entry-shaped sections, so each is described once here and the generator
iterates this config instead of spelling the mapping out itself.
"""

def render_title(entry: dict, spec: dict) -> str:
    """Return the title as it should render for an entry.

    Entries marked ``future: true`` get an ``(Incoming) `` prefix so the
    position reads as not-yet-started. A title that already starts with
    ``(Incoming)`` is left alone to avoid a double prefix.
    """
    title = entry.get(spec['title_field'], '')
    if entry.get('future') and title and not title.lower().startswith('(incoming'):
        title = f'(Incoming) {title}'
    return title


SECTIONS = (
    {
        'key': 'education',
        'title': 'EDUCATION',
        'kind': 'entries',
        'org_field': 'institution',
        'title_field': 'degree',
        'bullets_field': 'details',
        'dates_field': 'date',
    },
    {
        'key': 'experience',
        'title': 'EXPERIENCE',
        'kind': 'entries',
        'org_field': 'company',
        'title_field': 'title',
        'bullets_field': 'bullets',
        'dates_field': 'dates',
    },
    {
        'key': 'leadership',
        'title': 'LEADERSHIP AND COMMUNITY INVOLVEMENT',
        'kind': 'entries',
        'org_field': 'organization',
        'title_field': 'title',
        'bullets_field': 'bullets',
        'dates_field': 'dates',
    },
    {
        'key': 'additional',
        'title': 'ADDITIONAL INFORMATION',
        'kind': 'bullets',
    },
)


def ordered_specs(content: dict):
    """Yield the section specs to render for ``content``, in order.

    Sections render in the order their keys appear in the content dict
    (JSON object order is preserved on load), so reordering keys in the
    content JSON -- e.g. ``experience`` before ``education`` for a
    mid-career resume -- reorders the resume. Known sections that are
    absent from or empty in ``content`` are skipped entirely; no section
    is required. Unknown top-level keys (header, output, ...) are ignored.
    """
    by_key = {spec['key']: spec for spec in SECTIONS}
    yielded = set()
    for key, value in content.items():
        spec = by_key.get(key)
        if not spec or not value or key in yielded:
            continue
        yielded.add(key)
        yield spec
