"""V1.1 information architecture and first-round product surfaces.
Uses existing workspace, analysis and tutoring engines; no model calls on page load.
"""
from collections import Counter
from html import escape
import json
import streamlit as st
from ui.design import BRAND_TITLE
from core import education as edu, classroom as store
from ui.workbench import Runtime, heading, source_panel, status, message

TEACHER = ['作业批改', '班级错误分析', '历史记录']
STUDENT = ['AI解题与辅导', '我的错题本', '错因分析']
COMPAT = ['工作台首页','作业分析','旧版班级学情','教学任务','我的学习','拍题辅导','专项练习','学习档案']
LEGACY = ['教师批量分析', '证据复核与统计', '学生辅导体验', '学习认知画像', '运行记录']
PAGES = ['产品首页'] + TEACHER + STUDENT + ['高级设置','班级学情','AI 解题与辅导'] + COMPAT

def safe(value):
    return escape(str(value), quote=True)

def go(role, page, submission_id=None, task_id=None):
    # Consume before navigation widgets are instantiated on the next rerun.
    page={'班级学情':'班级错误分析','AI 解题与辅导':'AI解题与辅导'}.get(page,page)
    st.session_state['experience_destination'] = (role, page)
    if submission_id:
        st.session_state['studio_selected_question'] = submission_id
    if role == '教师工作空间' and page == '作业分析':
        st.session_state['teacher_open_review'] = bool(submission_id)
    if task_id:
        st.session_state['focus_task_id'] = task_id

def navigation():
    from ui.collaboration import connection_panel
    access=connection_panel()
    roles=['产品首页','教师工作空间','学生学习空间']
    destination=st.session_state.pop('experience_destination',None)
    if destination:
        role,page=destination
        page={'班级学情':'班级错误分析','AI 解题与辅导':'AI解题与辅导'}.get(page,page)
        st.session_state['experience_role']=role
        st.session_state['experience_page']=page
        if page in TEACHER+STUDENT+['产品首页']:st.session_state['experience_nav']=page
    st.session_state.setdefault('experience_role','产品首页')
    if access:
        fixed='教师工作空间' if access['role']=='teacher' else '学生学习空间'
        allowed=(TEACHER if access['role']=='teacher' else STUDENT)+['高级设置']
        st.session_state['experience_role']=fixed
        if st.session_state.get('experience_page') not in allowed:st.session_state['experience_page']=allowed[0]
        st.caption('教师课堂' if access['role']=='teacher' else '学生课堂')
    else:
        st.caption('切换工作空间')
        switch=st.columns(2,gap='small')
        for col,target,label in zip(switch,roles[1:],['教师','学生']):
            with col:
                st.button(label,key='switch_'+target,type='primary' if st.session_state['experience_role']==target else 'secondary',
                    width='stretch',on_click=go,args=(target,TEACHER[0] if target==roles[1] else STUDENT[0]))
    role=st.session_state['experience_role']
    options=TEACHER if role==roles[1] else STUDENT if role==roles[2] else ['产品首页']
    st.session_state.setdefault('experience_page',options[0])
    page=st.session_state['experience_page']
    if page not in PAGES+LEGACY:page=options[0]
    icons={TEACHER[0]:':material/task_alt:',TEACHER[1]:':material/grid_view:',TEACHER[2]:':material/history:',
        STUDENT[0]:':material/auto_awesome:',STUDENT[1]:':material/menu_book:',STUDENT[2]:':material/pie_chart:', '产品首页':':material/home:'}
    with st.container(key='main_navigation'):
        for label in options:
            st.button(label,key='nav_'+label,icon=icons[label],type='primary' if page==label else 'tertiary',
                width='stretch',on_click=go,args=(role,label))
    if not access:st.button('返回产品首页',on_click=go,args=('产品首页','产品首页'),width='stretch')
    st.markdown('<div class="sidebar-space"></div>',unsafe_allow_html=True)
    st.button('设置',icon=':material/settings:',on_click=go,args=(role,'高级设置'),width='stretch',key='open_settings')
    return page,role


def surface(key=None):
    index=st.session_state.get('_surface_index',0)
    st.session_state['_surface_index']=index+1
    return st.container(border=True,key='v11_surface_'+(key or str(index)))

def title(kicker, name, description):
    heading(kicker, name, description)

def card(kicker, name, description, variant=''):
    st.markdown('<div class="feature-card '+variant+'"><span class="card-kicker">'+safe(kicker)+'</span><h3>'+safe(name)+'</h3><p>'+safe(description)+'</p></div>', unsafe_allow_html=True)

def empty(name, description):
    st.markdown('<div class="empty-state"><div class="empty-symbol">↗</div><h3>'+safe(name)+'</h3><p>'+safe(description)+'</p></div>', unsafe_allow_html=True)

def badge(label, variant=''):
    return '<span class="status-tag '+variant+'">'+safe(label)+'</span>'

def topic_chips(points):
    return '<div class="topic-chips">'+''.join('<span>'+safe(v)+'</span>' for v in points[:8])+'</div>'

def teacher_submissions(w):
    return [s for s in w['submissions'] if s.get('source') != 'self_study']

def pending_review(w):
    result = []
    for sub in teacher_submissions(w):
        a=edu.latest_success(sub)
        r=store.latest_review(w,sub['id'])
        if a and (not r or r['analysis_id'] != a['id'] or r['decision']=='uncertain'):
            result.append(sub)
    return result

def load_examples(rt):
    rows=json.loads((rt.root/'data/highschool_examples.json').read_text(encoding='utf-8-sig'))
    for row in rows:
        rt.add(row,'constructed_examples')
    go('教师工作空间','作业分析')
    st.rerun()

def landing(rt):
    st.markdown('<div class="landing-intro"><span class="eyebrow">'+BRAND_TITLE+'</span><h1>看见学习的线索，<br>让每一步进步有迹可循。</h1><p>高中数学学情分析与个性化学习平台</p></div>', unsafe_allow_html=True)
    left,right=st.columns([1.45,1],gap='large')
    with left, surface(key='entry_teacher'):
        card('FOR TEACHERS / 教师工作空间','从一份作业，到下一步教学行动','批量分析作业，发现班级共性与个体重复问题。对照原始证据复核后，为学生安排针对性任务。','accent')
        st.markdown('<div class="entry-path"><span>作业分析</span><b>→</b><span>证据复核</span><b>→</b><span>学习干预</span></div>',unsafe_allow_html=True)
        st.button('进入教师工作台',type='primary',width='stretch',on_click=go,args=('教师工作空间','工作台首页'))
    with right, surface(key='entry_student'):
        card('FOR STUDENTS / 学生学习空间','带着问题来，带着理解走','领取老师的原题任务，或自主拍题。选择快速纠错或深入辅导，再用一道新题检验理解。')
        st.markdown('<div class="entry-path"><span>原题任务</span><b>→</b><span>针对辅导</span><b>→</b><span>新题验证</span></div>',unsafe_allow_html=True)
        st.button('进入学生学习中心',width='stretch',on_click=go,args=('学生学习空间','我的学习'))
    st.markdown('<div class="trust-strip"><span>◎ 原始作答可追溯</span><span>◎ 教师保留判断权</span><span>◎ 提示与独立完成分开记录</span></div>',unsafe_allow_html=True)
    a,b,c=st.columns(3,gap='large')
    with a:
        card('01 / 先保留证据','不用重复输入原题','教师保存的题目、步骤与学习目标，会随任务进入学生的学习空间。')
    with b:
        card('02 / 再采取行动','让分析连接辅导','错误类别能追溯到具体作答，复核结果能转为学生学习任务。')
    with c:
        card('03 / 用新题验证','让反馈回到教学','看过答案和独立作答分别记录，不用没有依据的掌握率替代学习证据。')
    st.caption('当前为演示工作空间。角色切换不是登录认证；模型分析可能出错，重要结论请由教师复核。')

def teacher_home(rt):
    title('TEACHING WORKSPACE / 工作台','今天，从一个值得关注的问题开始。','导入作业、复核证据，再把学习问题变成具体的教学行动。')
    subs=teacher_submissions(rt.w)
    pending=pending_review(rt.w)
    groups=edu.class_insights(rt.w)
    tasks=[t for t in rt.w['tasks'] if t.get('origin')!='self_study']
    left,right=st.columns([1.75,1],gap='large')
    with left,surface(key='teacher_welcome'):
        card('YOUR NEXT TEACHING MOVE','把作业，变成下一次进步的起点。','上传匿名作业图片；校对识别草稿后，分析学生的解题过程。原图、判断与教师意见一起保留。','accent')
        st.button('＋ 新建作业分析',type='primary',on_click=go,args=('教师工作空间','作业分析'))
    with right,surface():
        st.subheader('下一步，做什么？')
        if pending:
            st.markdown(badge(str(len(pending))+' 道作答待复核','warning'),unsafe_allow_html=True)
            st.write('AI 已给出分析，请对照原题确认错误与后续目标。')
            st.button('开始复核',on_click=go,args=('教师工作空间','作业分析',pending[0]['id']))
        elif subs and any(not edu.latest_success(s) for s in subs):
            st.write('材料已保存，准备好后可开始分析。')
            st.button('继续分析作业',on_click=go,args=('教师工作空间','作业分析'))
        else:
            st.write('第一次使用？先体验一组跨章节匿名材料，熟悉分析与复核流程。')
            if st.button('体验匿名示例',key='home_examples'):
                load_examples(rt)
            st.caption('示例为构造材料，分析需真实调用 AI。')
    if not subs:
        st.subheader('三步开启第一次教学分析')
        a,b,c=st.columns(3,gap='large')
        for col,k,n,d in [(a,'01','导入与校对','上传清晰、匿名的作业图片，确认题目与学生归属。'),(b,'02','分析与复核','查看首个错误、原文依据及需要进一步确认的问题。'),(c,'03','安排与反馈','分配学习任务，查看学生后续练习和验证情况。')]:
            with col,surface():
                card(k,n,d)
        return
    a,b,c=st.columns(3)
    a.metric('已导入作答',len(subs))
    b.metric('待复核作答',len(pending))
    c.metric('已安排任务',len(tasks))
    left,right=st.columns([1.5,1],gap='large')
    with left,surface():
        st.subheader('最近导入的作业')
        st.caption('按作答记录展示，当前版本尚未建立独立的班级批次管理。')
        for sub in subs[-4:][::-1]:
            a,b=st.columns([4,1])
            with a:
                st.markdown('**'+safe(sub['student_id'])+' · '+safe(sub['question_no'] or sub['topic'])+'**')
                st.caption(sub['question'][:95])
                st.markdown(badge(status(sub,rt.w)),unsafe_allow_html=True)
            b.button('查看',key='recent_'+sub['id'],on_click=go,args=('教师工作空间','作业分析',sub['id']))
    with right,surface():
        st.subheader('优先关注的学习问题')
        if groups:
            for g in groups[:3]:
                st.markdown('**'+g['label']+'**')
                st.caption(str(len(g['students']))+' 位学生 · 已复核 '+str(g['confirmed'])+' / 待复核 '+str(g['pending']))
            st.button('查看班级学情',on_click=go,args=('教师工作空间','班级学情'))
        else:
            st.write('分析并复核后，这里会显示有原始依据的学习问题。')
        st.divider()
        st.subheader('最近学生反馈')
        attempts=[a for a in rt.w['attempts'] if any(t['id']==a['task_id'] for t in tasks)]
        if not attempts:
            st.caption('学生完成任务练习后，反馈会回到这里。')
        for item in attempts[-2:][::-1]:
            st.write(item['student_id']+' · '+edu.learning_state([item]))
        if tasks:
            st.button('查看教学任务',on_click=go,args=('教师工作空间','教学任务'))

def class_insights(rt):
    title('CLASS INSIGHTS / 班级学情','从共性问题，找到教学的着力点。','每个类别都关联原始作答；区分模型建议与教师复核，避免把待确认判断当作事实。')
    groups=edu.class_insights(rt.w)
    if not groups:
        empty('还没有可展示的学习问题','先导入并分析作业。被教师驳回的结论不会进入错误分布。')
        st.button('前往作业分析',type='primary',on_click=go,args=('教师工作空间','作业分析'))
        return
    a,b,c=st.columns(3)
    a.metric('观察到的错误类别',len(groups))
    b.metric('涉及匿名学生',len({sid for g in groups for sid in g['students']}))
    c.metric('出现跨题重复的学生',len({sid for g in groups for sid in g['repeat_students']}))
    left,right=st.columns([1.45,1],gap='large')
    with left,surface():
        st.subheader('高频错误 · 复核分布')
        st.caption('条形长度按本页最大作答数缩放；同一作答可涉及多个类别，不作为班级错误率。')
        maximum=max(g['confirmed']+g['pending'] for g in groups)
        for g in sorted(groups,key=lambda x:x['confirmed']+x['pending'],reverse=True)[:8]:
            confirmed=100*g['confirmed']/maximum
            pending=100*g['pending']/maximum
            st.markdown('<div class="issue-bar"><div><b>'+safe(g['label'])+'</b><span>'+str(g['confirmed']+g['pending'])+' 条作答</span></div><div class="bar-track"><i style="width:'+str(confirmed)+'%"></i><em style="width:'+str(pending)+'%"></em></div><small>教师确认 '+str(g['confirmed'])+' · 待复核 '+str(g['pending'])+'</small></div>',unsafe_allow_html=True)
        st.markdown('<div class="chart-legend"><span>● 教师确认</span><span>● 待复核</span></div>',unsafe_allow_html=True)
    with right,surface():
        st.subheader('知识点与重复线索')
        points=Counter(p for g in groups for p in g['knowledge_points'])
        for point,count in points.most_common(6):
            st.markdown('<div class="knowledge-row"><span>'+safe(point)+'</span><b>'+str(count)+' 类关联</b></div>',unsafe_allow_html=True)
        st.caption('知识点关联的是错误类别数量，不是分数或掌握程度。')
        st.divider()
        repeated=[g for g in groups if g['repeat_students']]
        if not repeated:
            st.write('尚未发现同一学生在不同题目上的重复模式。')
        for g in repeated[:3]:
            st.markdown(badge('跨题重复','warning')+' '+safe('、'.join(g['repeat_students'])),unsafe_allow_html=True)
            st.write(g['label'])
    st.subheader('从错误类别，回到原始证据')
    selected=st.selectbox('选择需要查看的学习问题',[g['label'] for g in groups],key='insight_label')
    group=next(g for g in groups if g['label']==selected)
    st.markdown(topic_chips(group['knowledge_points']),unsafe_allow_html=True)
    st.caption('排序参考复核程度、涉及人数、严重性与跨题重复；不是能力评分。')
    matching=[s for s in teacher_submissions(rt.w) if s['id'] in group['submission_ids']]
    selected_id=st.selectbox('对应学生与题目',[s['id'] for s in matching],format_func=lambda k:next(s['student_id']+' / '+(s['question_no'] or s['topic']) for s in matching if s['id']==k))
    sub=next(s for s in matching if s['id']==selected_id)
    left,right=st.columns([1,1.1],gap='large')
    with left,surface():
        st.subheader('原始作答')
        source_panel(rt,sub)
    with right,surface():
        st.subheader('判断与复核依据')
        st.markdown(badge(status(sub,rt.w)),unsafe_allow_html=True)
        review=store.latest_review(rt.w,sub['id'])
        result=edu.latest_success(sub)
        if review and review['analysis_id']==result['id']:
            st.write('教师判断：'+review['label'])
            if review['note']:
                st.write('教师备注：'+review['note'])
        for step in result['analysis']['steps']:
            if step['verdict']!='correct':
                st.markdown('**第 '+str(step['number'])+' 步**')
                st.text(step['evidence_quote'])
                message(step['observation'])
        st.button('复核这道题 / 安排任务',type='primary',on_click=go,args=('教师工作空间','作业分析',sub['id']))
    with st.expander('更深入的教学建议'):
        st.caption('原有 AI 教学建议仍保留在作业分析工作区的班级共性问题中，点击操作才会调用模型。')
        st.button('前往完整教学分析',on_click=go,args=('教师工作空间','作业分析'))

def student_home(rt):
    title('MY LEARNING / 我的学习','每一次理解，都从一个具体问题开始。','领取老师的任务，或拍下自己的疑问。你可以快速纠错，也可以一步步理清思路。')
    ids=sorted({t['student_id'] for t in rt.w['tasks']} | {s['student_id'] for s in rt.w['submissions'] if s.get('source')=='self_study'})
    sid=None
    if ids:
        current=rt.assigned_student or st.session_state.get('studio_legacy_student')
        sid=st.selectbox('我的匿名学习编号',ids,index=ids.index(current) if current in ids else None,key='home_student')
        if sid is not None:st.session_state['studio_legacy_student']=sid
    own=[t for t in rt.w['tasks'] if t['student_id']==sid]
    pending=[t for t in own if t['status'] not in ('completed','needs_recheck')]
    left,right=st.columns([1.65,1],gap='large')
    with left,surface(key='student_welcome'):
        card('YOUR LEARNING JOURNEY','有疑问，就从这里开始。','老师安排的任务已经带上原题、原作答与目标。自主学习也可以直接拍题，不必从空白聊天框开始。','accent')
        st.button('拍一道题，开始学习',type='primary',on_click=go,args=('学生学习空间','拍题辅导'))
    with right,surface():
        st.subheader('学习方式，由你选择')
        st.markdown(badge('快速纠错')+' '+badge('深度辅导','purple'),unsafe_allow_html=True)
        st.write('已经理解错误？直接讲解或新题验证。仍然卡住？通过有目的的追问和四级提示继续。')
        st.caption('使用提示、查看答案与独立完成会分别记录。')
    st.subheader('待完成学习任务'+(' · '+str(len(pending)) if pending else ''))
    if not pending:
        empty('现在没有待完成的任务','收到老师的任务包后可直接导入；也可以自主拍题开始学习。')
        st.button('接收老师的学习任务',on_click=go,args=('学生学习空间','专项练习'))
    for task in pending[:5]:
        with surface():
            a,b=st.columns([4,1])
            with a:
                st.markdown(badge('老师安排' if task.get('origin')!='self_study' else '自主学习')+topic_chips(task['knowledge_points']),unsafe_allow_html=True)
                st.subheader(task['goal'])
                st.caption('原题与原始作答已随任务保留，无需重复输入。')
            b.button('继续学习',key='continue_'+task['id'],type='primary',on_click=go,args=('学生学习空间','专项练习',None,task['id']))
    left,right=st.columns([1.4,1],gap='large')
    with left,surface():
        st.subheader('最近学习记录')
        attempts=[a for a in rt.w['attempts'] if a['student_id']==sid]
        if not attempts:
            st.write('完成一次练习后，这里会保留你的验证结果。')
        for attempt in attempts[-3:][::-1]:
            st.markdown('**'+safe(edu.learning_state([attempt]))+'**')
            st.caption(attempt['exercise_question'][:100])
        st.button('查看学习档案',on_click=go,args=('学生学习空间','学习档案'))
    with right,surface():
        st.subheader('建议巩固的知识点')
        points=list(dict.fromkeys(p for t in pending for p in t['knowledge_points']))
        if points:
            st.markdown(topic_chips(points),unsafe_allow_html=True)
            st.write('先完成相关任务，再用一道新题检查是否能独立解决。')
        else:
            st.write('根据你的作答和任务反馈逐步形成建议，不预设学习短板。')
        if any(t['status']=='needs_recheck' for t in own):
            st.info('有任务正在等待老师重新确认，先保留已有学习记录。')

def render(page,root,shared,api_key=None):
    from ui.teacher import teacher,feedback_panel
    from ui.student import student,profiles,records
    page={'班级学情':'班级错误分析','AI 解题与辅导':'AI解题与辅导'}.get(page,page)
    if page in ['产品首页'] + TEACHER + STUDENT:
        from ui.product import render as render_product
        return render_product(page,root,shared,api_key)
    rt=Runtime(root,shared,api_key)
    st.session_state['_surface_index']=0
    if any(s.get('source') in ('constructed_examples','live_constructed_fixture') for s in rt.w['submissions']):
        st.caption('当前包含构造匿名材料，仅用于体验与测试，不代表真实课堂效果。')
    if page=='产品首页':
        landing(rt)
    elif page=='工作台首页':
        teacher_home(rt)
    elif page=='旧版班级学情':
        class_insights(rt)
    elif page=='我的学习':
        student_home(rt)
    elif page=='作业分析':
        teacher(rt,review_first=st.session_state.get('teacher_open_review',False))
    elif page=='教学任务':
        title('TEACHING TASKS / 教学任务','让每个教学目标，都收到具体反馈。','从确认的学习问题安排任务，查看学生如何练习、是否使用提示以及还需要什么支持。')
        feedback_panel(rt)
        st.button('从已复核问题安排任务',on_click=go,args=('教师工作空间','作业分析'))
    elif page in ('拍题辅导','专项练习'):
        student(rt,view='photo' if page=='拍题辅导' else 'tasks')
    elif page=='学习档案':
        profiles(rt)
    elif page=='高级设置':
        title('设置','工作空间设置','管理数据备份，了解当前工作空间的使用方式。')
        if rt.access and rt.access['number_demo']:
            st.info('当前是按学号进入的演示课堂。请使用虚构学号和作答。')
        elif rt.access:st.info('当前通过课堂访问码连接；学生学习码仅关联本人的记录。')
        else:st.info('当前为演示工作区。学生未选择学号时，仅显示本会话的自主学习记录。')
        if st.session_state.get('experience_role')=='教师工作空间':
            for item in store.capacity_status(rt.w):
                st.warning(f"{item['name']}已使用 {item['count']}/{item['limit']}。请先下载完整备份，再新建课堂继续；不会自动清理历史。")
            from ui.product import legacy_assignment_import
            legacy_assignment_import(rt)
        from core.settings import developer_enabled
        if developer_enabled() and not st.session_state.get('collab_access'):
            with st.expander('开发者兼容工具'):
                target=st.selectbox('兼容功能',LEGACY+COMPAT)
                if st.button('打开兼容功能'):
                    go(st.session_state.get('experience_role','教师工作空间'),target);st.rerun()
            records(rt)
        else:
            with st.expander('数据备份'):
                from ui.workbench import dumps
                if st.session_state.get('experience_role')=='学生学习空间':
                    from ui.product import student_id
                    from core.product import notebook_rows
                    sid=student_id(rt)
                    st.download_button('下载我的错题记录',dumps(notebook_rows(rt.w,sid)),'my_notebook.json','application/json')
                else:
                    st.download_button('下载工作区备份',dumps(rt.w),'mindtrace_workspace.json','application/json')
                    st.caption('备份包含当前工作区的全部学习记录，请由工作区所有者保管。')
                    st.caption('需要归档时请保留此备份及旧课堂恢复码，再新建课堂。旧课堂数据继续保留；当前不自动拆分或删除历史记录。')
