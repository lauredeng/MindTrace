"""Project-authored reference patterns, not a licensed examination question bank.

Symbolic checks cover only the specified subproblem. Full statements and
rubrics still require independent review before any generated exercise ships.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def _load():
    path=Path(__file__).resolve().parents[1]/'data'/'math_reference_patterns.json'
    return json.loads(path.read_text(encoding='utf-8'))


def examples(topic, knowledge_points=()):
    records=[row for row in _load() if row['topic']==topic]
    terms=set(knowledge_points)
    records.sort(key=lambda row:len(terms.intersection(row['knowledge_points'])),reverse=True)
    return [dict(deepcopy(row),source='项目原创参考模式；计算子问题有回归测试，整题未经教师审定') for row in records[:2]]
