/** GET /api/library/status -> {unlocked, key_hint}. The download page asks this on load. */
import { json, session, keyHint } from "../../_lib/library.js";

export async function onRequestGet({ request, env }) {
  const s = await session(request, env);
  const headers = s.setCookie ? { "set-cookie": s.setCookie } : {};
  return json({ unlocked: s.unlocked, key_hint: s.unlocked ? keyHint(s.payload.k) : "", reason: s.reason || "" }, 200, headers);
}
