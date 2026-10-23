// Human check before downloads: functions/_lib/human.js, /api/human and the
// /dl/ gate. fetch is mocked; no network.
// Run: node --test scripts/human_check.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { humanCookies, isHuman, network, HUMAN_TTL_S, SITEKEY } from '../functions/_lib/human.js';
import { onRequestPost as human } from '../functions/api/human.js';
import { onRequest as dl } from '../functions/dl/[[path]].js';

const ENV = { TURNSTILE_SECRET: 'test-turnstile-secret' };
const SHELF = { 'epub/a.epub': 'A.epub' };

const reply = (status, body) => new Response(JSON.stringify(body), { status });

const IP = '203.0.113.7';
const at = (ip = IP) => new Request('https://viapatrum.org/', { headers: { 'cf-connecting-ip': ip } });

function dlContext(path, { cookie = '', method = 'GET', env = ENV, ip = IP } = {}) {
  const body = new Uint8Array([1, 2, 3]);
  const object = { size: 3, body, httpEtag: '"e"', writeHttpMetadata: () => {} };
  return {
    request: new Request(`https://viapatrum.org/dl/${path}`, { method, headers: { 'cf-connecting-ip': ip, ...(cookie ? { cookie } : {}) } }),
    params: { path: path.split('/') },
    env: { ...env, ASSETS: { fetch: async () => reply(200, SHELF) }, LIBRARY: { get: async () => object, head: async () => object } },
  };
}

const vph = async (env = ENV, now = Date.now(), ip = IP) => (await humanCookies(env, at(ip), now))[0].split(';')[0];

test('dl: a GET without the cookie gets the Turnstile box, not the file', async () => {
  const r = await dl(dlContext('epub/a.epub'));
  assert.equal(r.status, 403);
  assert.equal(r.headers.get('content-disposition'), null);
  assert.match(await r.text(), /cf-turnstile/);
});

test('dl: a GET with a fresh signed cookie gets the file', async () => {
  const r = await dl(dlContext('epub/a.epub', { cookie: await vph() }));
  assert.equal(r.status, 200);
  assert.match(r.headers.get('content-disposition'), /A\.epub/);
});

test('dl: HEAD stays open (size checks, link checkers)', async () => {
  const r = await dl(dlContext('epub/a.epub', { method: 'HEAD' }));
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('content-length'), '3');
});

test('dl: files not on the shelf are still 404 before any check', async () => {
  const r = await dl(dlContext('epub/gone.epub'));
  assert.equal(r.status, 404);
});

// Shelf and bucket edge cases (moved from the retired library_pass.test.mjs).
test('dl: an unreadable shelf map is a 503, not an open door', async () => {
  // Fresh module: the shelf map is cached per isolate once read.
  const { onRequest: fresh } = await import('../functions/dl/[[path]].js?v=no-shelf');
  const c = dlContext('epub/a.epub', { cookie: await vph() });
  c.env.ASSETS = { fetch: async () => reply(500, 'x') };
  assert.equal((await fresh(c)).status, 503);
});

test('dl: a listed key missing from the bucket says it is not ready', async () => {
  const c = dlContext('epub/a.epub', { cookie: await vph() });
  c.env.LIBRARY = { get: async () => null, head: async () => null };
  const r = await dl(c);
  assert.equal(r.status, 404);
  assert.match(await r.text(), /not ready yet/);
});

test('dl: a failed If-Match is 412 (the file changed); a failed If-None-Match is 304', async () => {
  const stale = { size: 3, httpEtag: '"e"', writeHttpMetadata: () => {} }; // R2: onlyIf failed, no body
  const ask = async (headers) => {
    const c = dlContext('epub/a.epub', { cookie: await vph() });
    c.request = new Request(c.request.url, { headers: { ...Object.fromEntries(c.request.headers), ...headers } });
    c.env.LIBRARY = { get: async () => stale, head: async () => stale };
    return (await dl(c)).status;
  };
  assert.equal(await ask({ 'if-match': '"old"' }), 412);
  assert.equal(await ask({ 'if-unmodified-since': 'Tue, 01 Oct 2026 00:00:00 GMT' }), 412);
  assert.equal(await ask({ 'if-none-match': '"e"' }), 304);
});

test('cookie: expired, forged, or signed with another secret is refused', async () => {
  const req = (c) => new Request('https://viapatrum.org/dl/x', { headers: { cookie: c, 'cf-connecting-ip': IP } });
  const old = await vph(ENV, Date.now() - (HUMAN_TTL_S + 5) * 1000);
  assert.equal(await isHuman(ENV, req(old)), false);
  const [exp] = (await vph()).slice(4).split('.');
  assert.equal(await isHuman(ENV, req(`vph=${exp}.AAAA`)), false);
  assert.equal(await isHuman(ENV, req(await vph({ TURNSTILE_SECRET: 'other' }))), false);
  const far = Math.floor(Date.now() / 1000) + 30 * 24 * 3600; // a far-future expiry is refused even if signed
  assert.equal(await isHuman(ENV, req(`vph=${far}.x`)), false);
  assert.equal(await isHuman(ENV, req(await vph())), true);
});

test('cookie: a copy used from another network is refused; the same /24 is fine', async () => {
  const c = await vph();
  assert.equal((await dl(dlContext('epub/a.epub', { cookie: c, ip: '198.51.100.9' }))).status, 403);
  assert.equal((await dl(dlContext('epub/a.epub', { cookie: c, ip: '203.0.113.200' }))).status, 200);
  assert.equal(network(at('2001:db8:abcd:12::1')), '2001:db8:abcd');
  assert.equal(network(at('2001:db8::1')), '2001:db8:0');
  assert.equal(network(new Request('https://x/')), '');
});

test('cookie: with no TURNSTILE_SECRET the check is off and files serve', async () => {
  const r = await dl(dlContext('epub/a.epub', { env: {} }));
  assert.equal(r.status, 200);
});

test('/api/human: a good token sets the HttpOnly cookie; a bad one does not', async () => {
  const sent = [];
  globalThis.fetch = async (url, init) => {
    sent.push(init.body.get('response'));
    return reply(200, { success: init.body.get('response') === 'good', hostname: 'viapatrum.org' });
  };
  const post = (token) => human({ request: new Request('https://viapatrum.org/api/human', { method: 'POST', headers: { 'cf-connecting-ip': IP }, body: JSON.stringify({ token }) }), env: ENV });
  const ok = await post('good');
  assert.equal(ok.status, 200);
  const cookies = ok.headers.getSetCookie();
  assert.ok(cookies.some((c) => c.startsWith('vph=') && /HttpOnly/.test(c) && /Secure/.test(c)));
  assert.ok(cookies.some((c) => c.startsWith('vph_ok=1')));
  const bad = await post('bad');
  assert.equal(bad.status, 403);
  assert.equal(bad.headers.get('set-cookie'), null);
  assert.deepEqual(sent, ['good', 'bad']);
});

test('/api/human: a pass for some other site is refused', async () => {
  globalThis.fetch = async () => reply(200, { success: true, hostname: 'evil.example' });
  const r = await human({ request: new Request('https://viapatrum.org/api/human', { method: 'POST', body: JSON.stringify({ token: 't' }) }), env: ENV });
  assert.equal(r.status, 403);
});

// --- /api/library/admin (upload route for library_sync.py) -------------------
test('admin: with LIBRARY_ADMIN_TOKEN set, only that token passes; list stays on shelf prefixes', async () => {
  const { onRequest: admin } = await import('../functions/api/library/admin.js');
  const TOKEN = 'a'.repeat(40);
  let outbound = 0;
  globalThis.fetch = async () => { outbound++; return reply(200, {}); };
  const listed = [];
  const env = { LIBRARY_ADMIN_TOKEN: TOKEN, LIBRARY: { list: async (o) => { listed.push(o.prefix); return { objects: [], truncated: false }; } } };
  const call = (headers, q = 'action=list&prefix=epub/') => admin({ request: new Request(`https://viapatrum.org/api/library/admin?${q}`, { headers }), env });
  assert.equal((await call({ 'x-cf-token': 'c'.repeat(40) })).status, 403, 'a Cloudflare token no longer passes');
  assert.equal(outbound, 0, 'no round trip to Cloudflare');
  assert.equal((await call({ 'x-admin-token': 'b'.repeat(40) })).status, 403);
  assert.equal((await call({ 'x-admin-token': TOKEN })).status, 200);
  assert.equal((await call({ 'x-admin-token': TOKEN }, 'action=list&prefix=')).status, 400, 'no empty prefix');
  assert.equal((await call({ 'x-admin-token': TOKEN }, 'action=list&prefix=ask-log/')).status, 400);
  assert.deepEqual(listed, ['epub/']);
});

test('the page script uses the same Turnstile site key as the server', () => {
  const page = readFileSync(new URL('../assets/human-check.js', import.meta.url), 'utf8');
  const m = page.match(/SITEKEY = "([^"]+)"/);
  assert.ok(m, 'assets/human-check.js names its SITEKEY');
  assert.equal(m[1], SITEKEY);
});
