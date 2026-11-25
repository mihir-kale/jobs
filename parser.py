from pathlib import Path
from docx import Document
from PyPDF2 import PdfReader


def parse_file(file_path: str) -> str:
    """Parse a file and extract text content."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = path.suffix.lower()

    if suffix == '.txt':
        return _parse_txt(file_path)
    elif suffix == '.pdf':
        return _parse_pdf(file_path)
    elif suffix in ['.docx', '.doc']:
        return _parse_docx(file_path)
    elif suffix == '.md':
        return _parse_markdown(file_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")


parse_job_description = parse_file
parse_resume = parse_file


def _parse_txt(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def _parse_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return '\n\n'.join(text_parts)


def _parse_docx(file_path: str) -> str:
    doc = Document(file_path)
    text_parts = []
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if text:
            text_parts.append(text)
    for table in doc.tables:
        for row in table.rows:
            row_text = []
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text:
                    row_text.append(cell_text)
            if row_text:
                text_parts.append(' | '.join(row_text))
    return '\n'.join(text_parts)


def _parse_markdown(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.startswith('#'):
            line = line.lstrip('#').strip()
        line = line.replace('**', '').replace('*', '').replace('__', '').replace('_', '')
        if line.strip() in ['---', '***', '___']:
            continue
        if line.strip():
            cleaned_lines.append(line.strip())
    return '\n'.join(cleaned_lines)
