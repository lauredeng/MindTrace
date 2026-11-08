"""Bounded polynomial derivative checking; never evaluate Python input."""
import ast
from dataclasses import dataclass, asdict
from sympy import Symbol, Rational, Poly, diff, expand

X = Symbol('x')


@dataclass
class Result:
    student_id: str
    question: str
    student_answer: str
    status: str
    label: str
    evidence: str
    expected_answer: str
    checker: str = 'SymPy + limited deterministic rules'

    def to_dict(self):
        return asdict(self)


def _parse(expr: str):
    if not isinstance(expr, str) or not 0 < len(expr) <= 160:
        raise ValueError('表达式长度须为 1–160 字符')
    source = expr.replace('^', '**').replace('X', 'x').replace('×', '*').replace('−', '-').strip()
    tree = ast.parse(source, mode='eval')
    if len(list(ast.walk(tree))) > 90:
        raise ValueError('表达式节点过多')

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Name) and node.id == 'x':
            return X
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if not abs(node.value) <= 1000000:
                raise ValueError('数值超出范围')
            return Rational(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                value = a + b
            elif isinstance(node.op, ast.Sub):
                value = a - b
            elif isinstance(node.op, ast.Mult):
                value = a * b
            elif isinstance(node.op, ast.Div) and b.is_number and b != 0:
                value = a / b
            elif isinstance(node.op, ast.Pow) and b.is_Integer and 0 <= b <= 12:
                value = a ** b
            else:
                raise ValueError('仅支持数字分母和 0–12 次整数幂')
            poly = Poly(value, X)
            if poly.degree() > 24 or value.count_ops() > 100:
                raise ValueError('多项式次数或复杂度超出范围')
            if any(abs(c) > 10**30 for c in poly.all_coeffs()):
                raise ValueError('系数超出范围')
            return value
        raise ValueError('仅支持变量 x、数字和四则运算；乘法请使用 *')

    return visit(tree)


def analyze(row: dict) -> Result:
    sid = str(row.get('student_id', '')).strip() or 'anonymous'
    q = str(row.get('question', '')).strip()
    ans = str(row.get('student_answer', '')).strip()
    try:
        original, student = _parse(q), _parse(ans)
        expected = diff(original, X)
        if expand(student - expected) == 0:
            status, label, evidence = 'correct', '计算结果正确', '学生答案与该函数的导数在符号计算下等价。'
        else:
            status, label = 'incorrect', '结果不一致（具体错因待核实）'
            evidence = '学生答案与 SymPy 求得的导数不等价；仅凭最终答案不足以确定认知原因。'
            if original.is_Pow and original.base.has(X) and original.exp.is_Integer and original.exp > 1:
                outer_only = original.exp * original.base**(original.exp - 1)
                if expand(student - outer_only) == 0:
                    label = '遗漏内层导数（可观察模式）'
                    evidence = '学生结果等于外层幂函数求导部分，缺少内层函数导数因子；具体原因仍需追问。'
        return Result(sid, q, ans, status, label, evidence, str(expected))
    except Exception as exc:
        detail = str(exc) if isinstance(exc, ValueError) else '表达式无效或不在支持范围内'
        return Result(sid, q, ans, 'unverified', '未验证', f'未完成数学验证：{detail}', '', 'SymPy (not completed)')

