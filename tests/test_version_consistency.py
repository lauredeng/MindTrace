"""User-visible stale conclusions must not survive reference and verdict changes."""
from copy import deepcopy

import pytest

from core import classroom as c, education as e, math_tools, presentation as v, product as p


def make_batch():
    w = c.new_workspace()
    batch = p.create_batch(w, '单元作业', [dict(student_id='001', question='选出所有正确选项：A、B、C',
                           question_type='选择题', question_no='1', answer='AC', steps=[])],
                           grading_policy=p.CLASSROOM_POLICY)
    return w, batch, w['submissions'][0]


def model_reply(verdict='incorrect'):
    return dict(verdict=verdict, final_answer_status=verdict, basis='测试夹具：判定依据',
                evidence_id='ANSWER', first_error_step=None, process_checked=False,
                uncertainty_reason='other')


def save_reference(w, batch, answer):
    batch = next(b for b in w['batches'] if b['id'] == batch['id'])
    groups, _ = p.reference_catalog(w, batch)
    return p.save_references(w, batch['id'], {next(iter(groups)): (answer, '')},
                            p.digest(batch.get('answer_keys', {})))


def test_uncertain_preserves_notes_but_excludes_old_cause_and_is_idempotent():
    w, batch, sub = make_batch()
    p.run_batch(w, batch['id'], lambda *a, **k: model_reply())
    entry = w['notebook'][0]
    p.edit_entry(w, entry['id'], p.CATEGORIES[0], [], '我的学习笔记', True)
    p.quick_check(sub, lambda *a, **k: model_reply('uncertain'), force=True)
    p.sync_notebook(w, sub['id'])
    assert entry['notes'] == '我的学习笔记'
    assert entry['category_confirmed'] is True
    assert entry['active_error'] is False
    assert entry['evidence_status'] == 'awaiting_review'
    assert p.cause_stats(w['notebook'])['confirmed'] == {}
    events = len(w['book_events'])
    p.sync_notebook(w, sub['id'])
    assert len(w['book_events']) == events
    p.quick_check(sub, lambda *a, **k: model_reply(), force=True)
    p.sync_notebook(w, sub['id'])
    assert entry['active_error'] is True
    assert entry['notes'] == '我的学习笔记'


def test_correct_unconfirmed_verdict_also_retires_active_error():
    w, batch, sub = make_batch()
    p.run_batch(w, batch['id'], lambda *a, **k: model_reply())
    p.quick_check(sub, lambda *a, **k: model_reply('correct'), force=True)
    p.sync_notebook(w, sub['id'])
    assert not w['notebook'][0]['active_error']
    assert w['notebook'][0]['evidence_status'] == 'corrected'


def test_current_explanation_is_filtered_after_either_reference_or_material_changes():
    _, _, sub = make_batch()
    record = dict(id='explanation', mode='full', status='completed', material_fingerprint=sub['fingerprint'],
                  reference_revision=None, correction=dict(answer='AC', reference_tool={'status':'not_applicable'}))
    sub['solutions'] = [record]
    assert p.latest(sub, 'solutions') is record
    assert p.correction_for(sub)['answer'] == 'AC'
    sub['reference_revision'] = 'changed'
    assert p.latest(sub, 'solutions') is None
    assert p.correction_for(sub) is None
    sub.pop('reference_revision')
    sub['fingerprint'] = 'changed-material'
    assert p.latest(sub, 'solutions') is None
    assert len(sub['solutions']) == 1  # Retain the original history.


def test_revised_reference_does_not_keep_old_manual_override_as_current():
    w, batch, sub = make_batch()
    save_reference(w, batch, 'A')
    sub = w['submissions'][0]
    p.run_batch(w, batch['id'], lambda *a, **k: pytest.fail('Expected local comparison'))
    v.override_grade(w, sub['id'], 'incorrect', '教师已复核旧版参考')
    assert p.effective(w, w['submissions'][0])['confirmed']
    save_reference(w, batch, 'AC')
    sub = w['submissions'][0]
    assert p.effective(w, sub)['verdict'] == 'uncertain'
    assert not p.effective(w, sub)['confirmed']
    assert len(w['reviews']) == 1
    assert not w['notebook'][0]['active_error']
    p.run_batch(w, batch['id'], lambda *a, **k: pytest.fail('Expected local comparison'))
    assert p.effective(w, w['submissions'][0])['verdict'] == 'correct'


def test_explanation_is_reused_until_the_reference_changes():
    _, _, sub = make_batch()
    calls = []
    def explain(*args, **kwargs):
        calls.append(kwargs['purpose'])
        return dict(known_conditions=['选项已给定'], goal='确定正确选项', method='逐项检查',
                    correction=dict(answer='AC',steps=[dict(text='逐项检查可得 AC',reason='依据各选项的题设条件')],
                                    category=p.UNKNOWN,category_basis='没有充分证据推断错因',
                                    knowledge_points=[],supplements=[],uncertainties=[]))
    original = p.solve_question(sub, 'full', explain)
    assert original['status'] == 'completed'
    assert p.solve_question(sub, 'full', explain)['id'] == original['id']
    assert len(calls) == 1
    sub['reference_revision'] = 'teacher-revised-reference'
    assert p.correction_for(sub) is None
    regenerated = p.solve_question(sub, 'full', explain)
    assert regenerated['status'] == 'completed'
    assert regenerated['id'] != original['id']
    assert len(calls) == 2
    assert len(sub['solutions']) == 2


@pytest.mark.parametrize('question', ['求导 x**2', '求导数：x^3 - 2*x', '求导：x**2。'])
def test_explicit_polynomial_has_safe_local_route(question):
    answer = '3*x**2-2' if 'x^3' in question else '2*x'
    sub = e.normalize_submission(dict(student_id='001',question=question,answer=answer))
    before = deepcopy(sub)
    assert math_tools.evidence(sub)['final_answer_status'] == 'correct'
    assert sub == before


@pytest.mark.parametrize('question', [
    '设f(x)=x**2，求参数a使f(x)>a恒成立', '求导 x**2，讨论单调性',
    '求导 __import__("os").system("anything")', '求导 ln(x)',
])
def test_ambiguous_or_unsafe_questions_do_not_gain_derivative_authority(question):
    sub = e.normalize_submission(dict(student_id='001',question=question,answer='2*x'))
    assert math_tools.evidence(sub)['status'] == 'not_applicable'
