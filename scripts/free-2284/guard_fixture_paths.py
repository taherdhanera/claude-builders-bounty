"""Claude PreToolUse hook: permit only the disposable fixture, never other files."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys


def check(payload, fixture):
    name, data = payload.get('tool_name'), payload.get('tool_input', {})
    if name not in ('Read', 'Glob', 'Grep') or not isinstance(data, dict):
        return False
    base = fixture.resolve()
    value = data.get('file_path') if name == 'Read' else data.get('path', str(base))
    if not isinstance(value, str) or not value or '\x00' in value:
        return False
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        candidate.resolve().relative_to(base)
    except (ValueError, OSError):
        return False
    if name == 'Glob':
        pattern = data.get('pattern', '')
        if not isinstance(pattern, str) or Path(pattern).is_absolute() or '..' in pattern.replace('\\', '/').split('/'):
            return False
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = sys.stdin.read(2_000_000)
        payload = json.loads(raw)
        allowed = check(payload, args.root)
    except Exception:
        payload, allowed = {}, False
    record = dict(checkedAtUtc=datetime.now(timezone.utc).isoformat(), tool=payload.get('tool_name'), input=payload.get('tool_input'), allowed=allowed)
    with args.log.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record) + '\n')
    print(json.dumps(dict(hookSpecificOutput=dict(hookEventName='PreToolUse', permissionDecision='allow' if allowed else 'deny', permissionDecisionReason='Only the isolated public acceptance fixture is authorized.'))))
