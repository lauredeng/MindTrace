"""Local, accessible interactive pie chart. No network dependency."""
from pathlib import Path
import streamlit.components.v1 as components
_pie=components.declare_component('mindtrace_cause_pie',path=str(Path(__file__).parent/'components'/'cause_pie'))

def cause_pie(rows,total,selected=None,key='cause_pie'):
    return _pie(rows=rows,total=total,selected=selected,key=key,default=None)
