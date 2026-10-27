/**
 * GET /dl/<kind>/<file> -> a download from the private R2 bucket. Every file
 * on the shelf is free (2026-10-22; the library pass and its key check are
 * gone). Range requests work, so big audiobooks resume. A GET needs the
 * human-check cookie (functions/_lib/human.js); without it the reader gets a
 * Turnstile box that starts the file once it passes. HEAD stays open.
 */
import { SITEKEY, isHuman } from "../_lib/human.js";

// key -> "Title - Author (Via Patrum).epub", from /data/library-files.json.
// That map is also the shelf: downloads_page.py writes only the files this
// build lists (uploaded, current, not withdrawn), so a key missing from it is
// not served even if an older copy still sits in the bucket (2026-10-07: a
// recalled work's file stayed downloadable by its old link).
let namesPromise = null;
function names(context) {
  if (!namesPromise) {
    namesPromise = context.env.ASSETS.fetch(new URL("/data/library-files.json", context.request.url))
      .then((r) => (r.ok ? r.json() : r.status === 404 ? {} : null))
      .catch(() => null)
      .then((m) => {
        if (!m || typeof m !== "object") namesPromise = null; // a failed read is retried, never cached
        return m;
      });
  }
  return namesPromise;
}

function page(status, title, text, extra = {}) {
  const body = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>${title} · Via Patrum</title><link rel="stylesheet" href="/assets/site.css"></head>
<body><main class="wrap" style="max-width:40rem;margin:4rem auto;padding:0 1rem"><h1>${title}</h1><p>${text}</p>
<p><a href="/downloads/#shelf">Back to the shelf</a></p></main></body></html>`;
  return new Response(body, { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", ...extra } });
}

const NOT_ON_SHELF = () => page(404, "That file is not on the shelf",
  "This file is not part of the library right now. The work may be under correction, or its file has a new name. Everything on the shelf is listed on the downloads page.");

// The box for a reader who arrives without the cookie (a link from outside the
// shelf, or the cookie ran out). It passes most people without a click.
function humanPage() {
  const body = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>One moment · Via Patrum</title><link rel="stylesheet" href="/assets/site.css">
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script></head>
<body><main class="wrap" style="max-width:40rem;margin:4rem auto;padding:0 1rem"><h1>One moment</h1>
<p>Please confirm you are a person. This keeps bots from emptying the shelf. Your download starts as soon as the check passes.</p>
<div class="cf-turnstile" data-sitekey="${SITEKEY}" data-callback="vpHuman" data-error-callback="vpHumanFail" data-action="download"></div>
<p id="vp-msg" role="status" aria-live="polite"></p>
<p><a href="/downloads/#shelf">Back to the shelf</a></p></main>
<script>
function vpHumanFail() { document.getElementById("vp-msg").textContent = "The check did not load. Reload the page to try again."; }
function vpHuman(token) {
  var msg = document.getElementById("vp-msg");
  msg.textContent = "Starting your download…";
  fetch("/api/human", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: token }) })
    .then(function (r) {
      if (!r.ok) throw 0;
      // The file downloads and this page stays open, so say what happened.
      msg.textContent = "Your download should start now. If it does not, reload this page.";
      location.replace(location.href);
    })
    .catch(function () { msg.textContent = "The check did not pass. Reload the page to try again."; });
}
</script></body></html>`;
  return new Response(body, { status: 403, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "x-robots-tag": "noindex" } });
}

const OK_PATH = /^(epub|pdf|word|audio|bundles)\/[a-z0-9][a-z0-9._-]{0,180}\.(epub|pdf|zip|m4b)$/;

export async function onRequest(context) {
  const { request, env, params } = context;
  if (request.method !== "GET" && request.method !== "HEAD") return new Response("Method not allowed", { status: 405 });
  const path = [].concat(params.path || []).join("/");
  if (!OK_PATH.test(path)) return new Response("Not found", { status: 404 });
  const shelf = await names(context);
  if (!shelf) return page(503, "Please try again", "We could not read the shelf just now. Please try again in a minute.", { "retry-after": "30" });
  if (!Object.prototype.hasOwnProperty.call(shelf, path)) return NOT_ON_SHELF();
  if (request.method === "GET" && !(await isHuman(env, request))) return humanPage();
  if (!env.LIBRARY) return new Response("Downloads are not switched on yet.", { status: 503 });
  const obj = request.method === "HEAD"
    ? await env.LIBRARY.head(path)
    : await env.LIBRARY.get(path, { range: request.headers, onlyIf: request.headers });
  if (!obj) {
    return page(404, "That file is not ready yet",
      "This file is listed but has not reached our download store yet. Please try again later, or write to hi@saneapps.com and we will send it.");
  }
  const h = new Headers();
  obj.writeHttpMetadata(h);
  h.set("etag", obj.httpEtag);
  h.set("accept-ranges", "bytes");
  h.set("cache-control", "private, no-store");
  h.set("x-robots-tag", "noindex");
  const name = shelf[path] || (obj.customMetadata && obj.customMetadata.filename) || path.split("/").pop();
  h.set("content-disposition", `attachment; filename="${name.replace(/[^\x20-\x7e]/g, "_").replace(/"/g, "'")}"; filename*=UTF-8''${encodeURIComponent(name)}`);
  if (request.method === "HEAD") {
    h.set("content-length", String(obj.size));
    return new Response(null, { status: 200, headers: h });
  }
  if (!("body" in obj) || !obj.body) {
    // onlyIf failed. If-Match / If-Unmodified-Since failing means the file
    // changed: 412, so a resuming download manager starts over (RFC 9110).
    const changed = request.headers.has("if-match") || request.headers.has("if-unmodified-since");
    return new Response(null, { status: changed ? 412 : 304, headers: h });
  }
  const r = obj.range;
  if (r && request.headers.has("range")) {
    const suffix = typeof r.suffix === "number";
    const start = suffix ? obj.size - r.suffix : (typeof r.offset === "number" ? r.offset : 0);
    const len = suffix ? r.suffix : (typeof r.length === "number" ? r.length : obj.size - start);
    h.set("content-range", `bytes ${start}-${start + len - 1}/${obj.size}`);
    h.set("content-length", String(len));
    return new Response(obj.body, { status: 206, headers: h });
  }
  h.set("content-length", String(obj.size));
  return new Response(obj.body, { status: 200, headers: h });
}
