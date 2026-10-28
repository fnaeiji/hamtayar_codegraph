/* Optional browser acceptance check. Requires Playwright + Chromium.
 * PLAYWRIGHT_MODULE may point at an installed playwright package.
 * GRAPH_TEST_BROWSER may point at an existing Chromium executable.
 * All API data is synthetic; no user repositories or Neo4j data are accessed.
 */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const port=Number(process.env.GRAPH_TEST_PORT||5179),base=`http://127.0.0.1:${port}`;
const nodes=Array.from({length:80},(_,i)=>({id:`n${i}`,name:i===0?'AccommodationController':`ExampleVeryLongMemberName${i}`,kind:i===0?'Class':i<17?'Function':'Parameter',path:'Controllers/AccommodationController.cs',line:i+1,end:i+2}));
const edges=nodes.slice(1).map((n,i)=>({source:i<16?'n0':`n${1+i%16}`,target:n.id,kind:i<16?'CONTAINS':'USES'}));
const project={id:'visual-demo',name:'Synthetic graph',active_index:'v1',status:'ready',files:[],logs:[],counts:{nodes:80,relationships:79}};
const graph={nodes,edges,root:'n0',mode:'neighborhood',depth:2,expanded_depth:2,direction:'both',truncated:false,limits:{nodes:200,edges:600}};
(async()=>{
 let browser;const errors=[];const server=spawn(process.execPath,[path.join(root,'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',String(port),'--strictPort'],{cwd:root,stdio:'ignore'});
 try{
  for(let n=0;n<100;n++){try{if((await fetch(base)).ok)break;}catch{}if(n===99)throw Error('Vite did not start');await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({headless:true,...(process.env.GRAPH_TEST_BROWSER?{executablePath:process.env.GRAPH_TEST_BROWSER}:{}),args:['--no-sandbox','--disable-dev-shm-usage']});
  const page=await browser.newPage({viewport:{width:1500,height:1100}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',route=>{
   const url=new URL(route.request().url());let body;
   if(url.pathname==='/api/projects')body=[project];
   else if(url.pathname==='/api/projects/visual-demo')body=project;
   else if(url.pathname.endsWith('/search'))body=[{node:nodes[0]}];
   else if(url.pathname.endsWith('/graph/relations'))body=[{kind:'CONTAINS',total:16},{kind:'USES',total:63}];
   else if(url.pathname.endsWith('/graph'))body=graph;
   else if(url.pathname.endsWith('/archives/capabilities'))body={limits:{upload_mb:1024},rar_decoder:{available:true}};
   else if(url.pathname.endsWith('/capabilities'))body=[];
   else if(url.pathname.endsWith('/settings'))body={values:{}};
   else body={};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto(base);
  await page.getByRole('combobox',{name:'پروژه'}).selectOption('visual-demo');
  await page.getByRole('button',{name:'جست‌وجو و تحلیل',exact:true}).click();
  await page.getByLabel('Search',{exact:true}).fill('AccommodationController');
  await page.getByRole('button',{name:'جست‌وجو',exact:true}).click();
  await page.getByRole('button',{name:'گراف وابستگی این نود',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.graph-canvas')?._cyreg?.cy?.nodes().length===80);
  const styles=await page.evaluate(()=>{const cy=document.querySelector('.graph-canvas')._cyreg.cy;return {nodes:cy.nodes().map(n=>n.style('label')),edges:cy.edges().map(e=>e.style('label'))};});
  assert(styles.nodes.every(x=>x===''),'Node labels must be hidden by default');assert(styles.edges.every(x=>x===''),'Edge labels must be hidden by default');
  await page.locator('.graph-stage').scrollIntoViewIfNeeded();
  const position=await page.evaluate(()=>{const canvas=document.querySelector('.graph-canvas');const p=canvas._cyreg.cy.getElementById('n0').renderedPosition(),r=canvas.getBoundingClientRect();return {x:r.x+p.x,y:r.y+p.y};});
  await page.mouse.move(position.x,position.y);
  await page.getByRole('tooltip').getByText('AccommodationController',{exact:true}).waitFor();
  assert(await page.evaluate(()=>document.querySelector('.graph-canvas')._cyreg.cy.$('.dimmed').length)>0,'Hover must dim unrelated nodes/edges');
  if(process.env.GRAPH_TEST_SCREENSHOT)await page.screenshot({path:process.env.GRAPH_TEST_SCREENSHOT.replace(/\.png$/, '-hover.png')});
  await page.mouse.click(position.x,position.y);
  await page.mouse.move(position.x+200,position.y+150);
  assert(await page.evaluate(()=>document.querySelector('.graph-canvas')._cyreg.cy.$('node:selected').length)===1,'Click must retain selection');
  await page.getByRole('button',{name:'پاک‌کردن تمرکز',exact:true}).click();
  assert(await page.evaluate(()=>document.querySelector('.graph-canvas')._cyreg.cy.$('.dimmed').length)===0);
  await page.getByRole('button',{name:'نمایش همهٔ نام‌ها',exact:true}).click();
  assert(await page.evaluate(()=>document.querySelector('.graph-canvas')._cyreg.cy.nodes()[0].style('label')));
  await page.getByRole('button',{name:'پنهان‌کردن نام‌ها',exact:true}).click();
  await page.getByRole('combobox',{name:'Graph layout'}).selectOption('force');
  await page.getByRole('combobox',{name:'Graph layout'}).selectOption('radial');
  await page.getByRole('button',{name:'نمای بزرگ',exact:true}).click();
  assert(await page.locator('.graph-expanded').count()===1);
  await page.keyboard.press('Escape');assert(await page.locator('.graph-expanded').count()===0);
  await page.getByRole('button',{name:'جا دادن گراف',exact:true}).click();
  if(process.env.GRAPH_TEST_SCREENSHOT)await page.locator('.graph-view').screenshot({path:process.env.GRAPH_TEST_SCREENSHOT});
  const metrics=await page.evaluate(()=>{const cy=document.querySelector('.graph-canvas')._cyreg.cy;return {zoom:cy.zoom(),rootWidth:cy.getElementById('n0').renderedWidth(),minWidth:Math.min(...cy.nodes().map(n=>n.renderedWidth()))};});console.log(metrics);assert(metrics.rootWidth>=8,'Root must remain visible after fit');
  const overflow=await page.locator('.graph-actions').evaluate(el=>{const frame=el.getBoundingClientRect();return [...el.children].some(c=>c.getBoundingClientRect().right>frame.right+1||c.getBoundingClientRect().left<frame.left-1);});assert(!overflow,'Toolbar must wrap within the graph width');
  assert.deepEqual(errors,[],'No browser runtime errors');
  console.log('PASS: search-to-graph, quiet labels, hover tooltip/focus, retained selection, reset, label toggle, layouts, expanded view and Escape.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
