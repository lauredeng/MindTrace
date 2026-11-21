"""Explicit anonymous teacher/student integration fixture; never model evidence."""
from pathlib import Path
import json
import os
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MINDTRACE_ENV','development');os.environ['MINDTRACE_HEADLESS']='1'
os.environ.setdefault('MINDTRACE_DATA_DIR',str(ROOT/'.local_data'/'development'))
os.environ.setdefault('MINDTRACE_CLASSROOM_DIR',str(ROOT/'.local_data'/'development'/'classrooms'))
os.environ.setdefault('MINDTRACE_DATABASE',str(ROOT/'.local_data'/'development'/'mindtrace.db'))
from core import classroom as c,collaboration as x,education as e,product as p


def prepare():
    out=ROOT/'artifacts'/'deeptutor';out.mkdir(parents=True,exist_ok=True)
    file=out/'fixture.json'
    if file.exists():
        data=json.loads(file.read_text(encoding='utf-8'))
        try:x.resolve(data['student_code']);return data
        except (ValueError,OSError):pass
    teacher=x.create('DeepTutor 接入 · 匿名联动验证')
    w=x.load(teacher)
    question='已知函数 f(x)=ln(x)-a*x，其中 a>0。求函数的单调区间及最大值。'
    batch=p.create_batch(w,'函数与导数 · 离线联动示例',[
        {'student_id':sid,'question_no':'17','question':question,'topic':'函数与导数','question_type':'解答题',
         'steps':['定义域为x>0。',"f\u2032(x)=1/x。",'因此函数恒增，无最大值。'],'answer':'无最大值。'}
         for sid in ('DEMO-001','DEMO-002')],source='constructed_examples')
    for submission_id in [s['id'] for s in w['submissions']]:
        sub=next(s for s in w['submissions'] if s['id']==submission_id)
        report={'topic':sub['topic'],'knowledge_points':['对数函数求导','含参函数单调性','极值与最大值'],
            'method_summary':'离线教师材料：第二步遗漏-a，后续单调性与最大值判断因此错误。',
            'overall':'error_found','final_answer_status':'incorrect',
            'steps':[{'number':i,'verdict':'correct' if i==1 else 'incorrect',
                'observation':'定义域正确。' if i==1 else '第二步漏掉-a，第三步的单调性结论不成立。','evidence_quote':s}
                for i,s in enumerate(sub['steps'],1)],'first_error_step':2,'error_patterns':[],
            'hypotheses':[],'uncertainties':['构造匿名作答，仅用于验证联动，不是模型实测。'],
            'recommendation':'比较1/x与a的大小，结合x>0、a>0讨论。'}
        e.analyze_submission(sub,lambda *args,_r=report,**kw:_r)
        c.review(w,sub['id'],'confirm','求导遗漏线性项', ['对数函数求导','单调性'],
            '正确导数为1/x-a；在(0,1/a)上递增，在(1/a,+∞)上递减；最大值为-ln(a)-1。',
            'fixture-review-'+sub['id'],first_error_step=2)
        p.sync_notebook(w,sub['id'])
    c.save(w,x._folder(x.resolve(teacher)['class_id'])/'workspace.json')
    data={'teacher_code':teacher,'student_code':x.invite(teacher,'DEMO-001'),
          'peer_code':x.invite(teacher,'DEMO-002'),'submission_id':w['submissions'][0]['id'],
          'peer_submission_id':w['submissions'][1]['id'],'fixture_only':True}
    file.write_text(json.dumps(data),encoding='utf-8');return data


if __name__=='__main__':
    prepare();print('Anonymous teacher/student fixture prepared; credentials remain in ignored artifacts.')
