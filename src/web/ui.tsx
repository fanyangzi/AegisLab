import { useEffect, useRef, useId, cloneElement, isValidElement, type ReactNode, type ReactElement } from 'react'
import type { Tone } from './types'
const paths: Record<string, ReactNode> = {
 shield: <><path d="M12 3 21 7v6c0 5-9 9-9 9S3 18 3 13V7Z"/><path d="m8 12 3 3 5-6"/></>,
 cube: <><path d="m12 3 9 5v9l-9 5-9-5V8Z M3 8l9 5 9-5 M12 13v9 M7 5l10 6"/></>,
 plans: <><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v4H9z M9 11h6 M9 15h6 M9 18h3"/></>,
 tasks: <><path d="m3 6 2 2 3-4 M11 6h10 M3 13l2 2 3-4 M11 13h10 M3 20l2 2 3-4 M11 20h10"/></>,
 library: <><path d="M4 3h4v18H4z M10 3h4v18h-4z M16 5l4-1 3 16-4 1z"/></>,
 resources: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
 settings: <><path d="m9 3-.5 3-3 1-2-1-2 4 2 2v2l-2 2 2 4 3-1 2 1 1 3h5l1-3 2-1 3 1 2-4-2-2v-2l2-2-2-4-3 1-2-1-.5-3Z" transform="translate(1 -1) scale(.92)"/><circle cx="12" cy="12" r="3"/></>,
 graph: <><circle cx="12" cy="12" r="3"/><circle cx="5" cy="4" r="2"/><circle cx="20" cy="6" r="2"/><circle cx="5" cy="20" r="2"/><circle cx="20" cy="20" r="2"/><path d="m7 6 3 4 M15 10l3-3 M10 15l-3 3 M14 14l4 4"/></>,
 clock: <><circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/></>,
 search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></>,
 bell: <><path d="M5 17h14l-2-4V9a5 5 0 0 0-10 0v4z M10 21h4"/></>,
 plus: <path d="M12 5v14 M5 12h14"/>, close: <path d="m6 6 12 12 M6 18 18 6"/>,
 chevron: <path d="m9 5 7 7-7 7"/>, down: <path d="m6 9 6 6 6-6"/>,
 arrow: <path d="M4 12h16 m-6-6 6 6-6 6"/>, back: <path d="M20 12H4 m6-6-6 6 6 6"/>,
 check: <path d="m5 12 4 4L20 5"/>, alert: <><path d="m12 3 10 18H2z"/><path d="M12 9v5 M12 17h.01"/></>,
 info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v6 M12 7h.01"/></>,
 file: <><path d="M5 3h9l5 5v13H5z M14 3v6h5 M8 13h8 M8 17h6"/></>,
 export: <><path d="M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5"/></>,
 edit: <><path d="m14 4 6 6 M4 20l5-1L21 7l-5-5L4 14Z M12 21h9"/></>,
 target: <><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 1v4 M12 19v4 M1 12h4 M19 12h4"/></>,
 reset: <><path d="M3 11a9 9 0 1 1 2 7 M3 4v7h7"/></>,
 minus: <path d="M5 12h14"/>, layer: <path d="m12 3 10 5-10 5L2 8Z M2 12l10 5 10-5 M2 17l10 5 10-5"/>,
 filter: <><path d="M3 5h18 M6 12h12 M10 19h4"/></>,
 upload: <><path d="M12 16V3 m-5 5 5-5 5 5 M4 16v5h16v-5"/></>,
 user: <><circle cx="12" cy="8" r="4"/><path d="M4 22v-3a8 8 0 0 1 16 0v3"/></>,
 flask: <><path d="M8 3h8 M9 3v7L3 20q0 2 2 2h14q2 0 2-2l-6-10V3 M7 15h10"/></>,
 link: <><path d="m9 8 4-4a5 5 0 0 1 7 7l-4 4 M15 16l-4 4a5 5 0 0 1-7-7l4-4 M8 16l8-8"/></>,
 dots: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
 eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></>,
 layout: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16 M8 9h13"/></>,
 trash: <><path d="M3 6h18 M9 6V3h6v3 M6 6l1 15h10l1-15 M10 10v7 M14 10v7"/></>,
 spark: <><path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4Z M20 2v4 M18 4h4"/></>,
}
export function Icon({name, size=20}: {name: string; size?: number}) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.file}</svg> }
export function Badge({children, tone='muted'}: {children: ReactNode; tone?: Tone}) {return <span className={`al-badge ${tone}`}><i/>{children}</span>}
export function Button({children, icon, onClick, disabled, primary=false, className='', title}: {children?: ReactNode; icon?: string; onClick?:()=>void; disabled?:boolean; primary?:boolean; className?:string; title?:string}) {return <button type="button" className={`al-button ${primary?'primary':''} ${className}`} disabled={disabled} onClick={onClick} title={title} aria-label={title}>{icon&&<Icon name={icon} size={17}/>} {children}</button>}
export function Modal({title, children, onClose, wide=false}: {title:string; children:ReactNode; onClose:()=>void; wide?:boolean}) {
 const ref=useRef<HTMLDivElement>(null)
 useEffect(()=>{ const prev=document.activeElement as HTMLElement; const el=ref.current; el?.focus(); const key=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose();if(e.key==='Tab'&&el){const a=[...el.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select, textarea, [tabindex="0"]')]; const first=a[0],last=a.at(-1); if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}};document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);prev?.focus()}},[onClose])
 return <div className="al-modal-scrim" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><div ref={ref} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} className={`al-modal ${wide?'wide':''}`}><header><div><span className="al-eyebrow">AEGISLAB WORKSPACE</span><h2>{title}</h2></div><Button icon="close" title="关闭弹窗" onClick={onClose}/></header>{children}</div></div>
}
export function Empty({title,detail,children}: {title:string;detail:string;children?:ReactNode}) {return <div className="al-empty"><span className="al-empty-icon"><Icon name="layer" size={28}/></span><h3>{title}</h3><p>{detail}</p>{children}</div>}
export function Field({label,children,hint}: {label:string;children:ReactNode;hint?:string}) {
 const id=useId()
 const control=isValidElement(children)?cloneElement(children as ReactElement<{"aria-labelledby"?:string;"aria-describedby"?:string}>,{'aria-labelledby':id,'aria-describedby':hint?`${id}-hint`:undefined}):children
 return <label className="al-field"><span id={id}>{label}</span>{control}{hint&&<small id={`${id}-hint`}>{hint}</small>}</label>
}
export const toneFor = (state:string): Tone => state==='blocked'?'red':['unknown','draft','recheck','pending'].includes(state)?'amber':['approved','pass','verified','done'].includes(state)?'green':state==='ready'?'blue':'muted'
export const dateText=(value:string)=>new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})
export const timeText=(value:string)=>new Date(value).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false})
export const localDate=(d=new Date())=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
export const localInput=(value:string)=>{const d=new Date(value); return `${localDate(d)}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`}
export function exportJson(value:unknown,name:string) {const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
