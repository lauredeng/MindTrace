"""Clickable, local-only Streamlit heatmap, no external frontend dependencies."""
from pathlib import Path
import streamlit.components.v1 as components
_component=components.declare_component('mindtrace_question_heatmap',path=str(Path(__file__).parent/'components'/'question_heatmap'))

def question_heatmap(rows,selected=None,key='question_heatmap'):
    fields=('id','label','question_type','parent','child','errors','valid','pending','not_submitted','unreadable','ratio')
    return _component(rows=[{field:r[field] for field in fields} for r in rows],selected=selected,key=key,default=None)
