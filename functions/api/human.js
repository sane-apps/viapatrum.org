/**
 * POST /api/human {token} -> checks a Turnstile token (functions/_lib/human.js)
 * and sets the cookie that lets /dl/ serve files for two hours.
 */
import { checkOn, humanCookies, verifyToken } from "../_lib/human.js";

const reply = (body, status, extra = []) => {
  const h = new Headers({ "content-type": "application/json", "cache-control": "no-store" });
  extra.forEach((c) => h.append("set-cookie", c));
  return new Response(JSON.stringify(body), { status, headers: h });
};

export async function onRequestPost({ request, env }) {
  if (!checkOn(env)) return reply({ ok: true }, 200);
  let token = "";
  try {
    token = ((await request.json()) || {}).token;
  } catch {
    return reply({ ok: false }, 400);
  }
  const ok = await verifyToken(env, token, request.headers.get("cf-connecting-ip"));
  if (!ok) return reply({ ok: false }, 403);
  return reply({ ok: true }, 200, await humanCookies(env, request));
}

export const onRequest = () => new Response("Method not allowed", { status: 405, headers: { allow: "POST" } });
