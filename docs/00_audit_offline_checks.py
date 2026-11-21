"""Audit-only offline checks. No paid API requests; SDK placeholders are import-only.
Run from project root with a Python environment containing Streamlit, SymPy and Pillow:
python docs/00_audit_offline_checks.py
This is NOT a substitute for real SDK integration, OCR accuracy or browser acceptance tests.
"""
import sys, types, tempfile, unittest, io, os
from pathlib import Path
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
# Deliberately block every network-client construction, even if an SDK is installed.
sdk = types.ModuleType("openai")
class ForbiddenClient:
    def __init__(self, *args, **kwargs):
        raise AssertionError("Audit forbids network API calls")
sdk.OpenAI = ForbiddenClient
for name in ("APIConnectionError", "APIStatusError", "APITimeoutError"):
    setattr(sdk, name, type(name, (Exception,), {}))
sys.modules["openai"] = sdk
dotenv = types.ModuleType("dotenv")
dotenv.dotenv_values = lambda *args, **kwargs: {}
sys.modules["dotenv"] = dotenv

from core import product as p, education as e, classroom as c
from core import collaboration as co, agent as ag, presentation as v
from core import uploads as up, math_tools as mt
from core.limits import UsageLimitError
from PIL import Image

def row(sid="1001", answer="A", question="Choose A or B"):
    return dict(student_id=sid, question=question, answer=answer, steps=[],
                question_type="选择题", question_no="1")

def response(verdict="incorrect"):
    return dict(verdict=verdict, final_answer_status=verdict, basis="fixture",
                evidence_id="ANSWER", first_error_step=None,
                process_checked=False, uncertainty_reason="other")

def batch(rows):
    workspace = c.new_workspace()
    assignment = p.create_batch(workspace, "audit", rows, grading_policy=p.CLASSROOM_POLICY)
    return workspace, assignment

class AuditChecks(unittest.TestCase):
    def test_01_objective_reuse_and_idempotency(self):
        w, b = batch([row("1001"), row("1002")])
        calls = []
        def call(*a, **k):
            calls.append(k["purpose"])
            return response()
        p.run_batch(w, b["id"], call)
        self.assertEqual(len(calls), 1)
        p.run_batch(w, b["id"], call)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(w["notebook"]), 2)

    def test_02_confirmed_reference_skips_model(self):
        w, b = batch([row()])
        groups, _ = p.reference_catalog(w, b)
        p.save_references(w, b["id"], {next(iter(groups)): ("A", "")}, p.digest({}))
        p.run_batch(w, b["id"], lambda *a, **k: self.fail("Unexpected API call"))
        self.assertEqual(p.effective(w, w["submissions"][0])["verdict"], "correct")

    def test_03_resume_keeps_success(self):
        w, b = batch([row("1001", "A"), row("1002", "B")])
        calls = []
        def limited(*a, **k):
            calls.append(1)
            if len(calls) == 2:
                raise UsageLimitError("fixture")
            return response()
        p.run_batch(w, b["id"], limited)
        self.assertEqual(p.batch_execution(w, b["id"])["complete"], 1)
        resumed = []
        p.run_batch(w, b["id"], lambda *a, **k: (resumed.append(1) or response()))
        self.assertEqual(len(resumed), 1)

    def test_04_blank_skips_model_and_notebook(self):
        w, b = batch([row(answer="")])
        p.run_batch(w, b["id"], lambda *a, **k: self.fail())
        self.assertEqual(p.effective(w, w["submissions"][0])["verdict"], "incorrect")
        self.assertEqual(w["notebook"], [])

    def test_05_REPRO_uncertain_keeps_old_active_error(self):
        w, b = batch([row()])
        p.run_batch(w, b["id"], lambda *a, **k: response())
        sub = w["submissions"][0]
        p.quick_check(sub, lambda *a, **k: response("uncertain"), force=True)
        p.sync_notebook(w, sub["id"])
        self.assertEqual(p.effective(w, sub)["verdict"], "uncertain")
        self.assertTrue(w["notebook"][0]["active_error"])

    def test_06_teacher_correction_closes_error(self):
        w, b = batch([row()])
        p.run_batch(w, b["id"], lambda *a, **k: response())
        sub = w["submissions"][0]
        v.override_grade(w, sub["id"], "correct", "fixture")
        p.sync_notebook(w, sub["id"])
        self.assertFalse(w["notebook"][0]["active_error"])

    def test_07_REPRO_old_solution_not_bound_to_reference(self):
        w, b = batch([row()])
        sub = w["submissions"][0]
        sub["solutions"] = [dict(id="old", status="completed", mode="full",
            correction=dict(answer="OLD", reference_tool=dict(status="not_applicable")))]
        sub["reference_revision"] = "new-reference"
        self.assertEqual(p.correction_for(sub)["answer"], "OLD")

    def test_08_REPRO_OCR_punctuation_splits_question(self):
        w, b = batch([row("1001", question="求 x 的值"), row("1002", question="求x的值。")])
        self.assertEqual(len(b["questions"]), 2)

    def test_09_REPRO_derivative_routing_not_automatic(self):
        sub = e.normalize_submission(dict(student_id="1001", question="求导 x**2", steps=[], answer="2*x"))
        self.assertEqual(sub["task_type"], "general")
        self.assertEqual(mt.evidence(sub)["status"], "not_applicable")
        sub.update(task_type="derivative", tool_expression="x**2")
        self.assertEqual(mt.evidence(sub)["final_answer_status"], "correct")

    def test_10_student_scope_and_write_guard(self):
        w, b = batch([row("1001"), row("1002")])
        view = co.student_view(w, "1001")
        self.assertEqual({s["student_id"] for s in view["submissions"]}, {"1001"})
        after = deepcopy(view)
        after["submissions"][0]["student_id"] = "1002"
        with self.assertRaises(ValueError):
            co._student_changes(view, after, "1001")

    def test_11_REPRO_demo_number_is_sufficient_identity(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="audit-temp-") as root:
            code = co.create("audit", root, number_demo=True, creator_id="audit-offline")
            w = co.load(code, root)
            before = deepcopy(w)
            w["student_roster"] = ["1001"]
            co.save(code, before, w, root)
            access = co.resolve(co.demo_code(code.split(".")[0], "1001"), root)
            self.assertEqual(access["student_id"], "1001")

    def test_12_persistence_and_stale_write_guard(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="audit-temp-") as root:
            target = Path(root) / "workspace.json"
            w, b = batch([row()])
            c.save(w, target)
            stale = deepcopy(w)
            c.save(w, target)
            with self.assertRaises(ValueError):
                c.save(stale, target)
            self.assertEqual(c.load(target)["storage_version"], 2)

    def test_13_three_way_merge(self):
        self.assertEqual(co._merge(dict(a=1,b=1), dict(a=2,b=1), dict(a=1,b=2)), dict(a=2,b=2))
        with self.assertRaises(ValueError):
            co._merge(dict(a=1), dict(a=2), dict(a=3))

    def test_14_agent_tool_loop_and_idempotency(self):
        w, b = batch([row()])
        sub = w["submissions"][0]
        calls = []
        def call(*a, **k):
            calls.append(1)
            return dict(action="verify_math" if len(calls)==1 else "ask_student",
                        goal="check", rationale="fixture", evidence_ids=["QUESTION"],
                        message="" if len(calls)==1 else "Which option?",
                        step=None, target="original", verification_claim="unverified")
        result = ag.run(w, sub["id"], "1001", call)
        self.assertEqual((result["model_calls"], result["tool_calls"], result["status"]),
                         (2, 1, "waiting_student"))
        ag.run(w, sub["id"], "1001", call)
        self.assertEqual(len(calls), 2)

    def test_15_agent_rejects_other_student(self):
        w, b = batch([row()])
        with self.assertRaises(ValueError):
            ag.run(w, w["submissions"][0]["id"], "1002", lambda *a, **k: self.fail())

    def test_16_rejects_fabricated_evidence(self):
        sub = e.normalize_submission(dict(row(), steps=["x=1"]))
        payload = dict(method_summary="m", recommendation="r", knowledge_points=[], uncertainties=[],
            overall="error_found", final_answer_status="incorrect",
            steps=[dict(number=1, verdict="incorrect", observation="o", evidence_quote="invented")],
            first_error_step=1, error_patterns=[], hypotheses=[])
        with self.assertRaises(ValueError):
            e.validate_analysis(payload, sub)

    def test_17_images_and_local_PDF(self):
        from core.ocr import provider_image
        source = io.BytesIO()
        Image.new("RGB", (200, 200), "white").save(source, "PNG")
        payload, mime = provider_image(source.getvalue())
        self.assertEqual(mime, "image/png")
        pdf = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(pdf, "PDF")
        self.assertEqual(len(up._pdf_pages(pdf.getvalue(), 24)), 1)

    def test_18_default_limits(self):
        from core.limits import Limits
        self.assertEqual((Limits().session_day, Limits().session_minute), (50, 6))

if __name__ == "__main__":
    unittest.main(verbosity=2)

