/** POST /api/library/unlock {key} -> checks the licence key, then unlocks this browser. */
import { json, validateKey, sealCookie, keyHint } from "../../_lib/library.js";

export async function onRequestPost({ request, env }) {
  if (!env.LIBRARY_SECRET) return json({ ok: false, reason: "Downloads are not switched on yet." }, 503);
  const body = await request.json().catch(() => ({}));
  const key = String(body.key || "").trim();
  const v = await validateKey(env, key);
  if (!v.ok) return json({ ok: false, reason: v.reason }, v.unreachable ? 503 : 200); // a refused key is an answer, not an error
  const now = Math.floor(Date.now() / 1000);
  return json({ ok: true, key_hint: keyHint(key) }, 200, { "set-cookie": await sealCookie(env, { k: key, v: now, i: now }) });
}
