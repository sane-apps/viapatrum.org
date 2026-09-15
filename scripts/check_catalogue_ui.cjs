// Mini Brave checks + review gate. No screenshot is marked inspected by this script.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const crypto = require("node:crypto");
const {chromium} = require("playwright");
const sha = value => crypto.createHash("sha256").update(value).digest("hex");
const REQUIRED_SHOTS = [
 ...[1440,1024,768,390].flatMap(w=>["author-"+w,"author-group-"+w]),
 "title-1440","title-390","search-390","empty-390","keyboard-focus-1440",
 "reader-1440","reader-390","mobile-menu-390","index-error-390","index-recovered-390",
 ...["home","author-hub","topic","explore"].flatMap(n=>[n+"-1440",n+"-390"]),
 "unavailable-390","about-390","methodology-390","help-390","julian-bible-1440","julian-source-390"
].map(n=>n+".png");
const REQUIRED_CHECKS=["sort","filters","search","keyboard","menu","contents","index-retry","templates","source-details","geometry"];
function artifact(root=process.cwd(),base=path.join(root,"dist")) {
 const files=[];
 function walk(dir) {for(const d of fs.readdirSync(dir,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))) {
  const f=path.join(dir,d.name);assert(!d.isSymbolicLink(),"Symlink in dist: "+f);
  if(d.isDirectory()) walk(f); else if(d.isFile()) files.push(f);
 }}
 walk(base);assert(files.length,"Empty dist");
 const h=crypto.createHash("sha256");let bytes=0;
 for(const f of files){const data=fs.readFileSync(f);bytes+=data.length;h.update(path.relative(base,f)+"\0"+sha(data)+"\n");}
 return {sha256:h.digest("hex"),files:files.length,bytes,
  css:sha(fs.readFileSync(path.join(base,"assets/site.css"))),
  js:sha(fs.readFileSync(path.join(base,"assets/site.js"))),
  runner:sha(fs.readFileSync(path.join(root,"scripts/check_catalogue_ui.cjs")))};
}
function verifyReview(root=process.cwd(), out=path.join(root,"outputs/ui-review"),dist=path.join(root,"dist")) {
 const r=JSON.parse(fs.readFileSync(path.join(out,"browser-receipt.json"),"utf8"));
 assert.equal(r.schema,2,"Old browser receipt schema");
 assert.equal(r.status,"passed","Browser checks did not pass");
 assert.deepEqual(r.artifact,artifact(root,dist),"Build or browser checks changed after review");
 assert.deepEqual([...r.completed_checks].sort(),[...REQUIRED_CHECKS].sort(),"Incomplete browser checks");
 assert.deepEqual([...r.screenshots.map(s=>s.path)].sort(),[...REQUIRED_SHOTS].sort(),"Missing/duplicate visual states");
 assert.equal(r.errors.length,0,"Browser exceptions recorded");
 assert.equal(r.review?.status,"passed","Images need actual agent visual review");
 assert.equal(r.review?.method,"image-inspection","Review must be based on opened images");
 assert((r.review?.reviewer||"").trim().length>=3,"Reviewer identity missing");
 assert(Number.isFinite(Date.parse(r.review.reviewed_at)) && Date.parse(r.review.reviewed_at)>=Date.parse(r.started) && Date.parse(r.review.reviewed_at)<=Date.now()+300000,"Review timestamp invalid");
 for(const s of r.screenshots) {
  assert.equal(s.sha256,sha(fs.readFileSync(path.join(out,s.path))),"Screenshot changed: "+s.path);
  assert.equal(s.inspected,true,"Image not inspected: "+s.path);
  assert(typeof s.result==="string" && s.result.trim().length>=25 && !/TODO|pending|not inspected/i.test(s.result),"Concrete visual finding missing: "+s.path);
  assert.equal(s.geometry.failures.length,0,"Layout errors: "+s.path);
 }
 return r;
}
async function geometry(page) {
 return page.evaluate(()=>{
  const failures=[], limitations=[];
  if(document.documentElement.scrollWidth>innerWidth+1) failures.push("horizontal document overflow");
  const canvas=document.createElement("canvas");canvas.width=canvas.height=1;
  const ctx=canvas.getContext("2d"),cache=new Map();
  function rgba(s){if(cache.has(s))return cache.get(s);ctx.clearRect(0,0,1,1);ctx.fillStyle=s;ctx.fillRect(0,0,1,1);const a=[...ctx.getImageData(0,0,1,1).data];cache.set(s,a);return a;}
  function mix(f,b){const a=f[3]/255;return [0,1,2].map(i=>f[i]*a+b[i]*(1-a)).concat(255);}
  function luminance(c){return c.slice(0,3).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((a,x,i)=>a+x*[.2126,.7152,.0722][i],0);}
  let measured=0;
  for(const e of document.querySelectorAll("h1,h2,h3,p,a,button,summary,strong,span,label")) {
   const box=e.getBoundingClientRect(),style=getComputedStyle(e);
   if(box.width<2||box.height<2||box.bottom<=0||box.top>=innerHeight||style.visibility!=="visible"||e.closest(".vh,.skip,[hidden]"))continue;
   const text=[...e.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE&&n.textContent.trim());
   if(!text.length)continue;
   const chain=[];for(let n=e;n;n=n.parentElement)chain.push(n);
   if(chain.some(n=>Number(getComputedStyle(n).opacity)===0))continue;
   if(box.left < -1 || box.right>innerWidth+1) failures.push("text outside viewport: "+e.textContent.trim().slice(0,60));
   if(chain.some(n=>getComputedStyle(n).backgroundImage!=="none")){limitations.push("image background: "+e.tagName);continue;}
   let bg=[255,255,255,255];for(const n of chain.reverse())bg=mix(rgba(getComputedStyle(n).backgroundColor),bg);
   const fg=mix(rgba(style.color),bg), l1=luminance(fg),l2=luminance(bg),contrast=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);
   const large=parseFloat(style.fontSize)>=24||(parseFloat(style.fontSize)>=18.66&&Number(style.fontWeight)>=700),minimum=large?3:4.5;
   measured++;if(contrast+.03<minimum) failures.push("contrast "+contrast.toFixed(2)+" < "+minimum+": "+e.textContent.trim().slice(0,60));
  }
  const rows=[...document.querySelectorAll("#works-list > li:not([hidden])")].map(e=>e.getBoundingClientRect());
  for(let i=1;i<rows.length;i++)if(rows[i-1].bottom>rows[i].top+1)failures.push("catalogue rows overlap");
  return {failures:[...new Set(failures)],contrast_nodes:measured,limitations:[...new Set(limitations)]};
 });
}
async function run(base,out) {
 assert(/mini/i.test(os.hostname()),"Run browser verification on Mini.");
 fs.mkdirSync(out,{recursive:true});
 const receipt={schema:2,host:os.hostname(),base,artifact:artifact(),started:new Date().toISOString(),checks:[],screenshots:[],errors:[],review:{status:"pending",method:"image-inspection",reviewer:"",reviewed_at:""}};
 fs.writeFileSync(path.join(out,"REVIEW.md"),"Open every PNG listed in browser-receipt.json at native size. Review author/title priority, content readability, source/citation sequence (including repeated-source fragments), clipping/overlap, color contrast, focus, controls, empty/error/recovery states, and mobile proportions. Read the source context in AGENTS.md and docs/UI_REVIEW.md. For each image set inspected=true and write a concrete result only after viewing. Record review.status=passed, method=image-inspection, reviewer identity, and reviewed_at ISO timestamp after every image passes. Leave pending or failed if uncertain. This is an agent inspection step, not a standing human queue. The receipt is bound to the entire dist and browser runner. No visual claim may be inferred from deterministic checks alone.\n");

 let page;
 const browser = await chromium.launch({executablePath:"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",headless:true});
 try {
  page = await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
  page.setDefaultTimeout(10000);
  async function visit(url,options) {
   const response=await page.goto(url,options);
   const pathname=decodeURIComponent(new URL(url).pathname);
   const local=path.resolve("dist","."+pathname+(pathname.endsWith("/")?"index.html":""));
   assert(local.startsWith(path.resolve("dist")+path.sep),"Preview path escaped dist");
   assert.equal(response.status(),200,"Preview HTTP error: "+pathname);
   assert.equal(sha(await response.body()),sha(fs.readFileSync(local)),"Served HTML differs from built artifact: "+pathname);
   return response;
  }
  for(const asset of ["site.css","site.js"]) {
   const response=await page.request.get(base+"/assets/"+asset,{timeout:30000});
   assert.equal(response.status(),200,"Missing served asset");
   assert.equal(sha(await response.body()),sha(fs.readFileSync("dist/assets/"+asset)),"Stale preview asset: "+asset);
  }

  page.on("pageerror", e => receipt.errors.push(e.message));
  await visit(base+"/works/?sort=author",{waitUntil:"networkidle",timeout:30000});
  const rows=page.locator("#works-list .work-entry");
  const visible=page.locator("#works-list .work-entry:visible");
  const total=await rows.count();
  assert(total>0,"No catalogue rows: review an explicit empty-library release separately");
  const sampleAuthor=await rows.first().getAttribute("data-author");
  async function shot(label,width) {
   const height=width<800?900:1000;
   if(page.viewportSize().width!==width || page.viewportSize().height!==height) await page.setViewportSize({width,height});
   await page.waitForTimeout(350); // Settle layout before measuring and capturing.
   const layout=await geometry(page);
   assert.equal(layout.failures.length,0,label+": "+layout.failures.join("; "));
   await page.screenshot({path:path.join(out,label+"-"+width+".png")});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),"Horizontal overflow "+label+" "+width);
   receipt.screenshots.push({path:label+"-"+width+".png",sha256:sha(fs.readFileSync(path.join(out,label+"-"+width+".png"))),url:page.url(),viewport:page.viewportSize(),geometry:layout,inspected:false,result:""});
  }
  for(const width of [1440,1024,768,390]) {
   await page.evaluate(()=>scrollTo(0,0));
   await shot("author",width);
   await rows.first().scrollIntoViewIfNeeded();
   await shot("author-group",width);
  }
  await page.setViewportSize({width:1440,height:1000});
  for(const sort of ["author","title","chrono"]) {
   const btn=page.locator('[data-sort="'+sort+'"]');
   await btn.click();
   assert.equal(await btn.getAttribute("aria-pressed"),"true");
   const data=await visible.evaluateAll(es=>es.map(e=>({...e.dataset})));
   for(let i=1;i<data.length;i++) {
    const cmp=sort==="chrono"?Number(data[i-1].year)-Number(data[i].year):data[i-1][sort].localeCompare(data[i][sort],undefined,{sensitivity:"base",numeric:true});
    assert(cmp<=0,"Incorrect "+sort+" order at "+i);
   }
   const groupNames=await page.locator(".author-group h2 a").allTextContents();
   if(sort==="title") assert.equal(groupNames.length,0,"Title sort retains author groups");
   else assert(groupNames.length>0,"Author headings absent");
   if(sort==="author") assert.equal(groupNames.length,new Set(data.map(d=>d.author)).size,"Duplicate/missing author group");
   receipt.checks.push({sort,rows:data.length,groups:groupNames.length});
   await page.evaluate(()=>scrollTo(0,0));
   if(sort==="title") for(const width of [1440,390]) await shot("title",width);
   await page.setViewportSize({width:1440,height:1000});
  }
  for(const filter of ["Apostolic","Ante-Nicene","Nicene","Post-Nicene","oet","all"]) {
   const btn=page.locator('[data-filter="'+filter+'"]');
   if(!await btn.count()) continue;
   await btn.click();
   const eras=await visible.evaluateAll(es=>es.map(e=>({era:e.dataset.era,oet:e.dataset.oet})));
   assert(eras.every(e=>filter==="all"||(filter==="oet"?e.oet==="1":e.era===filter)),"Wrong filter membership");
   assert((await page.locator("#works-status").innerText()).startsWith(String(eras.length)),"Status count mismatch");
   receipt.checks.push({filter,count:eras.length});
  }
  await page.locator('[data-sort="author"]').click();
  await page.locator("#works-q").fill(sampleAuthor);
  assert(await visible.count()>0,"Author search returned nothing");
  assert((await visible.evaluateAll(es=>es.map(e=>e.dataset.author))).every(a=>a===sampleAuthor));
  await shot("search",390);
  await page.locator("#works-q").fill("zzzz-no-such-work-9182");
  assert.equal(await visible.count(),0);
  assert.equal(await page.locator(".author-group").count(),0,"Empty search retained group headings");
  await shot("empty",390);
  await page.locator("#works-q").fill("");
  assert.equal(await visible.count(),total);
  await page.setViewportSize({width:1440,height:1000});
  const titleButton=page.locator('[data-sort="title"]');
  await titleButton.focus();
  await page.keyboard.press("Enter");
  assert.equal(await titleButton.getAttribute("aria-pressed"),"true");
  const link=visible.first().locator("a.work-link");
  const href=await link.getAttribute("href");
  await link.focus();
  assert(await link.evaluate(e=>e.matches(":focus-visible")),"Row focus absent");
  await shot("keyboard-focus",1440);
  await page.keyboard.press("Enter");
  await page.waitForURL(base+href);
  assert(await page.locator("h1").isVisible(),"Reader title absent");
  receipt.checks.push({search:true,emptyState:true,keyboardSort:true,keyboardRowNavigation:href});
  assert(!/-collective-\d/.test(await page.locator("main").innerText()),"Internal fragment IDs leaked into reader labels");
  await shot("reader",1440);
  await shot("reader",390);
  const contents=page.locator("details#contents");
  if(await contents.evaluate(e=>e.open)) await contents.locator("summary").click();
  assert.equal(await contents.evaluate(e=>e.open),false,"Reader contents does not close");
  await contents.locator("summary").click();
  assert(await contents.evaluate(e=>e.open),"Reader contents does not open");
  await contents.locator("a").first().click();
  assert(new URL(page.url()).hash,"Contents did not navigate to a passage");
  await visit(base+"/works/?sort=author",{waitUntil:"networkidle"});
  await page.setViewportSize({width:390,height:844});
  const nav=page.locator("#site-nav");
  assert(await nav.isVisible(),"Primary nav missing on mobile");
  assert((await page.locator("#site-nav a").count())>=5,"Primary nav links incomplete on mobile");
  const menu=page.locator(".nav-toggle");
  assert.equal(await menu.isVisible(),false,"Menu toggle must stay hidden when top nav is always on");
  await shot("mobile-menu",390);
  // Escape/focus still covered by scripts/ui.test.mjs; keep the handler wired in site.js.
  receipt.checks.push({mobileNavAlwaysOn:true,readerContents:true});

  const index=JSON.parse(fs.readFileSync("dist/data/search-index.json","utf8"));
  const sample=index.find(r=>r.kind==="work"&&r.text?.length>600)||index.find(r=>r.text?.length>100);
  assert(sample,"No searchable passage sample");
  const term=sample.text.slice(sample.text.length>600?450:30,sample.text.length>600?510:75);
  let attempts=0;
  await page.route("**/data/search-index.json",async route=>{
   attempts++;if(attempts===1)await route.fulfill({status:503,body:"Temporary failure"});else await route.continue();
  });
  await visit(base+"/works/?filter=invalid",{waitUntil:"networkidle"});
  assert.equal(await page.locator('[data-filter="all"]').getAttribute("aria-pressed"),"true");
  assert.equal(attempts,0,"Search index fetched before searching");
  await page.locator("#works-q").fill(term);
  await page.locator(".search-retry").waitFor();
  await page.locator("#passage-hits").scrollIntoViewIfNeeded();
  await shot("index-error",390);
  await page.locator(".search-retry").click();
  await page.locator("#passage-results a").first().waitFor();
  assert((await page.locator("#passage-results a").evaluateAll(es=>es.map(e=>e.getAttribute("href")))).includes(sample.href),"Full passage search missed expected source");
  await page.locator("#passage-hits").scrollIntoViewIfNeeded();
  await shot("index-recovered",390);
  await page.unroute("**/data/search-index.json");
  for(const term of ["","🔥 <>&\"'","x".repeat(10000),"   "])await page.locator("#works-q").fill(term);
  const authorHref=await page.locator(".author-group h2 a").first().getAttribute("href");
  const templates=[["home","/"],["author-hub",authorHref],["topic","/topics/free-will/"],["explore","/explore/?topic=free-will"]];
  for(const [label,url] of templates) {
   const response=await visit(base+url,{waitUntil:"networkidle",timeout:30000});
   assert.equal(response.status(),200,label+" returned HTTP "+response.status());
   await page.locator("h1").first().waitFor();
   if(label==="explore")await page.locator(".explore-point").first().waitFor();
   for(const width of [1440,390]) {await page.evaluate(()=>scrollTo(0,0));await shot(label,width);}
  }
  for(const label of ["about","methodology","help"]) {
   await visit(base+"/"+(label==="help"?"contribute":label)+"/",{waitUntil:"networkidle"});
   if(label==="methodology")await page.locator("h2").filter({hasText:"Review status"}).evaluate(e=>scrollTo(0,e.getBoundingClientRect().top+scrollY-100));
   if(label==="help")await page.locator("#ai-prompt code").evaluate(e=>{
    const node=e.firstChild,start=node.textContent.indexOf("Check exact author/work/source");
    if(start<0)throw new Error("Source evidence instruction missing");
    const range=document.createRange();range.setStart(node,start);range.setEnd(node,start+20);
    scrollTo(0,range.getBoundingClientRect().top+scrollY-350);
   });
   await shot(label,390);
  }
  await visit(base+"/works/julian-to-florus/1.27/",{waitUntil:"networkidle"});
  const body=await page.locator("main").innerText();
  for(const ref of ["Deuteronomy 32:4","Psalm 11:7","Psalm 119:172"])assert(body.includes(ref),"Julian reference missing: "+ref);
  await shot("julian-bible",1440);
  await page.setViewportSize({width:390,height:900});
  const source=page.locator("details.reader-about");
  await source.locator("summary").click();
  assert(await source.evaluate(e=>e.open),"Source details did not open");
  await source.scrollIntoViewIfNeeded();
  await shot("julian-source",390);
  await visit(base+"/404.html",{waitUntil:"networkidle"});
  assert((await page.locator("h1").innerText()).includes("unavailable"));
  await shot("unavailable",390);

  assert.equal(receipt.errors.length,0,"Browser exceptions");
  assert.deepEqual(artifact(),receipt.artifact,"Built files changed during checks");
  receipt.completed_checks=REQUIRED_CHECKS;
  receipt.status="passed";
 } catch(error) {receipt.status="failed";receipt.failure=error.stack;if(page)await page.screenshot({path:path.join(out,"failure.png")}).catch(()=>{});throw error;}
 finally {await browser.close();fs.writeFileSync(path.join(out,"browser-receipt.json"),JSON.stringify(receipt,null,2));}

}
module.exports={artifact,verifyReview,REQUIRED_SHOTS,REQUIRED_CHECKS};
if(require.main===module) {
 if(process.argv[2]==="--verify-review") {
  try {const r=verifyReview(process.cwd(),path.join(process.cwd(),"outputs/ui-review"),process.argv[3]||path.join(process.cwd(),"dist"));console.log("Visual review matches build "+r.artifact.sha256);}
  catch(error){console.error("BLOCKED: "+error.message);process.exitCode=1;}
 } else run(process.argv[2]||"http://127.0.0.1:48765",process.argv[3]||"outputs/ui-review").catch(error=>{console.error(error);process.exitCode=1});
}
