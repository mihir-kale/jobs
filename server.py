#!/usr/bin/env python3
"""Local web UI for the JSON -> PDF resume renderer.

Run:
    python3.12 server.py             # http://127.0.0.1:5000
    python3.12 server.py --port 8080 # custom port
"""

import argparse
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from flask import Flask, after_this_request, jsonify, render_template, request, send_file, send_from_directory

from cover_letter_generator import generate_cover_letter_pdf
from pdf_generator import generate_resume_pdf
from resume_customizer import ConfigError, customize, load_base_resume, load_env

BASE_DIR = Path(__file__).resolve().parent
INSTRUCTIONS_PATH = BASE_DIR / 'resume_customization_prompt.md'
COVER_INSTRUCTIONS_PATH = BASE_DIR / 'cover_letter_prompt.md'
JOBS_DIR = BASE_DIR / 'static' / 'jobs'

app = Flask(__name__)


def _slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_') or ''


def _detect_type(content: dict) -> str:
    """Return 'cover_letter' if the JSON has a body array, else 'resume'."""
    if 'body' in content and isinstance(content['body'], list):
        return 'cover_letter'
    return 'resume'


def _name_stem(content: dict) -> str:
    """Build the output filename stem: LastName_FirstName_[Resume/Cover_Letter]_MM_DD_Company."""
    names = str(content.get('header', {}).get('name', '')).replace(',', ' ').split()
    if len(names) >= 2:
        base = f"{names[-1]}_{names[0]}"
    elif names:
        base = names[0]
    else:
        base = 'Resume'

    output = content.get('output', {}) or {}
    company = ' '.join(str(output.get('company', '') or '').split())
    if company:
        company = ''.join(w.capitalize() for w in re.sub(r'[^a-zA-Z0-9 ]', ' ', company).split())
    date_str = datetime.now().strftime('%m_%d')
    doc_type = 'Cover_Letter' if _detect_type(content) == 'cover_letter' else 'Resume'
    stem = f"{base}_{doc_type}_{date_str}"
    if company:
        stem = f"{stem}_{company}"
    return stem


@app.route('/')
@app.route('/jobs')
@app.route('/jobs/')
def jobs():
    return send_from_directory(JOBS_DIR, 'index.html')


@app.route('/jobs/<path:filename>')
def jobs_static(filename):
    return send_from_directory(JOBS_DIR, filename)


@app.route('/data/<path:filename>')
def jobs_data(filename):
    return send_from_directory(JOBS_DIR / 'data', filename)


@app.route('/source')
@app.route('/source/')
def source_view():
    return render_template('source.html')


@app.route('/source/data/<path:filename>')
def source_data(filename):
    return send_from_directory(BASE_DIR / 'static' / 'source', filename)


@app.route('/source/add', methods=['POST'])
def source_add():
    load_env()
    data = request.get_json(silent=True) or {}
    firm_name = str(data.get('firm') or '').strip()
    title = str(data.get('title') or '').strip()
    if not firm_name or not title:
        return jsonify({'error': 'firm and title are required'}), 400

    supabase_url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    service_key = os.environ.get('SUPABASE_SERVICE_KEY', '')
    if not supabase_url or not service_key:
        return jsonify({'error': 'Supabase not configured'}), 500

    def _request(method, path, payload=None):
        url = f'{supabase_url}/rest/v1/{path}'
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header('apikey', service_key)
        req.add_header('Authorization', f'Bearer {service_key}')
        if body is not None:
            req.add_header('Content-Type', 'application/json')
            req.add_header('Prefer', 'return=representation')
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {'error': raw}

    # Find or create firm.
    encoded = urllib.parse.quote(firm_name, safe='')
    status, firms = _request('GET', f'firms?name=eq.{encoded}&select=id')
    firm_id = None
    if status == 200 and isinstance(firms, list) and firms:
        firm_id = firms[0].get('id')
    if not firm_id:
        status, created = _request('POST', 'firms', {'name': firm_name})
        if status in (200, 201) and isinstance(created, list) and created:
            firm_id = created[0].get('id')
        elif isinstance(created, dict):
            firm_id = created.get('id')
    if not firm_id:
        return jsonify({'error': 'could not create firm'}), 500

    # Extract program year from title if present.
    m = re.search(r'(20\d{2})', title)
    program_year = int(m.group(1)) if m else None
    payload = {
        'firm_id': firm_id,
        'title': title,
        'application_status': 'interested',
    }
    if program_year:
        payload['program_year'] = program_year

    status, created = _request('POST', 'jobs', payload)
    if status not in (200, 201):
        return jsonify({'error': (created or {}).get('message', 'insert failed')}), 500
    return jsonify({'ok': True})


@app.route('/apply')
@app.route('/apply/')
def apply_view():
    return render_template('index.html')


@app.route('/network')
@app.route('/network/')
def network_view():
    return render_template('network.html')


@app.route('/instructions')
def instructions():
    if not INSTRUCTIONS_PATH.is_file():
        return jsonify({'error': 'instructions file not found'}), 404
    return send_file(INSTRUCTIONS_PATH, mimetype='text/markdown')


@app.route('/cover-letter-instructions')
def cover_letter_instructions():
    if not COVER_INSTRUCTIONS_PATH.is_file():
        return jsonify({'error': 'instructions file not found'}), 404
    return send_file(COVER_INSTRUCTIONS_PATH, mimetype='text/markdown')


@app.route('/convert-to-json', methods=['POST'])
def convert_to_json():
    """Tailor a base resume JSON for a pasted job description via the LLM."""
    load_env()
    data = request.get_json(silent=True) or {}
    jd = str(data.get('jd') or '').strip()
    if not jd:
        return jsonify({'error': 'job description is required'}), 400
    base = data.get('base')
    if not isinstance(base, dict):
        base = None
    try:
        content = customize(jd, base)
    except ConfigError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'content': content})


@app.route('/render', methods=['POST'])
def render():
    data = request.get_json(silent=True) or {}
    content = data.get('content')
    if not isinstance(content, dict):
        return jsonify({'error': 'content must be a JSON object'}), 400

    stem = _name_stem(content) or 'resume'
    fd, tmp = tempfile.mkstemp(suffix='.pdf', prefix='resume_')
    os.close(fd)
    try:
        if _detect_type(content) == 'cover_letter':
            generate_cover_letter_pdf(content, tmp)
        else:
            generate_resume_pdf(content, tmp)

        @after_this_request
        def cleanup(response, _tmp=tmp):
            try:
                os.remove(_tmp)
            except OSError:
                pass
            return response

        return send_file(tmp, as_attachment=True, download_name=f'{stem}.pdf',
                         mimetype='application/pdf')
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Local resume renderer web UI')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)
