import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js'
import type { Equipment, Laboratory, Plan, Selection, Check } from './types'
import { Button, Icon } from './ui'

const C={white:0xf8fbff,body:0xdfe8f1,blue:0x3c76e8,ink:0x4a5e76,metal:0xaebfcd,glass:0xb6dded,worktop:0xfdfefe}
function material(color:number, more:THREE.MeshStandardMaterialParameters={}) {return new THREE.MeshStandardMaterial({color,roughness:.52,metalness:.05,...more})}
function box(g:THREE.Group, x:number,y:number,z:number,w:number,h:number,d:number,color:number,round=.035) {
 const m=new THREE.Mesh(round?new RoundedBoxGeometry(w,h,d,2,Math.min(round,w/4,h/4,d/4)):new THREE.BoxGeometry(w,h,d),material(color));m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;g.add(m);return m
}
function cylinder(g:THREE.Group,x:number,y:number,z:number,r:number,h:number,color:number,top=r) {const m=new THREE.Mesh(new THREE.CylinderGeometry(top,r,h,16),material(color));m.position.set(x,y,z);m.castShadow=true;g.add(m);return m}
function tube(g:THREE.Group,points:number[][],radius:number,color:number) {const curve=new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p as [number,number,number])));const m=new THREE.Mesh(new THREE.TubeGeometry(curve,16,radius,8,false),material(color,{metalness:.7,roughness:.25}));g.add(m);return m}
function bottle(g:THREE.Group,x:number,y:number,z:number,scale=1,color=0xa9d9d3) {const h=.28*scale;cylinder(g,x,y+h/2,z,.075*scale,h,color);cylinder(g,x,y+h+.015*scale,z,.04*scale,.06*scale,C.ink);box(g,x,y+h/2,z+.075*scale,.09*scale,.11*scale,.004,C.white,0)}
function flask(g:THREE.Group,x:number,y:number,z:number,scale=1) {const bulb=new THREE.Mesh(new THREE.SphereGeometry(.12*scale,14,10),material(C.glass,{transparent:true,opacity:.7,roughness:.12}));bulb.position.set(x,y+.13*scale,z);g.add(bulb);cylinder(g,x,y+.30*scale,z,.035*scale,.23*scale,C.glass);cylinder(g,x,y+.42*scale,z,.05*scale,.03*scale,C.white)}
function label(g:THREE.Group,text:string,x:number,y:number,z:number,width=1.0){const canvas=document.createElement('canvas');canvas.width=256;canvas.height=80;const ctx=canvas.getContext('2d')!;ctx.fillStyle='#346bea';ctx.fillRect(0,0,256,80);ctx.fillStyle='white';ctx.font='600 40px Arial';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(text,128,42);const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;const mesh=new THREE.Mesh(new THREE.PlaneGeometry(width,width*80/256),new THREE.MeshBasicMaterial({map:texture}));mesh.position.set(x,y,z);g.add(mesh)}
function cabinetBase(g:THREE.Group,w:number,d:number) {box(g,0,.47,0,w,.9,d,C.body);box(g,0,.08,0,w-.12,.12,d-.04,C.ink);for(const side of [-1,1]){box(g,side*w/4,.5,d/2+.018,w/2-.045,.74,.035,C.white);box(g,side*.11,.67,d/2+.055,.035,.23,.035,C.metal)}}
function model(e:Equipment){const g=new THREE.Group();let h=1.4,w=2,d=1.3
 if(e.kind==='hood') {w=2.5;d=1.35;h=2.85;cabinetBase(g,w,d);box(g,0,1.01,0,w+.10,.12,d+.1,C.ink);box(g,0,1.87,-.60,w,1.65,.10,C.body);for(const s of [-1,1])box(g,s*1.18,1.89,0,.14,1.7,d,C.white);box(g,0,2.7,0,w,.3,d,C.white);box(g,0,2.54,.66,w-.32,.035,.045,C.metal);const glass=box(g,0,2.1,.58,w-.35,.8,.035,C.glass);(glass.material as THREE.MeshStandardMaterial).transparent=true;(glass.material as THREE.MeshStandardMaterial).opacity=.28;box(g,0,1.69,.61,w-.32,.04,.07,C.metal);box(g,0,2.53,-.3,1.7,.035,.16,0xe3f6ff);cylinder(g,0,2.99,-.28,.25,.35,C.metal);label(g,e.code,0,2.72,.687,.67);box(g,1.18,1.46,.72,.12,.32,.03,C.ink);box(g,1.18,1.54,.74,.07,.06,.01,0x89d3be);bottle(g,-.72,1.10,-.27,.95);bottle(g,-.48,1.10,-.28,.8,0xc3ceea);flask(g,.37,1.10,-.13,1.25);box(g,-.1,1.08,.06,.55,.04,.5,C.metal)}
 else if(e.kind==='bench') {w=3.5;d=1.48;h=2.1;cabinetBase(g,w,d);box(g,0,1.0,0,w+.1,.13,d+.08,C.worktop);for(const x of [-1.42,1.42])box(g,x,1.46,0,.065,.88,.07,C.metal);box(g,0,1.73,0,3.1,.055,.42,C.metal);box(g,0,1.36,0,3.1,.055,.42,C.white);for(let i=0;i<7;i++)bottle(g,-1.25+i*.39,1.765,0,.7,i%3===0?0xc5a876:0xbddbd4);box(g,-1.2,1.17,.43,.38,.2,.34,C.body);flask(g,.45,1.085,.44,.9);flask(g,.85,1.085,.38,.8);box(g,-.25,1.09,.42,.5,.025,.35,C.blue);for(const x of [-1.05,1.05]){cylinder(g,x,.63,1.12,.26,.10,C.ink);cylinder(g,x,.36,1.12,.035,.5,C.metal);for(const off of [-.22,.22])box(g,x+off,.12,1.12,.5,.035,.04,C.metal)}label(g,e.code,0,.60,d/2+.05,.65)}
 else if(e.kind==='storage') {w=1.8;d=1.05;h=2.5;box(g,0,1.25,0,w,2.5,d,C.body);box(g,0,.09,0,w-.1,.15,d,C.ink);for(const s of [-1,1]){box(g,s*.44,1.3,.54,.84,2.25,.05,C.white);const glass=box(g,s*.44,1.65,.58,.64,1.19,.03,C.glass);(glass.material as THREE.MeshStandardMaterial).roughness=.2;box(g,s*.1,1.13,.61,.035,.27,.045,C.metal);for(let i=0;i<3;i++)box(g,s*.44,.66+i*.44,.6,.60,.024,.03,C.metal)}label(g,e.code,0,2.33,.59,.62)}
 else if(e.kind==='analyzer'){w=2.35;d=1.35;h=2.0;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.1,d+.08,C.worktop);box(g,-.42,1.43,-.02,.89,.79,.9,C.white);box(g,-.42,1.59,.455,.70,.28,.02,C.ink);box(g,-.42,1.60,.472,.55,.14,.015,0x91bfdc);box(g,-.43,1.25,.46,.60,.07,.03,C.metal);cylinder(g,-.18,1.38,.51,.035,.025,C.blue);box(g,.7,1.08,0,.60,.06,.54,C.metal);box(g,.7,1.36,-.2,.06,.56,.08,C.ink);box(g,.7,1.64,-.16,.68,.42,.06,C.ink);box(g,.7,1.64,-.12,.59,.34,.012,0xb2d3e7);label(g,e.code,0,.60,.725,.66)}
 else if(e.kind==='sink'){w=2.25;d=1.26;h=1.7;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.1,d+.05,C.worktop);box(g,-.18,1.06,.02,1.20,.025,.78,C.metal);box(g,-.18,1.077,.02,1.02,.012,.63,0x71899e);tube(g,[[.03,1.05,-.45],[.03,1.61,-.45],[.03,1.65,-.1],[.03,1.44,-.1]],.036,C.metal);bottle(g,.86,1.06,-.3,1.2);label(g,e.code,0,.6,.68,.65)}
 else {w=1.7;d=1.1;h=1.7;box(g,0,.8,0,w,1.6,d,0xefd7a5);for(const s of [-1,1]){box(g,s*.4,.82,.57,.73,1.35,.045,0xf9e3b4);box(g,s*.1,.95,.61,.03,.25,.03,C.ink)}box(g,0,1.65,0,w+.06,.07,d+.05,C.ink);label(g,e.code,0,1.37,.603,.65);box(g,0,.38,.61,.60,.15,.01,0xc89b44)}
 g.position.set(e.x,0,e.z);g.rotation.y=e.rotation*Math.PI/180;g.traverse(o=>o.userData.equipmentId=e.id)
 return {group:g,height:h,width:w,depth:d}
}
function room(lab:Laboratory) {const g=new THREE.Group(),w=lab.width,d=lab.depth
 box(g,0,-.16,0,w,.28,d,0xe1e9f2,.1);box(g,0,-.005,0,w-.08,.03,d-.08,0xf1f5f9,.01)
 const lines=new THREE.Group();for(let i=-Math.floor(w/2);i<=w/2;i++)box(lines,i,.015,0,.009,.006,d-.15,0xdce4ed,0);for(let i=-Math.floor(d/2);i<=d/2;i++)box(lines,0,.015,i,w-.15,.006,.009,0xdce4ed,0);g.add(lines)
 box(g,0,1.65,-d/2,w,3.3,.16,0xe7edf3);box(g,w/2,1.65,0,.16,3.3,d,0xe7edf3)
 box(g,0,.22,-d/2+.09,w,.35,.04,0xcfddeb);box(g,w/2-.09,.22,0,.04,.35,d,0xcfddeb)
 for(let x=-w/2+2;x<w/2-1;x+=3){box(g,x,2.80,-d/2+.09,2.40,.38,.035,0xc1ddee);for(const a of [-1,1])box(g,x+a*1.21,2.8,-d/2+.12,.06,.46,.045,C.white);box(g,x,2.8,-d/2+.12,.045,.4,.045,C.white)}
 for(let z=-d/2+2;z<d/2-1;z+=3){box(g,w/2-.10,2.15,z,.04,1.45,2.15,0xc2dcea);for(const a of [-1,0,1])box(g,w/2-.14,2.15,z+a*1.04,.04,1.55,.05,C.white);box(g,w/2-.13,2.93,z,.05,.05,2.2,C.white);box(g,w/2-.13,1.4,z,.14,.08,2.3,C.white)}
 box(g,0,3.08,-d/2+.15,w-.5,.12,.13,C.white);box(g,w/2-.15,3.08,0,.13,.12,d-.5,C.white)
 label(g,lab.name.slice(0,12),-w/2+1.7,2.45,-d/2+.11,2.0)
 return g
}

interface Props { lab:Laboratory; equipment:Equipment[]; plans:Plan[]; checks:Check[]; selection:Selection; planId:string; onSelect:(value:Selection)=>void; reduced:boolean; flat:boolean }
export default function LabScene(props:Props) {
 const host=useRef<HTMLDivElement>(null), overlay=useRef<HTMLDivElement>(null), lines=useRef<SVGSVGElement>(null)
 const live=useRef(props);live.current=props
 const actions=useRef<{zoom:(delta:number)=>void;reset:()=>void;focus:()=>void}|null>(null)
 const [failed,setFailed]=useState(false)
 const layout=JSON.stringify([props.lab,props.equipment.map(({id,kind,x,z,rotation,code})=>({id,kind,x,z,rotation,code}))])
 useEffect(()=>{
  if(props.flat)return
  const el=host.current; if(!el)return; let renderer:THREE.WebGLRenderer
  try {renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'high-performance'})}catch{setFailed(true);return}
  setFailed(false);renderer.setPixelRatio(Math.min(window.devicePixelRatio,1.7));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;el.appendChild(renderer.domElement);renderer.domElement.setAttribute('aria-label','可交互三维实验室：拖动旋转，滚轮缩放；设备也可通过对象清单选择。')
  const scene=new THREE.Scene();const ambient=new THREE.HemisphereLight(0xf7fbff,0xadc3dc,2.1);scene.add(ambient)
  const light=new THREE.DirectionalLight(0xfffaf3,3.2);light.position.set(-7,15,9);light.castShadow=true;light.shadow.mapSize.set(2048,2048);light.shadow.camera.left=-16;light.shadow.camera.right=16;light.shadow.camera.top=16;light.shadow.camera.bottom=-16;light.shadow.normalBias=.035;light.shadow.bias=-.0002;light.shadow.radius=4;scene.add(light)
  const fill=new THREE.DirectionalLight(0xcce4ff,1);fill.position.set(8,7,-8);scene.add(fill)
  scene.add(room(props.lab))
  const camera=new THREE.OrthographicCamera(-10,10,8,-8,.1,200)
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.dampingFactor=.09;controls.minZoom=.5;controls.maxZoom=3;controls.minPolarAngle=.30;controls.maxPolarAngle=Math.PI*.45;controls.enablePan=true;controls.target.set(0,.6,0)
  const reset=()=>{camera.position.set(16,14,19);camera.zoom=1;controls.target.set(0,.5,0);camera.updateProjectionMatrix();controls.update()};reset()
  const models=props.equipment.map(e=>{const m=model(e);scene.add(m.group);const outline=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(m.width+.12,m.height+.1,m.depth+.12)),new THREE.LineBasicMaterial({color:C.blue,transparent:true,opacity:.8}));outline.position.set(e.x,m.height/2,e.z);outline.rotation.y=e.rotation*Math.PI/180;scene.add(outline);return {...m,e,outline}})
  const pointers=new Map<string,HTMLButtonElement>()
  if(overlay.current){overlay.current.replaceChildren();models.forEach(({e})=>{const b=document.createElement('button');b.type='button';b.className='al-scene-label';b.setAttribute('aria-label',`选择设备 ${e.code}`);b.innerHTML='<span class="dot"></span><div><b></b><small></small></div>';b.querySelector('b')!.textContent=`${e.name} ${e.code}`;b.addEventListener('click',()=>live.current.onSelect({type:'equipment',id:e.id}));overlay.current!.appendChild(b);pointers.set(e.id,b)})}
  let width=1,height=1
  const resize=()=>{width=el.clientWidth;height=el.clientHeight;if(!width||!height)return;renderer.setSize(width,height);const base=Math.max(props.lab.width*.46,props.lab.depth*.64,6.1);camera.top=base;camera.bottom=-base;camera.left=-base*width/height;camera.right=base*width/height;camera.updateProjectionMatrix()}
  const ro=new ResizeObserver(resize);ro.observe(el);resize()
  const raycaster=new THREE.Raycaster(),mouse=new THREE.Vector2();let down=[0,0]
  const pointerDown=(e:PointerEvent)=>down=[e.clientX,e.clientY]
  const pointerUp=(ev:PointerEvent)=>{if(Math.hypot(ev.clientX-down[0],ev.clientY-down[1])>5)return;const r=el.getBoundingClientRect();mouse.set((ev.clientX-r.left)/r.width*2-1,-(ev.clientY-r.top)/r.height*2+1);raycaster.setFromCamera(mouse,camera);const hit=raycaster.intersectObjects(models.map(m=>m.group),true).find(h=>h.object.userData.equipmentId);if(hit)live.current.onSelect({type:'equipment',id:hit.object.userData.equipmentId})}
  renderer.domElement.addEventListener('pointerdown',pointerDown);renderer.domElement.addEventListener('pointerup',pointerUp)
  const contextLost=(e:Event)=>{e.preventDefault();setFailed(true)};renderer.domElement.addEventListener('webglcontextlost',contextLost)
  let focusTarget:THREE.Vector3|null=null
  actions.current={reset,zoom:(delta)=>{camera.zoom=THREE.MathUtils.clamp(camera.zoom+delta,.5,3);camera.updateProjectionMatrix()},focus:()=>{const selected=live.current.selection;const e=live.current.equipment.find(e=>selected?.type==='equipment'&&e.id===selected.id);if(e)focusTarget=new THREE.Vector3(e.x,.8,e.z)}}
  let raf=0, previousSelection='',previousStamp='';const points=new Map<string,{x:number;y:number}>()
  const draw=()=>{
    const p=live.current;const selectionKey=JSON.stringify(p.selection)
    if(previousSelection!==selectionKey){previousSelection=selectionKey;focusTarget=null}
    if(focusTarget){const before=controls.target.clone();controls.target.lerp(focusTarget,p.reduced?1:.10);camera.position.add(controls.target.clone().sub(before));if(controls.target.distanceTo(focusTarget)<.015)focusTarget=null}
    controls.update();points.clear()
    const currentPlan=p.plans.find(q=>q.id===p.planId),planEq=new Set(currentPlan?.reservations.map(r=>r.equipmentId)||[])
    const boxes:{x:number;y:number}[]=[]
    models.sort((a,b)=>Number(p.selection?.id===b.e.id)-Number(p.selection?.id===a.e.id)).forEach(({e,height:mh,outline})=>{
      const selected=p.selection?.type==='equipment'&&p.selection.id===e.id
      const bad=p.checks.some(c=>c.equipmentId===e.id&&c.state==='blocked'),unknown=p.checks.some(c=>c.equipmentId===e.id&&c.state==='unknown')
      outline.visible=selected||Boolean(p.planId&&planEq.has(e.id));(outline.material as THREE.LineBasicMaterial).color.setHex(bad?0xe26476:C.blue)
      const world=new THREE.Vector3(e.x,mh+.35,e.z).project(camera),v={x:(world.x+1)*width/2,y:(-world.y+1)*height/2};points.set(e.id,v)
      const b=pointers.get(e.id)!;const show=selected||((!p.planId||planEq.has(e.id))&&boxes.every(q=>Math.abs(q.x-v.x)>165||Math.abs(q.y-v.y)>61))
      b.hidden=!show||v.x<75||v.x>width-80||v.y<45||v.y>height-50
      if(!b.hidden)boxes.push(v)
      b.style.transform=`translate(${v.x}px,${v.y}px) translate(-50%,-100%)`;b.className=`al-scene-label ${selected?'selected':''} ${bad?'red':unknown?'amber':'blue'}`
      b.querySelector('small')!.textContent=bad?'预约约束冲突':unknown?'有待核验事项':`${p.plans.filter(q=>q.reservations.some(r=>r.equipmentId===e.id)).length} 项关联计划`
    })
    if(lines.current){const center=new THREE.Vector3(0,1.75,1.0).project(camera),cx=(center.x+1)*width/2,cy=(-center.y+1)*height/2
      const selectedEq=p.selection?.type==='equipment'?p.selection.id:null
      const relevant=p.planId?currentPlan:p.plans.find(q=>q.reservations.some(r=>r.equipmentId===selectedEq))
      const dest=[...new Set(relevant?.reservations.map(r=>r.equipmentId)||[])].map(id=>({id,pos:points.get(id)})).filter(x=>x.pos)
      const stamp=JSON.stringify([dest,cx,cy,relevant?.id,p.checks.filter(c=>c.state==='blocked').map(c=>c.equipmentId)])
      if(stamp!==previousStamp){previousStamp=stamp;lines.current.replaceChildren();if(relevant){dest.forEach(({id,pos})=>{const path=document.createElementNS('http://www.w3.org/2000/svg','path');const bad=p.checks.some(c=>c.planId===relevant.id&&c.equipmentId===id&&c.state==='blocked');path.setAttribute('d',`M ${cx} ${cy} Q ${cx} ${pos!.y+20} ${pos!.x} ${pos!.y+12}`);path.setAttribute('class',`al-scene-connection ${bad?'red':''}`);path.setAttribute('aria-label',`${relevant.code} 使用 ${id}`);path.addEventListener('click',()=>live.current.onSelect({type:'equipment',id}));lines.current!.appendChild(path)});const circle=document.createElementNS('http://www.w3.org/2000/svg','circle');circle.setAttribute('cx',String(cx));circle.setAttribute('cy',String(cy));circle.setAttribute('r','6');circle.setAttribute('fill','#3975eb');lines.current.appendChild(circle)}}}
    renderer.render(scene,camera);raf=requestAnimationFrame(draw)
  };draw()
  return()=>{cancelAnimationFrame(raf);ro.disconnect();controls.dispose();renderer.domElement.removeEventListener('pointerdown',pointerDown);renderer.domElement.removeEventListener('pointerup',pointerUp);renderer.domElement.removeEventListener('webglcontextlost',contextLost);scene.traverse(o=>{const m=o as THREE.Mesh;m.geometry?.dispose();const materials=Array.isArray(m.material)?m.material:[m.material];materials.forEach(mat=>{if(mat){Object.values(mat).forEach(v=>{if(v instanceof THREE.Texture)v.dispose()});mat.dispose()}})});renderer.dispose();renderer.domElement.remove();overlay.current?.replaceChildren();lines.current?.replaceChildren();actions.current=null}
 },[layout,props.flat,failed])
 if(props.flat||failed)return <div className="al-flat-stage"><svg viewBox={`0 0 ${props.lab.width*55} ${props.lab.depth*55}`} role="img" aria-label="实验室二维平面"><defs><pattern id="floor-grid" width="55" height="55" patternUnits="userSpaceOnUse"><path d="M55 0H0V55" fill="none" stroke="#dfe7f2"/></pattern></defs><rect x="2" y="2" width={props.lab.width*55-4} height={props.lab.depth*55-4} rx="8" fill="url(#floor-grid)" stroke="#c1d0e3" strokeWidth="4"/>{props.equipment.map(e=><g key={e.id} role="button" tabIndex={0} aria-label={`选择设备 ${e.code}`} onClick={()=>props.onSelect({type:'equipment',id:e.id})} onKeyDown={ev=>{if(ev.key==='Enter')props.onSelect({type:'equipment',id:e.id})}} transform={`translate(${(e.x+props.lab.width/2)*55},${(e.z+props.lab.depth/2)*55})`}><rect x="-48" y="-30" width={e.kind==='bench'?135:95} height="60" rx="6" fill={props.selection?.id===e.id?'#dbe8ff':'white'} stroke={props.checks.some(c=>c.equipmentId===e.id&&c.state==='blocked')?'#e57785':'#b9cce5'} strokeWidth="2"/><text textAnchor="middle" y="-3" fontSize="14" fill="#253c5c">{e.name}</text><text textAnchor="middle" y="18" fontSize="12" fill="#577394">{e.code}</text></g>)}</svg>{failed&&<div className="al-webgl-note"><Icon name="info" size={16}/> 三维渲染不可用，已切换二维；业务操作不受影响。</div>}</div>
 return <div className="al-stage"><div ref={host} className="al-three-host"/><svg ref={lines} className="al-scene-lines"/><div ref={overlay} className="al-scene-labels"/><div className="al-stage-tools"><Button title="放大场景" icon="plus" onClick={()=>actions.current?.zoom(.15)}/><Button title="缩小场景" icon="minus" onClick={()=>actions.current?.zoom(-.15)}/><span/><Button title="聚焦选中设备" icon="target" onClick={()=>actions.current?.focus()}/><Button title="重置视角" icon="reset" onClick={()=>actions.current?.reset()}/></div><div className="al-compass"><span>N</span><i/></div><div className="al-stage-caption"><Icon name="cube" size={15}/> 正交空间 <span>拖动旋转 · 滚轮缩放</span></div></div>
}
