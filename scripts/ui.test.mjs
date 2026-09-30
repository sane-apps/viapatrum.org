import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
const script = readFileSync(new URL('../assets/site.js', import.meta.url), 'utf8');
const catalog = readFileSync(new URL('../dist/works/index.html', import.meta.url), 'utf8');
const reader = readFileSync(new URL('../dist/works/julian-letter-to-rome/index.html', import.meta.url), 'utf8');
const index = JSON.parse(readFileSync(new URL('../dist/data/search-index.json', import.meta.url), 'utf8'));
const longPassage = index.find(r=>r.kind==='work'&&r.text.length>600);
const searchPhrase = longPassage.text.slice(450,510);
const settle = () => new Promise(resolve => setImmediate(resolve));
function mount(html, path='/works/', fetcher=async()=>({ok:true,json:async()=>index})) {
  const dom=new JSDOM(html,{url:`https://fathers.saneapps.com${path}`,runScripts:'outside-only',pretendToBeVisual:true});
  dom.window.fetch=fetcher;
  dom.window.eval(script);
  return dom;
}
function query(dom, value) {
  const input=dom.window.document.querySelector('#works-q');
  input.value=value;input.dispatchEvent(new dom.window.Event('input'));
}
test('work passages are searchable, including words beyond 400 characters',async()=>{
  const dom=mount(catalog);await settle();
  const row=index.find(r=>r.kind==='work'&&r.text.length>600);
  query(dom,row.text.slice(450,510));await settle();
  assert.ok([...dom.window.document.querySelectorAll('#passage-results a')].some(a=>a.getAttribute('href')===row.href));
  dom.window.close();
});
test('failed passage index yields no hits; healthy fetch recovers',async()=>{
  const bad=mount(catalog,'/works/',async()=>({ok:false}));
  await settle();
  query(bad,searchPhrase);await settle();
  assert.equal(bad.window.document.querySelectorAll('#passage-results a').length,0);
  bad.window.close();
  const good=mount(catalog,'/works/',async()=>({ok:true,json:async()=>index}));
  await settle();
  query(good,searchPhrase);await settle();
  assert.ok(good.window.document.querySelector('#passage-results a'));
  good.window.close();
});
test('invalid filters fall back to All and empty author search hides rows',async()=>{
  const dom=mount(catalog,'/works/?filter=invalid');await settle();
  assert.equal(dom.window.document.querySelector('[data-filter="all"]').getAttribute('aria-pressed'),'true');
  assert.ok(dom.window.document.querySelector('#works-list.author-catalog'));
  const total=dom.window.document.querySelectorAll('#works-list > li.author-entry').length;
  assert.ok(total>0);
  query(dom,'zzzznonexistent');await settle();
  assert.equal(dom.window.document.querySelectorAll('#works-list > li.author-entry:not([hidden])').length,0);
  query(dom,'');await settle();
  assert.equal(dom.window.document.querySelectorAll('#works-list > li.author-entry:not([hidden])').length,total);
  dom.window.close();
});
test('mobile primary nav stays available without hamburger discovery',()=>{
  const dom=mount(reader);const doc=dom.window.document;const toggle=doc.querySelector('.nav-toggle');
  const nav=doc.querySelector('#site-nav');
  assert.ok(nav);
  assert.ok(toggle);
  assert.equal(toggle.getAttribute('aria-expanded')||'false','false');
  assert.ok(doc.querySelectorAll('#site-nav a').length>=5);
  dom.window.close();
});
test('Contents jump target exists on reader pages',()=>{
  const dom=mount(reader);const doc=dom.window.document;
  const contents=doc.querySelector('#contents');
  assert.ok(contents);
  assert.ok(doc.querySelector('a[href="#contents"], .reader-quick a, a.reader-top'));
  contents.open=true;
  assert.equal(contents.open,true);
  contents.querySelector('summary')?.click();
  dom.window.close();
});

test('author catalog prefetches the passage index for find-as-you-type',async()=>{
  let calls=0;const dom=mount(catalog,'/works/',async()=>{calls++;return {ok:true,json:async()=>index};});
  await settle();assert.equal(calls,1);query(dom,'numbering');await settle();assert.equal(calls,1);dom.window.close();
});

test('timeline tooltip stays inside canvas and does not cover touch selections', async()=>{
  const html=readFileSync(new URL('../dist/explore/index.html',import.meta.url),'utf8');
  const data=JSON.parse(readFileSync(new URL('../dist/data/explore-index.json',import.meta.url),'utf8'));
  const dom=new JSDOM(html,{url:'https://fathers.saneapps.com/explore/?topic=free-will',runScripts:'outside-only',pretendToBeVisual:true});
  const w=dom.window,doc=w.document;
  w.fetch=async()=>({ok:true,json:async()=>data});
  w.matchMedia=()=>({matches:false});
  w.ResizeObserver=class { observe() {} disconnect() {} };
  w.HTMLElement.prototype.scrollIntoView=()=>{};
  const canvas=doc.querySelector('#explore-canvas'),tip=doc.querySelector('#explore-tooltip');
  canvas.getBoundingClientRect=()=>({left:0,top:0,width:390,height:420,bottom:420});
  tip.getBoundingClientRect=()=>({width:256,height:100});
  w.eval(readFileSync(new URL('../assets/explore.js',import.meta.url),'utf8'));await settle();await settle();
  const point=doc.querySelector('.explore-point');assert.ok(point);
  const touch=new w.MouseEvent('pointerenter',{clientX:389,clientY:419});Object.defineProperty(touch,'pointerType',{value:'touch'});
  point.dispatchEvent(touch);assert.equal(tip.classList.contains('is-on'),false);
  point.dispatchEvent(new w.MouseEvent('pointerenter',{clientX:389,clientY:419}));
  assert.equal(tip.classList.contains('is-on'),true);
  assert.ok(parseFloat(tip.style.left)>=8 && parseFloat(tip.style.left)+256<=382);
  assert.ok(parseFloat(tip.style.top)>=8 && parseFloat(tip.style.top)+100<=412);
  point.dispatchEvent(new w.MouseEvent('click'));assert.equal(tip.classList.contains('is-on'),false);
  dom.window.close();
});

test('explore summary counts positions for the topic', async()=>{
  const html=readFileSync(new URL('../dist/explore/index.html',import.meta.url),'utf8');
  const data=JSON.parse(readFileSync(new URL('../dist/data/explore-index.json',import.meta.url),'utf8'));
  const dom=new JSDOM(html,{url:'https://fathers.saneapps.com/explore/?topic=free-will',runScripts:'outside-only',pretendToBeVisual:true});
  const w=dom.window,doc=w.document;
  w.fetch=async()=>({ok:true,json:async()=>data});
  w.matchMedia=()=>({matches:false});
  w.ResizeObserver=class { observe() {} disconnect() {} };
  w.HTMLElement.prototype.scrollIntoView=()=>{};
  w.eval(readFileSync(new URL('../assets/explore.js',import.meta.url),'utf8'));await settle();await settle();
  const s=doc.querySelector('#explore-summary');assert.ok(s);
  assert.match(s.textContent,/positions/);
  assert.match(s.textContent,/writers/);
  assert.match(s.textContent,/affirms/);
  dom.window.close();
});

test('explore progress strip matches pipeline counts', ()=>{
  const html=readFileSync(new URL('../dist/explore/index.html',import.meta.url),'utf8');
  const q=JSON.parse(readFileSync(new URL('../outputs/catalogue-quality.json',import.meta.url),'utf8'));
  const dom=new JSDOM(html,{url:'https://fathers.saneapps.com/explore/',runScripts:'outside-only',pretendToBeVisual:true});
  const s=dom.window.document.querySelector('#explore-progress');assert.ok(s);
  assert.match(s.textContent,new RegExp(`${q.published_works} works live`));
  assert.match(s.textContent,new RegExp(`${q.corpus_translated_sections} of ${q.corpus_total_sections} sections translated`));
  assert.match(s.textContent,new RegExp(`${q.held_works.length} held for review`));
  dom.window.close();
});

test('home has favicon and a deduped feed without repeated author', ()=>{
  const html=readFileSync(new URL('../dist/index.html',import.meta.url),'utf8');
  const dom=new JSDOM(html,{url:'https://fathers.saneapps.com/'});
  const doc=dom.window.document;
  assert.ok(doc.querySelector('link[rel="icon"]'),'favicon link present');
  assert.match(doc.querySelector('link[rel="icon"]').getAttribute('href'),/\/assets\/favicon\.svg/);
  const section=[...doc.querySelectorAll('section h2')].find(h=>h.textContent.includes('From the topics')).parentElement;
  const feed=[...section.querySelectorAll('li')];
  assert.equal(feed.length,8);
  const roman={i:'1',ii:'2',iii:'3',iv:'4',v:'5',vi:'6',vii:'7',viii:'8',ix:'9',x:'10'};
  const seen=new Set();
  for(const li of feed){
    const strong=li.querySelector('strong').textContent.trim();
    const span=li.querySelector('span').textContent.trim();
    assert.ok(!span.startsWith(strong+' — ')&&!span.startsWith(strong+' - '),'subline repeats author: '+span);
    const key=(strong+' '+span).toLowerCase().split(/[^a-z0-9]+/).filter(Boolean).map(t=>roman[t]||t).join(' ');
    assert.ok(!seen.has(key),'duplicate feed entry: '+span); seen.add(key);
  }
  dom.window.close();
});

function mountExplore(url, html, data) {
  const dom=new JSDOM(html,{url,runScripts:'outside-only',pretendToBeVisual:true});
  const w=dom.window;
  w.fetch=async()=>({ok:true,json:async()=>data});
  w.matchMedia=()=>({matches:false});
  w.ResizeObserver=class { observe() {} disconnect() {} };
  w.HTMLElement.prototype.scrollIntoView=()=>{};
  w.eval(readFileSync(new URL('../assets/explore.js',import.meta.url),'utf8'));
  return dom;
}
const exploreHtml=()=>readFileSync(new URL('../dist/explore/index.html',import.meta.url),'utf8');
const exploreData=()=>JSON.parse(readFileSync(new URL('../dist/data/explore-index.json',import.meta.url),'utf8'));

test('explore table states each writer verdict: Ignatius says No to appearance-only',async()=>{
  const dom=mountExplore('https://fathers.saneapps.com/explore/?topic=against-docetism&view=table',exploreHtml(),exploreData());
  await settle();await settle();
  const doc=dom.window.document;
  assert.ok(doc.querySelector('.verdict-table'));
  const heads=[...doc.querySelectorAll('.verdict-table thead th')].map(th=>th.textContent.trim());
  assert.deepEqual(heads,['Writer','Truly born','Only appeared']);
  const row=[...doc.querySelectorAll('.verdict-table tbody tr')].find(tr=>tr.querySelector('th').textContent.includes('Ignatius'));
  assert.ok(row);
  const cells=[...row.querySelectorAll('td')];
  assert.match(cells[0].textContent,/^Yes · 4/);
  assert.match(cells[1].textContent,/^No · 2/);
  assert.equal(cells[1].querySelector('button').getAttribute('data-claim'),'dokew');
  cells[1].querySelector('button').click();await settle();
  assert.match(doc.querySelector('#explore-drawer').textContent,/teaches NO/);
  dom.window.close();
});

test('explore timeline draws denials as X marks with plain-words tooltips',async()=>{
  const dom=mountExplore('https://fathers.saneapps.com/explore/?topic=against-docetism',exploreHtml(),exploreData());
  await settle();await settle();
  const doc=dom.window.document;
  const deny=doc.querySelector('.explore-point[data-stance="denies"]');
  assert.ok(deny);
  assert.equal(deny.querySelectorAll('line').length,2);
  assert.ok(doc.querySelector('.explore-point[data-stance="affirms"] circle'));
  const tip=doc.querySelector('#explore-tooltip');
  deny.dispatchEvent(new dom.window.MouseEvent('pointerenter',{clientX:100,clientY:100}));
  assert.equal(tip.classList.contains('is-on'),true);
  assert.match(tip.textContent,/DENIES/);
  assert.match(tip.textContent,/Only appeared/);
  dom.window.close();
});

test('explore timeline places one excerpt once per claim lane',async()=>{
  const dom=mountExplore('https://fathers.saneapps.com/explore/?topic=against-docetism',exploreHtml(),exploreData());
  await settle();await settle();
  const doc=dom.window.document;
  const twins=[...doc.querySelectorAll('.explore-point')].filter(g=>(g.getAttribute('data-id')||'').startsWith('excerpt:ignatius_smyrn_2_true|'));
  assert.equal(twins.length,2);
  const stances=twins.map(g=>g.getAttribute('data-stance')).sort();
  assert.deepEqual(stances,['affirms','denies']); // 2026-09-28: smyrn_2 re-rated affirms on author context (stance review)
  const cys=twins.map(g=>parseFloat(g.querySelector('circle').getAttribute('cy')));
  assert.ok(Math.abs(cys[0]-cys[1])>40,'same-id marks share a lane');
  dom.window.close();
});

test('explore consensus charts one line per claim',async()=>{
  const dom=mountExplore('https://fathers.saneapps.com/explore/?topic=against-docetism&view=consensus',exploreHtml(),exploreData());
  await settle();await settle();
  const doc=dom.window.document;
  const lines=[...doc.querySelectorAll('.consensus-line')].map(g=>g.getAttribute('data-claim')).sort();
  assert.deepEqual(lines,['dokew','truly-born-suffered']);
  dom.window.close();
});

test('explore search narrows positions to matching writers',async()=>{
  const dom=mountExplore('https://fathers.saneapps.com/explore/?topic=against-docetism',exploreHtml(),exploreData());
  await settle();await settle();
  const doc=dom.window.document;
  const q=doc.querySelector('#explore-q');assert.ok(q);
  q.value='novatian';q.dispatchEvent(new dom.window.Event('input'));await settle();
  assert.match(doc.querySelector('#explore-summary').textContent,/^1 positions/);
  assert.equal(doc.querySelectorAll('.explore-point').length,1);
  q.value='';q.dispatchEvent(new dom.window.Event('input'));await settle();
  assert.match(doc.querySelector('#explore-summary').textContent,/^8 positions/);
  dom.window.close();
});

test('favicon files ship in dist', ()=>{
  assert.ok(readFileSync(new URL('../dist/favicon.ico',import.meta.url)).length>100);
  assert.match(readFileSync(new URL('../dist/assets/favicon.svg',import.meta.url),'utf8'),/<svg/);
});

test('link hover system ships in built CSS', ()=>{
  const css=readFileSync(new URL('../dist/assets/site.css',import.meta.url),'utf8');
  const hovers=(css.match(/:hover/g)||[]).length;
  assert.ok(hovers>=40,'expected site-wide :hover coverage, got '+hovers);
  const focus=(css.match(/:focus-visible/g)||[]).length;
  assert.ok(focus>=20,'expected focus-visible parity, got '+focus);
  assert.match(css,/\.card-list li a:hover/,'works-list row hover missing');
  assert.match(css,/\.topic-list li a:hover/,'topic-list row hover missing');
  assert.match(css,/\.related li a:hover/,'related row hover missing');
  assert.match(css,/inset [23]px 0 0 var\(--gold-deep\)/,'gold leading rule missing');
  assert.match(css,/\.site-nav a:hover/,'nav hover missing');
  assert.match(css,/prefers-reduced-motion/,'reduced-motion handling missing');
  assert.ok(!/purple|indigo|violet/i.test(css),'forbidden hue in CSS');
  assert.ok(!/scale\(/.test(css),'scale transform in CSS');
});
