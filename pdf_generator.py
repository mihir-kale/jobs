"""Direct PDF generation from resume content JSON.

The resume PDF is rendered straight from the content dict -- no intermediate
DOCX and no headless-office conversion. Layout:

  - US Letter, 0.5" margins on all sides
  - Times New Roman: 16pt bold name, 12pt bold section headings, 10.5pt body
  - Single line spacing (1.15x font size); no paragraph spacing
   - Section headings carry a full-width bottom rule
   - Org lines: bold organization, regular " - location", date right-aligned
   - Bullets hang at 0.25" (glyph) / 0.5" (text) from the text margin
   - Body sections render in content-JSON key order; absent sections are
     skipped, and ``content['section_titles']`` may rename any heading
"""

import logging
import os
from pathlib import Path

from fpdf import FPDF

from sections import ordered_specs, render_title

MARGIN = 36.0
PAGE_W = 612.0
PAGE_H = 792.0
RIGHT = PAGE_W - MARGIN
CONTENT_W = PAGE_W - 2 * MARGIN

NAME_SIZE = 16.0
HEADING_SIZE = 12.0
BODY_SIZE = 10.5

ASCENT = 0.891
LINE_FACTOR = 1.15
SECTION_RULE_GAP = 4.0

FONT_DIRS = [
    '/System/Library/Fonts/Supplemental',
    '/Library/Fonts',
    'C:/Windows/Fonts',
    '/usr/share/fonts/truetype/msttcorefonts',
    '/usr/share/fonts/truetype/liberation2',
    '/usr/share/fonts/truetype/liberation',
    '/usr/share/fonts/truetype/dejavu',
    '/usr/share/fonts/truetype/times',
    str(Path(__file__).resolve().parent / 'fonts'),
]

# Candidate serif families in preference order. Liberation Serif and Nimbus
# Roman are metric-compatible with Times New Roman, so layout stays stable.
FONT_FAMILIES = (
    ('Times New Roman.ttf', 'Times New Roman Bold.ttf',
     'Times New Roman Italic.ttf', 'Times New Roman Bold Italic.ttf'),
    ('Times_New_Roman.ttf', 'Times_New_Roman_Bold.ttf',
     'Times_New_Roman_Italic.ttf', 'Times_New_Roman_Bold_Italic.ttf'),
    ('LiberationSerif-Regular.ttf', 'LiberationSerif-Bold.ttf',
     'LiberationSerif-Italic.ttf', 'LiberationSerif-BoldItalic.ttf'),
    ('NimbusRoman-Regular.ttf', 'NimbusRoman-Bold.ttf',
     'NimbusRoman-Italic.ttf', 'NimbusRoman-BoldItalic.ttf'),
    ('DejaVuSerif.ttf', 'DejaVuSerif-Bold.ttf',
     'DejaVuSerif-Italic.ttf', 'DejaVuSerif-BoldItalic.ttf'),
)


def _find_ttf(names):
    for d in FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None


def _load_fonts(pdf):
    """Register a Times New Roman family (or a metric-compatible substitute).

    Raises with an actionable message if no usable serif TTF is installed.
    """
    logger = logging.getLogger('fpdf.fonts')
    previous = logger.level
    logger.setLevel(logging.ERROR)
    try:
        for regular, bold, italic, bold_italic in FONT_FAMILIES:
            path = _find_ttf([regular])
            if not path:
                continue
            pdf.add_font('TNR', '', path)
            pdf.add_font('TNR', 'B', _find_ttf([bold]) or path)
            pdf.add_font('TNR', 'I', _find_ttf([italic]) or path)
            pdf.add_font('TNR', 'BI', _find_ttf([bold_italic]) or _find_ttf([bold]) or path)
            return
        raise FileNotFoundError(
            'No Times New Roman (or metric-compatible serif) font found. '
            'Install one of: Times New Roman, Liberation Serif, Nimbus Roman, DejaVu Serif.'
        )
    finally:
        logger.setLevel(previous)


class _Layout:
    """Cursor-driven line renderer with an explicit y grid."""

    def __init__(self, pdf, margin=MARGIN):
        self.pdf = pdf
        self.margin = margin
        self.right = PAGE_W - margin
        self.y = margin

    def advance(self, size):
        return size * LINE_FACTOR

    def _need_page(self, advance):
        if self.y + advance > PAGE_H - self.margin:
            self.pdf.add_page()
            self.y = self.margin
            return True
        return False

    def line(self, text, size=BODY_SIZE, bold=False, italic=False, right=False, advance=None, link=None):
        pdf = self.pdf
        step = advance if advance is not None else self.advance(size)
        self._need_page(step)
        style = 'B' if bold else ('I' if italic else '')
        pdf.set_font('TNR', style, size)
        pdf.set_text_color(0, 0, 0)
        w = pdf.get_string_width(text)
        x = self.right - w if right else self.margin
        pdf.text(x, self.y + ASCENT * size, text)
        if link:
            pdf.link(x, self.y, w, size * LINE_FACTOR, link)
        self.y += step
        return w

    def org_line(self, org, location, date):
        pdf = self.pdf
        self._need_page(self.advance(BODY_SIZE))
        pdf.set_text_color(0, 0, 0)
        baseline = self.y + ASCENT * BODY_SIZE
        x = self.margin
        if org:
            pdf.set_font('TNR', 'B', BODY_SIZE)
            pdf.text(x, baseline, org)
            x += pdf.get_string_width(org)
        loc = f' \u2013 {location}' if location else ''
        if loc:
            pdf.set_font('TNR', '', BODY_SIZE)
            pdf.text(x, baseline, loc)
        if date:
            pdf.set_font('TNR', '', BODY_SIZE)
            pdf.text(self.right - pdf.get_string_width(date), baseline, date)
        self.y += self.advance(BODY_SIZE)

    def bullet(self, text):
        pdf = self.pdf
        if not text:
            return
        chunks = _wrap(pdf, text, self.right - (self.margin + 36), BODY_SIZE, False)
        for i, chunk in enumerate(chunks):
            self._need_page(self.advance(BODY_SIZE))
            baseline = self.y + ASCENT * BODY_SIZE
            pdf.set_font('TNR', '', BODY_SIZE)
            pdf.set_text_color(0, 0, 0)
            if i == 0:
                pdf.text(self.margin + 18, baseline, '\u2022')
            pdf.text(self.margin + 36, baseline, chunk)
            self.y += self.advance(BODY_SIZE)

    def blank(self, size=BODY_SIZE):
        self.y += self.advance(size)

    def section(self, title):
        self.line(title, HEADING_SIZE, bold=True)
        self.y += 1.5
        pdf = self.pdf
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.5)
        pdf.line(self.margin, self.y, self.right, self.y)
        self.y += SECTION_RULE_GAP


def _wrap(pdf, text, width, size, bold):
    pdf.set_font('TNR', 'B' if bold else '', size)
    words = text.split()
    lines = []
    cur = ''
    for word in words:
        cand = f'{cur} {word}'.strip()
        if pdf.get_string_width(cand) <= width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or ['']


def _entry(lay, spec, entry):
    """Render one entry (org line, italic title, bullets) from a section schema."""
    lay.org_line(entry.get(spec['org_field'], ''), entry.get('location', ''), entry.get(spec['dates_field'], ''))
    title = render_title(entry, spec)
    if title:
        lay.line(title, BODY_SIZE, italic=True)
    for b in entry.get(spec['bullets_field'], []):
        lay.bullet(b)
    lay.blank()


def generate_resume_pdf(content, output_path, ats_keywords=None):
    """Render a resume PDF directly from content JSON.

    If ats_keywords is provided, appends them in 1pt white font -- invisible
    to human readers but readable by ATS parsers.
    """
    pdf = FPDF(unit='pt', format='Letter')
    pdf.set_auto_page_break(False)
    _load_fonts(pdf)
    pdf.add_page()
    pdf.set_margin(MARGIN)
    lay = _Layout(pdf, margin=MARGIN)

    header = content.get('header', {})
    name = header.get('name', '')
    if name:
        lay.line(name.upper(), NAME_SIZE, bold=True)

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
            pdf.link(x_email, lay.y - lay.advance(BODY_SIZE), pdf.get_string_width(email), BODY_SIZE * LINE_FACTOR, f'mailto:{email}')
        elif email:
            pdf = lay.pdf
            pdf.set_font('TNR', '', BODY_SIZE)
            pdf.link(lay.right - w, lay.y - lay.advance(BODY_SIZE), w, BODY_SIZE * LINE_FACTOR, f'mailto:{email}')

    linkedin = header.get('linkedin', '')
    if linkedin:
        w = lay.line(linkedin, BODY_SIZE, right=True)
        url = linkedin if linkedin.startswith('http') else f'https://www.{linkedin}'
        lay.pdf.link(lay.right - w, lay.y - lay.advance(BODY_SIZE), w, BODY_SIZE * LINE_FACTOR, url)

    title_overrides = content.get('section_titles', {})
    for spec in ordered_specs(content):
        lay.section(title_overrides.get(spec['key'], spec['title']))
        if spec.get('kind') == 'bullets':
            for b in content[spec['key']].get('bullets') or []:
                lay.bullet(b)
            lay.blank()
            continue
        for entry in content[spec['key']]:
            _entry(lay, spec, entry)

    if ats_keywords:
        keywords = ' '.join(ats_keywords)
        lay.blank()
        pdf = lay.pdf
        pdf.set_font('TNR', '', 1.0)
        pdf.set_text_color(255, 255, 255)
        pdf.text(lay.margin, lay.y + ASCENT * 1.0, keywords)
        pdf.set_text_color(0, 0, 0)

    pdf.output(output_path)
