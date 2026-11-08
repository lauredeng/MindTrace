"""Small shared presentation primitives for the Academic-inspired product shell."""
from html import escape
import streamlit as st

ICONS={
 'people':'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M16 3a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-3.87"/><circle cx="9" cy="7" r="4"/>',
 'review':'<path d="M9 5H5v16h14V5h-4M9 3h6v4H9zM8 13h8M8 17h5"/>',
 'book':'<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 3H20v19H6.5A2.5 2.5 0 0 1 4 19.5V5.5A2.5 2.5 0 0 1 6.5 3z"/>',
 'chart':'<path d="M3 3v18h18M8 16v-4M13 16V8M18 16V5"/>',
 'check':'<path d="m5 12 4 4L19 6"/>',
}
def icon(name):
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+ICONS.get(name,ICONS['chart'])+'</svg>'

def page_header(title,description,kicker='',tag=''):
    st.markdown('<div class="product-heading"><div><div class="product-kicker">'+escape(kicker)+'</div><h1>'+escape(title)+'</h1><p>'+escape(description)+'</p></div>'+
        ('<span class="product-tag">'+escape(tag)+'</span>' if tag else '')+'</div>',unsafe_allow_html=True)

def metric(label,value,detail='',accent=False,icon_name='chart'):
    st.markdown('<div class="academic-metric '+('accent' if accent else '')+'"><div class="metric-top"><span class="metric-symbol">'+icon(icon_name)+'</span><span>'+escape(label)+'</span></div><div class="metric-number">'+escape(str(value))+'</div><div class="metric-detail">'+escape(detail)+'</div></div>',unsafe_allow_html=True)

def note(title,text):
    st.markdown('<div class="context-note"><b>'+escape(title)+'</b><p>'+escape(text)+'</p></div>',unsafe_allow_html=True)

