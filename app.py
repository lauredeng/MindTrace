"""MindTrace: teacher-first local workspace, retaining student learning flows."""
import hashlib
import html
import json
from copy import deepcopy
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from core.ai import ai_ready as server_ai_ready, ask_ai as request_ai, TEACHER_PROMPT, TUTOR_PROMPT
from core.settings import development_mode, developer_enabled, setting
from core.analyzer import analyze
from core.ocr import recognize_image as request_ocr, prepare_image
from core.storage import load_runs as disk_load, append_record as disk_append, save_review as disk_review, STUDENT_STORE
from core.workflow import read_csv, make_run, make_exercise, import_run, REQUIRED
from ui.experience import PAGES as STUDIO_PAGES, render as render_studio, navigation
from ui.design import BRAND_NAME, BRAND_ENGLISH, BRAND_TITLE

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title=BRAND_TITLE, page_icon='📘', layout='wide')
st.markdown('<style>' + (ROOT / 'assets/style.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)
PAGES = STUDIO_PAGES + ['教师批量分析', '证据复核与统计', '学生辅导体验', '学习认知画像', '运行记录']
STATUS = {'correct': '结果正确', 'incorrect': '结果不一致', 'unverified': '未验证'}
SHARED_MODE = not development_mode() or setting('MINDTRACE_SHARED_MODE', '0') == '1'
DEVELOPER_ENABLED = developer_enabled()
if not DEVELOPER_ENABLED:
    st.session_state.pop('visitor_api_key', None)
    st.session_state.pop('use_visitor_key', None)
st.session_state.setdefault('ai_usage_id', str(uuid4()))


def developer_key_mode():
    return DEVELOPER_ENABLED and st.session_state.get('use_visitor_key', False)


def visitor_key():
    return st.session_state.get('visitor_api_key', '').strip() if developer_key_mode() else ''


def ai_ready():
    return bool(visitor_key()) if developer_key_mode() else server_ai_ready()


def ask_ai(system, user):
    return request_ai(system, user, api_key=visitor_key() if developer_key_mode() else None,
                      session_id=st.session_state.ai_usage_id)


def recognize_image(data):
    return request_ocr(data, api_key=visitor_key() if developer_key_mode() else None,
                       session_id=st.session_state.ai_usage_id)


def load_runs(path=None):
    if SHARED_MODE:
        name = 'shared_student_records' if path is not None else 'shared_batch_records'
        return deepcopy(st.session_state.get(name, []))
    return disk_load() if path is None else disk_load(path)


def append_record(record, path=None):
    if not SHARED_MODE:
        return disk_append(record) if path is None else disk_append(record, path)
    name = 'shared_student_records' if path is not None else 'shared_batch_records'
    items = st.session_state.setdefault(name, [])
    if not any(item.get('id') == record.get('id') for item in items):
        if len(items) >= 200:
            raise ValueError('当前会话记录已满，请下载留存后开启新会话。')
        items.append(deepcopy(record))


def save_review(run_id, row_index, review):
    if not SHARED_MODE:
        return disk_review(run_id, row_index, review)
    for run in st.session_state.get('shared_batch_records', []):
        if run.get('id') == run_id:
            run.setdefault('reviews', {})[str(row_index)] = deepcopy(review)
            return
    raise ValueError('当前会话中没有该批次。')


def clear_visitor_key():
    st.session_state['visitor_api_key'] = ''


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def local_time(value):
    try:
        return datetime.fromisoformat(value).astimezone().strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError):
        return str(value)


def records(path=None):
    try:
        return load_runs() if path is None else load_runs(path)
    except (OSError, ValueError):
        st.error('本地记录读取失败，原文件未改动。请检查 .local_data 中的 JSON。')
        return []


def current_run():
    return st.session_state.get('active_run')


def set_run(run):
    st.session_state.active_run = run
    st.session_state.current_results = run['results']  # v0.1 session compatibility
    st.session_state.pop('teacher_advice', None)


def start_batch(rows, source, **metadata):
    run = make_run(rows, source, **metadata)
    set_run(run)
    try:
        append_record(run)
        st.success(f'已完成 {run["count"]} 条数学验证，批次已保存' + ('到当前会话。' if SHARED_MODE else '到本机。'))
    except (OSError, ValueError):
        st.warning('分析已完成，但记录未保存。请检查本地 JSON 后点击“重试保存批次”。')


def batch_metrics(run):
    results = run['results'] if run else []
    counts = Counter(r['status'] for r in results)
    cols = st.columns(4)
    cols[0].metric('本批作业条目', len(results) if results else '—')
    cols[1].metric('数学结果正确', counts['correct'] if results else '—')
    cols[2].metric('需要重点复核', counts['incorrect'] if results else '—')
    cols[3].metric('超出范围 / 未验证', counts['unverified'] if results else '—')


def result_table(run, key):
    frame = pd.DataFrame(run['results'])
    filters = st.columns([2, 1])
    query = filters[0].text_input('搜索匿名编号', placeholder='输入编号筛选作业…', key=key + '_search')
    status = filters[1].selectbox('验证状态', ['全部'] + list(STATUS.values()), key=key + '_filter')
    if query:
        frame = frame[frame.student_id.str.contains(query, regex=False, case=False)]
    if status != '全部':
        frame = frame[frame.status.map(STATUS) == status]
    frame = frame[['student_id', 'question', 'student_answer', 'status', 'label']].copy()
    frame['status'] = frame['status'].map(STATUS)
    frame.columns = ['匿名编号', '原函数', '学生导数', '验证状态', '观察到的模式']
    st.dataframe(frame, hide_index=True, width='stretch')
    st.caption('统计单位是作业条目；数学结果正确不等于已掌握，观察模式也不等于认知原因。')


with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-mark">m.</div><div><div class="brand-name">'+BRAND_ENGLISH+'</div><div class="brand-sub">'+BRAND_NAME+'</div></div></div>', unsafe_allow_html=True)
    page, workspace_role = navigation()
    st.divider()
    if not ai_ready():st.caption('AI 暂不可用')
    if SHARED_MODE and not st.session_state.get('collab_access') and workspace_role=='学生学习空间':
        st.caption('自主学习记录仅保留在本次会话。')
    if DEVELOPER_ENABLED:
        with st.expander('开发者设置', expanded=False):
            st.checkbox('使用临时自带 Key', key='use_visitor_key', on_change=clear_visitor_key)
            if developer_key_mode():
                st.text_input('开发者 DeepSeek API Key', type='password', key='visitor_api_key',
                              help='仅本次会话使用，不写入文件；只发往 DeepSeek 官方接口。')
                st.button('清除本次会话密钥', on_click=clear_visitor_key, disabled=not visitor_key())
            st.caption('默认由服务端提供 AI，临时自带 Key 仅用于调试；同样受体验额度限制。')
            if st.button('检查 AI 连接', disabled=not ai_ready()):
                try:
                    with st.spinner('正在检查…'):
                        ask_ai('请用中文简短回复。', '请回复：连接成功。')
                    st.success('实际 API 请求成功。')
                except (RuntimeError, ValueError) as exc:
                    st.error(str(exc))

st.markdown('<div class="topline"><span>' + BRAND_TITLE + ' &nbsp; / &nbsp; <strong>' + html.escape(page) + '</strong></span><span class="pill">' + html.escape(workspace_role if workspace_role!='产品首页' else '高中数学学习平台') + '</span></div>', unsafe_allow_html=True)

if page in STUDIO_PAGES:
    render_studio(page, ROOT, SHARED_MODE, visitor_key() if developer_key_mode() else None)
    st.stop()

if page == '教师批量分析':
    st.markdown('<div class="eyebrow">ASSIGNMENT INTELLIGENCE</div>', unsafe_allow_html=True)
    st.title('看见班级共性，照顾每个不同。')
    st.caption('批量整理数学作业，用可复核的证据找到下一节课的重点。')
    st.markdown('''<div class="hero"><div class="hero-copy"><div class="hero-tag">从作业到教学洞察</div><h2>少一点重复整理，<br>多一点有依据的教学。</h2><p>导入作业 · 独立数学验证 · 教师证据复核<br>从一份作业开始，建立清晰的班级学习观察。</p></div><div class="hero-art" aria-hidden="true"><div class="sheet back"></div><div class="sheet"><div class="line"></div><div class="line" style="width:65%"></div><div class="formula">f ′(x) = ?</div><div class="line"></div><div class="line" style="width:80%"></div></div><div class="check-mark">✓</div></div></div>''', unsafe_allow_html=True)
    batch_metrics(current_run())
    st.write('')
    left, right = st.columns([2.15, 1], gap='large')
    with left:
        with st.container(border=True):
            st.markdown('<div class="section-num">01 / 新建分析批次</div>', unsafe_allow_html=True)
            st.subheader('把作业带进来')
            csv_tab, photo_tab = st.tabs(['CSV 批量导入', '图片转写 · 需复核'])
            with csv_tab:
                st.caption('每行一条求导题 · 最多 100 条 · UTF-8 编码')
                upload = st.file_uploader('上传作业 CSV', type=['csv'], key='batch_csv')
                if upload:
                    try:
                        rows = read_csv(upload.getvalue())
                        st.caption(f'已读取 {len(rows)} 条待分析作业')
                        st.dataframe(pd.DataFrame(rows).head(5), hide_index=True, width='stretch')
                        if st.button('开始批量分析', type='primary', width='stretch'):
                            start_batch(rows, 'CSV 上传')
                            st.rerun()
                    except (ValueError, OSError, UnicodeError) as exc:
                        st.error(f'导入未完成：{exc}')
                a, b = st.columns(2)
                if a.button('载入 12 份匿名示例作业', width='stretch'):
                    start_batch(read_csv((ROOT / 'data/demo.csv').read_bytes()), '人工构造匿名样例')
                    st.rerun()
                b.download_button('下载 CSV 示例模板', (ROOT / 'data/demo.csv').read_bytes(),
                                  'mindtrace_demo.csv', 'text/csv', width='stretch')
                with st.expander('支持什么样的数学题？'):
                    st.write('当前独立验证支持变量 x 的多项式求导，数字分母，0–12 次整数幂，总次数不超过 24。乘法写 *，乘方写 ** 或 ^。')
                    st.code('student_id,question,student_answer\nS01,(3*x**2+1)**5,5*(3*x**2+1)**4', language='text')
                    st.caption('三角函数、方程、不等式和完整手写步骤暂不做独立验证；无法解析时明确标为“未验证”。')
            with photo_tab:
                st.caption('真实 DeepSeek 视觉接口 → 原文对照 → 编辑确认 → SymPy 验证')
                photos = st.file_uploader('上传数学作业图片', type=['png', 'jpg', 'jpeg', 'webp'],
                                          accept_multiple_files=True, key='photos')
                if photos:
                    if len(photos) > 5:
                        st.warning('每次最多识别 5 张，请减少图片。')
                    selected = st.selectbox('预览图片', range(len(photos)), format_func=lambda i: photos[i].name)
                    try:
                        prepare_image(photos[selected].getvalue())
                        st.image(photos[selected].getvalue(), width=420)
                    except ValueError as exc:
                        st.error(str(exc))
                consent = st.checkbox('我确认图片已匿名化，同意发送至 DeepSeek 进行识别。')
                if st.button('开始真实图片识别', disabled=not (photos and consent and ai_ready() and len(photos) <= 5),
                             type='primary', width='stretch'):
                    st.session_state.ocr_results = []
                    st.session_state.ocr_images = {}
                    for photo in photos:
                        try:
                            with st.spinner(f'正在转写 {photo.name}…'):
                                result = recognize_image(photo.getvalue())
                            result['filename'] = photo.name
                            st.session_state.ocr_results.append(result)
                            st.session_state.ocr_images[result['image_sha256']] = photo.getvalue()
                        except (RuntimeError, ValueError) as exc:
                            st.error(f'{photo.name}：{exc}')
                if not ai_ready():
                    st.info('图片识别服务尚未启用，请联系演示提供者。你仍可使用 CSV 分析；当前没有生成任何转写。')
                ocr_results = st.session_state.get('ocr_results', [])
                if ocr_results:
                    st.warning('以下为模型转写草稿。请逐项对照图片；未确认的内容不会进入数学分析。')
                    for item in ocr_results:
                        with st.expander('原始转写 · ' + item['filename'], expanded=True):
                            original_image = st.session_state.get('ocr_images', {}).get(item['image_sha256'])
                            if original_image:
                                st.image(original_image, width=420)
                            st.text(item['transcription'])
                            for note in item['warnings']:
                                st.warning(note)
                            st.caption('不提供未经校准的识别置信度。')
                    draft = [row for item in ocr_results for row in item['records']]
                    signature = hashlib.sha256(dump(ocr_results).encode()).hexdigest()[:12]
                    if not draft:
                        st.info('未提取到可验证的求导题。可按原文手动添加，或重新裁剪上传。')
                    edited = st.data_editor(pd.DataFrame(draft, columns=REQUIRED), num_rows='dynamic',
                                            hide_index=True, width='stretch', key='ocr_editor_' + signature)
                    confirmed = st.checkbox('我已对照原图，确认上表题目与学生答案。', key='confirm_' + signature)
                    if st.button('确认转写并进行数学验证', disabled=not confirmed, width='stretch'):
                        try:
                            start_batch(edited.fillna('').to_dict('records'), '图片转写 · 教师已确认',
                                        ocr_evidence=ocr_results, confirmed_at=now())
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
    with right:
        with st.container(border=True):
            st.markdown('<div class="section-num">YOUR WORKFLOW</div>', unsafe_allow_html=True)
            st.subheader('三步，让证据更清晰')
            st.markdown('''<div class="step-card"><span>01</span><div><b>导入与整理</b><p>选择 CSV 或图片转写，保留原始内容。</p></div></div><div class="step-card"><span>02</span><div><b>验证与复核</b><p>查看符号运算依据，记录教师判断。</p></div></div><div class="step-card"><span>03</span><div><b>追问与练习</b><p>针对可观察模式追问，用新题收集证据。</p></div></div>''', unsafe_allow_html=True)
            st.divider()
            st.caption('首批体验')
            st.write('先用匿名示例体验分析，再查看每一份作业的数学证据。')
            st.caption('12 条样例均为人工构造，样例结果不会默认计入学习画像。')
    st.write('')
    with st.container(border=True):
        st.markdown('<div class="section-num">02 / 分析结果</div>', unsafe_allow_html=True)
        st.subheader('本批作业一览')
        run = current_run()
        if not run:
            st.markdown('<div class="empty-state">↥<b>准备好第一批作业了吗？</b><p>上传 CSV，或载入匿名样例，查看真实的数学验证结果。</p></div>', unsafe_allow_html=True)
        else:
            st.caption('来源：' + run.get('source', '旧版记录') + ' · ' + local_time(run['created_at']))
            if run.get('source') == '人工构造匿名样例':
                st.info('当前展示人工构造样例；数学验证为本机实时计算。')
            result_table(run, 'home')
            a, b = st.columns(2)
            a.download_button('导出本批证据 JSON', dump(run), 'mindtrace_batch.json', 'application/json', width='stretch')
            if b.button('重试保存批次', width='stretch'):
                try:
                    append_record(run)
                    st.success('批次已保存，相同批次不会重复写入。')
                except (OSError, ValueError):
                    st.error('保存失败，请检查 .local_data 文件。')
            st.caption('在左侧“证据复核与统计”查看每条计算依据并保存复核意见。')

elif page == '证据复核与统计':
    st.markdown('<div class="eyebrow">EVIDENCE & INSIGHTS</div>', unsafe_allow_html=True)
    st.title('让每个判断，都有据可查。')
    st.caption('从班级错误分布回到每一份原始作业，保留教师的独立判断。')
    run = current_run()
    if not run:
        st.info('请先在教师首页导入作业，或从“运行记录”恢复已有批次。')
    else:
        batch_metrics(run)
        st.write('')
        left, right = st.columns([1, 1.6], gap='large')
        with left, st.container(border=True, key='review_summary'):
            st.subheader('作业模式分布')
            counts = Counter(r['label'] for r in run['results'])
            st.bar_chart(pd.DataFrame({'条目数': counts}), color='#598767', horizontal=True)
            st.caption('统计描述可观察的答案模式，不直接判断学生的真实错因。')
            if st.button('生成教师教学建议', disabled=not ai_ready(), width='stretch'):
                try:
                    with st.spinner('根据统计与数学证据生成建议…'):
                        advice = ask_ai(TEACHER_PROMPT, dump({'total': run['count'], 'labels': counts,
                                                            'evidence': list(dict.fromkeys(r['evidence'] for r in run['results']))}))
                    st.session_state.teacher_advice = {'run_id': run.get('id'), 'text': advice}
                except (RuntimeError, ValueError) as exc:
                    st.error(str(exc))
            advice = st.session_state.get('teacher_advice')
            if advice and advice['run_id'] == run.get('id'):
                st.caption('AI 建议 · 需教师复核')
                st.markdown(advice['text'])
        with right, st.container(border=True, key='review_detail'):
            st.subheader('逐份证据复核')
            index = st.selectbox('选择匿名作业', range(len(run['results'])),
                                 format_func=lambda i: f"{i+1:02d} · {run['results'][i]['student_id']} · {run['results'][i]['label']}")
            row = run['results'][index]
            st.caption('原函数')
            st.code(row['question'], language='text')
            a, b = st.columns(2)
            a.caption('学生给出的导数')
            a.code(row['student_answer'], language='text')
            b.caption('SymPy 所得导数')
            b.code(row['expected_answer'] or '未验证', language='text')
            st.info(row['evidence'])
            st.caption('验证器：' + row['checker'])
            existing = run.get('reviews', {}).get(str(index), {})
            with st.form('review_' + str(run.get('id')) + '_' + str(index)):
                decision = st.selectbox('教师复核结论', ['待复核', '认可数学证据', '需要修正 / 补充证据'],
                                        index=['待复核', '认可数学证据', '需要修正 / 补充证据'].index(existing.get('decision', '待复核')))
                note = st.text_area('复核备注', value=existing.get('note', ''), max_chars=2000, placeholder='记录原始过程、补充观察或待追问的问题…')
                if st.form_submit_button('保存教师复核', type='primary'):
                    review = {'decision': decision, 'note': note, 'reviewed_at': now()}
                    try:
                        if not run.get('id'):
                            run['id'] = str(uuid4())
                            append_record(run)
                        save_review(run['id'], index, review)
                        run.setdefault('reviews', {})[str(index)] = review
                        st.success('复核意见已保存。')
                    except (OSError, ValueError) as exc:
                        st.error(f'复核未保存：{exc}')
        st.download_button('下载含教师复核的证据 JSON', dump(run), 'mindtrace_reviewed.json', 'application/json')

elif page == '学生辅导体验':
    st.markdown('<div class="eyebrow">PERSONAL LEARNING STUDIO</div>', unsafe_allow_html=True)
    st.title('从“哪里错了”，走向“下一步怎么想”。')
    st.caption('动态追问与自适应提示保留完整上下文；变式练习由 SymPy 实时核验。')
    tutor_tab, practice_tab = st.tabs(['错因诊断与动态追问', '变式训练'])
    with tutor_tab:
        with st.form('student_start'):
            sid = st.text_input('匿名学习编号', value='Learner-01', max_chars=80)
            q = st.text_input('原函数表达式', value='(3*x**2+1)**5', max_chars=160)
            answer = st.text_input('学生给出的最终导数', value='5*(3*x**2+1)**4', max_chars=160)
            solution = st.text_area('补充解题过程', value="先求外层导数，得到 5*(3*x**2+1)**4。", max_chars=4000)
            begin = st.form_submit_button('建立诊断与追问', type='primary')
        if begin:
            evidence = analyze({'student_id': sid, 'question': q, 'student_answer': answer}).to_dict()
            session = {'id': str(uuid4()), 'created_at': now(), 'student_id': sid.strip() or 'anonymous',
                       'question': q, 'student_answer': answer, 'solution': solution, 'evidence': evidence, 'turns': []}
            st.session_state.tutor_session = session
            st.session_state.pop('tutor_saved', None)
            if ai_ready():
                try:
                    with st.spinner('根据作业证据设计追问…'):
                        reply = ask_ai(TUTOR_PROMPT, dump(session) + '\n请先提出一个诊断性问题。')
                    session['turns'].append({'role': 'assistant', 'text': reply})
                except (RuntimeError, ValueError) as exc:
                    st.error(str(exc))
            else:
                st.info('已完成数学验证。AI 辅导服务暂未启用，请联系演示提供者。')
        session = st.session_state.get('tutor_session')
        if session:
            st.caption('当前辅导对应：' + session['student_id'] + ' · ' + session['question'])
            st.info(session['evidence']['evidence'])
            for turn in session['turns']:
                with st.chat_message(turn['role']):
                    st.write(turn['text'])
            pending = bool(session['turns'] and session['turns'][-1]['role'] == 'user')
            if pending:
                st.warning('上一条回答尚未得到 AI 回复，请重试；不会把失败请求当作辅导结果。')
            reply_input = st.chat_input('说说你的想法，AI 会根据回答调整提示…',
                                       disabled=not ai_ready() or pending or len(session['turns']) >= 20, max_chars=2000)
            retry = st.button('重试生成追问', disabled=not ai_ready()) if pending or not session['turns'] else False
            if reply_input or retry:
                if reply_input:
                    session['turns'].append({'role': 'user', 'text': reply_input})
                try:
                    with st.spinner('结合新证据调整提示…'):
                        reply = ask_ai(TUTOR_PROMPT, dump(session) + '\n根据最新回答给一个简短提示或追问。')
                    session['turns'].append({'role': 'assistant', 'text': reply})
                    st.session_state.pop('tutor_saved', None)
                    st.rerun()
                except (RuntimeError, ValueError) as exc:
                    st.error(str(exc))
            if len(session['turns']) >= 20:
                st.info('本次辅导已达 20 条消息，请整理证据并开始新一轮。')
            if st.button('保存本次辅导证据', disabled=st.session_state.get('tutor_saved', False)):
                try:
                    snapshot = dict(session, id=str(uuid4()), session_id=session['id'], kind='tutoring')
                    append_record(snapshot, STUDENT_STORE)
                    st.session_state.tutor_saved = True
                    st.success(('已保存到当前会话' if SHARED_MODE else '已保存到本机学习记录') + '，认知画像页可查看。')
                except (OSError, ValueError):
                    st.error('辅导记录保存失败，原文件未改动。')
    with practice_tab:
        st.subheader('链式法则 · 独立变式')
        st.caption('针对复合函数求导的新题，练习结果只代表本次表现；可独立验证。')
        if st.button('生成一道新变式', type='primary'):
            st.session_state.exercise = make_exercise()
            st.session_state.pop('exercise_result', None)
        exercise = st.session_state.get('exercise')
        if exercise:
            st.code('求导：y = ' + exercise['question'], language='text')
            with st.expander('需要一点提示？'):
                st.write(exercise['hint'])
            with st.form('practice_answer'):
                learner = st.text_input('练习匿名编号', value=st.session_state.get('tutor_session', {}).get('student_id', 'Learner-01'), max_chars=80)
                attempt = st.text_input('你的导数表达式', max_chars=160)
                check = st.form_submit_button('提交并验证')
            if check:
                if not attempt.strip() or not learner.strip():
                    st.warning('请填写编号与导数表达式。')
                else:
                    result = analyze({'student_id': learner, 'question': exercise['question'], 'student_answer': attempt}).to_dict()
                    item = {'id': str(uuid4()), 'created_at': now(), 'student_id': learner,
                            'kind': 'practice', 'evidence': result}
                    st.session_state.exercise_result = result
                    try:
                        append_record(item, STUDENT_STORE)
                        st.success('练习已验证并保存。')
                    except (OSError, ValueError):
                        st.warning('验证完成，但本地保存失败。')
            result = st.session_state.get('exercise_result')
            if result:
                st.info(STATUS[result['status']] + ' · ' + result['evidence'])
                with st.expander('查看独立计算的参考导数'):
                    st.code(exercise['answer'], language='text')
        else:
            st.info('生成一道新题，检验这次能否记得内层导数。')

elif page == '学习认知画像':
    st.markdown('<div class="eyebrow">LEARNING EVIDENCE</div>', unsafe_allow_html=True)
    st.title('用持续的证据，记录学习变化。')
    st.caption('探索版认知画像：汇集已保存的答题与追问证据，不给出未经验证的能力分或心理标签。')
    sessions = records(STUDENT_STORE)
    batches = records()
    include_demo = st.checkbox('包含人工构造样例', value=False)
    observations = []
    for run in batches:
        if not include_demo and run.get('source') in (None, '人工构造匿名样例'):
            continue
        for row in run.get('results', []):
            observations.append(dict(row, created_at=run['created_at'], source=run.get('source', '旧版记录')))
    # A tutoring snapshot is conversation evidence; repeated saves are not new attempts.
    unique_sessions = {}
    for item in sessions:
        if item.get('kind') == 'tutoring':
            unique_sessions[item.get('session_id', item['id'])] = item
        elif item.get('kind') == 'practice':
            observations.append(dict(item['evidence'], created_at=item['created_at'], source='独立变式训练'))
    for item in unique_sessions.values():
        observations.append(dict(item['evidence'], created_at=item['created_at'], source='辅导初始作答'))
    identifiers = sorted(set(r['student_id'] for r in observations))
    if not identifiers:
        st.info('还没有真实学习证据。可导入匿名作业，或完成并保存一次学生辅导 / 变式练习。')
    else:
        student = st.selectbox('选择匿名学习编号', identifiers)
        selected = [r for r in observations if r['student_id'] == student]
        counts = Counter(r['status'] for r in selected)
        a, b, c = st.columns(3)
        a.metric('已记录答题证据', len(selected))
        b.metric('结果正确', counts['correct'])
        c.metric('待核实 / 未验证', counts['incorrect'] + counts['unverified'])
        st.write('')
        st.subheader('可观察模式')
        st.dataframe(pd.DataFrame([{'时间': local_time(r['created_at']), '来源': r['source'],
                                    '原函数': r['question'], '状态': STATUS[r['status']], '证据': r['label']}
                                   for r in sorted(selected, key=lambda r: r['created_at'], reverse=True)]),
                     hide_index=True, width='stretch')
        dialogue = [r for r in unique_sessions.values() if r['student_id'] == student]
        with st.expander(f'已保存的追问记录 · {len(dialogue)} 次辅导'):
            for entry in dialogue:
                st.caption(local_time(entry['created_at']) + ' · ' + entry['question'])
                for turn in entry['turns']:
                    st.write(('学生：' if turn['role'] == 'user' else 'AI：') + turn['text'])
        st.info('下一步建议：对未解决的答案模式进行追问，再用独立新题收集证据。当前样本不支持推断稳定掌握度。')

else:
    st.markdown('<div class="eyebrow">LOCAL ARCHIVE</div>', unsafe_allow_html=True)
    st.title('每次分析，都留下一条可追溯记录。')
    if SHARED_MODE:
        st.caption('当前会话的记录彼此隔离；刷新、断线或服务重启后可能丢失，请下载 JSON 留存。')
    with st.expander('导入以前导出的批次 JSON'):
        history_file = st.file_uploader('选择本机保存的批次记录', type=['json'], key='history_json')
        if history_file and st.button('导入并重新验证批次'):
            try:
                restored = import_run(history_file.getvalue())
                append_record(restored)
                set_run(restored)
                st.success('已导入当前工作区，数学结果已重新验证。')
            except (ValueError, OSError):
                st.error('导入失败：请使用有效的批次 JSON，最多 1 MB、100 条作业。')
    runs = records()
    st.metric('当前会话批次' if SHARED_MODE else '本机已保存批次', len(runs))
    for index, run in enumerate(reversed(runs)):
        with st.expander(f"{local_time(run.get('created_at', ''))} · {run.get('count', 0)} 条 · {run.get('source', 'v0.1 历史记录')}"):
            st.dataframe(pd.DataFrame(run.get('results', [])), hide_index=True, width='stretch')
            if st.button('恢复到当前工作区', key=f'restore_{index}'):
                set_run(run)
                st.success('已恢复，请进入教师首页或证据复核工作区。')
            st.download_button('导出此批次 JSON', dump(run), f'mindtrace_run_{index}.json',
                               'application/json', key=f'export_{index}')
    if not runs:
        st.info('暂无批次。教师首页完成首次分析后，记录将保存在' + ('当前会话。' if SHARED_MODE else '本地。'))

st.markdown('<div class="footer"><span>' + BRAND_TITLE + '</span><span>' + ('共享体验 · 记录仅留当前会话' if SHARED_MODE else '本机单用户原型') + ' · 教师保留最终判断</span></div>', unsafe_allow_html=True)


