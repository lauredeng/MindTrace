"""Deterministic acceptance fixture, not model or classroom evaluation."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import education as e, product as p, presentation as v, classroom as c

ROOT=Path.cwd();OUT=ROOT/'artifacts/final-ui-fixture';OUT.mkdir(parents=True,exist_ok=True)
path=OUT/'classroom_v1.json'
if path.exists():
    print('Existing isolated fixture retained.');raise SystemExit(0)
slots=[(str(i),'选择题','','') for i in range(1,11)]+[(str(i),'填空题','','') for i in range(11,15)]+[
    ('15','解答题','',''),('16','解答题','',''),('17(1)','解答题','17','1'),('17(2)','解答题','17','2'),('18','解答题','',''),('19','解答题','','')]
rows=[];expected={}
for index,(label,kind,parent,child) in enumerate(slots):
    errors=index%5;missing=1 if index==4 else 0;unreadable=1 if index==3 else 0;pending=1 if index==2 else 0
    expected[label]={'errors':errors,'valid':5-missing-unreadable-pending,'pending':pending,'not_submitted':missing,'unreadable':unreadable}
    for student in range(5):
        answer=3 if student<errors or index==2 and student==4 else 2
        row={'student_id':'S'+str(student+1).zfill(2),'question_no':label,'question_type':kind,
            'parent_question_no':parent,'subquestion_no':child,'topic':'综合应用与证明',
            'question':f'解方程x+{index+1}={index+3}','steps':[f'x+{index+1}={index+3}',f'x={answer}'],'answer':f'x={answer}'}
        if index==3 and student==4:row.update(submission_status='unreadable',steps=['[无法辨认]'],answer='')
        if index==4 and student==4:row.update(submission_status='not_submitted',steps=[],answer='')
        rows.append(row)
w=c.new_workspace();batch=p.create_batch(w,'高一数学 · 单元作业','' if False else rows,'heatmap_acceptance_fixture')
for sid in list(batch['submission_ids']):
    sub=next(s for s in w['submissions'] if s['id']==sid)
    if sub['submission_status']!='submitted':continue
    is_error=sub['answer']=='x=3'
    quick={'verdict':'incorrect' if is_error else 'correct','final_answer_status':'incorrect' if is_error else 'correct',
        'basis':'验收构造：移项后应得x=2。','evidence_id':'S2','evidence_quote':sub['steps'][1],
        'first_error_step':2 if is_error else None,'knowledge_points':['等式变形'],'category':'计算失误' if is_error else p.UNKNOWN,
        'category_basis':'验收构造的候选原因，不是真实学生诊断。','process_checked':True}
    p.quick_check(sub,lambda *a,_q=quick,**kw:_q)
    if is_error:
        data={'topic':sub['topic'],'knowledge_points':['等式变形'],'method_summary':'移项时对常数的处理不正确。',
            'overall':'error_found','final_answer_status':'incorrect','steps':[
                {'number':1,'verdict':'correct','observation':'照录原方程。','evidence_quote':sub['steps'][0]},
                {'number':2,'verdict':'incorrect','observation':'两边同减常数，应得到x=2。','evidence_quote':sub['steps'][1]}],
            'first_error_step':2,'error_patterns':[{'label':'移项计算错误','step_numbers':[2],'severity':1,'evidence_quote':sub['steps'][1]}],
            'hypotheses':[],'uncertainties':['验收构造响应，不是真实模型评测。'],'recommendation':'核对等式两边相同的运算。',
            'correction':{'answer':'x=2','steps':[{'text':sub['steps'][0],'reason':'原方程'},
                {'text':'x=2','reason':'等式两边同时减去相同常数'}],'knowledge_points':['等式变形'],
                'category':'计算失误','category_basis':'验收构造原因，尚需本人确认。',
                'supplements':[{'kind':'method','content':'若a=b，则a-c=b-c。','conditions':'等式两边同时减去同一个实数。',
                                'connection':'本题两边同减常数，得到未知数的值。'}],'uncertainties':[]}}
        p.deep_analyze(sub,lambda *a,_d=data,**kw:_d)
    if not (sub['question_no']=='3' and sub['student_id']=='S05'):
        v.confirm_short(w,sub['id'])
for sid in list(batch['submission_ids']):
    sub=next(s for s in w['submissions'] if s['id']==sid)
    item=p.sync_notebook(w,sub['id'])
    if item and sub['student_id']=='S01':
        number=next(i for i,slot in enumerate(slots) if slot[0]==sub['question_no'])
        cause=['计算失误','公式或定理误用','推理或关键步骤遗漏','审题失误'][number%4]
        p.edit_entry(w,item['id'],cause,[],'验收脚本模拟的分类确认，用于检查统计联动。',True)
batch=next(b for b in w['batches'] if b['id']==batch['id']);batch['status']='processed'
c.save(w,path)
actual=v.heatmap_rows(w,batch['id'])
for r in actual:
    assert all(r[k]==value for k,value in expected[r['label']].items()),r
notes=p.notebook_rows(w,'S01')
manifest={'batch_id':batch['id'],'expected_questions':expected,'student':'S01',
    'notebook_counts':{kind:sum(v.kind(n)==kind for n in notes) for kind in v.TYPES},
    'causes':{label:len(group['ids']) for label,group in v.cause_distribution(notes)[0].items()},
    'note':'All records and confirmations are constructed offline acceptance data, not actual students or new API calls.'}
(OUT/'expected.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('Isolated fixture created:20 questions,100 records; statistics independently checked.')

