import {useEffect,useRef,useState} from 'react';
import cytoscape from 'cytoscape';

type Tip={title:string;subtitle:string;detail:string;x:number;y:number};
const colors:Record<string,string>={Function:'#60a5fa',Class:'#c084fc',Interface:'#a78bfa',Struct:'#a78bfa',File:'#34d399',Directory:'#2dd4bf',Module:'#fbbf24',Parameter:'#64748b',Variable:'#94a3b8'};

export function Graph({data,onSelect}:{data:any,onSelect:(node:any)=>void}){
 const container=useRef<HTMLDivElement>(null),frame=useRef<HTMLDivElement>(null),instance=useRef<cytoscape.Core|null>(null);
 const selectCallback=useRef(onSelect);selectCallback.current=onSelect;
 const [tip,setTip]=useState<Tip|null>(null),[layout,setLayout]=useState('auto'),[names,setNames]=useState(false),[focus,setFocus]=useState(''),[expanded,setExpanded]=useState(false);
 const applyLayout=useRef<()=>void>(()=>{});
 const showTip=useRef<(node:cytoscape.NodeSingular)=>void>(()=>{});

 useEffect(()=>{
  if(!container.current)return;
  setTip(null);setFocus('');
  const nodes=data?.nodes||[],edges=data?.edges||[];
  // Distances are used only for radial placement; arrow semantics remain unchanged.
  const adjacency=new Map<string,string[]>();nodes.forEach((n:any)=>adjacency.set(n.id,[]));
  edges.forEach((e:any)=>{adjacency.get(e.source)?.push(e.target);adjacency.get(e.target)?.push(e.source);});
  const distance=new Map<string,number>();
  if(data?.root){distance.set(data.root,0);const queue=[data.root];for(let i=0;i<queue.length;i++)for(const next of adjacency.get(queue[i])||[])if(!distance.has(next)){distance.set(next,distance.get(queue[i])!+1);queue.push(next);}}
  const order=new Map([...distance.keys()].map((id,i)=>[id,i]));
  const orderedNodes=[...nodes].sort((a:any,b:any)=>(order.get(a.id)??nodes.length)-(order.get(b.id)??nodes.length));
  const cy=cytoscape({
   container:container.current,
   elements:[...orderedNodes.map((n:any)=>({data:{id:n.id,label:n.name,color:colors[n.kind]||'#94a3b8',size:n.id===data?.root?21:n.kind==='Class'||n.kind==='File'?13:n.kind==='Function'?10:8,node:n,root:n.id===data?.root?1:0,ring:distance.get(n.id)??10}})),
    ...edges.map((e:any,i:number)=>({data:{id:'edge-'+i,source:e.source,target:e.target,label:e.kind}}))],
   style:[
    {selector:'node',style:{'background-color':'data(color)',label:'','overlay-opacity':0,width:'data(size)',height:'data(size)','border-width':0,color:'#e2e8f0','font-size':10,'text-valign':'bottom','text-margin-y':7,'text-background-color':'#0b1020','text-background-opacity':.9,'text-background-padding':'3px','min-zoomed-font-size':8}},
    {selector:'edge',style:{width:.7,'line-color':'#50719c','target-arrow-color':'#50719c','target-arrow-shape':'triangle','arrow-scale':.5,'curve-style':'bezier',opacity:.36,label:'','overlay-opacity':0}},
    {selector:'node[root = 1]',style:{'border-width':2,'border-color':'#fbbf24'}},
    {selector:'node.names-on',style:{label:'data(label)','min-zoomed-font-size':0,'text-max-width':'130px','text-wrap':'ellipsis'}},
    {selector:'.dimmed',style:{opacity:.08}},
    {selector:'node.emphasized',style:{opacity:1,'border-width':1.5,'border-color':'#e2e8f0'}},
    {selector:'edge.emphasized',style:{opacity:.95,width:1.4,'line-color':'#93c5fd','target-arrow-color':'#93c5fd','arrow-scale':.7}},
    {selector:'node:selected',style:{'border-width':2,'border-color':'#f8fafc'}}
   ],
   layout:{name:'preset'},minZoom:.08,maxZoom:3,wheelSensitivity:.2,hideEdgesOnViewport:true,textureOnViewport:true
  });
  instance.current=cy;
  function fit(elements:cytoscape.CollectionReturnValue=cy.elements()){
   if(!elements.length)return;cy.fit(elements,60);if(cy.zoom()>1.5)cy.zoom({level:1.5,renderedPosition:{x:cy.width()/2,y:cy.height()/2}});
  }
  applyLayout.current=()=>{
   const chosen=layout==='auto'?(data?.root?'radial':'force'):layout;
   if(chosen==='radial')cy.layout({name:'concentric',animate:false,padding:60,minNodeSpacing:24,avoidOverlap:true,spacingFactor:1.15,equidistant:false,concentric:n=>n.data('root')?6:Math.max(0,6-Number(n.data('ring'))),levelWidth:()=>1}).run();
   else cy.layout({name:'cose',animate:false,padding:60,fit:false,nodeRepulsion:()=>14000,idealEdgeLength:()=>100,edgeElasticity:()=>90,gravity:.12,numIter:1200,componentSpacing:100,randomize:true}).run();
   fit();
  };
  applyLayout.current();
  function emphasize(node?:cytoscape.NodeSingular,edge?:cytoscape.EdgeSingular){
   cy.batch(()=>{cy.elements().removeClass('dimmed emphasized');if(node||edge){const neighborhood=node?node.closedNeighborhood():edge!.connectedNodes().union(edge!);cy.elements().difference(neighborhood).addClass('dimmed');neighborhood.addClass('emphasized');}});
  }
  function nodeTip(n:cytoscape.NodeSingular){
   const value=n.data('node'),pos=n.renderedPosition();
   setTip({title:value.name,subtitle:`${value.kind} · ${n.connectedEdges().length} رابطه در این نما`,detail:value.path?`${value.path}:${value.line||1}`:'بدون مسیر سورس',x:pos.x,y:pos.y});
  }
  showTip.current=nodeTip;
  cy.on('mouseover','node',e=>{emphasize(e.target);nodeTip(e.target);});
  cy.on('mouseover','edge',e=>{const edge=e.target as cytoscape.EdgeSingular;emphasize(undefined,edge);const pos=e.renderedPosition||edge.midpoint();setTip({title:edge.data('label'),subtitle:`${edge.source().data('label')} → ${edge.target().data('label')}`,detail:'جهت رابطه مطابق فلش است',x:pos.x,y:pos.y});});
  cy.on('mouseout','node, edge',()=>{setTip(null);const selected=cy.$('node:selected');emphasize(selected.length?selected[0] as cytoscape.NodeSingular:undefined);});
  cy.on('tap','node',e=>{const n=e.target as cytoscape.NodeSingular;setFocus(n.id());emphasize(n);nodeTip(n);selectCallback.current(n.data('node'));});
  cy.on('tap',e=>{if(e.target===cy){cy.elements().unselect();setFocus('');setTip(null);emphasize();selectCallback.current(null);}});
  cy.on('pan zoom drag',()=>setTip(null));
  const observer=new ResizeObserver(()=>{cy.resize();fit();setTip(null);});observer.observe(container.current);
  return()=>{observer.disconnect();cy.destroy();instance.current=null;};
 },[data,layout]);

 useEffect(()=>{const cy=instance.current;if(cy)cy.nodes().toggleClass('names-on',names);},[names,data,layout]);
 useEffect(()=>{
  function exit(e:KeyboardEvent){if(e.key==='Escape')setExpanded(false);}
  document.addEventListener('keydown',exit);return()=>document.removeEventListener('keydown',exit);
 },[]);
 function reset(){const cy=instance.current;if(!cy)return;cy.elements().unselect().removeClass('dimmed emphasized');setFocus('');setTip(null);selectCallback.current(null);}
 function fit(){const cy=instance.current;if(!cy?.elements().length)return;cy.fit(cy.elements(),60);if(cy.zoom()>1.5)cy.zoom({level:1.5,renderedPosition:{x:cy.width()/2,y:cy.height()/2}});}
 function zoom(factor:number){const cy=instance.current;if(cy)cy.zoom({level:Math.min(3,Math.max(.08,cy.zoom()*factor)),renderedPosition:{x:cy.width()/2,y:cy.height()/2}});}
 function choose(id:string){const cy=instance.current;if(!cy)return;const n=cy.getElementById(id);if(!n.length)return;cy.elements().unselect().removeClass('dimmed emphasized');n.select();const neighborhood=n.closedNeighborhood();cy.elements().difference(neighborhood).addClass('dimmed');neighborhood.addClass('emphasized');cy.animate({center:{eles:n},duration:180});setFocus(id);showTip.current(n as cytoscape.NodeSingular);selectCallback.current(n.data('node'));}
 return <section ref={frame} className={'graph-view'+(expanded?' graph-expanded':'')} aria-label="کاوش بصری گراف">
  <div className="graph-actions">
   <label>چیدمان <select aria-label="Graph layout" value={layout} onChange={e=>setLayout(e.target.value)}><option value="auto">خودکار</option><option value="radial">حلقه‌ای از مرکز</option><option value="force">پخش‌شده</option></select></label>
   <button onClick={fit}>جا دادن گراف</button><button aria-label="Zoom in" onClick={()=>zoom(1.25)}>+</button><button aria-label="Zoom out" onClick={()=>zoom(.8)}>−</button>
   <button onClick={()=>applyLayout.current()}>چیدمان دوباره</button>
   <button aria-pressed={names} onClick={()=>setNames(!names)}>{names?'پنهان‌کردن نام‌ها':'نمایش همهٔ نام‌ها'}</button>
   <button disabled={!focus} onClick={reset}>پاک‌کردن تمرکز</button>
   <button aria-pressed={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'خروج از نمای بزرگ':'نمای بزرگ'}</button>
  </div>
  <div className="graph-stage">
   <div ref={container} className="graph-canvas"/>
   {!(data?.nodes?.length)&&<div className="graph-placeholder">گرافی برای نمایش بارگذاری نشده است.</div>}
   {tip&&<div role="tooltip" className="graph-tooltip" style={{left:Math.max(10,Math.min(tip.x+18,(container.current?.clientWidth||500)-290)),top:Math.max(10,Math.min(tip.y+18,(container.current?.clientHeight||500)-126))}}><strong dir="ltr">{tip.title}</strong><span>{tip.subtitle}</span><code>{tip.detail}</code></div>}
   <div className="graph-corner">{data?.nodes?.length||0} نود · {data?.edges?.length||0} رابطه <span>هاور: جزئیات و همسایه‌ها · کلیک: نگه‌داشتن تمرکز</span></div>
  </div>
  <div className="graph-legend"><span><i style={{background:colors.Class}}/>کلاس</span><span><i style={{background:colors.Function}}/>تابع / متد</span><span><i style={{background:colors.File}}/>فایل</span><span><i style={{background:colors.Module}}/>ماژول</span><span>حاشیهٔ طلایی: مرکز · برای گسترش از دکمهٔ زیر گراف استفاده کنید</span></div>
  <details className="graph-node-list"><summary>انتخاب نود از فهرست، بدون ماوس</summary><select aria-label="Select graph node" value={focus} onChange={e=>e.target.value?choose(e.target.value):reset()}><option value="">انتخاب نود…</option>{(data?.nodes||[]).map((n:any)=><option key={n.id} value={n.id}>{n.name} — {n.kind} — {n.path}</option>)}</select></details>
 </section>;
}
