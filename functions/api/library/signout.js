/** POST /api/library/signout -> forgets the key in this browser. */
import { json, clearCookie } from "../../_lib/library.js";

export async function onRequestPost() {
  return json({ ok: true }, 200, { "set-cookie": clearCookie() });
}
