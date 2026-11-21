"""Launch with the official runtime's Python interpreter; keep model keys server-side."""
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import dotenv_values

runtime=ROOT/'.local_data'/'deeptutor'
runtime.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('DEEPTUTOR_HOME',str(runtime))
os.environ.setdefault('MINDTRACE_ENV','development')
os.environ['MINDTRACE_HEADLESS']='1'
os.environ.setdefault('MINDTRACE_DATA_DIR',str(ROOT/'.local_data'/'development'))
os.environ.setdefault('MINDTRACE_CLASSROOM_DIR',str(ROOT/'.local_data'/'development'/'classrooms'))
os.environ.setdefault('MINDTRACE_DATABASE',str(ROOT/'.local_data'/'development'/'mindtrace.db'))
local=dotenv_values(ROOT/'.env',interpolate=False)
for name in ('MINDTRACE_TUTOR_API_KEY','MINDTRACE_TUTOR_BASE_URL','MINDTRACE_TUTOR_MODEL',
             'MINDTRACE_TUTOR_SECURE_COOKIE'):
    if local.get(name):os.environ.setdefault(name,str(local[name]))

if __name__=='__main__':
    import uvicorn
    uvicorn.run('integrations.deeptutor.server:app',host='127.0.0.1',port=int(os.getenv('MINDTRACE_TUTOR_PORT','8591')))
