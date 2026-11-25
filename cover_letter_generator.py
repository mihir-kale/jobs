"""PDF generation for cover letter content JSON.

Renders a standard business-letter PDF directly from the content dict:

  - US Letter, 0.5" margins
  - Same font family as resume (Times New Roman / Liberation Serif fallback)
  - 16pt bold name, 10.5pt body, 1.5x paragraph spacing
  - Layout: sender header -> date -> recipient -> greeting -> body -> closing
"""

import re
from datetime import datetime

from pdf_generator import (
    ASCENT,
    BODY_SIZE,
    LINE_FACTOR,
    MARGIN,
    NAME_SIZE,
    RIGHT,
    _Layout,
    _load_fonts,
    _wrap,
)

from fpdf import FPDF


def _para(lay, text):
    """Render a wrapped paragraph followed by a blank line."""
    width = RIGHT - lay.margin
    chunks = _wrap(lay.pdf, text, width, BODY_SIZE, False)
    for chunk in chunks:
        lay.line(chunk, BODY_SIZE)
    lay.blank()


def _name_stem(content):
    """Build the output filename stem: LastName_FirstName_Cover_Letter_MM_DD_CompanyName."""
    parts = [p for p in str(content.get('header', {}).get('name', '')).split() if p]
    if len(parts) >= 2:
        base = f'{parts[-1]}_{parts[0]}'
    elif parts:
        base = parts[0]
    else:
        base = 'cover_letter'

    slug = re.sub(r'[^a-z0-9]+', '_', base.lower()).strip('_') or 'cover_letter'
    output = content.get('output', {}) or {}
    company = re.sub(r'[^a-z0-9]+', '', str(output.get('company', '') or '').lower())
    date_str = re.sub(r'[^a-z0-9]+', '_', str(content.get('date', '') or '').lower()).strip('_')
    try:
        parsed = datetime.strptime(content.get('date', ''), '%B %d, %Y')
        date_str = parsed.strftime('%m_%d')
    except (ValueError, TypeError):
        date_str = ''
    slug = f'{slug}_Cover_Letter'
    if date_str:
        slug = f'{slug}_{date_str}'
    if company:
        slug = f'{slug}_{company[:1].upper()}{company[1:]}'
    return slug


def generate_cover_letter_pdf(content, output_path):
    """Render a cover letter PDF from content JSON."""
    pdf = FPDF(unit='pt', format='Letter')
    pdf.set_auto_page_break(False)
    _load_fonts(pdf)
    pdf.add_page()
    pdf.set_margin(MARGIN)
    lay = _Layout(pdf, margin=MARGIN)

    header = content.get('header', {})
    name = header.get('name', '')
    if name:
        lay.line(name, NAME_SIZE, bold=True)

    contact = header.get('contact', '')
    email = header.get('email', '')
    contact_text = contact + (f' | {email}' if email else '')
    if contact_text:
        w = lay.line(contact_text, BODY_SIZE, right=True)
        if email and contact:
            prefix = f'{contact} | '
            pdf = lay.pdf
            pdf.set_font('TNR', '', BODY_SIZE)
            x_email = lay.right - w + pdf.get_string_width(prefix)
            pdf.link(x_email, lay.y - lay.advance(BODY_SIZE),
                     pdf.get_string_width(email), BODY_SIZE * LINE_FACTOR,
                     f'mailto:{email}')
        elif email:
            pdf = lay.pdf
            pdf.set_font('TNR', '', BODY_SIZE)
            pdf.link(lay.right - w, lay.y - lay.advance(BODY_SIZE),
                     w, BODY_SIZE * LINE_FACTOR, f'mailto:{email}')

    linkedin = header.get('linkedin', '')
    if linkedin:
        w = lay.line(linkedin, BODY_SIZE, right=True)
        url = linkedin if linkedin.startswith('http') else f'https://www.{linkedin}'
        lay.pdf.link(lay.right - w, lay.y - lay.advance(BODY_SIZE),
                     w, BODY_SIZE * LINE_FACTOR, url)

    lay.blank()
    lay.blank()

    date = content.get('date', '')
    if date:
        lay.line(date, BODY_SIZE, right=True)

    lay.blank()

    recipient = content.get('recipient', {})
    for field in ('name', 'title', 'company', 'address'):
        val = recipient.get(field, '')
        if val:
            lay.line(val, BODY_SIZE)

    lay.blank()

    greeting = content.get('greeting', '')
    if greeting:
        lay.line(greeting, BODY_SIZE)

    lay.blank()

    body = content.get('body', [])
    for i, paragraph in enumerate(body):
        if paragraph:
            _para(lay, paragraph)
            if i < len(body) - 1:
                lay.blank()

    lay.blank()

    closing = content.get('closing', '')
    if closing:
        lay.line(closing, BODY_SIZE)

    lay.blank()
    lay.blank()

    if name:
        lay.line(name, BODY_SIZE)

    lay.blank()
    lay.line('Enclosure: Résumé', BODY_SIZE)

    stem = _name_stem(content)
    pdf.output(output_path)
    return f'{stem}.pdf'
