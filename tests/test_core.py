from core.analyzer import analyze
from core.storage import save_runs, load_runs

def test_correct():
    r=analyze({'student_id':'1','question':'(3*x**2+1)**5','student_answer':'30*x*(3*x**2+1)**4'})
    assert r.status=='correct'

def test_missing_inner_derivative():
    r=analyze({'student_id':'2','question':'(3*x**2+1)**5','student_answer':'5*(3*x**2+1)**4'})
    assert r.status=='incorrect'
    assert '遗漏内层导数' in r.label

def test_not_overdiagnose():
    r=analyze({'student_id':'3','question':'x**3','student_answer':'3*x'})
    assert r.status=='incorrect'
    assert r.label=='结果不一致（具体错因待核实）'

def test_unverified_does_not_execute_code():
    r=analyze({'student_id':'4','question':'__import__("os")','student_answer':'0'})
    assert r.status=='unverified'

def test_json_roundtrip(tmp_path):
    target=tmp_path/'runs.json'
    save_runs([{'n':1}],target)
    assert load_runs(target)==[{'n':1}]
