"""Optional local evidence. Unsupported tools never block AI admission."""
import re
import sympy as sp
from core.analyzer import _parse, analyze, X


def _equation(text):
    # No natural-language extraction beyond a short explicit equation suffix.
    text = re.sub(r'^(解方程|方程|求解)[:：\s]*', '', text.strip())
    if text.count('=') != 1:
        raise ValueError('Not a single equation')
    left, right = text.split('=')
    expr = _parse(left) - _parse(right)
    if sp.Poly(expr, X).degree() > 4:
        raise ValueError('Only degree <=4')
    real_x = sp.Symbol('x', real=True)
    return sp.solveset(expr.subs(X, real_x), real_x, domain=sp.S.Reals)


def _solutions(text,result,stage):
    try:
        return _equation(text)
    except (ValueError,SyntaxError,TypeError,sp.PolynomialError,NotImplementedError):
        return None  # Known unsupported syntax or solver range, not proof of correctness.
    except Exception:
        result.setdefault('diagnostics',[]).append({'code':'tool_execution_failed','stage':stage})
        return None  # Never store a raw exception or potentially sensitive input.


def evidence(submission):
    result = {'tool': 'SymPy bounded evidence', 'status': 'not_applicable',
              'scope': '仅支持显式多项式求导或相邻四次以内实数多项式方程解集；不验证完整证明。', 'checks': []}
    if submission.get('task_type') == 'derivative':
        original = submission.get('tool_expression') or submission['question']
        original = re.sub(r'^(求导|求导数)[:：\s]*', '', original.strip())
        r = analyze({'student_id': submission['student_id'], 'question': original,
                     'student_answer': submission.get('answer', '')}).to_dict()
        if r['status'] != 'unverified':
            result.update(status='checked', final_answer_status=r['status'], expected_answer=r['expected_answer'])
            result['observable_pattern'] = r['label']
            result['checks'].append({'step': None, 'verdict': r['status'], 'evidence': r['evidence']})
        return result
    previous = None
    previous = _solutions(submission['question'],result,'question')
    if previous is not None and submission.get('answer'):
        final = _solutions(submission['answer'],result,'answer')
        if final is not None:
            result['final_answer_status'] = 'correct' if final == previous else 'incorrect'
            result['expected_answer'] = '原方程实数解集：' + str(previous)
    for index, line in enumerate(submission.get('steps', []), 1):
        solutions = _solutions(line,result,'step')
        if solutions is not None:
            verdict = 'baseline' if previous is None else ('correct' if solutions == previous else 'incorrect')
            result['checks'].append({'step': index, 'verdict': verdict,
                'evidence': f'相邻方程实数解集：{previous} → {solutions}；仅相对上一式比较，不保证原题过程正确。'})
            previous = solutions
        else:
            previous = None
    judged = [c for c in result['checks'] if c['verdict'] != 'baseline']
    if judged:
        result['status'] = 'partial'
    elif result.get('final_answer_status'):
        result['status'] = 'checked'
    elif result.get('diagnostics'):
        result['status'] = 'failed'
    return result


def conflicts(analysis, tool):
    found = []
    final = tool.get('final_answer_status')
    if final in ('correct', 'incorrect') and analysis.get('final_answer_status') in ('correct', 'incorrect') and final != analysis['final_answer_status']:
        found.append('最终答案的 AI 判断与数学工具证据不一致。')
    by_step = {s['number']: s['verdict'] for s in analysis.get('steps', [])}
    for check in tool.get('checks', []):
        number, verdict = check.get('step'), check['verdict']
        if number and verdict in ('correct', 'incorrect') and by_step.get(number) in ('correct', 'incorrect') and by_step[number] != verdict:
            found.append(f'第 {number} 步 AI 判断与局部方程核验不同；请区分相邻等价与符合原题。')
    return found


def incorrect_steps(tool):
    """Only actual failed local checks; unsupported input is not a failure proof."""
    return [check for check in tool.get('checks', []) if check.get('verdict') == 'incorrect']


def reference_conflicts(tool):
    return tool.get('final_answer_status') == 'incorrect' or bool(incorrect_steps(tool))


def quick_conflicts(verdict, final, tool):
    found = conflicts({'final_answer_status': final, 'steps': []}, tool)
    if verdict == 'correct' and incorrect_steps(tool):
        found.append('整体正确的 AI 判断与局部过程核验不一致，请深析并复核原始步骤。')
    return found

