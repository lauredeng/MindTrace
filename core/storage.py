"""Local JSON persistence for demo use only (single user / single machine)."""
import json
import os
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv('MINDTRACE_DATA_DIR', str(ROOT / '.local_data')))
STORE = DATA_DIR / 'runs.json'
STUDENT_STORE = DATA_DIR / 'student_sessions.json'
LOCK = threading.RLock()

def load_runs(path=STORE):
    path = Path(path)
    if not path.exists():
        return []
    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError('Storage format must be a list.')
    return data

def save_runs(runs, path=STORE):
    if not isinstance(runs, list):
        raise ValueError('Storage format must be a list.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.tmp-', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(runs, f, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def append_record(record, path=STORE):
    """Read/modify/write in one process lock; preserve unreadable originals."""
    with LOCK:
        records = load_runs(path)
        if record.get('id') and any(r.get('id') == record['id'] for r in records):
            return
        records.append(record)
        save_runs(records, path)


def save_review(run_id, row_index, review, path=STORE):
    with LOCK:
        records = load_runs(path)
        for run in records:
            if run.get('id') == run_id:
                if not 0 <= row_index < len(run['results']):
                    raise ValueError('Invalid review index')
                run.setdefault('reviews', {})[str(row_index)] = review
                save_runs(records, path)
                return
        raise ValueError('批次尚未保存，无法保存复核。')
