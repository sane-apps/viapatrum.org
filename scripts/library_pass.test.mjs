// Library pass Functions: the daily key recheck (functions/_lib/library.js)
// and the /dl gate (functions/dl/[[path]].js). fetch is mocked; no network.
// Run: node --test scripts/library_pass.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { session, sealCookie, validateKey, REVALIDATE_S, UNREACHABLE_GRACE_S, allowAttempt, UNLOCK_LIMIT, UNLOCK_WINDOW_MS } from '../functions/_lib/library.js';
import { onRequestPost as unlock } from '../functions/api/library/unlock.js';
import { onRequest as dl } from '../functions/dl/[[path]].js';

const ENV = { LIBRARY_SECRET: 'test-secret', LIBRARY_STORE_ID: '1', LIBRARY_PRODUCT_IDS: '4', LEMONSQUEEZY_API_KEY: 'k' };
const KEY = '38b1460a-5104-4067-a91d-77b872934d51';
const VALID = { valid: true, license_key: { status: 'active' }, meta: { store_id: 1, product_id: 4, order_id: 2 } };

function reply(status, body) {
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), { status });
}

// Route the two Lemon Squeezy calls: licence validate, then the order.
function store({ validate, order }) {
  const calls = [];
  globalThis.fetch = async (url) => {
    const u = String(url);
    calls.push(u);
    if (u.endsWith('/licenses/validate')) return typeof validate === 'function' ? validate() : validate;
    if (u.includes('/orders/')) return order || reply(200, { data: { attributes: { status: 'paid', refunded: false } } });
    throw new Error('unexpected fetch ' + u);
  };
  return calls;
}

async function staleCookie(age = REVALIDATE_S + 60) {
  const old = Math.floor(Date.now() / 1000) - age;
  const c = await sealCookie(ENV, { k: KEY, v: old, i: old });
  return new Request('https://viapatrum.org/api/library/status', { headers: { cookie: c.split(';')[0] } });
}

test('session: a valid key and a paid order stay unlocked and refresh the cookie', async () => {
  const calls = store({ validate: reply(200, VALID) });
  const s = await session(await staleCookie(), ENV);
  assert.equal(s.unlocked, true);
  assert.match(s.setCookie, /^vpl=/);
  assert.equal(calls.length, 2);
});

for (const [name, validate] of [
  ['429 rate limit', () => reply(429, { error: 'Too Many Attempts.' })],
  ['503', () => reply(503, 'busy')],
  ['408', () => reply(408, '')],
  ['a reply that is not JSON', () => reply(200, '<html>gateway</html>')],
  ['a network error', () => { throw new TypeError('fetch failed'); }],
]) {
  test(`session: ${name} keeps the cookie (the store gave no answer)`, async () => {
    store({ validate });
    const s = await session(await staleCookie(), ENV);
    assert.equal(s.unlocked, true);
    assert.equal(s.setCookie, undefined);
  });
}

test('session: an unreachable store keeps a pass only 7 days after its last good check', async () => {
  store({ validate: () => reply(429, {}) });
  const s = await session(await staleCookie(UNREACHABLE_GRACE_S + 60), ENV);
  assert.equal(s.unlocked, false);
  assert.match(s.setCookie, /Max-Age=0/);
  assert.match(s.reason, /Enter your key again/);
  store({ validate: () => reply(429, {}) });
  assert.equal((await session(await staleCookie(UNREACHABLE_GRACE_S - 3600), ENV)).unlocked, true);
});

test('session: a disabled key locks and clears the cookie', async () => {
  store({ validate: reply(200, { valid: false, license_key: { status: 'disabled' }, meta: {} }) });
  const s = await session(await staleCookie(), ENV);
  assert.equal(s.unlocked, false);
  assert.match(s.setCookie, /Max-Age=0/);
  assert.match(s.reason, /turned off/);
});

for (const status of ['refunded', 'fraudulent']) {
  test(`session: a ${status} order locks even while the key is still active`, async () => {
    store({ validate: reply(200, VALID), order: reply(200, { data: { attributes: { status, refunded: status === 'refunded' } } }) });
    const s = await session(await staleCookie(), ENV);
    assert.equal(s.unlocked, false);
    assert.match(s.setCookie, /Max-Age=0/);
  });
}

test('session: a partial refund keeps the pass', async () => {
  store({ validate: reply(200, VALID), order: reply(200, { data: { attributes: { status: 'partial_refund', refunded: false } } }) });
  assert.equal((await session(await staleCookie(), ENV)).unlocked, true);
});

test('session: no answer about the order is not a refusal', async () => {
  store({ validate: reply(200, VALID), order: reply(500, 'down') });
  assert.equal((await session(await staleCookie(), ENV)).unlocked, true);
});

test('validateKey: a test-mode key unlocks only with LIBRARY_ALLOW_TEST_KEYS=1', async () => {
  const testKey = { ...VALID, license_key: { status: 'active', test_mode: true } };
  store({ validate: reply(200, testKey) });
  assert.equal((await validateKey(ENV, KEY)).ok, false);
  store({ validate: reply(200, testKey) });
  assert.equal((await validateKey({ ...ENV, LIBRARY_ALLOW_TEST_KEYS: '1' }, KEY)).ok, true);
});

// --- /api/library/unlock ------------------------------------------------------

function unlockReq(key, ip) {
  return new Request('https://viapatrum.org/api/library/unlock', {
    method: 'POST', body: JSON.stringify({ key }), headers: { 'content-type': 'application/json', 'cf-connecting-ip': ip },
  });
}

test('unlock: an unreachable store never unlocks (503, no cookie)', async () => {
  store({ validate: () => reply(429, {}) });
  const r = await unlock({ request: unlockReq(KEY, '10.0.0.1'), env: ENV });
  assert.equal(r.status, 503);
  assert.equal(r.headers.get('set-cookie'), null);
  assert.equal((await r.json()).ok, false);
});

test('unlock: a key that is not a UUID is refused without calling the store', async () => {
  const calls = store({ validate: reply(200, VALID) });
  for (const junk of ['AAAAAAAA', 'x'.repeat(40), '38b1460a-5104-4067-a91d-77b872934d5Z']) {
    const r = await unlock({ request: unlockReq(junk, '10.0.0.2'), env: ENV });
    assert.equal((await r.json()).ok, false);
  }
  assert.equal(calls.length, 0);
});

test('unlock: a valid key unlocks', async () => {
  store({ validate: reply(200, VALID) });
  const r = await unlock({ request: unlockReq(KEY, '10.0.0.3'), env: ENV });
  assert.equal((await r.json()).ok, true);
  assert.match(r.headers.get('set-cookie'), /^vpl=/);
});

test('unlock: each address gets a limited number of tries per window', async () => {
  const calls = store({ validate: reply(200, { valid: false, meta: {} }) });
  let last;
  for (let i = 0; i <= UNLOCK_LIMIT; i++) last = await unlock({ request: unlockReq(KEY, '10.0.0.4'), env: ENV });
  assert.equal(last.status, 429);
  assert.equal(calls.length, UNLOCK_LIMIT);
  const t = Date.now() + UNLOCK_WINDOW_MS + 1;
  assert.equal(allowAttempt('10.0.0.4', t), true);
});

// --- /dl ---------------------------------------------------------------------

function dlContext(path, { shelf, cookie = '', object = null } = {}) {
  const url = `https://viapatrum.org/dl/${path}`;
  return {
    request: new Request(url, { headers: cookie ? { cookie } : {} }),
    params: { path: path.split('/') },
    env: {
      ...ENV,
      ASSETS: { fetch: async () => (shelf === undefined ? reply(500, 'x') : reply(200, shelf)) },
      LIBRARY: {
        get: async () => object,
        head: async () => object,
      },
    },
  };
}

async function freshCookie() {
  const now = Math.floor(Date.now() / 1000);
  return (await sealCookie(ENV, { k: KEY, v: now, i: now })).split(';')[0];
}

// Runs first: the shelf map is cached per isolate once read, and a failed
// read must not be cached.
test('dl: an unreadable shelf map is a 503, not an open door', async () => {
  const r = await dl(dlContext('epub/a.epub', { cookie: await freshCookie(), object: { size: 1 } }));
  assert.equal(r.status, 503);
});

test('dl: a key that is not on this build\'s shelf is 404, even for a buyer', async () => {
  const r = await dl(dlContext('epub/recalled-work.epub', { shelf: { 'epub/a.epub': 'A.epub' }, cookie: await freshCookie(), object: { size: 1 } }));
  assert.equal(r.status, 404);
  assert.match(await r.text(), /not on the shelf/);
});

test('dl: a listed key sends a locked browser to /downloads/', async () => {
  const r = await dl(dlContext('epub/a.epub', { shelf: { 'epub/a.epub': 'A.epub' } }));
  assert.equal(r.status, 302);
  assert.match(r.headers.get('location'), /\/downloads\/\?need=epub%2Fa\.epub$/);
});

test('dl: a listed key missing from the bucket says it is not ready', async () => {
  const r = await dl(dlContext('epub/a.epub', { shelf: { 'epub/a.epub': 'A.epub' }, cookie: await freshCookie(), object: null }));
  assert.equal(r.status, 404);
  assert.match(await r.text(), /not ready yet/);
});
