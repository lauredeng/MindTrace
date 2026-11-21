"""Allowlisted source export: never open credential files or runtime artifacts."""
from pathlib import Path
import argparse
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'core/uploads.py', 'ui/assignment_upload.py', 'tests/test_assignment_upload.py',
    'core/execution.py', 'core/records.py', 'tests/test_audit_fixes.py', 'AUDIT_FIXES_ACCEPTANCE.md',
    'core/agent.py', 'ui/agent.py', 'tests/test_agent.py', 'tests/test_agent_ui.py', 'AGENT_ACCEPTANCE.md',
    'scripts/evaluate_agent_live.py', 'scripts/serve_agent_fixture.py', 'scripts/browser_agent.py', 'scripts/serve_agent_replay.py',
    'core/collaboration.py', 'ui/collaboration.py', 'tests/test_collaboration.py', 'tests/test_collaboration_ui.py',
    'scripts/serve_collaboration_fixture.py', 'scripts/browser_collaboration.py', 'CROSS_BROWSER_ACCEPTANCE.md',
    'BATCH_RECOVERY_ACCEPTANCE.md', 'scripts/serve_batch_failure_fixture.py', 'scripts/browser_batch_recovery.py',
    'scripts/browser_home_unified.py',
    'HOME_FOLLOWUP_ACCEPTANCE.md', 'scripts/browser_home_followup.py',
    'FIVE_FIXES_ACCEPTANCE.md', 'scripts/browser_five_fixes.py',
    'ui/design.py', 'ui/pie.py', 'ui/components/cause_pie/index.html',
    'tests/navigation_helpers.py', 'scripts/browser_academic_ui.py', 'ACADEMIC_UI_ACCEPTANCE.md',
    'app.py', 'README.md', 'ACCEPTANCE.md', 'PRODUCT_ACCEPTANCE.md', 'SECURITY.md', 'DEPLOYMENT.md', '.gitignore',
    'requirements.txt', 'requirements-dev.txt', 'packages.txt', 'start.bat', '.streamlit/config.toml',
    'assets/style.css', 'data/demo.csv', 'core/__init__.py', 'core/ai.py',
    'core/analyzer.py', 'core/ocr.py', 'core/storage.py', 'core/workflow.py',
    'core/settings.py', 'core/limits.py', '.streamlit/secrets.example.toml',
    'scripts/export_source.py', 'scripts/check_live_api.py', 'scripts/browser_acceptance.py',
    'tests/test_core.py', 'tests/test_workflow.py', 'tests/test_ui.py', 'tests/test_security.py',
    'tests/conftest.py', 'tests/test_limits.py',
    'AUDIT_V1.md', 'V1_ACCEPTANCE.md', 'V1_COMPARISON.md', 'LIVE_ACCEPTANCE.md',
    'core/classroom.py', 'core/education.py', 'core/math_tools.py', 'core/usage.py',
    'ui/__init__.py', 'ui/workbench.py', 'ui/teacher.py', 'ui/student.py',
    'data/highschool_examples.json', 'tests/test_education.py', 'tests/test_studio_ui.py',
    'tests/test_runtime_v1.py', 'scripts/evaluate_v1_live.py', 'scripts/browser_v1.py',
    'scripts/prepare_browser_v1.py', 'scripts/complete_reference_check.py',
    'core/presentation.py', 'ui/results.py', 'ui/heatmap.py', 'ui/components/question_heatmap/index.html',
    'tests/test_presentation.py', 'scripts/prepare_final_ui_fixture.py', 'scripts/browser_final_ui.py', 'FINAL_UI_ACCEPTANCE.md',
    'core/product.py', 'core/answer_keys.py', 'ui/product.py',
    'tests/test_product.py', 'tests/test_product_ui.py', 'tests/test_answer_keys.py',
    'scripts/evaluate_v12_live.py', 'scripts/capture_v12_real.py',
    'scripts/serve_v12_fixture.py', 'scripts/browser_v12_offline.py',
    'V12_AUDIT.md', 'V12_ACCEPTANCE.md',
    'scripts/summarize_v1_live.py', 'ui/experience.py', 'scripts/browser_v11.py', 'V11_ROUND1.md',
)
FILES += (
    'core/math_kernel.py','core/exercise_review.py','core/question_patterns.py',
    'data/math_reference_patterns.json','tests/test_math_kernel.py',
    'docs/07_math_capability_upgrade.md','licenses/sympy-LICENSE.txt',
    'requirements.in', 'requirements.lock.txt', 'pytest.ini', '.github/workflows/test.yml',
    'tests/test_core_regressions.py', 'tests/test_version_consistency.py', 'tests/ui_fixture.py',
    'scripts/verify_ui.py', 'docs/00_current_project_audit.md', 'docs/01_open_source_research.md',
    'docs/02_target_architecture.md', 'docs/02_implementation_plan.md', 'docs/03_phase01_acceptance.md',
    'tests/test_batch_reliability.py', 'docs/04_batch_reliability.md',
    'core/identities.py','core/learning_records.py','core/learning_validation.py','core/review_scheduler.py',
    'core/learning_service.py',
    'core/repository.py','core/background.py','core/backend_client.py','core/backup.py',
    'api/__init__.py','api/app.py','ui/learning_hub.py','ui/background.py',
    'scripts/run_worker.py','scripts/start_development.ps1','scripts/manage_backup.py','scripts/verify_learning_ui.py',
    'tests/test_persistent_learning.py','tests/test_backend_api.py','tests/test_learning_ui.py','tests/platform_fixture.py',
    'tests/test_recovery_and_assets.py','scripts/verify_cross_browser.py',
    'licenses/fsrs-LICENSE.txt','licenses/fastapi-LICENSE.txt','licenses/uvicorn-LICENSE.txt',
    'docs/05_platform_upgrade.md','docs/06_development_and_recovery.md','docs/THIRD_PARTY_NOTICES.md',
)
FILES += (
    'core/tutor_bridge.py','core/tutor_client.py','ui/tutoring.py',
    'integrations/deeptutor/runtime.py','integrations/deeptutor/server.py',
    'integrations/deeptutor/requirements.lock.txt','integrations/deeptutor/web/page.tsx',
    'integrations/deeptutor/web/MindTraceDock.tsx','licenses/deeptutor-LICENSE.txt',
    'scripts/run_deeptutor.py','scripts/prepare_deeptutor_web.py','scripts/prepare_tutor_fixture.py',
    'scripts/verify_deeptutor_ui.py','scripts/verify_deeptutor_live.py',
    'scripts/install_deeptutor.ps1','scripts/start_deeptutor.ps1',
    'tests/test_tutor_bridge.py','docs/08_deeptutor_integration.md',
    'core/tutor_learning.py','tests/test_tutor_learning.py','integrations/deeptutor/tools.py',
    'integrations/deeptutor/plugin/pyproject.toml','integrations/deeptutor/plugin/mindtrace_deeptutor_plugin.py',
    'integrations/deeptutor/web/LearningDashboard.tsx','integrations/deeptutor/web/MindTrace.module.css',
    'scripts/verify_deeptutor_tools.py','scripts/verify_student_learning_loop.py','docs/09_student_learning_upgrade.md',
)
TEMPLATE = """DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_VISION_MODEL=deepseek-flash
DEEPSEEK_TIMEOUT_SECONDS=90
DEEPSEEK_MAX_RETRIES=0
DEEPSEEK_INPUT_PRICE_PER_MILLION=
DEEPSEEK_OUTPUT_PRICE_PER_MILLION=
DEEPSEEK_PRICE_CURRENCY=CNY
MINDTRACE_TUTOR_API_KEY=
MINDTRACE_TUTOR_BASE_URL=https://api.deepseek.com
MINDTRACE_TUTOR_MODEL=deepseek-flash
VISION_PROVIDER=dashscope
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_VISION_MODEL=qwen3.8-flash
"""


def linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def export_source(root=ROOT, destination=None):
    root = Path(root).resolve()
    export_dir = root / 'exports'
    destination = Path(destination) if destination else export_dir / 'MindTrace-source.zip'
    if destination.resolve().parent != export_dir.resolve() or destination.suffix != '.zip':
        raise ValueError('Export destination must be a .zip directly inside exports/.')
    if linked(export_dir):
        raise ValueError('Export directory cannot be a link.')
    payloads = {}
    for name in FILES:
        path = root / name
        if not path.exists():
            continue
        if linked(path) or any(linked(p) for p in path.parents):
            raise ValueError('Linked source paths are not allowed.')
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('Source path is invalid.')
        data = path.read_bytes()
        # Reject common hardcoded key shapes without ever printing the match.
        # This is not a complete secret detector.
        if re.search(rb'sk-[A-Za-z0-9_-]{20,}', data):
            raise ValueError('Possible hardcoded credential detected; export refused.')
        payloads['mindtrace_mvp/' + name] = data
    payloads['mindtrace_mvp/.env.example'] = TEMPLATE.encode('utf-8')
    export_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='MindTrace-Academic-UI-source.zip', help='Filename directly inside exports/; existing files are never overwritten.')
    args = parser.parse_args()
    try:
        if Path(args.name).name != args.name:
            raise ValueError('Use a filename only for --name.')
        print('Source export created: ' + str(export_source(destination=ROOT / 'exports' / args.name)))
    except (OSError, ValueError) as exc:
        raise SystemExit('Export refused: ' + str(exc)) from None
