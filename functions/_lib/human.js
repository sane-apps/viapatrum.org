/**
 * Human check for downloads (owner 2026-10-23: one click on the shelf must
 * not let a bot pull 30,000 files). A Cloudflare Turnstile box proves a
 * person once; /api/human checks its token with Cloudflare and sets a signed
 * cookie that lets /dl/ serve files for HUMAN_TTL_S. No accounts, no database.
 *
 *   vph = <expiry seconds> "." base64url(HMAC-SHA256(K, "vp-dl-v2|" + expiry + "|" + net))
 *   K   = SHA-256("vp-dl-cookie|" + TURNSTILE_SECRET), a key of its own
 *   net = the reader's network: IPv4 /24 or IPv6 /48 (cf-connecting-ip). A
 *         cookie copied to other machines elsewhere stops working; a phone
 *         that changes networks sees the box again.
 *
 * vph_ok=1 rides alongside, readable by page script, so the shelf knows it
 * can skip the box. It proves nothing: /dl/ only trusts vph.
 *
 * Pages project settings:
 *   TURNSTILE_SECRET   secret: widget "Via Patrum downloads" (keychain
 *                      VIAPATRUM_TURNSTILE_SECRET). Unset = the check is off.
 */
export const SITEKEY = "0x4AAAAAAFjC_XeO0FeHn9dp";
export const COOKIE = "vph";
export const HUMAN_TTL_S = 2 * 3600;
const VERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
const HOSTS = new Set(["viapatrum.org", "fathers-site.pages.dev"]);

const enc = new TextEncoder();
const b64u = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function mac(secret, exp, net) {
  const raw = await crypto.subtle.digest("SHA-256", enc.encode(`vp-dl-cookie|${secret}`));
  const key = await crypto.subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64u(await crypto.subtle.sign("HMAC", key, enc.encode(`vp-dl-v2|${exp}|${net}`)));
}

/** The reader's network prefix: IPv4 /24, IPv6 /48, "" when unknown. */
export function network(request) {
  const ip = (request.headers.get("cf-connecting-ip") || "").trim().toLowerCase();
  if (/^\d+\.\d+\.\d+\.\d+$/.test(ip)) return ip.split(".").slice(0, 3).join(".");
  if (ip.includes(":")) {
    const [head, tail = ""] = ip.split("::");
    const left = head ? head.split(":") : [];
    const right = tail ? tail.split(":") : [];
    const full = ip.includes("::") ? [...left, ...Array(8 - left.length - right.length).fill("0"), ...right] : left;
    return full.slice(0, 3).map((h) => h.replace(/^0+(?=.)/, "")).join(":");
  }
  return "";
}

export const checkOn = (env) => Boolean(env && env.TURNSTILE_SECRET);

function cookie(request, name) {
  const all = request.headers.get("cookie") || "";
  for (const part of all.split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return "";
}

/** True when the request carries an unexpired cookie we signed. */
export async function isHuman(env, request, now = Date.now()) {
  if (!checkOn(env)) return true;
  const [exp, sig] = cookie(request, COOKIE).split(".");
  const n = Number(exp);
  if (!sig || !Number.isInteger(n) || n * 1000 <= now || n * 1000 > now + HUMAN_TTL_S * 1000 + 60_000) return false;
  const want = await mac(env.TURNSTILE_SECRET, n, network(request));
  if (want.length !== sig.length) return false;
  let diff = 0;
  for (let i = 0; i < want.length; i++) diff |= want.charCodeAt(i) ^ sig.charCodeAt(i);
  return diff === 0;
}

/** Set-Cookie values for a person who just passed the box. */
export async function humanCookies(env, request, now = Date.now()) {
  const exp = Math.floor(now / 1000) + HUMAN_TTL_S;
  const sig = await mac(env.TURNSTILE_SECRET, exp, network(request));
  const tail = `Path=/; Max-Age=${HUMAN_TTL_S}; Secure; SameSite=Lax`;
  return [`${COOKIE}=${exp}.${sig}; ${tail}; HttpOnly`, `vph_ok=1; ${tail}`];
}

/** Ask Cloudflare whether a Turnstile token is good. Each token works once. */
export async function verifyToken(env, token, ip) {
  if (typeof token !== "string" || !token || token.length > 2048) return false;
  const body = new FormData();
  body.append("secret", env.TURNSTILE_SECRET);
  body.append("response", token);
  if (ip) body.append("remoteip", ip);
  try {
    const r = await fetch(VERIFY, { method: "POST", body });
    const out = await r.json();
    return Boolean(out && out.success && (!out.hostname || HOSTS.has(out.hostname) || out.hostname.endsWith(".fathers-site.pages.dev")));
  } catch {
    return false;
  }
}
