/**
 * Library pass: one $50 Lemon Squeezy purchase unlocks every download
 * (owner 2026-10-05). Reading and listening on the site stay free.
 *
 * Proof of purchase is the Lemon Squeezy licence key. The browser holds it in
 * a signed, HttpOnly cookie ("vpl"), so no accounts and no database:
 *   vpl = base64url(JSON {k: key, v: last check (s), i: issued (s)}) "." base64url(HMAC-SHA256)
 * Every REVALIDATE_S the key is checked again with the public Licence API, so
 * a refunded or disabled key stops working; if Lemon Squeezy is unreachable
 * the cookie keeps working until it can be checked.
 *
 * Pages project settings:
 *   LIBRARY            R2 binding, private bucket "viapatrum-downloads"
 *   LIBRARY_SECRET     secret: cookie HMAC key, kept only on Pages (rotating it
 *                      just asks buyers to enter their key again)
 *   LEMONSQUEEZY_API_KEY  secret: reads an order to unlock right after checkout
 *   LIBRARY_STORE_ID   e.g. "270691"
 *   LIBRARY_PRODUCT_IDS  comma list of product ids that unlock (live + test)
 */
export const COOKIE = "vpl";
export const REVALIDATE_S = 7 * 24 * 3600;
const MAX_AGE_S = 400 * 24 * 3600; // browsers cap cookie lifetime at 400 days
const LS = "https://api.lemonsqueezy.com/v1";

const enc = new TextEncoder();
const b64u = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

export function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
  });
}

async function hmac(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return crypto.subtle.sign("HMAC", key, enc.encode(data));
}

export function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

export async function sealCookie(env, payload) {
  const body = b64u(enc.encode(JSON.stringify(payload)));
  const sig = b64u(await hmac(env.LIBRARY_SECRET, body));
  return `${COOKIE}=${body}.${sig}; Max-Age=${MAX_AGE_S}; Path=/; HttpOnly; Secure; SameSite=Lax`;
}

export const clearCookie = () => `${COOKIE}=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax`;

export async function readCookie(request, env) {
  if (!env.LIBRARY_SECRET) return null;
  const raw = (request.headers.get("cookie") || "").split(/;\s*/).find((c) => c.startsWith(COOKIE + "="));
  if (!raw) return null;
  const [body, sig] = raw.slice(COOKIE.length + 1).split(".");
  if (!body || !sig) return null;
  const want = b64u(await hmac(env.LIBRARY_SECRET, body));
  if (!timingSafeEqual(sig, want)) return null;
  try {
    const p = JSON.parse(new TextDecoder().decode(unb64u(body)));
    return p && typeof p.k === "string" ? p : null;
  } catch {
    return null;
  }
}

const allowedProducts = (env) => new Set(String(env.LIBRARY_PRODUCT_IDS || "").split(",").map((s) => s.trim()).filter(Boolean));

/** Check a key with the public Licence API. Returns {ok, reason, meta, test}. */
export async function validateKey(env, key) {
  key = String(key || "").trim();
  if (!/^[A-Za-z0-9-]{8,64}$/.test(key)) return { ok: false, reason: "That does not look like a licence key." };
  let r;
  try {
    r = await fetch(`${LS}/licenses/validate`, {
      method: "POST",
      headers: { accept: "application/json", "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ license_key: key }),
    });
  } catch {
    return { ok: false, reason: "We could not reach the store. Please try again in a minute.", unreachable: true };
  }
  if (r.status >= 500) return { ok: false, reason: "The store is not answering. Please try again in a minute.", unreachable: true };
  const d = await r.json().catch(() => ({}));
  const meta = d.meta || {};
  if (!d.valid) {
    const status = d.license_key && d.license_key.status;
    const reason = status === "disabled" ? "This key has been turned off (for example after a refund)."
      : status === "expired" ? "This key has expired."
      : "We could not find that key. Check it against your receipt email.";
    return { ok: false, reason };
  }
  if (String(meta.store_id) !== String(env.LIBRARY_STORE_ID) || !allowedProducts(env).has(String(meta.product_id))) {
    return { ok: false, reason: "That key is for a different product." };
  }
  return { ok: true, meta, test: Boolean(d.license_key && d.license_key.test_mode) };
}

/** Is this browser unlocked? Re-checks the key when the last check is stale. */
export async function session(request, env) {
  const p = await readCookie(request, env);
  if (!p) return { unlocked: false };
  const now = Math.floor(Date.now() / 1000);
  if (now - (p.v || 0) < REVALIDATE_S) return { unlocked: true, payload: p };
  const v = await validateKey(env, p.k);
  if (v.ok) {
    const fresh = { ...p, v: now };
    return { unlocked: true, payload: fresh, setCookie: await sealCookie(env, fresh) };
  }
  if (v.unreachable) return { unlocked: true, payload: p };
  return { unlocked: false, setCookie: clearCookie(), reason: v.reason };
}

export const keyHint = (k) => (k ? `…${String(k).slice(-4).toUpperCase()}` : "");

/** Lemon Squeezy REST call with the store API key. */
export async function lsGet(env, path) {
  const r = await fetch(`${LS}${path}`, {
    headers: { accept: "application/vnd.api+json", authorization: `Bearer ${env.LEMONSQUEEZY_API_KEY}` },
  });
  if (!r.ok) return null;
  return r.json().catch(() => null);
}

export { allowedProducts };
