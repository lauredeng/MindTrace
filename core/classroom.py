"""Versioned JSON classroom records, separate from v0.2 data. Demo only."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4
from core.storage import save_runs, load_runs, LOCK, DATA_DIR
from core.records import validate_links

# Evidence histories grow faster than submissions. Never silently truncate them.
CAPACITIES = {'submissions':2000,'reviews':12000,'tasks':4000,'learning':4000,'attempts':16000,
              'events':20000,'usage':20000,'batches':2000,'notebook':2000,'book_events':20000,'study_sessions':4000}
CAPACITY_LABELS = {'submissions':'作答材料','reviews':'教师复核','tasks':'学习任务','learning':'学习过程',
                   'attempts':'练习记录','events':'操作历史','usage':'服务使用记录','batches':'作业批次',
                   'notebook':'错题记录','book_events':'错题修订历史','study_sessions':'辅导记录'}


def capacity_status(workspace):
    return [{'name':CAPACITY_LABELS[key],'count':len(workspace.get(key,[])),'limit':limit}
            for key,limit in CAPACITIES.items() if len(workspace.get(key,[]))>=limit*.8]


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid4())


def new_workspace():
    return {'schema_version': 1, 'id': uid(), 'revision': 0, 'storage_version': 0, 'submissions': [],
            'reviews': [], 'tasks': [], 'learning': [], 'attempts': [], 'events': [], 'usage': [],
            'batches': [], 'notebook': [], 'book_events': [], 'study_sessions': []}


def validate_workspace(data):
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('工作区版本无效。')
    if not isinstance(data.get('id'),str) or not 0<len(data['id'])<=100 or type(data.get('revision')) is not int or data['revision']<0:
        raise ValueError('工作区编号或修订版本无效。')
    for key,limit in CAPACITIES.items():
        if key not in data and key in ('batches', 'notebook', 'book_events', 'study_sessions'):
            continue
        if not isinstance(data.get(key), list):
            raise ValueError(CAPACITY_LABELS[key]+'格式无效。')
        if len(data[key]) > limit:
            raise ValueError(CAPACITY_LABELS[key]+'已达容量上限，请下载备份并新建课堂；原记录不会自动删除。')
        ids = [item.get('id') for item in data[key] if isinstance(item, dict)]
        if len(ids) != len(data[key]) or any(not isinstance(k, str) or not 0 < len(k) <= 100 for k in ids) or len(set(ids)) != len(ids):
            raise ValueError('工作区记录缺少有效唯一ID。')
    validate_links(data)
    # No config or secret objects are part of this schema.
    clean = {key: deepcopy(data[key]) for key in ('schema_version', 'id', 'revision', 'submissions', 'reviews', 'tasks', 'learning', 'attempts', 'events', 'usage')}
    generation = data.get('storage_version', 0)
    if type(generation) is not int or generation < 0:
        raise ValueError('存储版本无效。')
    clean['storage_version'] = generation
    for key in ('batches', 'notebook', 'book_events', 'study_sessions'):
        clean[key] = deepcopy(data.get(key, []))
    return clean


def commit(workspace, command_id, operation):
    if any(e['command_id'] == command_id for e in workspace['events']):
        return False
    draft = deepcopy(workspace)
    operation(draft)
    draft['revision'] += 1
    draft['events'].append({'id': uid(), 'command_id': command_id, 'created_at': now()})
    validate_workspace(draft)
    workspace.clear()
    workspace.update(draft)
    return True


def save(workspace, path=None):
    target = Path(path) if path else DATA_DIR / 'classroom_v1.json'
    with LOCK:
        current = load_runs(target)
        if current and (current[0].get('id') != workspace['id'] or current[0].get('storage_version', 0) != workspace.get('storage_version', 0)):
            raise ValueError('另一会话已更新磁盘工作区，未覆盖。请先下载当前备份，再刷新。')
        clean = validate_workspace(workspace)
        clean['storage_version'] += 1
        save_runs([clean], target)
        workspace['storage_version'] = clean['storage_version']


def load(path=None):
    target = Path(path) if path else DATA_DIR / 'classroom_v1.json'
    with LOCK:
        rows = load_runs(target)
    if not rows:
        return new_workspace()
    if len(rows) != 1:
        raise ValueError('工作区文件格式错误，原文件未改动。')
    return validate_workspace(rows[0])


def latest_review(workspace, submission_id):
    items = [r for r in workspace['reviews'] if r['submission_id'] == submission_id]
    return items[-1] if items else None


def review(workspace, submission_id, decision, label, knowledge_points, note, command_id, first_error_step=None, is_error=True):
    if decision not in ('confirm', 'modify', 'reject', 'uncertain'):
        raise ValueError('复核结论无效。')
    submission = next(s for s in workspace['submissions'] if s['id'] == submission_id)
    if not submission.get('analyses'):
        raise ValueError('须先完成一次分析或记录分析失败。')
    if not all(isinstance(v, str) and len(v) <= 2000 for v in (label, note)):
        raise ValueError('复核内容过长。')
    if not isinstance(knowledge_points, list) or len(knowledge_points) > 12 or any(not isinstance(p, str) or len(p) > 100 for p in knowledge_points):
        raise ValueError('知识点格式无效。')
    if first_error_step is not None and (type(first_error_step) is not int or not 1 <= first_error_step <= len(submission['steps'])):
        raise ValueError('错误步骤不存在。')
    item = {'id': uid(), 'submission_id': submission_id, 'analysis_id': submission['analyses'][-1]['id'],
            'decision': decision, 'label': label.strip(), 'knowledge_points': knowledge_points[:12],
            'note': note, 'first_error_step': first_error_step, 'is_error': bool(is_error), 'created_at': now()}
    previous = latest_review(workspace, submission_id)
    if previous and all(previous.get(k) == item.get(k) for k in ('analysis_id','decision','label','knowledge_points','note','first_error_step','is_error')):
        return previous
    def apply(w):
        w['reviews'].append(item)
        for task in w['tasks']:
            if task['submission_id'] == submission_id and task['review_id'] != item['id']:
                task['status'] = 'needs_recheck'
    commit(workspace, command_id, apply)
    return item


def assign(workspace, submission_id, goal, mode, command_id):
    submission = next(s for s in workspace['submissions'] if s['id'] == submission_id)
    confirmed = latest_review(workspace, submission_id)
    if not confirmed or confirmed['decision'] not in ('confirm', 'modify'):
        raise ValueError('只能根据教师确认或修改后的结论创建任务。')
    if not goal.strip() or len(goal) > 2000 or mode not in ('quick', 'deep'):
        raise ValueError('请填写训练目标并选择有效模式。')
    if any(t.get('command_id') == command_id for t in workspace['tasks']):
        return next(t for t in workspace['tasks'] if t.get('command_id') == command_id)
    task = {'id': uid(), 'command_id': command_id, 'student_id': submission['student_id'],
            'submission_id': submission_id, 'review_id': confirmed['id'], 'goal': goal.strip(),
            'knowledge_points': confirmed['knowledge_points'], 'teacher_note': confirmed['note'],
            'confirmed_label': confirmed['label'], 'mode': mode, 'created_at': now(), 'status': 'assigned'}
    commit(workspace, command_id, lambda w: w['tasks'].append(task))
    return task


def attach_image(data, directory=None):
    digest = hashlib.sha256(data).hexdigest()
    directory = Path(directory) if directory else DATA_DIR / 'classroom_images'
    directory.mkdir(parents=True, exist_ok=True)
    # Only generated hashes determine names, never an uploaded file path.
    target = directory / (digest + '.image')
    if not target.exists():
        with tempfile.NamedTemporaryFile(dir=directory,delete=False) as handle:
            temporary=Path(handle.name)
            try:
                handle.write(data)
                handle.close()
                os.replace(temporary,target)
            finally:
                handle.close()
                temporary.unlink(missing_ok=True)
    return digest


def read_image(digest, directory=None):
    if not re.fullmatch(r'[a-f0-9]{64}', digest):
        raise ValueError('图片引用无效。')
    directory = Path(directory) if directory else DATA_DIR / 'classroom_images'
    target = directory / (digest + '.image')
    return target.read_bytes() if target.exists() else None

