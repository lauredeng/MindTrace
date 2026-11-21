"use client";
import {useEffect,useRef,useState} from "react";
import {ArrowRight,BookOpen,CalendarClock,Check,ChevronRight,Layers3,Plus,RefreshCw,X} from "lucide-react";
import MarkdownRenderer from "@/components/common/MarkdownRenderer";
import {apiFetch,apiUrl} from "@/lib/api";
import styles from "./MindTrace.module.css";

export type Entry={id:string;submission_id:string;question:string;question_type:string;active_error:boolean;knowledge_points:string[];progress:{state:string;label:string}|null};
type Evidence={submission_id:string;kind:string;verdict:string;independent?:boolean};
export type Home={student_id:string;notebook:Entry[];due:{submission_id:string;objective:string}[];
  profile:{points:{label:string;original_correct:number;original_incorrect:number;unconfirmed:number;independent_success:number;assisted_success:number;evidence:Evidence[]}[]}};
type Unit={unit_id:string;submission_id:string;question:string;objective:string;due:string;stale:boolean;is_due:boolean;valid_reviews:number;pending_run_id:string|null};
type Run={run_id:string;question:string;unit_id:string;submission_id:string;objective:string};
type Result={attempt_id:string;independent:boolean;assessment:{verdict:string;note:string;method:string}|null;can_rate:boolean;can_recall_success:boolean};

async function request<T>(path:string,body?:object):Promise<T>{
  const response=await apiFetch(apiUrl('/api/mindtrace'+path),{skipAuthRedirect:true,...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
  if(!response.ok){const data=await response.json().catch(()=>null);throw Error(typeof data?.detail==='string'?data.detail:'暂时未能完成，请稍后重试。');}
  return response.json();
}
const time=(s:string)=>new Date(s).toLocaleString('zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
const math=(text:string)=><MarkdownRenderer content={text} allowHtml={false} enableImages={false}/>;

export default function LearningDashboard({home,open,opening,refresh}:{home:Home;open:(id:string)=>Promise<void>;opening:string;refresh:()=>Promise<void>}){
  const[tab,setTab]=useState<'notebook'|'review'|'profile'>('notebook');
  const[filter,setFilter]=useState<'all'|'active'|'corrected'>('all');
  const[units,setUnits]=useState<Unit[]>([]);const[error,setError]=useState('');const[notice,setNotice]=useState('');
  const[busy,setBusy]=useState(false);const[run,setRun]=useState<Run|null>(null);const[result,setResult]=useState<Result|null>(null);
  const[steps,setSteps]=useState('');const[answer,setAnswer]=useState('');const[helped,setHelped]=useState(false);
  const dialog=useRef<HTMLDialogElement>(null);
  const[reviewError,setReviewError]=useState('');
  const refreshUnits=()=>request<Unit[]>('/reviews').then(setUnits);
  useEffect(()=>{void refreshUnits().catch(e=>setError(e.message));},[]);
  useEffect(()=>{if(run&&!dialog.current?.open)dialog.current?.showModal();else if(!run)dialog.current?.close();},[run]);
  async function action(work:()=>Promise<void>){setBusy(true);setError('');setNotice('');try{await work();}catch(e){setError(e instanceof Error?e.message:'暂时无法完成。');}finally{setBusy(false);}}
  async function add(id:string){await action(async()=>{await request('/review-units',{submission_id:id});await refreshUnits();await refresh();setNotice('已加入复习计划。');});}
  async function begin(unit:Unit,resume=false){await action(async()=>{
    setReviewError('');setSteps('');setAnswer('');setHelped(false);setResult(null);
    if(resume&&unit.pending_run_id){
      const saved=await request<Result>('/review-runs/'+unit.pending_run_id+'/result');setResult(saved);
      setRun({run_id:unit.pending_run_id,question:unit.question,unit_id:unit.unit_id,submission_id:unit.submission_id,objective:unit.objective});
    }else setRun(await request<Run>('/review-runs',{unit_id:unit.unit_id}));
  });}
  async function reviewAction(work:()=>Promise<void>){setBusy(true);setReviewError('');try{await work();}catch(e){setReviewError(e instanceof Error?e.message:'操作未完成。');}finally{setBusy(false);}}
  const visible=home.notebook.filter(i=>filter==='all'||(filter==='active'?i.active_error:!i.active_error));
  const active=home.notebook.filter(i=>i.active_error).length;
  return <>
    <section className={styles.metrics} aria-label="学习概览">
      <button onClick={()=>setTab('notebook')}><BookOpen size={20}/><span><b>{home.notebook.length}</b><small>个人错题</small></span></button>
      <button onClick={()=>setTab('review')}><CalendarClock size={20}/><span><b>{units.filter(u=>u.is_due).length}</b><small>到期复习</small></span></button>
      <button onClick={()=>{setTab('notebook');setFilter('active');}}><Layers3 size={20}/><span><b>{active}</b><small>待巩固题目</small></span></button>
      <div><span className={styles.identity}>课堂学生</span><strong>{home.student_id}</strong></div>
    </section>
    <nav className={styles.tabs} aria-label="学习内容">
      {([['notebook','我的错题'],['review','复习计划'],['profile','学习证据']] as const).map(([id,label])=><button key={id} aria-current={tab===id?'page':undefined} onClick={()=>{setTab(id);setError('');setNotice('');}}>{label}{id==='review'&&units.some(u=>u.is_due)&&<i/>}</button>)}
    </nav>
    {error&&<p role="alert" className={styles.error}>{error}</p>}{notice&&<p role="status" className={styles.notice}><Check size={16}/>{notice}</p>}
    {tab==='notebook'&&<>
      <div className={styles.sectionHeading}><div><h2>每一道错题，都是下一步的起点。</h2><p>查看教师反馈，继续辅导，或安排一次独立重做。</p></div>
        <div className={styles.filters} aria-label="错题筛选">{([['all','全部'],['active','待巩固'],['corrected','已订正']] as const).map(([id,label])=><button key={id} aria-pressed={filter===id} onClick={()=>setFilter(id)}>{label}</button>)}</div>
      </div>
      {!visible.length&&<div className={styles.empty}><BookOpen size={32}/><h3>{home.notebook.length?'当前分类暂无题目':'你的错题本，从一次作答开始。'}</h3><p>{home.notebook.length?'可以切换分类查看其他题目。':'教师批改后收录的个人错题将在这里呈现。'}</p></div>}
      <div className={styles.grid}>{visible.map(item=><article className={styles.card} key={item.id}>
        <div className={styles.cardMeta}><span>{item.question_type}</span><span>{item.progress?.label||(item.active_error?'待巩固':'已订正')}</span></div>
        <div className={styles.question}>{math(item.question)}</div><div className={styles.tags}>{item.knowledge_points.map(p=><span key={p}>{p}</span>)}</div>
        <div className={styles.cardActions}><button disabled={!!opening||busy} onClick={()=>void open(item.submission_id)}>理解与订正 <ArrowRight size={17}/></button>
          <button aria-label={'加入复习 '+item.question} disabled={busy||units.some(u=>u.submission_id===item.submission_id&&!u.stale)} onClick={()=>void add(item.submission_id)}><Plus size={16}/>{units.some(u=>u.submission_id===item.submission_id&&!u.stale)?'已加入':'安排复习'}</button></div>
      </article>)}</div>
    </>}
    {tab==='review'&&<>
      <div className={styles.sectionHeading}><div><h2>用独立作答，检验真正理解。</h2><p>先重做，再核验；根据实际完成情况，由 FSRS 安排下一次复习。</p></div><button className={styles.textButton} aria-label="刷新复习计划" onClick={()=>void action(refreshUnits)}><RefreshCw size={17}/>刷新</button></div>
      {!units.length&&<div className={styles.empty}><CalendarClock size={32}/><h3>选择一道值得重做的题。</h3><p>在错题卡片中点击「安排复习」，即可建立个人计划。</p><button className={styles.primary} onClick={()=>setTab('notebook')}>选择错题 <ChevronRight size={16}/></button></div>}
      <div className={styles.reviewList}>{units.map(u=><article className={styles.reviewRow} key={u.unit_id}>
        <div className={styles.reviewMarker}><CalendarClock size={22}/></div><div className={styles.reviewBody}><div className={styles.cardMeta}><span>{u.objective}</span><span>{u.stale?'依据已更新':u.is_due?'今日待复习':'按计划复习'}</span></div><div className={styles.question}>{math(u.question)}</div><small>{u.stale?'原计划保留，请为新版重新安排复习。':time(u.due)+' · 已记录 '+u.valid_reviews+' 次有效复习'}</small></div>
        <div className={styles.reviewActions}>{u.stale?<button className={styles.secondary} disabled={busy} onClick={()=>void add(u.submission_id)}>更新计划</button>:<><button className={styles.primary} disabled={busy} onClick={()=>void begin(u)}>独立重做 <ArrowRight size={16}/></button>{u.pending_run_id&&<button className={styles.textButton} disabled={busy} onClick={()=>void begin(u,true)}>查看作答反馈</button>}</>}</div>
      </article>)}</div>
    </>}
    {tab==='profile'&&<>
      <div className={styles.sectionHeading}><div><h2>理解有迹可循，进步有据可查。</h2><p>区分原答、辅导后完成与独立验证；每项记录都可回到原题。</p></div></div>
      {!home.profile.points.length&&<div className={styles.empty}><Layers3 size={32}/><h3>学习证据正在积累。</h3><p>完成作答、订正和复习后，这里将呈现具体记录。</p></div>}
      <div className={styles.evidenceGrid}>{home.profile.points.map(point=>{
        const counts=[point.original_correct,point.original_incorrect,point.assisted_success,point.independent_success];const total=counts.reduce((a,b)=>a+b,0);
        return <article className={styles.evidenceCard} key={point.label}><h3>{point.label}</h3><div className={styles.evidenceBar} aria-label={point.label+'作答证据分布'}>{counts.map((n,i)=>n>0&&<i key={i} style={{width:(100*n/Math.max(total,1))+'%',background:['#77b39d','#dfaa71','#bac1ec','#536bdc'][i]}}/>)}</div>
          <div className={styles.evidenceStats}>{['原答正确','原答错误','辅导后完成','独立验证'].map((label,i)=><span key={label}><b>{counts[i]}</b>{label}</span>)}</div>
          <div className={styles.evidenceLinks}>{Array.from(new Set(point.evidence.map(e=>e.submission_id))).slice(-3).map((id,i)=><button key={id} onClick={()=>void open(id)}>来源题目 {i+1}<ChevronRight size={13}/></button>)}</div></article>;
      })}</div><p className={styles.footnote}>统计的是具体作答证据，不换算为未经验证的能力分数或掌握概率。</p>
    </>}
    <dialog ref={dialog} className={styles.dialog} onCancel={()=>setRun(null)} aria-label="独立重做">
      {run&&<><header className={styles.dialogHeading}><div><small>INDEPENDENT PRACTICE</small><h2>{result?'本次作答反馈':'独立重做'}</h2></div><button aria-label="关闭复习" onClick={()=>setRun(null)}><X size={21}/></button></header>
        <div className={styles.reviewQuestion}>{math(run.question)}</div>
        {reviewError&&<p role="alert" className={styles.error}>{reviewError}</p>}
        {!result?<form onSubmit={e=>{e.preventDefault();void reviewAction(async()=>{setResult(await request<Result>('/review-runs/'+run.run_id+'/attempt',{steps:steps.split('\n').filter(s=>s.trim()),answer,helped}));await refreshUnits();await refresh();});}}>
          <label className={styles.label}>解题过程<textarea aria-label="复习解题过程" rows={6} maxLength={8000} value={steps} onChange={e=>setSteps(e.target.value)} placeholder="写出关键条件与推导过程"/></label>
          <label className={styles.label}>最终答案<textarea aria-label="复习最终答案" rows={2} maxLength={2000} value={answer} onChange={e=>setAnswer(e.target.value)}/></label>
          <label className={styles.check}><input type="checkbox" checked={helped} onChange={e=>setHelped(e.target.checked)}/>本次借助了提示、参考答案或他人帮助</label>
          <footer className={styles.dialogActions}><button type="button" className={styles.textButton} disabled={busy} onClick={()=>void open(run.submission_id)}>需要帮助，进入辅导</button><button type="submit" className={styles.primary} disabled={busy||(!steps.trim()&&!answer.trim())}>{busy?'正在保存…':'提交作答'}</button></footer>
        </form>:<section className={styles.result}>
          <p className={styles.resultTitle}>{result.assessment?({correct:'本次核验通过',incorrect:'本次仍需订正',uncertain:'等待教师进一步复核'}[result.assessment.verdict]||'作答已保存'):'作答已保存，等待教师复核'}</p>
          <p>{result.assessment?.note||'本题需要结合解题过程核验。教师反馈后，可刷新查看结果。'}</p>
          <p className={styles.footnote}>{result.independent?'记录为本次未使用帮助的作答。':'已记录使用帮助；本次不能记为独立回忆成功。'}</p>
          {result.can_rate?<><h3>本次完成情况</h3><div className={styles.rating}>{[1,2,3,4].map((rating,i)=><button key={rating} className={styles.secondary} disabled={busy||(rating===1?result.can_recall_success:!result.can_recall_success)} onClick={()=>void reviewAction(async()=>{const next=await request<{due:string}>('/review-runs/'+run.run_id+'/rating',{attempt_id:result.attempt_id,rating});setRun(null);await refreshUnits();await refresh();setNotice('复习已记录，下次复习：'+time(next.due));})}>{['未能独立完成','较吃力','顺利完成','轻松完成'][i]}</button>)}</div></>:<button className={styles.secondary} disabled={busy} onClick={()=>void reviewAction(async()=>setResult(await request<Result>('/review-runs/'+run.run_id+'/result')))}>刷新核验结果</button>}
        </section>}
      </>}
    </dialog>
  </>;
}
