"""Prepare an isolated browser fixture using actual API reports, not fabricated diagnoses."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from core import education as e,classroom as c
root=Path.cwd();out=root/'artifacts'/'v1-browser-20261107-A'
out.mkdir(parents=True,exist_ok=True)
path=out/'classroom_v1.json'
if path.exists():
    print('Existing isolated browser workspace retained.')
else:
    w=c.load(root/'artifacts/v1-live/constructed_loop_workspace.json')
    cases=json.loads((root/'data/highschool_examples.json').read_text(encoding='utf-8-sig'))
    report=json.loads((root/'artifacts/v1-live/math.json').read_text(encoding='utf-8'))
    existing={s['question_no'] for s in w['submissions']}
    for item in report['checks']:
        if item['status']!='completed' or item['name'] in existing:
            continue
        source=next(row for row in cases if row['question_no']==item['name'])
        sub=e.normalize_submission(source,'live_constructed_fixture')
        sub['analyses']=[item['result']['record']]
        w['submissions'].append(sub)
    vision=json.loads((root/'artifacts/v1-live/vision.json').read_text(encoding='utf-8'))['checks'][0]['result']['draft']
    image=(root/'artifacts/v1-live/printed_fixture_1.png').read_bytes()
    ref=c.attach_image(image,out/'classroom_images')
    for sub in w['submissions']:
        if sub['question_no'] in ('Q01','Q05'):
            sub['image_ref']=ref
            sub['transcription']=vision['transcription']
    ids={v['id'] for v in w['usage']}
    for suite in ('math','vision','learning'):
        r=json.loads((root/'artifacts/v1-live'/f'{suite}.json').read_text(encoding='utf-8'))
        w['usage'].extend(v for v in r['usage'] if v['id'] not in ids)
        ids={v['id'] for v in w['usage']}
    c.save(w,path)
    print('Isolated fixture: real API outputs, constructed anonymous materials, reference replay flagged.')

