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

test('library progress line on About matches pipeline counts', ()=>{
  const html=readFileSync(new URL('../dist/about/index.html',import.meta.url),'utf8');
  const q=JSON.parse(readFileSync(new URL('../dist/data/progress.json',import.meta.url),'utf8'));
  const dom=new JSDOM(html,{url:'https://fathers.saneapps.com/about/'});
  const s=dom.window.document.querySelector('#explore-progress');assert.ok(s);
  assert.match(s.textContent,new RegExp(`${q.published_works} works live`));
  const fmt=n=>Number(n).toLocaleString("en-US");
  assert.match(s.textContent,new RegExp(`${fmt(q.corpus_translated_sections)} of ${fmt(q.corpus_total_sections)} sections translated`));
  assert.match(s.textContent,new RegExp(`${q.held_works} held for review`));
  dom.window.close();
});

test('home: favicon, today passage, deduped daily pool, road, Play kept', ()=>{
  const html=readFileSync(new URL('../dist/index.html',import.meta.url),'utf8');
  const dom=new JSDOM(html,{url:'https://fathers.saneapps.com/'});
  const doc=dom.window.document;
  assert.ok(doc.querySelector('link[rel="icon"]'),'favicon link present');
  assert.match(doc.querySelector('link[rel="icon"]').getAttribute('href'),/\/assets\/favicon\.svg/);
  assert.match(doc.title,/^Via Patrum/);
  const card=doc.querySelector('[data-daily]');
  assert.ok(card,'today passage card');
  assert.ok(card.querySelector('.vp-daily-q').textContent.split(/\s+/).length>=14);
  const pool=JSON.parse(readFileSync(new URL('../dist/data/daily.json',import.meta.url),'utf8'));
  assert.ok(pool.length>=30,'daily pool too small: '+pool.length);
  const roman={i:'1',ii:'2',iii:'3',iv:'4',v:'5',vi:'6',vii:'7',viii:'8',ix:'9',x:'10'};
  const seen=new Set();
  for(const r of pool){
    assert.ok(!r.c.startsWith(r.a+' — '),'citation repeats author: '+r.c);
    const key=(r.a+' '+r.c).toLowerCase().split(/[^a-z0-9]+/).filter(Boolean).map(t=>roman[t]||t).join(' ');
    assert.ok(!seen.has(key),'duplicate daily entry: '+r.c); seen.add(key);
  }
  assert.ok(doc.querySelectorAll('.vp-road li').length>=10,'road of the Fathers');
  const play=doc.querySelector('.play-promo');
  assert.ok(play&&play.querySelector('a[href="https://play.viapatrum.org/daily"]'),'Play section kept');
  assert.ok(doc.querySelector('#site-nav a[href="https://play.viapatrum.org/"]'),'Play nav kept');
  dom.window.close();
});

const page=(p)=>new JSDOM(readFileSync(new URL('../dist/'+p,import.meta.url),'utf8'),{url:'https://viapatrum.org/'+p.replace(/index\.html$/,'')}).window.document;

test('question page timeline: one row per claim, stance marks link to passages', ()=>{
  const doc=page('topics/against-docetism/index.html');
  const rows=[...doc.querySelectorAll('#over-time .tl-row')];
  assert.equal(rows.length,2);
  const appeared=rows.find(r=>/only in appearance/i.test(r.querySelector('.tl-claim-text').textContent));
  assert.ok(appeared,'rival claim row present');
  const denies=appeared.querySelectorAll('.tl-pt.denies');
  assert.ok(denies.length>=1,'a writer rejects appearance-only');
  assert.match(denies[0].textContent,/Ignatius/);
  for(const m of denies){
    assert.match(m.getAttribute('aria-label'),/rejects this/);
    const href=m.getAttribute('href');
    assert.ok(href&&(href.startsWith('#')?doc.getElementById(href.slice(1)):href.startsWith('/e/')),'mark links to its passage: '+href);
  }
  assert.match(appeared.querySelector('.tl-tally').textContent,/reject/);
});

test('free will: later turn sits in time order and the summary voice is labeled', ()=>{
  const doc=page('topics/free-will/index.html');
  assert.ok(doc.querySelector('#over-time .tl-turn'),'turn line on the timeline');
  assert.ok(doc.querySelector('.tl-pt.contrast'),'Augustine summary mark');
  const voices=[...doc.querySelector('.voices').children].filter(e=>e.tagName!=='H2');
  const turn=voices.findIndex(e=>e.querySelector&&e.querySelector('#turn')||e.id==='turn');
  assert.ok(turn>0,'turn placed among voices, not first');
  assert.match(doc.querySelector('.contrast-card .meta').textContent,/not yet in this library/);
});

test('over time overview: every question with stances gets a card and a mini timeline', ()=>{
  const doc=page('explore/index.html');
  const data=JSON.parse(readFileSync(new URL('../dist/data/explore-index.json',import.meta.url),'utf8'));
  const withPoints=new Set(data.points.map(p=>p.topic));
  const cards=doc.querySelectorAll('.ot-card');
  assert.equal(cards.length,data.topics.filter(t=>withPoints.has(t.id)).length);
  for(const c of cards){
    assert.ok(c.querySelector('.tl-lane'),'mini timeline in '+c.id);
    assert.match(c.querySelector('h3 a').getAttribute('href'),/^\/topics\/[a-z0-9-]+\/#over-time$/);
  }
  assert.ok(!doc.querySelector('script[src*="explore.js"]'),'old chart script retired');
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
