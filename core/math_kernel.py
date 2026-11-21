"""Typed SymPy adapters. No eval, Python tool, filesystem or network commands.

Each calculation runs in a disposable process with a wall-clock deadline.
Results establish the submitted mathematical model, not its translation from
a natural-language problem and never an arbitrary student's complete proof.
"""
from functools import lru_cache
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore

VERSION = 'sympy-contract-1'
OPERATIONS = ('evaluate', 'derivative', 'equation', 'inequality', 'system',
              'sum', 'dot', 'cross', 'norm', 'distance', 'set')
BASE = Path(__file__).resolve()
_SLOTS = BoundedSemaphore(4)


class _TemporaryFailure(RuntimeError):
    def __init__(self, result):
        self.result=result


def validate(request):
    if not isinstance(request, dict):
        raise ValueError('数学请求必须是对象。')
    raw = json.dumps(request, ensure_ascii=False, allow_nan=False, sort_keys=True)
    if len(raw) > 8000 or request.get('operation') not in OPERATIONS:
        raise ValueError('数学请求超出支持范围。')
    allowed = {'operation', 'expression', 'variable', 'domain', 'equations',
               'variables', 'lower', 'upper', 'left', 'right', 'expected', 'source_quote'}
    if set(request) - allowed:
        raise ValueError('数学请求包含未知字段。')
    return json.loads(raw)


def check(request, *, timeout=6):
    """Cached pure calculation; no credentials or user profiles reach the child."""
    try:
        clean = validate(request)
    except (ValueError, TypeError, OverflowError):
        return {'status': 'unsupported', 'reason': '数学请求格式无效。', 'engine': VERSION}
    # An expected answer belongs in the cache key. Quoted text is provenance,
    # not an operand; its binding is separately reviewed by the caller.
    clean.pop('source_quote', None)
    if not _SLOTS.acquire(timeout=0.2):
        return {'status':'busy','engine':VERSION,'reason':'数学计算正在排队，请稍后重试。'}
    try:
        try:
            return json.loads(_cached(json.dumps(clean, sort_keys=True), timeout))
        except _TemporaryFailure as exc:
            return exc.result
    finally:
        _SLOTS.release()


@lru_cache(maxsize=256)
def _cached(raw, timeout):
    env = {k: v for k, v in os.environ.items() if k.upper() in
           ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH', 'LANG')}
    try:
        result = subprocess.run([sys.executable, '-I', str(BASE)], input=raw,
                                capture_output=True, text=True, encoding='utf-8',
                                timeout=timeout, env=env,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        output = json.loads(result.stdout) if result.returncode == 0 else {}
        if output.get('engine') != VERSION:
            raise ValueError('Invalid worker result')
        return json.dumps(output, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        raise _TemporaryFailure({'status': 'timeout', 'engine': VERSION,
                           'reason': '本次数学计算达到时限，未据此判错。'}) from None
    except (OSError, ValueError):
        raise _TemporaryFailure({'status': 'unresolved', 'engine': VERSION,
                           'reason': '本次数学计算未完成，未据此判错。'}) from None


def _compute(request):
    import sympy as s
    from sympy.calculus.util import continuous_domain
    symbols = {name: s.Symbol(name, real=True) for name in ('x', 'y', 'z', 'a', 'b', 't')}
    symbols.update({name: s.Symbol(name, integer=True, positive=True) for name in ('n', 'k')})
    constants = {'pi': s.pi, 'E': s.E, 'oo': s.oo}
    functions = {'sin': s.sin, 'cos': s.cos, 'tan': s.tan, 'asin': s.asin,
                 'acos': s.acos, 'atan': s.atan, 'exp': s.exp, 'log': s.log,
                 'sqrt': s.sqrt, 'abs': s.Abs, 'binomial': s.binomial,
                 'factorial': s.factorial}

    def parse(value):
        if not isinstance(value, str) or not 1 <= len(value) <= 360:
            raise ValueError('Expression length')
        value = value.replace('^', '**').replace('−', '-').replace('×', '*').strip()
        tree = ast.parse(value, mode='eval')
        if len(list(ast.walk(tree))) > 100:
            raise ValueError('Expression complexity')

        def bound(value):
            if value.is_Rational and max(abs(int(value.p)).bit_length(),int(value.q).bit_length())>4096:
                raise ValueError('Rational bit bound')
            if s.count_ops(value)>160:
                raise ValueError('Intermediate complexity')
            return value

        def visit(node, depth=0):
            if depth > 16:
                raise ValueError('Expression nesting')
            child = lambda n: bound(visit(n, depth + 1))
            if isinstance(node, ast.Expression):
                return child(node.body)
            if isinstance(node, ast.Name) and node.id in symbols | constants:
                return (symbols | constants)[node.id]
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                if not abs(node.value) <= 1000000:
                    raise ValueError('Number bound')
                return s.Rational(str(node.value))
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
                return -child(node.operand) if isinstance(node.op, ast.USub) else child(node.operand)
            if isinstance(node, ast.BinOp):
                left, right = child(node.left), child(node.right)
                if isinstance(node.op, ast.Add):
                    return left + right
                if isinstance(node.op, ast.Sub):
                    return left - right
                if isinstance(node.op, ast.Mult):
                    return left * right
                if isinstance(node.op, ast.Div) and right != 0:
                    return left / right
                if isinstance(node.op, ast.Pow):
                    if right.is_number and (right.is_real is not True or abs(right) > 100):
                        raise ValueError('Power bound')
                    if not right.free_symbols <= {symbols['n'], symbols['k']}:
                        raise ValueError('Symbolic power bound')
                    return left ** right
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions and not node.keywords:
                args = [child(a) for a in node.args]
                name = node.func.id
                if len(args) != (2 if name == 'binomial' else 1):
                    raise ValueError('Function arity')
                if name in ('binomial', 'factorial') and any(a.is_number and (a.is_Integer is not True or not 0 <= a <= 1000) for a in args):
                    raise ValueError('Combinatorics bound')
                return functions[name](*args)
            raise ValueError('Unsupported syntax')

        result = bound(visit(tree))
        if result.has(s.zoo, s.nan) or s.count_ops(result) > 160:
            raise ValueError('Undefined or complex expression')
        return result

    def variable(name):
        if name not in symbols:
            raise ValueError('Unknown variable')
        return symbols[name]

    def domain(raw):
        if raw in (None, 'Reals'):
            return s.S.Reals
        if raw == 'Integers':
            return s.S.Integers
        if isinstance(raw, dict) and set(raw) <= {'lower', 'upper', 'left_open', 'right_open'}:
            if any(type(raw.get(k, False)) is not bool for k in ('left_open', 'right_open')):
                raise ValueError('Interval boundaries')
            return s.Interval(parse(raw['lower']), parse(raw['upper']),
                              left_open=raw.get('left_open', False), right_open=raw.get('right_open', False))
        raise ValueError('Unsupported domain')

    def relation(raw):
        if not isinstance(raw, str):
            raise ValueError('Relation string')
        import re
        match = re.fullmatch(r'(.+?)(<=|>=|=|<|>)(.+)', raw)
        if not match:
            raise ValueError('Expected one relation')
        left, op, right = match.groups()
        if any(c in left + right for c in '=<>'):
            raise ValueError('Chained relation')
        a, b = parse(left), parse(right)
        return {'=': s.Eq, '<': s.Lt, '>': s.Gt, '<=': s.Le, '>=': s.Ge}[op](a, b, evaluate=False)

    def vector(raw):
        if not isinstance(raw, list) or not 2 <= len(raw) <= 3:
            raise ValueError('Vector dimensions')
        return s.Matrix([parse(v) for v in raw])

    def source_domain(source, var, initial):
        """Intersect AST subexpression domains before SymPy cancellation.

        In particular x/x=1 must exclude zero even when the expression reduces
        to 1. Parameterized domains remain unsupported rather than guessed.
        """
        tree = ast.parse(source.strip().replace('^', '**').replace('−', '-').replace('×', '*'), mode='eval')
        valid = initial
        for node in ast.walk(tree):
            if not isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Call)):
                continue
            value = parse(ast.unparse(node))
            if value.has(var):
                valid = valid.intersect(continuous_domain(value, var, s.S.Reals))
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                denominator = parse(ast.unparse(node.right))
                valid = valid - s.solveset(denominator, var, domain=s.S.Reals)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                power = parse(ast.unparse(node.right))
                if power.is_negative:
                    base = parse(ast.unparse(node.left))
                    valid = valid - s.solveset(base, var, domain=s.S.Reals)
        if valid.has(s.ConditionSet):
            raise ValueError('Unresolved domain')
        return valid

    op = request['operation']
    x = variable(request.get('variable', 'x'))
    d = domain(request.get('domain'))
    if x in (symbols['n'], symbols['k']):
        d = d.intersect(s.S.Naturals)
    limitations = ['仅核验给定数学模型；未自动证明自然语言建模或完整解题过程。']
    if op in ('equation', 'inequality'):
        r = relation(request['expression'])
        if r.free_symbols - {x}:
            raise ValueError('Parameterized solution needs case analysis')
        if op == 'equation':
            if not isinstance(r, s.Equality):
                raise ValueError('Expected equality')
            # Preserve original denominators/log restrictions, including x/x.
            raw_left, raw_right = request['expression'].split('=')
            result = s.solveset(r.lhs - r.rhs, x, domain=d)
            # AST domain walker below checks restrictions erased by simplification.
            for source in (raw_left, raw_right):
                result = result.intersect(source_domain(source, x, d))
        else:
            if isinstance(r, s.Equality):
                raise ValueError('Expected inequality')
            result = s.solve_univariate_inequality(r, x, relational=False, domain=d)
            import re
            for source in re.split(r'<=|>=|<|>', request['expression']):
                result = result.intersect(source_domain(source, x, d))
    elif op == 'derivative':
        original = parse(request['expression'])
        result = s.diff(original, x)
        d = source_domain(request['expression'], x, d)
        d = d.intersect(continuous_domain(result, x, s.S.Reals))
        limitations.append('导数在原函数与结果共同有定义处比较；未覆盖端点可导性。')
    elif op == 'evaluate':
        result = s.simplify(parse(request['expression']))
        d = source_domain(request['expression'], x, d)
    elif op == 'sum':
        lower, upper = parse(request['lower']), parse(request['upper'])
        if lower.is_integer is not True or upper.is_integer is not True:
            raise ValueError('Integer sum bounds required')
        result = s.summation(parse(request['expression']), (x, lower, upper))
    elif op == 'system':
        names = request['variables']
        equations = request['equations']
        if not isinstance(names, list) or not 1 <= len(names) <= 3 or len(set(names)) != len(names):
            raise ValueError('System variables')
        vs = [variable(v) for v in names]
        if not isinstance(equations, list) or not 1 <= len(equations) <= 3:
            raise ValueError('System equations')
        expressions = []
        for source in equations:
            r = relation(source)
            if not isinstance(r, s.Equality) or r.free_symbols - set(vs):
                raise ValueError('System relation')
            # Polynomial-only systems avoid denominator cancellation/domain bugs.
            for operand in source.split('='):
                tree = ast.parse(operand.strip().replace('^', '**'), mode='eval')
                for node in ast.walk(tree):
                    if isinstance(node, (ast.BinOp, ast.Call)) and not parse(ast.unparse(node)).is_polynomial(*vs):
                        raise ValueError('System needs explicit domain review')
                    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and parse(ast.unparse(node.right)).free_symbols:
                        raise ValueError('System denominator depends on variables')
            expr = r.lhs - r.rhs
            if not expr.is_polynomial(*vs) or s.Poly(expr, *vs).total_degree() > 4:
                raise ValueError('System degree')
            expressions.append(expr)
        solved = s.solve_poly_system(expressions, *vs)
        if solved is None:
            solved = []
        result = s.FiniteSet(*(s.Tuple(*row) for row in solved))
        if any(v.is_real is None for row in result for v in row):
            raise ValueError('System root reality unresolved')
        if any(v.is_real is not True for row in result for v in row):
            result = s.FiniteSet(*(row for row in result if all(v.is_real is True for v in row)))
    elif op in ('dot', 'cross', 'distance', 'norm'):
        left = vector(request['left'])
        if op == 'norm':
            result = s.sqrt(left.dot(left))
        else:
            right = vector(request['right'])
            if left.shape != right.shape:
                raise ValueError('Vector dimensions differ')
            if op == 'dot':
                result = left.dot(right)
            elif op == 'cross':
                if len(left) != 3:
                    raise ValueError('Cross product requires 3D')
                result = s.Tuple(*left.cross(right))
            else:
                delta = left - right
                result = s.sqrt(delta.dot(delta))
        result = s.simplify(result)
    elif op == 'set':
        # Finite explicit sets, useful for combinations of objective conditions.
        left, right = request['left'], request['right']
        if not isinstance(left, list) or not isinstance(right, list) or len(left) + len(right) > 60:
            raise ValueError('Finite set bounds')
        result = s.FiniteSet(*(parse(v) for v in left)).intersect(s.FiniteSet(*(parse(v) for v in right)))

    def expected_value(raw, sample):
        if isinstance(sample, s.Set):
            if isinstance(raw, list) and len(raw) <= 40:
                return s.FiniteSet(*(s.Tuple(*(parse(v) for v in item)) if isinstance(item, list) else parse(item) for item in raw))
            if raw == 'EmptySet':
                return s.S.EmptySet
            if isinstance(raw, dict):
                return domain(raw)
            raise ValueError('Expected set or interval')
        if isinstance(sample, s.Tuple):
            if not isinstance(raw, list) or len(raw) != len(sample):
                raise ValueError('Expected vector')
            return s.Tuple(*(parse(v) for v in raw))
        return parse(raw)

    if d.is_empty is True:
        raise ValueError('Empty valid domain')
    status, verdict = 'computed', 'unresolved'
    if result.has(s.ConditionSet, s.Sum, s.Integral, s.Derivative):
        status = 'unresolved'
    elif 'expected' in request:
        expected = expected_value(request['expected'], result)
        # Never collapse undefined original domains or unknown symbolic results
        # into an incorrect verdict. No numerical sampling used as a proof.
        if isinstance(result, s.Set):
            difference = s.SymmetricDifference(result, expected)
            equality = True if difference.is_empty is True else False if difference.is_empty is False else None
        elif isinstance(result, s.Tuple):
            parts = [s.simplify(a - b) for a, b in zip(result, expected)]
            equality = True if all(v == 0 for v in parts) else False if any(v.is_zero is False for v in parts) else None
        else:
            if expected.free_symbols - result.free_symbols - {x}:
                raise ValueError('Unexpected answer variables')
            delta = s.simplify(result - expected)
            equality = True if delta == 0 else False if delta.is_zero is False else None
            # Cancellation may make an expected answer appear equal outside its
            # valid domain. For derivatives/evaluations require equal domains.
            if equality is True and isinstance(request['expected'], str) and op in ('evaluate','derivative'):
                valid = source_domain(request['expected'], x, d)
                if valid != d:
                    equality = None
        verdict = 'correct' if equality is True else 'incorrect' if equality is False else 'unresolved'
        status = 'checked' if equality is not None else 'unresolved'
    return {'engine': VERSION, 'operation': op, 'status': status,
            'verdict': verdict, 'result': str(result), 'latex': s.latex(result),
            'domain': str(d), 'assumptions': 'x,y,z,a,b,t为实数；n,k为正整数。', 'limitations': limitations}

def _run_worker(raw):
    try:
        return _compute(validate(json.loads(raw)))
    except (ValueError, TypeError, SyntaxError, KeyError, NotImplementedError):
        return {'status': 'unsupported', 'engine': VERSION,
                'reason': '表达式、定义域或所需分类讨论超出本次工具契约。'}
    except Exception:
        return {'status': 'unresolved', 'engine': VERSION,
                'reason': '符号工具未得出确定结论，未据此判错。'}


if __name__ == '__main__':
    # Bounds stdin before decoding; the parent always reaps timed-out workers.
    print(json.dumps(_run_worker(sys.stdin.read(8001)), ensure_ascii=True))
