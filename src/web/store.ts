import { useCallback, useEffect, useRef, useState } from 'react'
import type { Workspace, Snapshot, Operation } from './types'
import { uid } from './types'
import { applyLocal, assertWorkspace, checkWorkspace, emptyWorkspace, planStatus } from './domain'
const KEY='aegislab.web.workspace.v1'
export const API_BASE=(import.meta.env.VITE_API_BASE_URL||'').replace(/\/$/,'')
let token=''
export const setSessionToken=(value:string)=>{token=value}
export const authHeaders=()=>token?{Authorization:`Bearer ${token}`}:{Authorization:''}
export async function request<T>(path:string, body?:unknown):Promise<T> {
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),path.endsWith("/analysis")||path.includes("/ai-preview")?45000:10000)
 try {const response=await fetch(`${API_BASE}${path}`,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:`请求失败（${response.status}），请检查输入或连接。`);return data} finally {clearTimeout(timer)}
}
const localSnapshot=(workspace:Workspace):Snapshot=>{const checks=checkWorkspace(workspace);return {workspace,checks,statuses:Object.fromEntries(workspace.plans.map(p=>[p.id,planStatus(workspace,p,checks)])),mode:'local'}}
function readLocal(): {value:Workspace; error:string} {try{const raw=localStorage.getItem(KEY);if(!raw)return {value:emptyWorkspace(),error:''};const value=JSON.parse(raw);assertWorkspace(value);return {value,error:''}}catch{return {value:emptyWorkspace(),error:'浏览器存档无法读取；原存档未覆盖。请在设置中导出原始存档后处理。'}}}
export function useWorkspace() {
 const initial=useRef(readLocal()),[snapshot,setSnapshot]=useState<Snapshot>(()=>localSnapshot(initial.current.value)),[busy,setBusy]=useState(false),[booting,setBooting]=useState(true),[connection,setConnection]=useState('正在检查服务端 API'),[error,setError]=useState(initial.current.error)
 const current=useRef(snapshot);current.current=snapshot
 const inFlight=useRef(false)
 useEffect(()=>{let live=true;request<Snapshot>('/api/spatial').then(s=>{assertWorkspace(s.workspace);if(!live)return;setConnection('API 可连接');
   // A previous build may have left a small example snapshot in localStorage.
   // Example data is explicitly replaceable; user-authored workspaces are not.
   const local=initial.current.value
   const localIsExample=local.provenance==='example'
   const serverIsRicher=s.workspace.equipment.length>local.equipment.length||s.workspace.plans.length>local.plans.length||s.workspace.revision>local.revision
   if(!initial.current.error&&(!local.laboratories.length||(localIsExample&&serverIsRicher))){
     setSnapshot({...s,mode:'server'});setConnection('服务端 API 已连接')
   }
 }).catch(()=>{if(live)setConnection('浏览器草稿 · API 未连接')}).finally(()=>{if(live)setBooting(false)});return()=>{live=false}},[])
 useEffect(()=>{const changed=(event:StorageEvent)=>{if(event.key===KEY&&current.current.mode==='local'){const data=readLocal();if(data.error)setError(data.error);else {setSnapshot(localSnapshot(data.value));setConnection('已同步其他标签页的浏览器存档')}}};window.addEventListener('storage',changed);return()=>window.removeEventListener('storage',changed)},[])
 const mutate=useCallback(async(op:Operation)=>{
  if(inFlight.current)throw new Error('上一项操作尚未完成，请稍后。')
  if(initial.current.error&&current.current.mode==='local')throw new Error(initial.current.error)
  inFlight.current=true;setBusy(true);setError('')
  try {
   const s=current.current
   if(s.mode==='server'){
    const result=await request<Snapshot>('/api/spatial/actions',{...op,expectedRevision:s.workspace.revision,requestId:uid('request')});assertWorkspace(result.workspace);setSnapshot({...result,mode:'server'});current.current={...result,mode:'server'}
   } else {
    const saveDraft=()=>{
    const saved=readLocal();if(saved.error)throw new Error(saved.error)
    if(saved.value.revision!==s.workspace.revision){setSnapshot(localSnapshot(saved.value));throw new Error('存档被其他标签页更新，请重新检查后保存。')}
    const workspace=applyLocal(s.workspace,op);localStorage.setItem(KEY,JSON.stringify(workspace));const result=localSnapshot(workspace);setSnapshot(result);current.current=result
    };
    if(navigator.locks)await navigator.locks.request('aegislab.web.workspace',saveDraft);else saveDraft();
   }
  }catch(e){const message=e instanceof Error?e.message:'操作未完成。';setError(message);if(message.includes('工作区已被其他请求更新')){try{const latest=await request<Snapshot>('/api/spatial');setSnapshot({...latest,mode:'server'})}catch{}}throw e}
  finally{inFlight.current=false;setBusy(false)}
 },[])
 const connect=useCallback(async()=>{const data=await request<Snapshot>('/api/spatial');assertWorkspace(data.workspace);setSnapshot({...data,mode:'server'});setConnection('服务端 API 已连接');setError('')},[])
 const openLocal=useCallback(()=>{const data=readLocal();setSnapshot(localSnapshot(data.value));setError(data.error);setConnection('浏览器草稿 · 与服务器存档分离')},[])
 const refresh=useCallback(async()=>{if(current.current.mode==='server')await connect();else{const data=readLocal();setSnapshot(localSnapshot(data.value));setError(data.error)}},[connect])
 return {snapshot,busy,booting,connection,error,setError,mutate,connect,openLocal,refresh,exportRaw:()=>localStorage.getItem(KEY)}
}
