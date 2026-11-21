"use client";

// MindTrace business entry. Teaching screens and runtime remain upstream.
import { useEffect, useState } from "react";
import { apiFetch, apiUrl } from "@/lib/api";
import { invalidateAuthStatusCache } from "@/lib/auth";
import { hasStoredLanguage,hasStoredResponseLanguage,writeStoredLanguage,writeStoredResponseLanguage } from "@/context/app-shell-storage";
import { RefreshCw } from "lucide-react";
import LearningDashboard,{type Home} from "./LearningDashboard";
import styles from "./MindTrace.module.css";

export default function MindTraceEntry() {
  const [home, setHome] = useState<Home | null>(null);
  const [error, setError] = useState("");
  const [opening, setOpening] = useState("");
  const [code, setCode] = useState("");
  async function open(submission_id: string) {
    setOpening(submission_id); setError("");
    try {
      const response = await apiFetch(apiUrl("/api/mindtrace/open"), { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ submission_id }), skipAuthRedirect:true });
      if (!response.ok) throw Error("题目暂时无法打开，请刷新课堂后重试。");
      const result = await response.json();
      if (!result.route?.startsWith("/learning/mastery/")) throw Error("学习入口响应无效。");
      window.location.assign(result.route);
    } catch (e) { setError(e instanceof Error ? e.message : "打开失败。"); setOpening(""); }
  }
  async function load() {
    const response = await apiFetch(apiUrl("/api/mindtrace/me"), { skipAuthRedirect:true });
    if (!response.ok) throw Error("请从学生课堂进入，或使用自己的课堂学习码连接。");
    setHome(await response.json());
  }
  async function connect(ticket: string) {
    const response = await apiFetch(apiUrl("/api/mindtrace/connect"), { method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({ticket}),skipAuthRedirect:true });
    if (!response.ok) throw Error("入口已过期，请从课堂重新进入。");
    const result=await response.json(); invalidateAuthStatusCache();
    if(!hasStoredLanguage())writeStoredLanguage('zh');
    if(!hasStoredResponseLanguage())writeStoredResponseLanguage('zh');
    if (result.submission_id) await open(result.submission_id); else await load();
  }
  useEffect(() => {
    const ticket=new URLSearchParams(window.location.hash.slice(1)).get("ticket");
    window.history.replaceState(null,"",window.location.pathname);
    void (ticket ? connect(ticket) : load()).catch(e=>setError(e.message));
    // One-time handoff is consumed once, never copied into browser storage.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function connectCode() {
    setError("");
    try {
      const response=await apiFetch(apiUrl("/api/mindtrace/tickets"),{method:"POST",
        headers:{"Content-Type":"application/json",Authorization:"Bearer "+code.trim()},
        body:JSON.stringify({}),skipAuthRedirect:true});
      if(!response.ok) throw Error("学生学习码无效，请核对课堂入口。");
      const result=await response.json();setCode("");await connect(result.ticket);
    } catch(e){setError(e instanceof Error?e.message:"连接失败。");}
  }
  return <main style={{maxWidth:1120,margin:"0 auto",padding:"64px 28px 96px"}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:52}}>
      <a href="/mindtrace" style={{fontSize:22,fontWeight:650,letterSpacing:"-.6px"}}>MindTrace <span style={{color:"#4f63dc"}}>循理 AI</span></a>
      {home&&<button onClick={()=>void load().catch(e=>setError(e.message))} aria-label="刷新学习记录"><RefreshCw size={18}/></button>}
    </div>
    <p style={{color:"#6371a2",fontSize:12,letterSpacing:3,marginBottom:16}}>PERSONAL LEARNING SPACE</p>
    <h1 className={styles.heroTitle}><span>循理而学，</span><span>知其所以然。</span></h1>
    <p style={{color:"#73798b",lineHeight:1.9,maxWidth:650}}>从自己的作答出发，理解关键步骤，完成独立订正。教师反馈、辅导记录与复习计划，在这里衔接。</p>
    {error&&<div role="alert" style={{marginTop:24,padding:18,borderRadius:12,background:"#fff1e9",color:"#854b2a"}}>{error}</div>}
    {!home&&!opening&&<form onSubmit={e=>{e.preventDefault();void connectCode();}} style={{marginTop:40,maxWidth:470,display:"flex",gap:12}}>
      <input aria-label="学生课堂学习码" type="password" autoComplete="off" value={code} onChange={e=>setCode(e.target.value)} placeholder="学生课堂学习码" required
        style={{flex:1,minWidth:0,padding:"14px 16px",border:"1px solid #dce0eb",borderRadius:12}}/>
      <button type="submit" style={{padding:"12px 24px",borderRadius:12,background:"#4e62d8",color:"white"}}>进入</button>
    </form>}
    {opening&&<p role="status" style={{marginTop:36,color:"#4e62d8"}}>正在关联原题与教师反馈…</p>}
    {home&&<LearningDashboard home={home} open={open} opening={opening} refresh={load}/>}
    <p style={{fontSize:11,color:"#9aa0b1",marginTop:54}}>MindTrace 循理 AI · 教学能力基于 HKUDS DeepTutor 开源运行时</p>
  </main>;
}
