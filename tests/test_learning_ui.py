"""Real Streamlit component runs using explicit offline educational fixtures."""
from copy import deepcopy
from streamlit.testing.v1 import AppTest
from test_persistent_learning import setup_work,assess


def page(workspace,view):
    import streamlit as st
    from pathlib import Path
    from core import classroom as c
    from ui.learning_hub import student_workspace,teacher_corrections
    if 'w' not in st.session_state:st.session_state.w=workspace
    class Runtime:
        root=Path.cwd()
        assigned_student='001'
        shared=True
        access=None
        def __init__(self):self.w=st.session_state.w
        def ready(self):return False
        def persist(self,*,strict=False):c.validate_workspace(self.w)
        def image(self,ref):return None
    rt=Runtime()
    if view=='teacher':teacher_corrections(rt,rt.w['submissions'][0])
    else:student_workspace(rt,view=view)


def test_student_submits_correction_and_original_stays_unchanged():
    w,b,sub=setup_work();original=deepcopy(sub)
    app=AppTest.from_function(page,args=(w,'review')).run()
    assert not app.exception
    fields={field.label:field for field in app.text_area}
    fields['本次解题过程'].set_value('逐项检查，A、C符合题意。')
    fields['本次最终答案'].set_value('AC')
    next(button for button in app.button if button.label=='提交作答').click().run()
    assert not app.exception
    assert app.session_state.w['submissions'][0]==original
    assert app.session_state.w['correction_attempts'][0]['answer']=='AC'


def test_teacher_reviews_correction_and_profile_renders_evidence():
    w,b,sub=setup_work();attempt,_=assess(w,sub)
    app=AppTest.from_function(page,args=(w,'teacher')).run()
    assert not app.exception
    next(control for control in app.segmented_control if control.label=='订正结论').set_value('correct')
    next(field for field in app.text_area if field.label=='反馈与依据').set_value('本次完整选项集合已核对，订正正确。')
    next(button for button in app.button if button.label=='保存订正反馈').click().run()
    assert not app.exception
    assert app.session_state.w['correction_reviews'][-1]['verdict']=='correct'
    profile=AppTest.from_function(page,args=(app.session_state.w,'profile')).run()
    assert not profile.exception
    assert profile.dataframe


def test_backend_configured_model_enables_grading_without_frontend_key(monkeypatch):
    from core import backend_client
    monkeypatch.setattr(backend_client,'enabled',lambda:True)
    monkeypatch.setattr(backend_client,'request',lambda method,path,**kwargs:{'model_configured':True} if path=='/health' else [])
    def backend_page(workspace):
        import streamlit as st
        from ui.product import teacher
        class Runtime:
            assigned_student=None
            shared=False
            access={'role':'teacher','code':'offline-fixture'}
            key=None
            def __init__(self):self.w=workspace
            def ready(self):return False
            def image(self,ref):return None
        teacher(Runtime())
    w,b,sub=setup_work()
    app=AppTest.from_function(backend_page,args=(w,)).run()
    assert not app.exception
    assert not next(button for button in app.button if button.label=='开始批改').disabled
