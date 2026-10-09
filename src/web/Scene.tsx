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
function aiCore(){
 const g=new THREE.Group();
 const base=material(0x5e8ee8,{emissive:0x1d4fbe,emissiveIntensity:.48,transparent:true,opacity:.88,roughness:.28,metalness:.18});
 const glow=material(0x8bd9f3,{emissive:0x218bc4,emissiveIntensity:.7,transparent:true,opacity:.52,roughness:.18,metalness:.08});
 const plate=new THREE.Mesh(new THREE.CylinderGeometry(.76,.76,.035,48),base);plate.position.y=.06;plate.castShadow=true;g.add(plate);
 const ring=new THREE.Mesh(new THREE.TorusGeometry(.69,.026,8,64),glow);ring.rotation.x=Math.PI/2;ring.position.y=.095;g.add(ring);
 const ring2=new THREE.Mesh(new THREE.TorusGeometry(.49,.014,8,64),new THREE.MeshBasicMaterial({color:0xb9edff,transparent:true,opacity:.8}));ring2.rotation.x=Math.PI/2;ring2.position.y=.11;g.add(ring2);
 const core=new THREE.Mesh(new THREE.OctahedronGeometry(.27,1),new THREE.MeshStandardMaterial({color:0xe9fbff,emissive:0x56c7ee,emissiveIntensity:.75,roughness:.14,metalness:.08,transparent:true,opacity:.94}));core.position.y=.39;core.rotation.y=Math.PI/4;core.castShadow=true;g.add(core);
 const beacon=new THREE.Mesh(new THREE.CylinderGeometry(.02,.06,.56,12),new THREE.MeshBasicMaterial({color:0x90e8ff,transparent:true,opacity:.68}));beacon.position.y=.52;g.add(beacon);
 g.traverse(o=>{o.userData.aiCore=true});
 return g;
}
function label(g:THREE.Group,text:string,x:number,y:number,z:number,width=1.0){const canvas=document.createElement('canvas');canvas.width=256;canvas.height=80;const ctx=canvas.getContext('2d');if(!ctx)return;ctx.fillStyle='#346bea';ctx.fillRect(0,0,256,80);ctx.fillStyle='white';ctx.font='600 40px Arial';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(text,128,42);const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;const mesh=new THREE.Mesh(new THREE.PlaneGeometry(width,width*80/256),new THREE.MeshBasicMaterial({map:texture}));mesh.position.set(x,y,z);g.add(mesh)}
type ZoneSpec={id:string;name:string;x:number;z:number;width:number;depth:number;color:number}
function zonesFor(lab:Laboratory):ZoneSpec[]{const w=lab.width,d=lab.depth;return [
 {id:'prep',name:'前处理区',x:-w*.27,z:-d*.22,width:w*.42,depth:d*.38,color:0x8eb7ef},
 {id:'analysis',name:'分析检测区',x:w*.22,z:-d*.22,width:w*.42,depth:d*.38,color:0x9bc8d7},
 {id:'wash',name:'清洗与废物',x:-w*.26,z:d*.27,width:w*.44,depth:d*.25,color:0xb4c8e7},
 {id:'storage',name:'化学品暂存',x:w*.26,z:d*.27,width:w*.38,depth:d*.25,color:0xe6c98d},
]}
function zoneFloor(g:THREE.Group,z:ZoneSpec){const plate=box(g,z.x,.045,z.z,z.width,.035,z.depth,z.color,.08);const mat=plate.material as THREE.MeshStandardMaterial;mat.transparent=true;mat.opacity=.16;mat.depthWrite=false;const edge=material(z.color,{transparent:true,opacity:.48,roughness:.8});for(const x of [z.x-z.width/2,z.x+z.width/2]){const bar=new THREE.Mesh(new THREE.BoxGeometry(.025,.018,z.depth),edge);bar.position.set(x,.07,z.z);g.add(bar)}for(const zz of [z.z-z.depth/2,z.z+z.depth/2]){const bar=new THREE.Mesh(new THREE.BoxGeometry(z.width,.018,.025),edge);bar.position.set(z.x,.07,zz);g.add(bar)}const canvas=document.createElement('canvas');canvas.width=320;canvas.height=64;const ctx=canvas.getContext('2d');if(!ctx)return;ctx.fillStyle='#ffffffc8';if(typeof ctx.roundRect==='function')ctx.roundRect(2,2,316,60,12);else ctx.fillRect(2,2,316,60);ctx.fill();ctx.fillStyle='#58769c';ctx.font='600 28px Arial';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(z.name,160,33);const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;const sign=new THREE.Mesh(new THREE.PlaneGeometry(Math.min(2.4,z.width*.65),.42),new THREE.MeshBasicMaterial({map:texture,transparent:true,depthWrite:false}));sign.rotation.x=-Math.PI/2;sign.position.set(z.x,.09,z.z);g.add(sign)}
function cabinetBase(g:THREE.Group,w:number,d:number) {box(g,0,.47,0,w,.9,d,C.body);box(g,0,.08,0,w-.12,.12,d-.04,C.ink);for(const side of [-1,1]){box(g,side*w/4,.5,d/2+.018,w/2-.045,.74,.035,C.white);box(g,side*.11,.67,d/2+.055,.035,.23,.035,C.metal)}}
function model(e:Equipment){const g=new THREE.Group();let h=1.4,w=2,d=1.3
 // Instrument families use distinct silhouettes so the spatial scene reads like a
 // real shared research facility rather than a wall of interchangeable cabinets.
 if(['nmr','epr'].includes(e.kind)) {
   w=2.45;d=1.75;h=3.25; cabinetBase(g,w,d); box(g,0,1.06,0,w+.1,.13,d+.1,C.worktop)
   cylinder(g,0,2.02,-.08,.62,1.92,0xd9e6f1,.70); cylinder(g,0,2.95,-.08,.76,.22,0xb8cde0,.78)
   box(g,0,1.18,.55,.72,.08,.20,C.blue); box(g,0,1.44,.55,.06,.38,.06,C.ink)
   box(g,.83,1.64,.18,.56,.85,.76,C.white); box(g,.83,1.82,.58,.40,.28,.03,0x7fa7c8); cylinder(g,.83,2.17,.58,.06,.05,C.blue)
   label(g,e.code,0,.61,d/2+.05,.68)
 } else if(['ftir','raman','uv_vis','xrd','xps','dls','spr'].includes(e.kind)) {
   w=2.35;d=1.40;h=1.95;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.11,d+.08,C.worktop)
   box(g,-.38,1.48,.02,1.02,.84,.90,0xf7fbff);box(g,-.38,1.67,.47,.70,.34,.025,0x78a8c8)
   box(g,-.38,1.30,.49,.48,.08,.04,C.metal);cylinder(g,-.42,1.70,.51,.11,.055,C.blue)
   box(g,.62,1.34,-.04,.62,.62,.65,0xd3e2ec);box(g,.62,1.62,.31,.47,.28,.03,C.ink);cylinder(g,.62,1.17,.33,.09,.07,C.glass)
   label(g,e.code,0,.61,d/2+.05,.66)
 } else if(['sem','tem','afm'].includes(e.kind)) {
   w=2.15;d=1.55;h=3.0;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.11,d+.08,C.worktop)
   box(g,0,2.05,-.04,.72,1.92,.76,0xe1ebf3);cylinder(g,0,2.98,-.04,.37,.26,0xb7ccdc,.40);cylinder(g,0,2.46,.38,.09,.45,C.metal)
   box(g,-.68,1.43,.34,.48,.68,.36,C.ink);box(g,-.68,1.62,.54,.29,.24,.02,0x6f9bc0)
   label(g,e.code,0,.61,d/2+.05,.66)
 } else if(['icp_ms','icp_oes','aas','xrf','mass_spec','elemental_analyzer'].includes(e.kind)) {
   w=2.65;d=1.45;h=2.15;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.11,d+.08,C.worktop)
   box(g,-.48,1.51,.02,1.28,.92,.88,0xeaf2f7);box(g,-.48,1.70,.47,.82,.32,.03,0x456d9a)
   for(const x of [-.94,-.57,-.2]) {cylinder(g,x,1.18,.51,.06,.30,C.glass);cylinder(g,x,1.37,.51,.035,.11,C.ink)}
   box(g,.78,1.35,-.02,.62,.66,.65,0xd3e0e9);box(g,.78,1.66,.31,.44,.25,.03,C.ink);cylinder(g,.78,1.12,.36,.11,.10,C.metal)
   label(g,e.code,0,.61,d/2+.05,.66)
 } else if(['reactor','microwave_reactor','photoreactor','electrochemistry'].includes(e.kind)) {
   w=2.55;d=1.45;h=2.35;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.11,d+.08,C.worktop)
   cylinder(g,-.48,1.76,.05,.38,1.12,0xd7e6ee,.43);cylinder(g,-.48,2.38,.05,.12,.16,C.metal);tube(g,[[-.48,2.44,.05],[-.48,2.72,.05],[.05,2.72,.05]],.035,C.metal)
   box(g,.62,1.58,.08,.78,.98,.72,0xe7f0f5);box(g,.62,1.78,.45,.52,.30,.03,0x6e9cca);cylinder(g,.62,1.18,.46,.12,.08,C.blue)
   label(g,e.code,0,.61,d/2+.05,.66)
 } else if(['gas_manifold','gas_cabinet','exhaust_treatment','vacuum_pump'].includes(e.kind)) {
   w=2.20;d=1.12;h=2.65;box(g,0,1.30,0,w,2.6,d,C.body);box(g,0,.10,0,w-.1,.16,d,C.ink)
   box(g,0,2.25,.55,w-.26,.06,.05,C.metal);for(const x of [-.72,-.24,.24,.72]){cylinder(g,x,1.45,.52,.13,.70,0xcad8e4);cylinder(g,x,1.88,.52,.045,.05,C.blue);tube(g,[[x,2.3,.52],[x,2.58,.52],[x+.25,2.58,.52]],.022,C.ink)}
   label(g,e.code,0,2.42,.60,.66)
 } else if(['liquid_nitrogen','cold_trap','lyophilizer','spray_dryer','co2_incubator'].includes(e.kind)) {
   w=1.95;d=1.20;h=2.25;box(g,0,1.12,0,w,2.2,d,0xe3edf4);box(g,0,.10,0,w-.1,.16,d,C.ink)
   const glass=box(g,0,1.38,.62,w-.28,1.30,.04,0xb9d9e7);(glass.material as THREE.MeshStandardMaterial).transparent=true;(glass.material as THREE.MeshStandardMaterial).opacity=.38
   for(const y of [.95,1.38,1.81])box(g,0,y,.60,w-.38,.024,.04,C.white);box(g,.54,2.05,.63,.20,.10,.03,C.blue);cylinder(g,-.52,.70,.63,.25,.18,C.metal)
   label(g,e.code,0,2.20,.67,.64)
 } else if(['glovebox','cleanroom','clean_bench','biosafety_cabinet'].includes(e.kind)) {
   w=2.95;d=1.48;h=2.55;cabinetBase(g,w,d);box(g,0,1.03,0,w+.10,.13,d+.08,C.worktop);box(g,0,2.05,-.10,w,1.78,.12,C.body)
   const glass=box(g,0,1.90,.56,w-.32,1.14,.035,C.glass);(glass.material as THREE.MeshStandardMaterial).transparent=true;(glass.material as THREE.MeshStandardMaterial).opacity=.28
   for(const x of [-.72,0,.72]){cylinder(g,x,1.88,.62,.18,.08,C.metal);cylinder(g,x,1.88,.64,.08,.10,C.ink)}
   box(g,0,2.73,0,w,.24,d,C.white);label(g,e.code,0,.64,d/2+.05,.7)
 }
 if(e.kind==='hood' || e.kind==='gas_cabinet') {w=2.5;d=1.35;h=2.85;cabinetBase(g,w,d);box(g,0,1.01,0,w+.10,.12,d+.1,C.ink);box(g,0,1.87,-.60,w,1.65,.10,C.body);for(const s of [-1,1])box(g,s*1.18,1.89,0,.14,1.7,d,C.white);box(g,0,2.7,0,w,.3,d,C.white);box(g,0,2.54,.66,w-.32,.035,.045,C.metal);const glass=box(g,0,2.1,.58,w-.35,.8,.035,C.glass);(glass.material as THREE.MeshStandardMaterial).transparent=true;(glass.material as THREE.MeshStandardMaterial).opacity=.28;box(g,0,1.69,.61,w-.32,.04,.07,C.metal);box(g,0,2.53,-.3,1.7,.035,.16,0xe3f6ff);cylinder(g,0,2.99,-.28,.25,.35,C.metal);label(g,e.code,0,2.72,.687,.67);box(g,1.18,1.46,.72,.12,.32,.03,C.ink);box(g,1.18,1.54,.74,.07,.06,.01,0x89d3be);bottle(g,-.72,1.10,-.27,.95);bottle(g,-.48,1.10,-.28,.8,0xc3ceea);flask(g,.37,1.10,-.13,1.25);box(g,-.1,1.08,.06,.55,.04,.5,C.metal)}
 else if(['bench','clean_bench','biosafety_cabinet'].includes(e.kind)) {w=3.5;d=1.48;h=2.1;cabinetBase(g,w,d);box(g,0,1.0,0,w+.1,.13,d+.08,C.worktop);for(const x of [-1.42,1.42])box(g,x,1.46,0,.065,.88,.07,C.metal);box(g,0,1.73,0,3.1,.055,.42,C.metal);box(g,0,1.36,0,3.1,.055,.42,C.white);for(let i=0;i<7;i++)bottle(g,-1.25+i*.39,1.765,0,.7,i%3===0?0xc5a876:0xbddbd4);box(g,-1.2,1.17,.43,.38,.2,.34,C.body);flask(g,.45,1.085,.44,.9);flask(g,.85,1.085,.38,.8);box(g,-.25,1.09,.42,.5,.025,.35,C.blue);for(const x of [-1.05,1.05]){cylinder(g,x,.63,1.12,.26,.10,C.ink);cylinder(g,x,.36,1.12,.035,.5,C.metal);for(const off of [-.22,.22])box(g,x+off,.12,1.12,.5,.035,.04,C.metal)}label(g,e.code,0,.60,d/2+.05,.65)}
 else if(['storage','flammable_cabinet','acid_base_cabinet','refrigerator','freezer','drying_oven','furnace'].includes(e.kind)) {w=1.8;d=1.05;h=2.5;box(g,0,1.25,0,w,2.5,d,C.body);box(g,0,.09,0,w-.1,.15,d,C.ink);for(const s of [-1,1]){box(g,s*.44,1.3,.54,.84,2.25,.05,C.white);const glass=box(g,s*.44,1.65,.58,.64,1.19,.03,C.glass);(glass.material as THREE.MeshStandardMaterial).roughness=.2;box(g,s*.1,1.13,.61,.035,.27,.045,C.metal);for(let i=0;i<3;i++)box(g,s*.44,.66+i*.44,.6,.60,.024,.03,C.metal)}label(g,e.code,0,2.33,.59,.62)}
 else if(['nmr','epr','xrd','xps','sem','tem','afm','ftir','raman','spr','dls','bet'].includes(e.kind)){w=2.45;d=1.48;h=2.35;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.1,d+.08,C.worktop);
   const accent=['nmr','epr'].includes(e.kind)?0x7e8ee8:['xrd','xps','sem','tem'].includes(e.kind)?0x9c7bd8:0x62b9bc;
   box(g,-.43,1.52,-.05,.98,1.02,.92,C.white);box(g,-.43,1.63,.435,.77,.34,.02,C.ink);box(g,-.43,1.64,.452,.59,.18,.015,accent);
   box(g,-.43,1.22,.47,.67,.08,.04,C.metal);cylinder(g,-.12,1.4,.53,.045,.035,accent);
   if(['nmr','epr'].includes(e.kind)){cylinder(g,.62,1.52,.02,.34,1.12,C.white);cylinder(g,.62,2.12,.02,.22,.12,accent);box(g,.62,1.57,.35,.56,.05,.06,C.metal)}
   else if(['xrd','xps','sem','tem'].includes(e.kind)){box(g,.62,1.55,.02,.68,.8,.66,C.body);box(g,.62,1.74,.36,.42,.18,.025,accent);cylinder(g,.62,1.23,.39,.16,.08,C.metal);box(g,.62,1.28,.39,.06,.28,.06,accent)}
   else {box(g,.62,1.38,.02,.72,.63,.78,C.body);box(g,.62,1.61,.43,.54,.18,.025,accent);for(const x of [-.24,.24])cylinder(g,.62+x,1.2,.46,.06,.12,C.metal)}
   label(g,e.code,0,.60,.79,.66)}
 else if(['reactor','microwave_reactor','photoreactor','electrochemistry','tga','dsc'].includes(e.kind)){w=2.25;d=1.34;h=2.5;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.1,d+.08,C.worktop);
   const accent=['photoreactor','electrochemistry'].includes(e.kind)?0x6fb9d9:0xd4a15b;
   box(g,-.50,1.35,.02,.8,.72,.78,C.body);box(g,-.50,1.55,.43,.58,.22,.025,accent);box(g,-.50,1.21,.43,.58,.06,.04,C.metal);
   if(e.kind==='reactor'){cylinder(g,.52,1.62,.04,.30,1.05,C.metal);cylinder(g,.52,2.20,.04,.20,.12,accent);tube(g,[[.52,2.27,.04],[.52,2.56,.04],[.88,2.56,.04]],.035,C.metal)}
   else if(e.kind==='photoreactor'){cylinder(g,.52,1.7,.04,.28,.92,0xb8e2eb);cylinder(g,.52,2.18,.04,.18,.1,accent);box(g,.52,1.68,.34,.08,.74,.06,accent)}
   else if(e.kind==='electrochemistry'){box(g,.52,1.62,.04,.66,.22,.56,C.white);for(const x of [.31,.52,.73])cylinder(g,x,1.84,.04,.035,.34,accent);box(g,.52,2.08,.04,.72,.07,.08,C.ink)}
   else {cylinder(g,.52,1.65,.04,.31,.74,C.white);cylinder(g,.52,2.08,.04,.21,.10,accent);box(g,.52,1.38,.32,.38,.06,.04,C.metal)}
   label(g,e.code,0,.60,.72,.66)}
 else if(['gas_manifold','exhaust_treatment','liquid_nitrogen','cold_trap'].includes(e.kind)){w=1.9;d=1.18;h=2.55;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.1,d+.08,C.worktop);const accent=e.kind==='liquid_nitrogen'?0x91b9e5:0x82b49e;
   if(e.kind==='gas_manifold'){for(const x of [-.54,-.18,.18,.54]){cylinder(g,x,1.66,.04,.14,1.1,C.metal);cylinder(g,x,2.28,.04,.09,.10,accent)}for(const x of [-.54,-.18,.18,.54])tube(g,[[x,2.34,.04],[x,2.58,.04],[0,2.58,.04]],.025,accent)}
   else if(e.kind==='liquid_nitrogen'){cylinder(g,0,1.68,.04,.4,1.48,C.white);cylinder(g,0,2.45,.04,.27,.12,accent);box(g,0,1.68,.40,.18,.93,.08,C.metal)}
   else {cylinder(g,0,1.5,.04,.34,.92,C.metal);cylinder(g,0,2.02,.04,.22,.12,accent);tube(g,[[0,2.09,.04],[.5,2.09,.04],[.5,2.45,.04]],.035,C.metal);box(g,.5,2.40,.04,.30,.12,.28,C.body)}
   label(g,e.code,0,.60,.63,.66)}
 else if(['analyzer','gc','hplc','uv_vis','mass_spec','elemental_analyzer','chromatography','ion_chromatography','centrifuge','pcr','balance','evaporator','vacuum_pump','nitrogen_blowdown'].includes(e.kind)){w=2.35;d=1.35;h=2.0;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.1,d+.08,C.worktop);box(g,-.42,1.43,-.02,.89,.79,.9,C.white);box(g,-.42,1.59,.455,.70,.28,.02,C.ink);box(g,-.42,1.60,.472,.55,.14,.015,0x91bfdc);box(g,-.43,1.25,.46,.60,.07,.03,C.metal);cylinder(g,-.18,1.38,.51,.035,.025,C.blue);box(g,.7,1.08,0,.60,.06,.54,C.metal);box(g,.7,1.36,-.2,.06,.56,.08,C.ink);box(g,.7,1.64,-.16,.68,.42,.06,C.ink);box(g,.7,1.64,-.12,.59,.34,.012,0xb2d3e7);label(g,e.code,0,.60,.725,.66)}
 else if(['sink','water_purification','eyewash','safety_shower','gas_detector','environment_monitor','access_control'].includes(e.kind)){w=2.25;d=1.26;h=1.7;cabinetBase(g,w,d);box(g,0,1.0,0,w+.08,.1,d+.05,C.worktop);box(g,-.18,1.06,.02,1.20,.025,.78,C.metal);box(g,-.18,1.077,.02,1.02,.012,.63,0x71899e);tube(g,[[.03,1.05,-.45],[.03,1.61,-.45],[.03,1.65,-.1],[.03,1.44,-.1]],.036,C.metal);bottle(g,.86,1.06,-.3,1.2);label(g,e.code,0,.6,.68,.65)}
 else {w=1.7;d=1.1;h=1.7;box(g,0,.8,0,w,1.6,d,0xefd7a5);for(const s of [-1,1]){box(g,s*.4,.82,.57,.73,1.35,.045,0xf9e3b4);box(g,s*.1,.95,.61,.03,.25,.03,C.ink)}box(g,0,1.65,0,w+.06,.07,d+.05,C.ink);label(g,e.code,0,1.37,.603,.65);box(g,0,.38,.61,.60,.15,.01,0xc89b44)}
 g.position.set(e.x,0,e.z);g.rotation.y=e.rotation*Math.PI/180;g.traverse(o=>o.userData.equipmentId=e.id)
 return {group:g,height:h,width:w,depth:d}
}
function room(lab:Laboratory) {const g=new THREE.Group(),w=lab.width,d=lab.depth
 box(g,0,-.16,0,w,.28,d,0xe1e9f2,.1);box(g,0,-.005,0,w-.08,.03,d-.08,0xf1f5f9,.01)
 zonesFor(lab).forEach(z=>zoneFloor(g,z))
 const lines=new THREE.Group();for(let i=-Math.floor(w/2);i<=w/2;i++)box(lines,i,.015,0,.009,.006,d-.15,0xdce4ed,0);for(let i=-Math.floor(d/2);i<=d/2;i++)box(lines,0,.015,i,w-.15,.006,.009,0xdce4ed,0);g.add(lines)
 box(g,0,1.65,-d/2,w,3.3,.16,0xe7edf3);box(g,w/2,1.65,0,.16,3.3,d,0xe7edf3)
 box(g,0,.22,-d/2+.09,w,.35,.04,0xcfddeb);box(g,w/2-.09,.22,0,.04,.35,d,0xcfddeb)
 for(let x=-w/2+2;x<w/2-1;x+=3){box(g,x,2.80,-d/2+.09,2.40,.38,.035,0xc1ddee);for(const a of [-1,1])box(g,x+a*1.21,2.8,-d/2+.12,.06,.46,.045,C.white);box(g,x,2.8,-d/2+.12,.045,.4,.045,C.white)}
 for(let z=-d/2+2;z<d/2-1;z+=3){box(g,w/2-.10,2.15,z,.04,1.45,2.15,0xc2dcea);for(const a of [-1,0,1])box(g,w/2-.14,2.15,z+a*1.04,.04,1.55,.05,C.white);box(g,w/2-.13,2.93,z,.05,.05,2.2,C.white);box(g,w/2-.13,1.4,z,.14,.08,2.3,C.white)}
 box(g,0,3.08,-d/2+.15,w-.5,.12,.13,C.white);box(g,w/2-.15,3.08,0,.13,.12,d-.5,C.white)
 // Diffuse ceiling light bays give the room the clean, softly lit look of a
 // modern university core facility while keeping the orthographic view open.
 for(let x=-w/2+1.7;x<w/2-1;x+=3.1){
  const panel=box(g,x,3.04,-d*.14,1.55,.025,.34,0xf5fbff,.02)
  const panelMat=panel.material as THREE.MeshStandardMaterial;panelMat.emissive.setHex(0xc4e8ff);panelMat.emissiveIntensity=.35
 }
 for(let z=-d/2+2.2;z<d/2-1;z+=3.1){
  const panel=box(g,w*.22,3.04,z,.34,.025,1.55,0xf5fbff,.02)
  const panelMat=panel.material as THREE.MeshStandardMaterial;panelMat.emissive.setHex(0xc4e8ff);panelMat.emissiveIntensity=.3
 }
 // A subtle central marker is the visual anchor for the AI safety twin. The
 // projected overlay added below carries the readable label and live state.
 const core=aiCore();core.position.set(0,.02,1.0);g.add(core)
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
  const reset=()=>{const w=props.lab.width,d=props.lab.depth;camera.position.set(w*1.08,Math.max(10,d*1.06),d*1.32);camera.zoom=1.08;controls.target.set(0,.55,0);camera.updateProjectionMatrix();controls.update()};reset()
  const models=props.equipment.map(e=>{const m=model(e);scene.add(m.group);const outline=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(m.width+.12,m.height+.1,m.depth+.12)),new THREE.LineBasicMaterial({color:C.blue,transparent:true,opacity:.8}));outline.position.set(e.x,m.height/2,e.z);outline.rotation.y=e.rotation*Math.PI/180;scene.add(outline);return {...m,e,outline}})
  const pointers=new Map<string,HTMLButtonElement>(),zonePointers=new Map<string,HTMLDivElement>()
  let aiPointer:HTMLDivElement|null=null
  if(overlay.current){overlay.current.replaceChildren();
   const ai=document.createElement('div');ai.className='al-scene-ai-core';ai.innerHTML='<span class="al-scene-ai-orb">AI</span><div><b>安全孪生引擎</b><small>理解 · 推演 · 放行</small></div>';overlay.current.appendChild(ai);aiPointer=ai
   models.forEach(({e})=>{const b=document.createElement('button');b.type='button';b.className='al-scene-label';b.setAttribute('aria-label',`选择设备 ${e.code}`);b.innerHTML='<span class="dot"></span><div><b></b><small></small></div>';b.querySelector('b')!.textContent=`${e.name} ${e.code}`;b.addEventListener('click',()=>live.current.onSelect({type:'equipment',id:e.id}));overlay.current!.appendChild(b);pointers.set(e.id,b)});zonesFor(props.lab).forEach(z=>{const node=document.createElement('div');node.className='al-zone-label';node.textContent=z.name;node.dataset.zone=z.id;overlay.current!.appendChild(node);zonePointers.set(z.id,node)})}
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
    if(previousSelection!==selectionKey){previousSelection=selectionKey;const selected=live.current.selection;const selectedEquipment=live.current.equipment.find(e=>selected?.type==='equipment'&&e.id===selected.id);if(selectedEquipment)focusTarget=new THREE.Vector3(selectedEquipment.x,.8,selectedEquipment.z);else if(selected?.type==='plan'){const plan=live.current.plans.find(p=>p.id===selected.id),items=live.current.equipment.filter(e=>plan?.reservations.some(r=>r.equipmentId===e.id));if(items.length)focusTarget=new THREE.Vector3(items.reduce((sum,e)=>sum+e.x,0)/items.length,.7,items.reduce((sum,e)=>sum+e.z,0)/items.length)}else focusTarget=null}
    if(focusTarget){const before=controls.target.clone();controls.target.lerp(focusTarget,p.reduced?1:.10);camera.position.add(controls.target.clone().sub(before));if(controls.target.distanceTo(focusTarget)<.015)focusTarget=null}
    controls.update();points.clear()
    const currentPlan=p.plans.find(q=>q.id===p.planId),planEq=new Set(currentPlan?.reservations.map(r=>r.equipmentId)||[])
    // Reserve the AI anchor's label footprint before placing equipment labels.
    // This prevents a selected instrument card from sitting directly on top of
    // the semantic center when the camera is zoomed or the viewport is narrow.
    const aiScreen=new THREE.Vector3(0,1.05,1.0).project(camera)
    const aiPosition={x:(aiScreen.x+1)*width/2,y:(-aiScreen.y+1)*height/2}
    const boxes:{x:number;y:number}[]=[]
    if(aiPosition.x>=70&&aiPosition.x<=width-70&&aiPosition.y>=34&&aiPosition.y<=height-45)boxes.push(aiPosition)
    models.sort((a,b)=>Number(p.selection?.id===b.e.id)-Number(p.selection?.id===a.e.id)).forEach(({e,height:mh,outline})=>{
      const selected=p.selection?.type==='equipment'&&p.selection.id===e.id
      const bad=p.checks.some(c=>c.equipmentId===e.id&&c.state==='blocked'),unknown=p.checks.some(c=>c.equipmentId===e.id&&c.state==='unknown')
      outline.visible=selected||Boolean(p.planId&&planEq.has(e.id));(outline.material as THREE.LineBasicMaterial).color.setHex(bad?0xe26476:C.blue)
      const world=new THREE.Vector3(e.x,mh+.35,e.z).project(camera),v={x:(world.x+1)*width/2,y:(-world.y+1)*height/2};points.set(e.id,v)
      const b=pointers.get(e.id)!;const show=selected||((!p.planId||planEq.has(e.id))&&boxes.every(q=>Math.abs(q.x-v.x)>165||Math.abs(q.y-v.y)>61))
      b.hidden=!show||v.x<75||v.x>width-80||v.y<45||v.y>height-50
      if(!b.hidden)boxes.push(v)
      const nearAI=Math.abs(v.x-aiPosition.x)<150&&Math.abs(v.y-aiPosition.y)<88
      const labelOffset=selected&&nearAI?(v.x<width/2?96:-96):0
      const labelX=Math.max(86,Math.min(width-86,v.x+labelOffset)),labelY=Math.max(42,v.y-(selected&&nearAI?20:0))
      b.style.transform=`translate(${labelX}px,${labelY}px) translate(-50%,-100%)`;b.className=`al-scene-label ${selected?'selected':''} ${bad?'red':unknown?'amber':'blue'}`
      b.querySelector('small')!.textContent=bad?'预约约束冲突':unknown?'有待核验事项':`${p.plans.filter(q=>q.reservations.some(r=>r.equipmentId===e.id)).length} 项关联计划`
    })
    zonesFor(p.lab).forEach(z=>{const node=zonePointers.get(z.id);if(!node)return;const world=new THREE.Vector3(z.x,.12,z.z).project(camera),v={x:(world.x+1)*width/2,y:(-world.y+1)*height/2};node.style.transform=`translate(${v.x}px,${v.y}px) translate(-50%,-50%)`;node.hidden=v.x<20||v.x>width-20||v.y<20||v.y>height-20})
    if(lines.current){const center=new THREE.Vector3(0,1.05,1.0).project(camera),cx=(center.x+1)*width/2,cy=(-center.y+1)*height/2
      if(aiPointer){aiPointer.style.transform=`translate(${cx}px,${cy}px) translate(-50%,-50%)`;aiPointer.hidden=cx<70||cx>width-70||cy<34||cy>height-45}
      const selectedEq=p.selection?.type==='equipment'?p.selection.id:null
      const relevant=p.planId?currentPlan:p.plans.find(q=>q.reservations.some(r=>r.equipmentId===selectedEq))
      const dest=[...new Set(relevant?.reservations.map(r=>r.equipmentId)||[])].map(id=>({id,pos:points.get(id)})).filter(x=>x.pos)
      const stamp=JSON.stringify([dest,cx,cy,relevant?.id,p.checks.filter(c=>c.state==='blocked').map(c=>c.equipmentId)])
      if(stamp!==previousStamp){previousStamp=stamp;lines.current.replaceChildren();
       const defs=document.createElementNS('http://www.w3.org/2000/svg','defs');const marker=document.createElementNS('http://www.w3.org/2000/svg','marker');marker.setAttribute('id','al-arrow');marker.setAttribute('viewBox','0 0 10 10');marker.setAttribute('refX','8');marker.setAttribute('refY','5');marker.setAttribute('markerWidth','4');marker.setAttribute('markerHeight','4');marker.setAttribute('orient','auto-start-reverse');const arrow=document.createElementNS('http://www.w3.org/2000/svg','path');arrow.setAttribute('d','M 0 0 L 10 5 L 0 10 z');arrow.setAttribute('fill','#6898e7');marker.appendChild(arrow);defs.appendChild(marker);lines.current.appendChild(defs)
       if(relevant){dest.forEach(({id,pos})=>{const path=document.createElementNS('http://www.w3.org/2000/svg','path');const bad=p.checks.some(c=>c.planId===relevant.id&&c.equipmentId===id&&c.state==='blocked');path.setAttribute('d',`M ${cx} ${cy} Q ${cx} ${pos!.y+20} ${pos!.x} ${pos!.y+12}`);path.setAttribute('class',`al-scene-connection ${bad?'red':''}`);path.setAttribute('marker-end','url(#al-arrow)');path.setAttribute('aria-label',`${relevant.code} 使用 ${id}`);path.addEventListener('click',()=>live.current.onSelect({type:'equipment',id}));lines.current!.appendChild(path);const node=document.createElementNS('http://www.w3.org/2000/svg','circle');node.setAttribute('cx',String(pos!.x));node.setAttribute('cy',String(pos!.y+12));node.setAttribute('r',bad?'5':'4');node.setAttribute('class',`al-scene-connection-node ${bad?'red':''}`);lines.current!.appendChild(node)});const halo=document.createElementNS('http://www.w3.org/2000/svg','circle');halo.setAttribute('cx',String(cx));halo.setAttribute('cy',String(cy));halo.setAttribute('r','18');halo.setAttribute('class','al-scene-ai-halo');lines.current.appendChild(halo);const circle=document.createElementNS('http://www.w3.org/2000/svg','circle');circle.setAttribute('cx',String(cx));circle.setAttribute('cy',String(cy));circle.setAttribute('r','6');circle.setAttribute('class','al-scene-ai-node');lines.current.appendChild(circle)}}}
    renderer.render(scene,camera);raf=requestAnimationFrame(draw)
  };draw()
  return()=>{cancelAnimationFrame(raf);ro.disconnect();controls.dispose();renderer.domElement.removeEventListener('pointerdown',pointerDown);renderer.domElement.removeEventListener('pointerup',pointerUp);renderer.domElement.removeEventListener('webglcontextlost',contextLost);scene.traverse(o=>{const m=o as THREE.Mesh;m.geometry?.dispose();const materials=Array.isArray(m.material)?m.material:[m.material];materials.forEach(mat=>{if(mat){Object.values(mat).forEach(v=>{if(v instanceof THREE.Texture)v.dispose()});mat.dispose()}})});renderer.dispose();renderer.domElement.remove();overlay.current?.replaceChildren();lines.current?.replaceChildren();actions.current=null}
 },[layout,props.flat,failed])
 if(props.flat||failed)return <div className="al-flat-stage"><svg viewBox={`0 0 ${props.lab.width*55} ${props.lab.depth*55}`} role="img" aria-label="实验室二维平面"><defs><pattern id="floor-grid" width="55" height="55" patternUnits="userSpaceOnUse"><path d="M55 0H0V55" fill="none" stroke="#dfe7f2"/></pattern></defs><rect x="2" y="2" width={props.lab.width*55-4} height={props.lab.depth*55-4} rx="8" fill="url(#floor-grid)" stroke="#c1d0e3" strokeWidth="4"/>{props.equipment.map(e=><g key={e.id} role="button" tabIndex={0} aria-label={`选择设备 ${e.code}`} onClick={()=>props.onSelect({type:'equipment',id:e.id})} onKeyDown={ev=>{if(ev.key==='Enter')props.onSelect({type:'equipment',id:e.id})}} transform={`translate(${(e.x+props.lab.width/2)*55},${(e.z+props.lab.depth/2)*55})`}><rect x="-48" y="-30" width={e.kind==='bench'?135:95} height="60" rx="6" fill={props.selection?.id===e.id?'#dbe8ff':'white'} stroke={props.checks.some(c=>c.equipmentId===e.id&&c.state==='blocked')?'#e57785':'#b9cce5'} strokeWidth="2"/><text textAnchor="middle" y="-3" fontSize="14" fill="#253c5c">{e.name}</text><text textAnchor="middle" y="18" fontSize="12" fill="#577394">{e.code}</text></g>)}</svg>{failed&&<div className="al-webgl-note"><Icon name="info" size={16}/> 三维渲染不可用，已切换二维；业务操作不受影响。</div>}</div>
 return <div className="al-stage"><div ref={host} className="al-three-host"/><svg ref={lines} className="al-scene-lines"/><div ref={overlay} className="al-scene-labels"/><div className="al-stage-tools"><Button title="放大场景" icon="plus" onClick={()=>actions.current?.zoom(.15)}/><Button title="缩小场景" icon="minus" onClick={()=>actions.current?.zoom(-.15)}/><span/><Button title="聚焦选中设备" icon="target" onClick={()=>actions.current?.focus()}/><Button title="重置视角" icon="reset" onClick={()=>actions.current?.reset()}/></div><div className="al-compass"><span>N</span><i/></div><div className="al-stage-caption"><Icon name="cube" size={15}/> 正交空间 <span>拖动旋转 · 滚轮缩放</span></div></div>
}
