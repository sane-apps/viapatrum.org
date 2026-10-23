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
const manifestText = readFileSync(new URL('data/search/manifest.json', DIST), 'utf8');
const manifest = JSON.parse(manifestText);
const shardText = new Map();
const index = [];
for (const shard of manifest.shards) {
  const name = String(shard.file || shard).split('/').pop();
  const text = readFileSync(new URL(`data/search/${name}`, DIST), 'utf8');
  shardText.set(`/data/search/${name}`, text);
  index.push(...JSON.parse(text));
}
// A fresh parse per fetch: the page deletes each row's text after it loads.
const site = async (u) => {
  const p = String(u).replace(/^https?:\/\/[^/]+/, '').split('?')[0];
  if (p === '/data/search/manifest.json') return { ok: true, json: async () => JSON.parse(manifestText) };
  if (shardText.has(p)) return { ok: true, json: async () => JSON.parse(shardText.get(p)) };
  if (p.startsWith('/data/words/')) {
    try { const t = readFileSync(new URL(p.slice(1), DIST), 'utf8'); return { ok: true, json: async () => JSON.parse(t) }; }
    catch { return { ok: false }; }
  }
  if (String(u).startsWith('/api/search')) return { ok: true, json: async () => ({ results: [] }) };
  return { ok: false };
};
const longPassage = index.find(r=>r.kind==='work'&&(r.text||'').length>600);
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
  const row=index.find(r=>r.kind==='work'&&(r.text||'').length>600);
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
test('phone Menu opens the primary nav; Escape and a tap outside close it (AGENTS rule 4)',()=>{
  const dom=mount(reader);const doc=dom.window.document;const toggle=doc.querySelector('.nav-toggle');
  const nav=doc.querySelector('#site-nav');
  assert.ok(nav);
  assert.ok(toggle);
  assert.equal(toggle.textContent.trim(),'Menu','labelled Menu, not a bare icon');
  assert.equal(toggle.getAttribute('aria-expanded')||'false','false');
  assert.ok(doc.querySelectorAll('#site-nav a').length>=5);
  const key=(k)=>doc.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:k,bubbles:true}));
  toggle.click();
  assert.ok(nav.classList.contains('is-open'));
  assert.equal(toggle.getAttribute('aria-expanded'),'true');
  nav.querySelector('a').focus();
  key('Escape');
  assert.ok(!nav.classList.contains('is-open'),'Escape closes the Menu');
  assert.equal(toggle.getAttribute('aria-expanded'),'false');
  assert.equal(doc.activeElement,toggle,'focus returns to Menu');
  toggle.click();
  assert.ok(nav.classList.contains('is-open'));
  nav.querySelector('a').addEventListener('click',(e)=>e.preventDefault());
  nav.querySelector('a').click();
  assert.ok(nav.classList.contains('is-open'),'a tap inside the Menu keeps it open');
  doc.querySelector('main, h1').click();
  assert.ok(!nav.classList.contains('is-open'),'a tap outside closes the Menu');
  assert.equal(toggle.getAttribute('aria-expanded'),'false');
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

test('author catalog loads the passage shards once',async()=>{
  const seen=[];
  let calls=0;
  const dom=mount(catalog,'/works/',async(u)=>{
    const p=String(u);
    seen.push(p);
    if(p.includes('/data/search/manifest.json'))calls++;
    return site(u);
  });
  await settle();query(dom,'numbering');await settle();assert.equal(calls,1);
  query(dom,'numbers');await settle();assert.equal(calls,1);
  assert.ok(!seen.some((u)=>u.includes('search-index.json')));
  dom.window.close();
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

test('home: favicon, today passage, deduped daily pool, one focus row, each link once', ()=>{
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
  // One focus (owner 2026-10-18): four cards under the Ask box, in this order.
  const focus=doc.querySelector('.vp-focus');
  assert.ok(focus,'focus row');
  assert.deepEqual([...focus.querySelectorAll(':scope > li > .k')].map(k=>k.textContent),['Listen','YouTube','App','Games'],'four cards in order');
  const fcard=(i)=>focus.querySelectorAll(':scope > li')[i];
  assert.deepEqual([...fcard(0).querySelectorAll('a')].map(a=>a.getAttribute('href')),['/listen/'],'Listen card has only its own link');
  assert.ok([...fcard(1).querySelectorAll('a')].every(a=>a.getAttribute('href').startsWith('https://www.youtube.com/')),'YouTube card');
  const yt=fcard(1).querySelector('a.yt-badge');
  assert.ok(yt && yt.querySelector('svg rect[fill="#FF0000"]') && yt.textContent.trim()==='YouTube','YouTube card has the red play mark and the YouTube label');
  assert.ok(fcard(2).querySelector('a.app-badge'),'App card keeps the badge');
  for(const sel of ['a[href="/listen/"]','a[href^="https://www.youtube.com/"]','a[href^="https://apps.apple.com/"]','a[href="https://play.viapatrum.org/daily"]','a[href="/games/"]'])
    assert.ok(focus.querySelector(sel),'first-screen link '+sel);
  assert.ok(!doc.querySelector('.vp-road, .vp-doors, .vp-chips, .vp-keep, .play-promo'),'old directory blocks gone');
  // Each destination once: nothing in the page body repeats itself or the menu.
  const norm=(h)=>h.replace(/^https:\/\/viapatrum\.org/,'').replace(/[?#].*$/,'');
  const body=[...doc.querySelectorAll('main a[href]')].map(a=>norm(a.getAttribute('href'))).filter(h=>!h.startsWith('#'));
  const dup=body.filter((h,i)=>body.indexOf(h)!==i);
  assert.deepEqual(dup,[],'repeated links in the home body');
  const nav=[...doc.querySelectorAll('#site-nav a[href]')].map(a=>norm(a.getAttribute('href')));
  assert.deepEqual(body.filter(h=>nav.includes(h)),[],'home body repeats the menu');
  assert.ok(!doc.querySelector('.header-tools .header-search')||doc.body.classList.contains('home'),'home hides the header search (Ask is the search)');
  // Ask hints: fixed accessible name, rotating hint list from real topics.
  const q=doc.querySelector('#home-q');
  assert.equal(q.getAttribute('aria-label'),'Ask what the Fathers said');
  const hints=JSON.parse(q.dataset.hints);
  assert.ok(hints.length>=5&&hints.every(h=>/^Ask about .+…$/.test(h)),'hints');
  assert.equal(q.getAttribute('placeholder'),hints[0]);
  dom.window.close();
  // Other pages keep the full menu.
  const works=page('works/index.html');
  for(const k of ['listen','games']) assert.ok(works.querySelector(`#site-nav a[href="/${k}/"]`),k+' in the menu off the home page');
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

test('where the churches stand: one answer list per dividing question, no topic cards (redesign 2026-10-14)', ()=>{
  // Owner-approved redesign: the dividing questions only, as answer lists; the topic
  // over-time timelines live on each topic page (#over-time).
  const doc=page('explore/churches/index.html');
  assert.equal(doc.querySelector('h1').textContent,'Where the churches stand');
  assert.equal(doc.querySelectorAll('.ot-card').length,0,'no topic or lane cards');
  assert.equal(doc.querySelectorAll('.tl-lane, .tl-pos').length,0,'no lanes on the overview');
  const qs=JSON.parse(readFileSync(new URL('../data/explore/doctrine_questions.json',import.meta.url),'utf8'));
  const cards=doc.querySelectorAll('article.cq');
  assert.equal(cards.length,qs.length);
  for(const c of cards){
    const href=c.querySelector('h3 a').getAttribute('href');
    assert.ok(href==='/explore/'+c.id+'/'||href==='/explore/churches/'+c.id+'/',href);
    assert.match(readFileSync(new URL(href.slice(1)+'index.html',DIST),'utf8'),/class="bpositions"/,'positions on '+c.id);
    assert.ok(c.querySelectorAll('.cq-pos[data-trads]').length>=2,'answers on '+c.id);
    const early=c.querySelector('.cq-early a');
    if(early){
      const e=early.getAttribute('href');
      assert.match(readFileSync(new URL(e.slice(1)+'index.html',DIST),'utf8'),/class="answer-box"/,'early link to a Timeline question: '+e);
    }
  }
  assert.ok(doc.querySelectorAll('.cq-early a').length>=20,'most questions link to what the early Church said');
  assert.ok(!doc.querySelector('a[href^="/beliefs"]'),'no Beliefs link');
  assert.equal(doc.querySelector('a[href="/creeds/"]').textContent,'Creeds and churches');
  assert.match(readFileSync(new URL('_redirects',DIST),'utf8'),/^\/beliefs\/:id\/ \/explore\/:id\/ 301$/m);
});

test('beliefs: eleven church chips, four new questions, new churches filter (owner 2026-10-06)', ()=>{
  const want=['All','Catholic','Orthodox','Oriental Orthodox','Church of the East','Lutheran','Reformed','Anglican','Methodist','Baptist','Anabaptist','Pentecostal'];
  for(const f of ['explore/churches/index.html','explore/christ-natures/index.html']){
    const chips=[...page(f).querySelectorAll('.bfilter .bchip')];
    assert.deepEqual(chips.map(c=>c.textContent.trim()),want,'chip row on '+f);
    assert.equal(chips.filter(c=>c.getAttribute('aria-pressed')==='true').length,1);
  }
  const doc=page('explore/churches/index.html');
  for(const id of ['spiritual-gifts','sanctification','christ-natures','millennium']){
    const card=doc.getElementById(id);
    assert.ok(card?.matches('article.cq'),'question '+id);
    assert.equal(card.querySelector('h3 a').getAttribute('href'),'/explore/'+id+'/');
    const q=page('explore/'+id+'/index.html');
    assert.equal(q.querySelectorAll('.bpos[data-trads]').length,3,'three positions on '+id);
  }
  // A new church is placed and a divided one is named in a note line.
  const cn=page('explore/christ-natures/index.html');
  assert.ok(cn.querySelector('.bpos[data-trads~="oriental-orthodox"]'));
  assert.ok(cn.querySelector('.bpos[data-trads~="church-of-the-east"]'));
  assert.match(cn.querySelector('.bnotes').textContent,/Coptic and Ethiopian/);
  const ep=page('explore/churches/eucharist-presence/index.html');
  assert.ok(ep.querySelector('.tl-row[data-trads~="methodist"]'),'a question with enough passages keeps its chart');
  assert.match(ep.querySelector('.bnotes').textContent,/Anabaptist:\s*Divided\./);
  assert.equal(ep.querySelector('a[data-tl]').getAttribute('href'),'/explore/eucharist-presence/','early link not moved');
});

test('timeline: 100 reader questions, static pages with quotes and the chart (owner 2026-10-13)', ()=>{
  const doc=page('explore/index.html');
  assert.equal(doc.querySelector('.tl h1').textContent,'Ask the early Church');
  const links=[...doc.querySelectorAll('.tl .group li > a')];
  assert.equal(links.length,100,'every question links to its page');
  assert.ok(doc.querySelector('#q[type="search"]'));
  assert.equal(doc.querySelector('a[href="/explore/churches/"]').textContent,'Where the churches stand');
  const s=JSON.parse(readFileSync(new URL('data/timeline-search.json',DIST),'utf8'));
  assert.equal(s.questions.length,100); assert.ok(s.quotes.length>500);
  const q=page('explore/infant-baptism/index.html');
  assert.equal(q.querySelector('.tl h1').textContent,'Did the early Church baptize infants?');
  assert.ok(q.querySelectorAll('.tl .card blockquote.q').length>=10,'quotes are in the HTML, not drawn by script');
  assert.ok(q.querySelector('.tl .card .orig[hidden]'),'original text is in the page');
  assert.ok(q.querySelector('#tl-data'));
  assert.ok(q.querySelector('a[href="/explore/baptism-subjects/"]'),'links to where each church stands');
  const ep=page('explore/eucharist-presence/index.html');
  assert.ok(ep.querySelector('.tl .answer-box'),'question page took the shared id');
  assert.ok(ep.querySelector('a[href="/explore/churches/eucharist-presence/"]'));
  assert.match(readFileSync(new URL('explore/churches/index.html',DIST),'utf8'),/<h1>Where the churches stand<\/h1>/);
});

test('creeds and churches page: timeline, eleven cards, reviewed dates (owner 2026-10-06)', ()=>{
  const doc=page('creeds/index.html');
  assert.equal(doc.querySelector('h1').textContent,'Creeds and churches');
  assert.equal(doc.querySelectorAll('.ch-card').length,11);
  assert.ok(doc.querySelector('link[href^="/assets/creeds.css"]'));
  assert.match(doc.querySelector('#c-filioque').textContent,/Lateran IV \(1215\).*Lyon II \(1274\).*Florence \(1439\)/s);
  assert.match(doc.querySelector('#k-methodist').textContent,/1784/);
  assert.equal(doc.querySelectorAll('#site-nav a[href="/creeds/"]').length,0,'creeds stays under Timeline, not a nav item');
  assert.equal(doc.querySelector('.crumbs a[href="/explore/"]').textContent,'Timeline');
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

test('free library: /downloads/ and Keep this book link only uploaded files (owner 2026-10-22)', ()=>{
  let names;
  try { names=JSON.parse(readFileSync(new URL('data/library-files.json',DIST),'utf8')); } catch { return; } // no uploads yet: page not built
  const keys=Object.keys(names);
  assert.ok(keys.length>0,'library-files.json lists uploaded files');
  const doc=page('downloads/index.html');
  const links=[...doc.querySelectorAll('a.dl-f, a.dl-b, a.keep-f')].map(a=>a.getAttribute('href'));
  assert.ok(links.length>0);
  for(const h of links){ assert.match(h,/^\/dl\//); assert.ok(names[h.slice(4)],'linked file is uploaded: '+h); }
  assert.equal(doc.querySelector('[data-buy], .lemonsqueezy-button, [data-open-key]'),null,'no checkout or key entry');
  assert.ok(!/\$\d/.test(doc.querySelector('.dl-hero').textContent),'no price on the free shelf');
  assert.ok(doc.querySelector('script[src^="/assets/downloads.js"]'));
  assert.match(readFileSync(new URL('./generate_works_gate.py',import.meta.url),'utf8'),/"\/dl\/\*"/,'/dl/* is routed to functions');
});

test('scripture: no gift link beside licensed Bible text; YouVersion versions are wired (2026-10-22)', ()=>{
  const doc=page('scripture/john/3/index.html');
  assert.equal(doc.querySelector('a[href*="sponsors"]'),null,'no Sponsors link on a Scripture page');
  assert.ok(page('about/index.html').querySelector('a[href*="sponsors"]'),'other pages keep the Sponsors link');
  const tools=doc.querySelector('.bx-tools[data-yv-key]');
  if(!tools) return; // built without the YouVersion key
  assert.ok(doc.querySelector('button[data-tr="niv"][data-yv="111"]'),'NIV from YouVersion');
  assert.equal(doc.querySelector('button[data-tr="niv"][data-remote]'),null,'NIV no longer from bolls.life');
  assert.equal(doc.querySelector('.bx-text').dataset.usfm,'JHN');
  const opts=[...doc.querySelectorAll('[data-tr-more] option[data-yv]')].map(o=>o.textContent);
  assert.ok(opts.includes('NASB 1995')&&!opts.some(o=>/TPT|Passion/.test(o)),'More menu: established versions only');
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
  assert.ok(sec('scripture/psalms/116/index.html','.desk-verse[data-for="11"]').some(t=>/empty and a falsehood/.test(t)),'Greek 115:2 on our 116:11');
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
  // By meaning answers after a 600 ms pause (site.js): wait it out.
  query(dom,'zzzznonexistent');await settle();await settle();await settle();
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

test('ask: /ask/ page, home hero asks there, answer/thin/error states (owner 2026-10-06)', async ()=>{
  const home=page('index.html');
  const form=home.querySelector('.vp-hero form.vp-ask');
  assert.equal(form.getAttribute('action'),'/ask/','home hero search goes to Ask');
  assert.equal(form.querySelector('input').getAttribute('name'),'q');
  const html=readFileSync(new URL('ask/index.html',DIST),'utf8');
  const doc=new JSDOM(html).window.document;
  assert.equal(doc.querySelector('h1').textContent,'Ask the Fathers');
  assert.ok(doc.querySelector('label[for="ask-q"]'),'labelled input');
  assert.equal(doc.querySelector('#ask-status').getAttribute('aria-live'),'polite');
  assert.ok(doc.querySelector('script[src^="/assets/ask.js"]')&&doc.querySelector('link[href^="/assets/ask.css"]'));
  assert.ok(doc.querySelectorAll('.ask-try a[href^="/ask/?q="]').length>=3,'example questions');
  const askJs=readFileSync(new URL('assets/ask.js',DIST),'utf8');
  const answer={query:'baptism',mode:'answer',passages:[
    {title:'First Apology 61',author:'Justin Martyr',href:'/e/j61/',kind:'excerpt',score:0.9,snippet:'Then we lead them'},
    {title:'Didache 7',author:'The Didache',href:'/e/d7/',kind:'excerpt',score:0.8,snippet:'Concerning baptism'}],
    answer:[{text:'Then we lead them to where there is water.',author:'Justin Martyr',author_dates:'c. 100–c. 165 AD',title:'First Apology 61',cite:'First Apology 61',href:'/e/j61/',year:165,ref:1,score:0.9},
      {text:'Concerning baptism, baptize in this way.',author:'Augustine of Hippo',author_dates:'354–430 AD',title:'x',cite:'Letters §5',href:'/works/aug/5/',year:430,ref:2,score:0.95}]};
  const thin={query:'internet',mode:'thin',answer:[],note:'Our library does not cover this well yet. These are the closest passages; more works are being translated.',passages:answer.passages};
  const open=async(q,reply)=>{
    const dom=new JSDOM(html,{url:'https://viapatrum.org/ask/?q='+encodeURIComponent(q),runScripts:'outside-only',pretendToBeVisual:true});
    dom.window.fetch=async(u)=>{ assert.match(String(u),/^\/api\/ask\?q=/); return reply(); };
    dom.window.eval(askJs); await settle(); return dom;
  };
  let dom=await open('baptism',()=>({ok:true,json:async()=>answer}));
  let d=dom.window.document;
  assert.equal(d.querySelectorAll('.ask-quotes > li').length,2);
  assert.match(d.querySelector('.ask-from').textContent,/From 2 passages, c\. 165–430 AD/);
  const cite=d.querySelector('.ask-cite a');
  assert.equal(cite.getAttribute('href'),'/e/j61/');
  assert.equal(cite.textContent,'Justin Martyr (c. 100–c. 165 AD), First Apology 61');
  assert.equal(d.querySelector('.ask-ref').getAttribute('href'),'#ask-p-1');
  assert.ok(d.querySelector('#ask-p-2 a[href="/e/d7/"]'),'numbered passage rows');
  assert.ok(d.querySelector('a[href="/works/?q=baptism"]'),'see every match');
  assert.match(d.querySelector('#ask-status').textContent,/Answer ready/);
  dom.window.close();
  dom=await open('internet',()=>({ok:true,json:async()=>thin}));
  d=dom.window.document;
  assert.ok(!d.querySelector('.ask-answer'),'no answer block when thin');
  assert.match(d.querySelector('.ask-thin').textContent,/does not cover this well yet/);
  assert.equal(d.querySelectorAll('.ask-plist > li').length,2);
  dom.window.close();
  dom=await open('grace',()=>({ok:false,status:502,json:async()=>({error:'x'})}));
  d=dom.window.document;
  assert.ok(d.querySelector('.ask-error a[href="/works/?q=grace"]'),'API down: fall back to the library search');
  assert.doesNotMatch(d.querySelector('.ask-note').textContent,/paused/);
  dom.window.close();
  dom=await open('grace',()=>({ok:false,status:503,json:async()=>({error:'Search by meaning is paused',paused:true})}));
  d=dom.window.document;
  assert.match(d.querySelector('.ask-note').textContent,/Ask is paused for now/,'AI_OFF: says paused, not broken');
  assert.ok(d.querySelector('.ask-error a[href="/works/?q=grace"]'),'paused: still links the library search');
  dom.window.close();
});

// One-word searches read data/words (build_site.write_search_words), not the
// text shards. Count and first 40 hits must equal a scan of the shards.
test('word index finds what a text scan finds, without the text shards', async () => {
  if (!manifest.words) return;
  const lc = (r) => `${r.title || ''} ${r.author || ''} ${r.text || ''}`.toLowerCase();
  for (const term of ['grace', 'baptism', 'logos', 'theotokos', '100', 'zzzzq']) {
    const seen = [];
    const dom = mount(catalog, '/works/', async (u) => { seen.push(String(u)); return site(u); });
    query(dom, term);
    for (let i = 0; i < 20 && /Searching/.test(dom.window.document.querySelector('#works-status').textContent); i++) await settle();
    const want = index.filter((r) => lc(r).includes(term));
    const status = dom.window.document.querySelector('#works-status').textContent;
    const m = status.match(/([\d,]+) passages? match/);
    assert.equal(m ? Number(m[1].replace(/,/g, '')) : 0, want.length, `${term}: ${status}`);
    const hrefs = [...dom.window.document.querySelectorAll('#passage-results a')].map((a) => a.getAttribute('href'));
    assert.deepEqual(hrefs, want.slice(0, 40).map((r) => r.href), term);
    assert.ok(!seen.some((u) => /\/data\/search\/\d/.test(u)), `${term} fetched a text shard`);
    dom.window.close();
  }
});

// Fixture mirrors scripture_verse_html + the desk in build_site.py (scripture_a11y_test.py checks that side).
const bxFixture = `<!doctype html><html><body><main><div class="bx" data-bx><div class="bx-grid">
<div class="bx-text" data-book="isaiah" data-chap="1"><p>
<span class="v cited" id="v1" data-v="1" style="--heat:1"><sup>1</sup><span class="vt">This is the vision.</span><button type="button" class="v-open vh" data-v="1" aria-controls="desk">Verse 1: 2 passages in the Fathers</button></span>
<span class="v" id="v2" data-v="2"><sup>2</sup><span class="vt">Listen, O heavens.</span></span>
</p></div>
<aside class="bx-desk" id="desk" aria-label="What the Fathers said">
<p class="vh" role="status" id="desk-status"></p>
<button type="button" class="desk-close" aria-label="Close">×</button>
<section class="desk-home" data-for="chapter"><h2>Isaiah 1</h2>
<ul class="desk-bars"><li><button type="button" class="desk-jump" data-v="1"><span class="ref">Isaiah 1:1</span><span class="bar"></span><span class="n">2<span class="vh"> passages</span></span></button></li></ul></section>
<section class="desk-verse" data-for="1" hidden><h2>Isaiah 1:1</h2><p class="desk-count">2 passages in the Fathers, earliest first</p>
<button type="button" class="desk-back">Back to the chapter</button></section>
</aside></div></div></main></body></html>`;

test('scripture: verse text stays readable; the opener is a real button; closing the desk returns focus (a11y 2026-10-23)', ()=>{
  const dom=mount(bxFixture,'/scripture/isaiah/1/');const w=dom.window;const doc=w.document;
  const verse=doc.querySelector('.v.cited');
  assert.equal(verse.getAttribute('role'),null,'no role=button hiding the verse text');
  assert.equal(verse.getAttribute('aria-label'),null,'no aria-label replacing the verse text');
  assert.equal(doc.querySelector('.bx-desk').getAttribute('aria-live'),null,'the desk is not one big live region');
  const open=verse.querySelector('button.v-open');
  open.focus();open.click();
  const sec=doc.querySelector('.desk-verse[data-for="1"]');
  assert.equal(sec.hidden,false);
  assert.equal(doc.activeElement,sec.querySelector('h2'),'keyboard open moves focus to the verse heading');
  sec.querySelector('.desk-back').click();
  assert.equal(sec.hidden,true);
  assert.equal(doc.activeElement,open,'Back to the chapter returns focus to the verse');
  open.click();
  doc.activeElement.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  assert.equal(sec.hidden,true);
  assert.equal(doc.activeElement,open,'Escape returns focus to the verse');
  verse.querySelector('.vt').click();
  assert.equal(sec.hidden,false,'a mouse click on the verse still opens the desk');
  assert.equal(doc.querySelector('#desk-status').textContent,'Isaiah 1:1, 2 passages in the Fathers, earliest first','one short status line when focus stays put');
  doc.querySelector('.desk-close').click();
  w.Element.prototype.scrollIntoView = () => {}; // the jump path scrolls; jsdom has no layout
  const jump=doc.querySelector('.desk-jump');
  jump.focus();jump.click();
  assert.equal(sec.hidden,false);
  assert.equal(doc.activeElement,sec.querySelector('h2'),'a Most cited jump hides its own list, so focus moves to the verse heading');
  doc.querySelector('.desk-close').click();
  assert.equal(doc.activeElement,open,'closing after a jump returns focus to the verse');
  assert.equal(doc.querySelector('#desk-status').textContent,'');
  w.history.replaceState(null,'','#v1');w.dispatchEvent(new w.HashChangeEvent('hashchange'));
  assert.equal(sec.hidden,false,'a #v link opens the desk');
  assert.equal(doc.querySelector('#desk-status').textContent,'','opening from the address bar says nothing extra');
  doc.querySelector('.desk-close').click();
  assert.match(doc.querySelector('.desk-jump').textContent,/2 passages$/,'the count says what it counts');
  dom.window.close();
});

test('home: a quote that opens or ends with its own quote mark gets no second one (a11y 2026-10-23)', async ()=>{
  const html=`<!doctype html><html><body><div class="vp-today-card" data-daily>
<blockquote class="vp-quote"><p><span class="vp-qm">&ldquo;</span><span class="vp-daily-q">x</span><span class="vp-qm">&rdquo;</span></p></blockquote>
<div class="vp-sc" data-daily-sc><blockquote class="vp-quote vp-sc-q"><p><span class="vp-qm">&ldquo;</span><span class="vp-sc-v">y</span><span class="vp-qm">&rdquo;</span></p></blockquote>
<span class="vp-sc-r"></span><span class="vp-sc-ch"></span><a class="vp-sc-h" href="/scripture/"></a></div></div></body></html>`;
  const row={q:'Plain words of a Father.',a:'A',d:'d',c:'c',h:'/e/x/',t:'t',th:'/topics/t/',sv:'\u201cWhat good to Me is your multitude of sacrifices?',sr:'Isaiah 1:11',sch:'Isaiah 1',sh:'/scripture/isaiah/1/#v11'};
  const rows=Array.from({length:7},()=>row);
  const dom=mount(html,'/',async()=>({ok:true,json:async()=>rows}));
  await settle();
  const doc=dom.window.document;
  const marks=(sel)=>[...doc.querySelector(sel).parentElement.querySelectorAll('.vp-qm')].map(m=>m.hidden);
  assert.equal(doc.querySelector('.vp-sc-v').textContent,row.sv);
  assert.deepEqual(marks('.vp-sc-v'),[true,true],'verse with its own opening quote: outer marks hidden');
  assert.deepEqual(marks('.vp-daily-q'),[false,false],'plain passage keeps its marks');
  dom.window.close();
  const closing={...row,q:'And He said, \u201cDo this in remembrance of Me.\u201d',sv:'It is written: \u201cAs surely as I live.\u201d'};
  const dom2=mount(html,'/',async()=>({ok:true,json:async()=>Array.from({length:7},()=>closing)}));
  await settle();
  const doc2=dom2.window.document;
  const marks2=(sel)=>[...doc2.querySelector(sel).parentElement.querySelectorAll('.vp-qm')].map(m=>m.hidden);
  assert.deepEqual(marks2('.vp-daily-q'),[true,true],'passage that ends with its own closing quote: outer marks hidden');
  assert.deepEqual(marks2('.vp-sc-v'),[true,true],'verse that ends with its own closing quote: outer marks hidden');
  dom2.window.close();
});
