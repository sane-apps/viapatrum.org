// The /dl gate (functions/dl/[[path]].js): the shelf map decides what is
// served. No TURNSTILE_SECRET here, so the human check is off (its own tests
// are in human_check.test.mjs). fetch is mocked; no network.
// Run: node --test scripts/downloads_dl.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { onRequest as dl } from '../functions/dl/[[path]].js';

const ENV = {};

function reply(status, body) {
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), { status });
}

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

// Runs first: the shelf map is cached per isolate once read, and a failed
// read must not be cached.
test('dl: an unreadable shelf map is a 503, not an open door', async () => {
  const r = await dl(dlContext('epub/a.epub', { object: { size: 1 } }));
  assert.equal(r.status, 503);
});

test('dl: a key that is not on this build\'s shelf is 404', async () => {
  const r = await dl(dlContext('epub/recalled-work.epub', { shelf: { 'epub/a.epub': 'A.epub' }, object: { size: 1 } }));
  assert.equal(r.status, 404);
  assert.match(await r.text(), /not on the shelf/);
});

test('dl: a listed file downloads without any key (free since 2026-10-22)', async () => {
  const body = new Uint8Array([1, 2, 3]);
  const object = { size: 3, body, httpEtag: '"e"', writeHttpMetadata: () => {} };
  const r = await dl(dlContext('epub/a.epub', { shelf: { 'epub/a.epub': 'A.epub' }, object }));
  assert.equal(r.status, 200);
  assert.match(r.headers.get('content-disposition'), /A\.epub/);
  assert.equal(r.headers.get('set-cookie'), null);
});

test('dl: a listed key missing from the bucket says it is not ready', async () => {
  const r = await dl(dlContext('epub/a.epub', { shelf: { 'epub/a.epub': 'A.epub' }, object: null }));
  assert.equal(r.status, 404);
  assert.match(await r.text(), /not ready yet/);
});
