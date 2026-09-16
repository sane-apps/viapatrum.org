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
test('failed passage index reports error and Retry recovers',async()=>{
  let calls=0;
  const dom=mount(catalog,'/works/?q='+encodeURIComponent(searchPhrase),async()=> ++calls===1?{ok:false}:{ok:true,json:async()=>index});
  await settle();
  assert.match(dom.window.document.querySelector('#passage-results').textContent,/could not load/);
  dom.window.document.querySelector('.search-retry').click();await settle();
  assert.ok(dom.window.document.querySelector('#passage-results a'));
  dom.window.close();
});
test('invalid filters fall back to All and empty searches explain recovery',async()=>{
  const dom=mount(catalog,'/works/?filter=invalid');await settle();
  assert.equal(dom.window.document.querySelector('[data-filter="all"]').getAttribute('aria-pressed'),'true');
  query(dom,'zzzznonexistent');await settle();
  assert.equal(dom.window.document.querySelector('.search-empty').hidden,false);
  assert.match(dom.window.document.querySelector('#passage-results').textContent,/No matching passages/);
  dom.window.close();
});
test('mobile menu closes on Escape and returns focus',()=>{
  const dom=mount(reader);const doc=dom.window.document;const toggle=doc.querySelector('.nav-toggle');
  toggle.click();assert.equal(toggle.getAttribute('aria-expanded'),'true');
  doc.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape'}));
  assert.equal(toggle.getAttribute('aria-expanded'),'false');assert.equal(doc.activeElement,toggle);
  dom.window.close();
});
test('Contents links reopen a collapsed table of contents',()=>{
  const dom=mount(reader);const doc=dom.window.document;
  doc.querySelector('#contents').open=false;
  doc.querySelector('.reader-quick a').click();
  assert.equal(doc.querySelector('#contents').open,true);dom.window.close();
});

test('catalog browsing does not download the passage index until a search',async()=>{
  let calls=0;const dom=mount(catalog,'/works/',async()=>{calls++;return {ok:true,json:async()=>index};});
  await settle();assert.equal(calls,0);query(dom,'numbering');await settle();assert.equal(calls,1);dom.window.close();
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
