/**
 * /api/library/admin?action=... : upload tool for scripts/library_sync.py.
 * Needs header x-cf-token: a Cloudflare API token that can read this Pages
 * project (the same token ship.sh deploys with), checked with Cloudflare and
 * cached briefly. No extra secret to store. Big files go up in parts
 * (R2 multipart), so a 2 GB audiobook bundle needs no S3 keys.
 *   GET  list&prefix=   GET head&key=   PUT put&key=
 *   POST create&key=    PUT part&key=&upload=&n=   POST complete&key=&upload= {parts}
 *   POST abort&key=&upload=   DELETE delete&key=
 */
import { json } from "../../_lib/library.js";

const PROJECT = "https://api.cloudflare.com/client/v4/accounts/2c267ab06352ba2522114c3081a8c5fa/pages/projects/fathers-site";
const trusted = new Map(); // sha256(token) -> expiry ms

async function allowed(token) {
  if (!/^[A-Za-z0-9_-]{30,200}$/.test(token)) return false;
  const h = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token)))]
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  if ((trusted.get(h) || 0) > Date.now()) return true;
  const r = await fetch(PROJECT, { headers: { authorization: `Bearer ${token}` } }).catch(() => null);
  if (!r || !r.ok) return false;
  trusted.set(h, Date.now() + 5 * 60 * 1000);
  return true;
}

const OK_KEY = /^(epub|pdf|word|audio|bundles)\/[a-z0-9][a-z0-9._-]{0,180}\.(epub|pdf|zip|m4b)$/;
const TYPES = { epub: "application/epub+zip", pdf: "application/pdf", zip: "application/zip", m4b: "audio/mp4" };

export async function onRequest({ request, env }) {
  if (!(await allowed(request.headers.get("x-cf-token") || ""))) return json({ error: "forbidden" }, 403);
  if (!env.LIBRARY) return json({ error: "no R2 binding" }, 503);
  const u = new URL(request.url);
  const action = u.searchParams.get("action");
  const key = u.searchParams.get("key") || "";
  if (action === "list") {
    const out = [];
    let cursor;
    for (let i = 0; i < 50; i++) {
      const page = await env.LIBRARY.list({ prefix: u.searchParams.get("prefix") || "", cursor, include: ["customMetadata"] });
      for (const o of page.objects) out.push({ key: o.key, size: o.size, sha256: (o.customMetadata || {}).sha256 || "" });
      if (!page.truncated) break;
      cursor = page.cursor;
    }
    return json({ objects: out });
  }
  if (!OK_KEY.test(key)) return json({ error: "bad key" }, 400);
  const meta = {
    httpMetadata: { contentType: TYPES[key.split(".").pop()] },
    customMetadata: { filename: request.headers.get("x-filename") || key.split("/").pop(), sha256: request.headers.get("x-sha256") || "" },
  };
  if (action === "head") {
    const o = await env.LIBRARY.head(key);
    return json(o ? { key, size: o.size, sha256: (o.customMetadata || {}).sha256 || "" } : { key, missing: true });
  }
  if (action === "put" && request.method === "PUT") {
    const o = await env.LIBRARY.put(key, request.body, meta);
    return json({ key, size: o.size });
  }
  if (action === "create" && request.method === "POST") {
    const m = await env.LIBRARY.createMultipartUpload(key, meta);
    return json({ key, upload: m.uploadId });
  }
  const upload = u.searchParams.get("upload") || "";
  if (action === "part" && request.method === "PUT") {
    const m = env.LIBRARY.resumeMultipartUpload(key, upload);
    const part = await m.uploadPart(Number(u.searchParams.get("n")), request.body);
    return json({ n: part.partNumber, etag: part.etag });
  }
  if (action === "complete" && request.method === "POST") {
    const { parts } = await request.json();
    const m = env.LIBRARY.resumeMultipartUpload(key, upload);
    const o = await m.complete(parts.map((p) => ({ partNumber: p.n, etag: p.etag })));
    return json({ key, size: o.size });
  }
  if (action === "abort" && request.method === "POST") {
    await env.LIBRARY.resumeMultipartUpload(key, upload).abort();
    return json({ key, aborted: true });
  }
  if (action === "delete" && request.method === "DELETE") {
    await env.LIBRARY.delete(key);
    return json({ key, deleted: true });
  }
  return json({ error: "unknown action" }, 400);
}
