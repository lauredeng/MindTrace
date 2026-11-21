"use client";
import { useEffect,useState } from "react";
import { usePathname } from "next/navigation";
import { apiFetch,apiUrl } from "@/lib/api";
import { BookOpen,Check,FileText,X } from "lucide-react";
import MarkdownRenderer from "@/components/common/MarkdownRenderer";

type Source={submission_id:string;question:string;original_steps:string[];original_answer:string;
  source_revision:string;
  material_fingerprint:string;reference_revision:string|null;grading_revision:string|null;
  judgment:{basis:string;confirmed:boolean};correction_progress:{state:string;feedback?:string}};

export default function MindTraceDock(){
  const path=usePathname();const[record,setRecord]=useState<Source|null>(null);
  const[stale,setStale]=useState(false);const[open,setOpen]=useState(false);
  const[answer,setAnswer]=useState("");const[steps,setSteps]=useState("");
  const[message,setMessage]=useState("");const[sending,setSending]=useState(false);
  useEffect(()=>{
    const id=path.match(/\/(?:sessions|chat)\/([^/]+)$/)?.[1];
    setRecord(null);setOpen(false);setMessage("");setAnswer("");setSteps("");
    if(!id)return;
    const controller=new AbortController();
    void apiFetch(apiUrl("/api/mindtrace/session/"+encodeURIComponent(id)),{signal:controller.signal,skipAuthRedirect:true})
      .then(r=>r.ok?r.json():null).then(data=>{if(data){setRecord(data.source);setStale(data.stale);}}).catch(()=>{});
    return()=>controller.abort();
  },[path]);
  if(!record)return null;
  async function submit(){
    if(!record)return;setSending(true);setMessage("");
    try{
      const response=await apiFetch(apiUrl("/api/mindtrace/corrections"),{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({submission_id:record.submission_id,expected_fingerprint:record.material_fingerprint,
          expected_source_revision:record.source_revision,
          expected_reference_revision:record.reference_revision,expected_grading_revision:record.grading_revision,
          answer,steps:steps.split("\n").filter(s=>s.trim()),command_id:crypto.randomUUID(),independent:false,hint_used:true,answer_revealed:true})});
      if(!response.ok)throw Error("未提交成功，请检查作答或重新打开原题。");
      setMessage("订正已回传，教师端可查看。");setAnswer("");setSteps("");
    }catch(e){setMessage(e instanceof Error?e.message:"提交失败，请重试。");}finally{setSending(false);}
  }
  return <>
    <div style={{position:"fixed",right:24,top:64,zIndex:55,display:"flex",gap:8,boxShadow:"0 8px 28px #26345a18",borderRadius:14,background:"var(--background,#fff)",border:"1px solid #dce1ef",padding:6}}>
      <a href="/mindtrace" aria-label="返回我的错题" style={{padding:10}}><BookOpen size={18}/></a>
      <button onClick={()=>setOpen(true)} style={{display:"flex",gap:8,alignItems:"center",padding:"8px 14px",color:"#4e63d5"}}><FileText size={17}/>原题与订正</button>
    </div>
    {open&&<div style={{position:"fixed",inset:0,zIndex:70,background:"#14203932"}} onClick={()=>setOpen(false)}>
      <aside role="dialog" aria-label="原题与订正" aria-modal="true" onClick={e=>e.stopPropagation()} style={{position:"absolute",right:0,top:0,bottom:0,width:"min(540px,100%)",overflowY:"auto",background:"var(--background,#fff)",padding:28,boxShadow:"-12px 0 50px #15234a15"}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:24}}><h2 style={{fontSize:22,fontWeight:600}}>原题与订正</h2><button onClick={()=>setOpen(false)} aria-label="关闭原题面板"><X size={21}/></button></div>
        {stale&&<p role="alert" style={{color:"#ac6334",marginBottom:18}}>教师已更新本题依据，请返回我的错题重新打开。</p>}
        <MarkdownRenderer content={record.question} allowHtml={false} enableImages={false}/>
        <h3 style={{fontWeight:600,marginTop:26,marginBottom:12}}>原始作答</h3>
        {record.original_steps.map((line,i)=><p key={i} style={{lineHeight:1.9}}>{i+1}. {line}</p>)}
        <p style={{marginTop:8}}>原答案：{record.original_answer||"未填写"}</p>
        <div style={{margin:"24px 0",padding:18,borderRadius:12,background:"#edf1ff",fontSize:14,lineHeight:1.8}}>
          <b>{record.judgment.confirmed?"教师确认的反馈":"批改建议"}</b><MarkdownRenderer content={record.judgment.basis} allowHtml={false} enableImages={false}/>
        </div>
        <h3 style={{fontWeight:600,marginBottom:12}}>提交本次订正</h3>
        <label style={{fontSize:13}}>解题过程<textarea aria-label="订正过程" value={steps} onChange={e=>setSteps(e.target.value)} rows={5} maxLength={8000} style={{width:"100%",border:"1px solid #dce1eb",borderRadius:12,padding:12,marginTop:8,marginBottom:16}}/></label>
        <label style={{fontSize:13}}>最终答案<textarea aria-label="订正答案" value={answer} onChange={e=>setAnswer(e.target.value)} rows={2} maxLength={2000} style={{width:"100%",border:"1px solid #dce1eb",borderRadius:12,padding:12,marginTop:8}}/></label>
        <p style={{fontSize:12,color:"#8a94aa",lineHeight:1.9,margin:"16px 0"}}>本次记录为辅导后订正。独立重做请进入<a href="/mindtrace" style={{color:"#5369c7"}}>复习计划</a>，作答前不展示参考答案。</p>
        <button disabled={stale||sending||(!answer.trim()&&!steps.trim())} onClick={()=>void submit()} style={{display:"flex",alignItems:"center",gap:8,padding:"12px 20px",background:"#4f64d6",color:"white",borderRadius:12,opacity:stale||sending?0.5:1}}><Check size={17}/>{sending?"正在提交…":"提交订正"}</button>
        {message&&<p role="status" style={{fontSize:14,marginTop:16,color:"#4e63b6"}}>{message}</p>}
      </aside>
    </div>}
  </>;
}
