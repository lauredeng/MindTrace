"""Batch validation and evidence-backed student practice."""
import io
import json
import random
from datetime import datetime, timezone
from uuid import uuid4
import pandas as pd
from core.analyzer import analyze, _parse, X
from sympy import diff

REQUIRED = ['student_id', 'question', 'student_answer']


def validate_rows(rows):
    if not 1 <= len(rows) <= 100:
        raise ValueError('每批须包含 1–100 条作业。')
    cleaned = []
    for i, row in enumerate(rows, 1):
        if not all(k in row for k in REQUIRED):
            raise ValueError('缺少字段：student_id、question、student_answer。')
        item = {k: str(row[k]).strip() for k in REQUIRED}
        if not all(item.values()):
            raise ValueError(f'第 {i} 行存在空字段，请补全后提交。')
        if any(len(v) > 160 for v in item.values()):
            raise ValueError(f'第 {i} 行字段超过 160 字符。')
        cleaned.append(item)
    return cleaned


def read_csv(data: bytes):
    if len(data) > 1024 * 1024:
        raise ValueError('CSV 文件须小于 1 MB。')
    frame = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding='utf-8-sig')
    return validate_rows(frame.to_dict('records'))


def make_run(rows, source, **metadata):
    rows = validate_rows(rows)
    results = [analyze(row).to_dict() for row in rows]
    return dict(metadata, id=str(uuid4()), created_at=datetime.now(timezone.utc).isoformat(),
                count=len(results), results=results, source=source, reviews={})


def make_exercise(seed=None):
    rng = random.Random(seed)
    a, b, n = rng.randint(2, 5), rng.randint(1, 5), rng.randint(2, 5)
    question = f'({a}*x**2+{b})**{n}'
    return {'question': question, 'hint': '先把内层函数设为 u，分别写出 dy/du 和 du/dx，再相乘。',
            'answer': str(diff(_parse(question), X))}


def import_run(data: bytes):
    """Portable persistence without accounts; recheck math and allowlist fields."""
    if len(data) > 1024 * 1024:
        raise ValueError('历史记录超过 1 MB。')
    payload = json.loads(data.decode('utf-8-sig'))
    if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
        raise ValueError('不是有效的批次记录。')
    if not all(isinstance(row, dict) for row in payload['results']):
        raise ValueError('作业条目格式无效。')
    source = '人工构造匿名样例' if payload.get('source') == '人工构造匿名样例' else '用户导入历史（已重新验证）'
    run = make_run(payload['results'], source)
    reviews = payload.get('reviews', {})
    if not isinstance(reviews, dict):
        raise ValueError('复核记录无效。')
    for index, review in reviews.items():
        if not index.isdigit() or not 0 <= int(index) < run['count'] or not isinstance(review, dict):
            raise ValueError('复核编号无效。')
        decision, note = review.get('decision'), review.get('note', '')
        if decision not in ('待复核', '认可数学证据', '需要修正 / 补充证据') or not isinstance(note, str) or len(note) > 2000:
            raise ValueError('复核内容无效。')
        run['reviews'][str(int(index))] = {'decision': decision, 'note': note, 'imported_at': datetime.now(timezone.utc).isoformat()}
    return run

