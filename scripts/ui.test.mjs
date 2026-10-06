import { pathToFileURL } from 'node:url';
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
// Built site under test: FATHERS_DIST=<dir> (a package build) or the repo dist/.
const DIST = process.env.FATHERS_DIST ? pathToFileURL(process.env.FATHERS_DIST.replace(/\/?$/, '/')) : new URL('../dist/', import.meta.url);
const script = readFileSync(new URL('../assets/site.js', import.meta.url), 'utf8');
const catalog = readFileSync(new URL('works/index.html',DIST), 'utf8');
const reader = readFileSync(new URL('works/julian-letter-to-rome/index.html',DIST), 'utf8');
const indexText = readFileSync(new URL('data/search-index.json',DIST), 'utf8');
const index = JSON.parse(indexText);
// P5 harness fix (outputs/pkg-P5-search-js/ui.test.mjs.patch): route like the site; a fresh parse per fetch.
const fresh = () => JSON.parse(indexText);
const site = async (u) => String(u).includes('/data/search-index.json') ? {ok:true,json:async()=>fresh()} : String(u).startsWith('/api/search') ? {ok:true,json:async()=>({results:[]})} : {ok:false};
const longPassage = index.find(r=>r.kind==='work'&&r.text.length>600);
const searchPhrase = longPassage.text.slice(450,510);
const settle = () => new Promise(resolve => setTimeout(resolve, 260));
function mount(html, path='/works/', fetcher=site) {
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
  const good=mount(catalog,'/works/',site);
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
  let calls=0;const dom=mount(catalog,'/works/',async(u)=>{if(String(u).includes('search-index'))calls++;return site(u);});
  await settle();query(dom,'numbering');await settle();assert.equal(calls,1);query(dom,'numbers');await settle();assert.equal(calls,1);dom.window.close();
});

test('library progress line on About matches pipeline counts', ()=>{
  const html=readFileSync(new URL('about/index.html',DIST),'utf8');
  const q=JSON.parse(readFileSync(new URL('data/progress.json',DIST),'utf8'));
  const dom=new JSDOM(html,{url:'https://fathers.saneapps.com/about/'});
  const s=dom.window.document.querySelector('#explore-progress');assert.ok(s);
  assert.match(s.textContent,new RegExp(`${q.published_works} works live`));
  const fmt=n=>Number(n).toLocaleString("en-US");
  assert.match(s.textContent,new RegExp(`${fmt(q.corpus_translated_sections)} of ${fmt(q.corpus_total_sections)} sections translated`));
  assert.match(s.textContent,new RegExp(`${q.held_works} held for review`));
  dom.window.close();
});

test('home: favicon, today passage, deduped daily pool, road, Play kept', ()=>{
  const html=readFileSync(new URL('index.html',DIST),'utf8');
  const dom=new JSDOM(html,{url:'https://fathers.saneapps.com/'});
  const doc=dom.window.document;
  assert.ok(doc.querySelector('link[rel="icon"]'),'favicon link present');
  assert.match(doc.querySelector('link[rel="icon"]').getAttribute('href'),/\/assets\/favicon\.svg/);
  assert.match(doc.title,/^Via Patrum/);
  const card=doc.querySelector('[data-daily]');
  assert.ok(card,'today passage card');
  assert.ok(card.querySelector('.vp-daily-q').textContent.split(/\s+/).length>=14);
  const pool=JSON.parse(readFileSync(new URL('data/daily.json',DIST),'utf8'));
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
  assert.ok(doc.querySelector('#site-nav a[href="/games/"]'),'Games nav kept (owner 2026-10-06: Play became Games)');
  dom.window.close();
});

const page=(p)=>new JSDOM(readFileSync(new URL(''+p,DIST),'utf8'),{url:'https://viapatrum.org/'+p.replace(/index\.html$/,'')}).window.document;

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
  const data=JSON.parse(readFileSync(new URL('data/explore-index.json',DIST),'utf8'));
  const withPoints=new Set(data.points.map(p=>p.topic));
  const cards=doc.querySelectorAll('.ot-card:not(.ot-belief)');
  // W3-topics (2026-10-06): a topic whose page draws no timeline (too few
  // writers) gets no card; it is listed as a plain link below the cards.
  for(const t of data.topics.filter(t=>withPoints.has(t.id))){
    assert.ok(doc.getElementById(t.id)?.matches('.ot-card')||doc.querySelector(`a[href="/topics/${t.id}/"]`),'no card or link for '+t.id);
  }
  assert.ok(cards.length>=20,'expected most topics to have a card, got '+cards.length);
  for(const c of cards){
    assert.ok(c.querySelector('.tl-lane'),'mini timeline in '+c.id);
    assert.match(c.querySelector('h3 a').getAttribute('href'),/^\/topics\/[a-z0-9-]+\/#over-time$/);
  }
  assert.ok(!doc.querySelector('script[src*="explore.js"]'),'old chart script retired');
});

test('beliefs live on the Timeline: a card per dividing question, no Beliefs tab (owner 2026-10-05)', ()=>{
  const doc=page('explore/index.html');
  const qs=JSON.parse(readFileSync(new URL('../data/explore/doctrine_map.json',import.meta.url),'utf8')).questions;
  const cards=doc.querySelectorAll('.ot-card.ot-belief');
  assert.equal(cards.length,qs.length);
  for(const c of cards){
    assert.equal(c.querySelector('h3 a').getAttribute('href'),'/explore/'+c.id+'/');
    assert.match(readFileSync(new URL('explore/'+c.id+'/index.html',DIST),'utf8'),/class="tl tl-pos[" ]/,'lanes on '+c.id);
  }
  assert.ok(!doc.querySelector('a[href^="/beliefs"]'),'no Beliefs link');
  assert.match(readFileSync(new URL('_redirects',DIST),'utf8'),/^\/beliefs\/:id\/ \/explore\/:id\/ 301$/m);
});

test('favicon files ship in dist', ()=>{
  assert.ok(readFileSync(new URL('favicon.ico',DIST)).length>100);
  assert.match(readFileSync(new URL('assets/favicon.svg',DIST),'utf8'),/<svg/);
});

test('link hover system ships in built CSS', ()=>{
  const css=readFileSync(new URL('assets/site.css',DIST),'utf8');
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

test('library pass: /downloads/ and Keep this book link only uploaded files (owner 2026-10-05)', ()=>{
  let names;
  try { names=JSON.parse(readFileSync(new URL('data/library-files.json',DIST),'utf8')); } catch { return; } // no uploads yet: page not built
  const keys=Object.keys(names);
  assert.ok(keys.length>0,'library-files.json lists uploaded files');
  const doc=page('downloads/index.html');
  const links=[...doc.querySelectorAll('a.dl-f, a.dl-b, a.keep-f')].map(a=>a.getAttribute('href'));
  assert.ok(links.length>0);
  for(const h of links){ assert.match(h,/^\/dl\//); assert.ok(names[h.slice(4)],'linked file is uploaded: '+h); }
  assert.match(doc.querySelector('[data-buy]')?.getAttribute('href')||'',/^https:\/\/saneapps\.lemonsqueezy\.com\/checkout\/buy\//);
  assert.ok(doc.querySelector('script[src^="/assets/downloads.js"]'));
  assert.match(readFileSync(new URL('./generate_works_gate.py',import.meta.url),'utf8'),/"\/dl\/\*"/,'/dl/* is routed to functions');
});

test('scripture: only real chapters get pages; Greek Psalm numbers are refiled (audit 2026-10-06)', async ()=>{
  const { readdirSync, existsSync } = await import('node:fs');
  const { gunzipSync } = await import('node:zlib');
  const bsb=JSON.parse(gunzipSync(readFileSync(new URL('../data/bibles/bsb.json.gz',import.meta.url))).toString('utf8'));
  const slug=(b)=>(b==='Psalm'?'Psalms':b).toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
  const count={}; for(const [b,cs] of Object.entries(bsb.books)) count[slug(b)]=Object.keys(cs).length;
  const extra=new Set(['daniel/13','daniel/14','psalms/151']);
  const root=new URL('scripture/',DIST);
  const over=[];
  for(const b of readdirSync(root)){ if(!count[b]) continue;
    for(const n of readdirSync(new URL(b+'/',root))) if(/^\d+$/.test(n)&&+n>count[b]&&!extra.has(b+'/'+n)) over.push(b+'/'+n); }
  assert.deepEqual(over,[],'no chapter page past the BSB count');
  const sm=readFileSync(new URL('sitemap-scripture.xml',DIST),'utf8');
  const bad=[...sm.matchAll(/\/scripture\/([^/]+)\/(\d+)\//g)].filter(m=>count[m[1]]&&+m[2]>count[m[1]]&&!extra.has(m[1]+'/'+m[2]));
  assert.equal(bad.length,0,'sitemap has no missing chapters');
  const desk=(p)=>[...page(p).querySelectorAll('.sc-list li')].map(li=>li.textContent);
  const ashamed=(t)=>/Fragments on the Psalms §216/.test(t)&&/not be ashamed/.test(t);
  assert.ok(!desk('scripture/psalms/118/index.html').some(ashamed),'Didymus on Greek Psalm 118:6 left our Psalm 118');
  assert.ok(desk('scripture/psalms/119/index.html').some(ashamed),'and sits on Psalm 119');
  assert.ok(desk('scripture/psalms/22/index.html').some(t=>/Against Marcion 3\.19/.test(t)),'Tertullian on Psalm 22');
  assert.ok(desk('scripture/psalms/110/index.html').some(t=>/Divine Institutes 4\.14/.test(t)),'Lactantius on Psalm 110');
  // A cite with no verse moves chapter only: it stays "on the chapter as a whole".
  const sec=(p,sel)=>[...page(p).querySelectorAll(sel+' .sc-list li')].map(li=>li.textContent);
  assert.ok(sec('scripture/psalms/22/index.html','.desk-home').some(t=>/Against Marcion 3\.19/.test(t)),'Tertullian 3.19 on Psalm 22 as a whole');
  assert.ok(sec('scripture/psalms/110/index.html','.desk-home').some(t=>/Divine Institutes 4\.14/.test(t)),'Lactantius 4.14 on Psalm 110 as a whole');
  // Greek verse numbers count the title: Greek 17:40 is our 18:39.
  assert.ok(sec('scripture/psalms/18/index.html','.desk-verse[data-for="39"]').some(t=>/shackled all who rise up/.test(t)),'Greek 17:40 on our 18:39');
  // Greek 115:1 is our 116:10, so Greek 115:2 is our 116:11.
  assert.ok(sec('scripture/psalms/116/index.html','.desk-verse[data-for="11"]').some(t=>/empty and a vapor/.test(t)),'Greek 115:2 on our 116:11');
  // "LXX/Vulgate Psalms 13:1" beside "Psalm 14:1" is the same verse: not listed on our Psalm 13.
  assert.ok(!desk('scripture/psalms/13/index.html').some(t=>/To Florus §3\.9/.test(t)),'LXX-labelled cite left our Psalm 13');
  assert.match(page('scripture/psalms/114/index.html').querySelector('.bx-psalm-note').textContent,/their Psalm\s114 is our Psalm\s116\b/);
  assert.match(page('scripture/psalms/113/index.html').querySelector('.bx-psalm-note').textContent,/their Psalm\s113 is our Psalms\s114 and 115\b/);
  assert.ok(!/numbered differently/.test(page('scripture/daniel/13/index.html').body.textContent),'Susanna is not "numbered differently"');
  assert.ok(existsSync(new URL('scripture/daniel/13/index.html',DIST)),'Susanna keeps its page');
});

test('authors: dates on every row but known gaps, no "0 passages", Augustine on the standard hub (audit 2026-10-06)', ()=>{
  const doc=page('authors/index.html');
  const rows=[...doc.querySelectorAll('.card-list > li > a')];
  // Georgius Peccator waits for dating research (his hymn is also counted as Synesius' Hymn 10).
  const undated=rows.filter(a=>!a.querySelector('.author-dates')).map(a=>a.getAttribute('href'));
  assert.deepEqual(undated.filter(h=>h!=='/authors/georgius-peccator/'),[]);
  assert.ok(!rows.some(a=>/\b0 (passages|works)\b/.test(a.textContent)));
  const aug=page('authors/augustine-of-hippo/index.html');
  assert.ok(aug.querySelector('.fa-head .author-dates'),'Augustine hub shows dates');
  assert.ok(aug.querySelector('.fa-head .fa-bio'),'and the bio');
  assert.ok(!/Explore/.test(aug.body.textContent),'no leftover Explore wording');
  // A letter is not a person: no "fl.", and the hub copy reads as a text.
  const dio=page('authors/mathetes-epistle-to-diognetus/index.html');
  assert.doesNotMatch(dio.querySelector('.fa-head .author-dates')?.textContent||'',/\bfl\./);
  assert.ok(!/What Letter to Diognetus said/.test(dio.body.textContent));
});

// ---- S-search (sketch 1): results first, Matching works by title ----
const doc=(dom)=>dom.window.document;
const tpl=()=>{const d=new JSDOM(catalog);return [...d.window.document.querySelector('#works-by-title').content.querySelectorAll('li.title-entry')];};
test('search blocks run Matching works, By meaning, Passages, Writers',()=>{
  const d=new JSDOM(catalog).window.document;
  const ids=['#works-status','#title-hits','#meaning-hits','#passage-hits','#writers-h','#works-list'].map(s=>d.querySelector(s));
  assert.ok(ids.every(Boolean));
  for(let i=1;i<ids.length;i++) assert.ok(ids[i-1].compareDocumentPosition(ids[i])&4,'order at '+i);
  assert.equal(d.querySelector('#passage-hits h2').textContent,'Passages');
  assert.equal(d.querySelector('#title-hits h2').textContent,'Matching works');
});
test('a work title search lists that work once, first, linking to the reader',async()=>{
  const li=tpl().find(l=>/Witch of Endor/i.test(l.textContent))||tpl()[0];
  const title=li.querySelector('.work-title').textContent;
  const dom=mount(catalog);await settle();
  query(dom,title);await settle();await settle();
  const rows=[...doc(dom).querySelectorAll('#title-results a')];
  assert.ok(rows.length>=1);
  assert.equal(rows[0].getAttribute('href'),li.querySelector('a').getAttribute('href'));
  assert.equal(rows.filter(a=>a.getAttribute('href')===rows[0].getAttribute('href')).length,1);
  assert.equal(doc(dom).querySelector('#title-hits').hidden,false);
  assert.match(doc(dom).querySelector('#works-status').textContent,/^\d+ works? (and \d+ passages? )?match(es)? “/);
  dom.window.close();
});
test('status drops the zero part and the Writers heading follows writer matches',async()=>{
  const dom=mount(catalog);await settle();
  assert.equal(doc(dom).querySelector('#writers-h').hidden,true);
  const author=doc(dom).querySelector('#works-list > li.author-entry').getAttribute('data-author');
  query(dom,author);await settle();await settle();
  assert.equal(doc(dom).querySelector('#writers-h').hidden,false);
  query(dom,'zzzznonexistent');await settle();await settle();
  assert.equal(doc(dom).querySelector('#writers-h').hidden,true);
  assert.equal(doc(dom).querySelector('#title-hits').hidden,true);
  assert.match(doc(dom).querySelector('#works-status').textContent,/^No works or passages match/);
  assert.equal(doc(dom).querySelector('#works-empty').hidden,false);
  dom.window.close();
});
test('Matching works caps at 20 with Show all N works',async()=>{
  const dom=mount(catalog);await settle();
  query(dom,'the');await settle();await settle();
  const more=doc(dom).querySelector('#title-more');
  assert.equal(doc(dom).querySelectorAll('#title-results > li').length,20);
  assert.equal(more.hidden,false);
  const n=Number(more.textContent.match(/\d+/)[0]);assert.ok(n>20);
  assert.match(doc(dom).querySelector('#works-status').textContent,new RegExp('^'+n+' works and [\\d,]+ passages match “the”'));
  more.click();
  assert.equal(doc(dom).querySelectorAll('#title-results > li').length,n);
  assert.equal(more.hidden,true);
  dom.window.close();
});
test('starting a search resets the era filter to All',async()=>{
  const dom=mount(catalog);await settle();
  const chip=[...doc(dom).querySelectorAll('[data-filter]')].find(b=>b.getAttribute('data-filter')!=='all'&&!b.hidden);
  chip.click();
  assert.equal(chip.getAttribute('aria-pressed'),'true');
  const author=[...doc(dom).querySelectorAll('#works-list > li.author-entry')].find(li=>!(li.getAttribute('data-era')||'').split(/\s+/).includes(chip.getAttribute('data-filter'))).getAttribute('data-author');
  query(dom,author);await settle();
  assert.equal(doc(dom).querySelector('[data-filter="all"]').getAttribute('aria-pressed'),'true');
  assert.equal(chip.getAttribute('aria-pressed'),'false');
  assert.ok(doc(dom).querySelectorAll('#works-list > li.author-entry:not([hidden])').length>0);
  dom.window.close();
});
