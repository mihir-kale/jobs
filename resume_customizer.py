"""Customize a base resume JSON for a target job description using the pinned LLM.

Server-side counterpart to the web UI's "Add Job Description" panel. Sends the
base resume JSON plus the pasted job description to the OpenAI-compatible
endpoint configured in `.env` (see `.env.example`), using `json_instructions.md`
as the system prompt, and returns the customized resume JSON object.

No resume content or job description is stored or logged.

Config (real environment variables take precedence over `.env`):

    LLM_API_KEY              API key for the model endpoint
    LLM_MODEL                pinned model identifier
    LLM_BASE_URL             defaults to https://api.openai.com/v1
    LLM_RESPONSE_FORMAT      json_object (default) | none
    BASE_RESUME_JSON         path to the default base resume JSON, defaults to
                             input/content.json

Usage:

    python3.12 resume_customizer.py job.txt            # print customized JSON
    python3.12 resume_customizer.py job.txt out.json   # write to file
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = BASE_DIR / 'json_instructions.md'
DEFAULT_BASE_RESUME = BASE_DIR / 'input' / 'content.json'
DEFAULT_BASE_URL = 'https://api.openai.com/v1'

USER_TEMPLATE = (
    'Customize the base resume below for the target job description. Tailor '
    'bullets, section order, headings, skills, and the output.company field to '
    'the requirements in the job description. Never fabricate experience, '
    'credentials, or achievements.\n\n'
    '<base_resume>\n{{BASE_RESUME}}\n</base_resume>\n\n'
    '<job_description>\n{{JOB_DESCRIPTION}}\n</job_description>'
)


class ConfigError(Exception):
    pass


class LLMError(RuntimeError):
    pass


def load_env(env_file: str | Path | None = None):
    """Populate os.environ from a .env file (existing env vars win)."""
    env_path = Path(env_file) if env_file else BASE_DIR / '.env'
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip()
        value = value.strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_config() -> dict:
    def req(name, default=None):
        value = os.environ.get(name) or default
        if value is None:
            raise ConfigError(f'missing required config {name} (see .env.example)')
        return value

    return {
        'api_key': req('LLM_API_KEY'),
        'model': req('LLM_MODEL'),
        'base_url': (os.environ.get('LLM_BASE_URL') or DEFAULT_BASE_URL).rstrip('/'),
        'response_format': (os.environ.get('LLM_RESPONSE_FORMAT') or 'json_object'),
        'timeout': int(os.environ.get('LLM_TIMEOUT') or '120'),
    }


def _http_json(url: str, payload: dict, headers: dict, timeout: int):
    data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode('utf-8')
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        message = e.read().decode('utf-8', errors='replace')
        raise LLMError(f'LLM endpoint {url} -> {e.code}: {message[:800]}') from e


def call_llm(cfg: dict, system_prompt: str, user_message: str) -> str:
    body = {
        'model': cfg['model'],
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message},
        ],
        'temperature': 0,
    }
    if cfg['response_format'] == 'json_object':
        body['response_format'] = {'type': 'json_object'}
    headers = {
        'Authorization': f'Bearer {cfg["api_key"]}',
        'Content-Type': 'application/json',
    }
    url = f'{cfg["base_url"]}/chat/completions'
    response = _http_json(url, body, headers, cfg['timeout'])
    content = (response or {}).get('choices', [{}])[0].get('message', {}).get('content')
    if not content:
        raise LLMError(f'LLM returned no content: {json.dumps(response)[:500]}')
    return content


def parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        outer = content.find('```json')
        if outer == -1:
            outer = content.find('```')
        if outer != -1:
            start = content.find('\n', outer) + 1
            end = content.find('```', start)
            content = content[start:end if end != -1 else None].strip()
            return json.loads(content)
        raise


def load_base_resume(path: str | Path | None = None) -> dict:
    """Load the default base resume JSON (never raises on missing file)."""
    config_path = Path(path) if path else Path(os.environ.get('BASE_RESUME_JSON')
                                               or DEFAULT_BASE_RESUME)
    if not config_path.is_file():
        raise ConfigError(f'base resume JSON not found: {config_path}')
    return json.loads(config_path.read_text(encoding='utf-8'))


def customize(job_description: str, base_content: dict | None = None,
              system_prompt: str | None = None) -> dict:
    """Run the LLM to tailor a base resume for the given job description."""
    if not job_description.strip():
        raise ValueError('job description is required')
    if base_content is None:
        base_content = load_base_resume()
    if not system_prompt:
        if not SYSTEM_PROMPT_PATH.is_file():
            raise ConfigError(f'system prompt not found: {SYSTEM_PROMPT_PATH}')
        system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding='utf-8')

    cfg = read_config()
    user_message = (USER_TEMPLATE
                    .replace('{{BASE_RESUME}}', json.dumps(base_content, indent=2))
                    .replace('{{JOB_DESCRIPTION}}', job_description))
    content = call_llm(cfg, system_prompt, user_message)
    return parse_json(content)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print('usage: python3.12 resume_customizer.py <job-description.txt> [out.json]',
              file=sys.stderr)
        return 2
    load_env()
    try:
        jd = Path(argv[0]).read_text(encoding='utf-8')
        result = customize(jd)
    except Exception as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    output = json.dumps(result, indent=2, ensure_ascii=False)
    if len(argv) > 1:
        Path(argv[1]).write_text(output + '\n', encoding='utf-8')
    else:
        print(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())