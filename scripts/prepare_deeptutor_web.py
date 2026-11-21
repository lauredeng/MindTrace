"""Apply the small, attributed MindTrace overlay to a pinned upstream checkout."""
from pathlib import Path
import argparse
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
COMMIT='341af371bf8143b2da3569084edf8e6cb46d7404'


def prepare(checkout):
    checkout=Path(checkout).resolve()
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip()
    if actual!=COMMIT:raise ValueError('DeepTutor版本不匹配；请先检出文档指定版本。')
    overlay=ROOT/'integrations'/'deeptutor'/'web'
    route=checkout/'web'/'app'/'mindtrace';route.mkdir(exist_ok=True)
    component=checkout/'web'/'components'/'mindtrace';component.mkdir(exist_ok=True)
    shutil.copyfile(overlay/'page.tsx',route/'page.tsx')
    for name in ('LearningDashboard.tsx','MindTrace.module.css'):
        shutil.copyfile(overlay/name,route/name)
    shutil.copyfile(overlay/'MindTraceDock.tsx',component/'MindTraceDock.tsx')
    layout=checkout/'web'/'app'/'layout.tsx';text=layout.read_text(encoding='utf-8')
    marker='import MindTraceDock from "@/components/mindtrace/MindTraceDock";'
    if marker not in text:
        text=marker+'\n'+text
        text=text.replace('<ToastViewport />','<ToastViewport />\n          <MindTraceDock />')
    text=text.replace('title: "DeepTutor"','title: "MindTrace 循理 AI"')
    text=text.replace('description: "Agent-native intelligent learning companion"','description: "高中数学作业批改、原题辅导与学习证据"')
    text=text.replace('lang="en"','lang="zh"')
    layout.write_text(text,encoding='utf-8')
    effort=checkout/'web'/'lib'/'reasoning-effort.ts'
    code=effort.read_text(encoding='utf-8')
    # Upstream ordinary-user grants may emit null for optional supported levels;
    # keep the native selector and guard only that wire-format mismatch.
    original='values.map((value) => value.trim())'
    guarded='(Array.isArray(values) ? values : []).map((value) => value.trim())'
    if guarded not in code:
        if original not in code:raise ValueError('推理档位兼容修正与固定源码不匹配。')
        effort.write_text(code.replace(original,guarded),encoding='utf-8')
    (route/'NOTICE.txt').write_text('MindTrace product entry adapter. The surrounding application is HKUDS/DeepTutor, Apache-2.0.\nPinned upstream: '+COMMIT+'\nModified: root layout adds MindTraceDock and MindTrace metadata/language; reasoning-effort.ts guards null optional levels. MindTrace entry adds notebook, official-FSRS review and evidence UI, reusing upstream MarkdownRenderer. Original copyright and LICENSE retained.\n',encoding='utf-8')
    print('MindTrace overlay prepared; official teaching UI and runtime preserved.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('checkout');prepare(parser.parse_args().checkout)
