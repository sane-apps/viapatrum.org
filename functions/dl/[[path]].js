/**
 * GET /dl/<kind>/<file> -> a download from the private R2 bucket, for
 * browsers unlocked with a library pass (functions/_lib/library.js).
 * Locked browsers are sent to /downloads/ with the file they wanted.
 * Range requests work, so big audiobooks resume.
 */
import { session } from "../_lib/library.js";

let namesPromise = null; // key -> "Title - Author (Via Patrum).epub", from /data/library-files.json
function names(context) {
  if (!namesPromise) {
    namesPromise = context.env.ASSETS.fetch(new URL("/data/library-files.json", context.request.url))
      .then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  }
  return namesPromise;
}

const OK_PATH = /^(epub|pdf|word|audio|bundles)\/[a-z0-9][a-z0-9._-]{0,180}\.(epub|pdf|zip|m4b)$/;

export async function onRequest(context) {
  const { request, env, params } = context;
  if (request.method !== "GET" && request.method !== "HEAD") return new Response("Method not allowed", { status: 405 });
  const path = [].concat(params.path || []).join("/");
  if (!OK_PATH.test(path)) return new Response("Not found", { status: 404 });
  const s = await session(request, env);
  if (!s.unlocked) {
    const to = new URL(`/downloads/?need=${encodeURIComponent(path)}`, request.url);
    const h = new Headers({ location: to.toString(), "cache-control": "no-store" });
    if (s.setCookie) h.append("set-cookie", s.setCookie);
    return new Response(null, { status: 302, headers: h });
  }
  if (!env.LIBRARY) return new Response("Downloads are not switched on yet.", { status: 503 });
  const obj = request.method === "HEAD"
    ? await env.LIBRARY.head(path)
    : await env.LIBRARY.get(path, { range: request.headers, onlyIf: request.headers });
  if (!obj) return new Response("Not found", { status: 404 });
  const h = new Headers();
  obj.writeHttpMetadata(h);
  h.set("etag", obj.httpEtag);
  h.set("accept-ranges", "bytes");
  h.set("cache-control", "private, no-store");
  h.set("x-robots-tag", "noindex");
  const name = (await names(context))[path] || (obj.customMetadata && obj.customMetadata.filename) || path.split("/").pop();
  h.set("content-disposition", `attachment; filename="${name.replace(/[^\x20-\x7e]/g, "_").replace(/"/g, "'")}"; filename*=UTF-8''${encodeURIComponent(name)}`);
  if (s.setCookie) h.append("set-cookie", s.setCookie);
  if (request.method === "HEAD") {
    h.set("content-length", String(obj.size));
    return new Response(null, { status: 200, headers: h });
  }
  if (!("body" in obj) || !obj.body) return new Response(null, { status: 304, headers: h }); // onlyIf failed
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
