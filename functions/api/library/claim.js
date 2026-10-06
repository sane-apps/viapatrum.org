/**
 * POST /api/library/claim {order_id, identifier}
 * Right after checkout, Lemon.js hands the page the new order. The order's
 * identifier is a UUID only the buyer sees, so (id, identifier) proves the
 * purchase. We read the order and its licence key with the store API key,
 * unlock this browser, and return the key so the buyer can keep it.
 * Answers 200 with ok:false (and pending:true while the order settles) so the
 * page can poll without filling the console with errors.
 */
import { json, lsGet, sealCookie, keyHint, allowedProducts } from "../../_lib/library.js";

export async function onRequestPost({ request, env }) {
  if (!env.LIBRARY_SECRET || !env.LEMONSQUEEZY_API_KEY) return json({ ok: false, reason: "Downloads are not switched on yet." }, 503);
  const body = await request.json().catch(() => ({}));
  const id = String(body.order_id || "");
  const identifier = String(body.identifier || "");
  if (!/^\d{1,12}$/.test(id) || !/^[0-9a-f-]{36}$/i.test(identifier)) return json({ ok: false, reason: "Missing order details." });
  const order = await lsGet(env, `/orders/${id}`);
  const a = order && order.data && order.data.attributes;
  if (!a || a.identifier !== identifier) return json({ ok: false, reason: "We could not find that order yet.", pending: true });
  if (String(a.store_id) !== String(env.LIBRARY_STORE_ID) || !allowedProducts(env).has(String(a.first_order_item && a.first_order_item.product_id))) {
    return json({ ok: false, reason: "That order is for a different product." });
  }
  if (a.status !== "paid") return json({ ok: false, reason: "The payment has not cleared yet.", pending: a.status === "pending" });
  const keys = await lsGet(env, `/license-keys?filter[order_id]=${id}`);
  const lk = keys && keys.data && keys.data[0] && keys.data[0].attributes;
  if (!lk || !lk.key) return json({ ok: false, reason: "Your key is still being made.", pending: true });
  if (lk.disabled || lk.status === "disabled") return json({ ok: false, reason: "This key has been turned off." });
  const now = Math.floor(Date.now() / 1000);
  return json({ ok: true, key: lk.key, key_hint: keyHint(lk.key), email: a.user_email || "" }, 200,
    { "set-cookie": await sealCookie(env, { k: lk.key, v: now, i: now }) });
}
