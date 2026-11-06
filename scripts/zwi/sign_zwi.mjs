#!/usr/bin/env node
// Sign every staged ZWI folder as did:psqr:viapatrum.org#publish (ES384), per Larry Sanger's spec of 6 Nov 2026.
//
// For each <stage>/<slug>/ it hashes metadata.json and media.json (SHA-1), makes a compact JWT
//   header  {"alg":"ES384","jwk":<public key>,"kid":"did:psqr:viapatrum.org#publish","typ":"JWT"}
//   payload {"iss":"Via Patrum","address":"https://viapatrum.org","iat":<s>,"metadata":<sha1>,"media":<sha1>}
// and writes signature.json. Packing into .zwi is pack_zwi.py; checking is check_zwi.py.
//
// The private key (a JWK) comes from the VIAPATRUM_PSQR_PUBLISH_JWK env var (Keychain loader), or, until it is in
// the Keychain, from --key-file. It is never printed or written anywhere.
//
// Usage: node sign_zwi.mjs --stage <dir> [--key-file <path>] [--only slug,slug]
import { createHash, createPrivateKey, sign } from "node:crypto";
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const KID = "did:psqr:viapatrum.org#publish";
const ISS = "Via Patrum";
const ADDRESS = "https://viapatrum.org";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, arr) => (a.startsWith("--") ? [...acc, [a.slice(2), arr[i + 1]]] : acc), []),
);
if (!args.stage) {
  console.error("usage: sign_zwi.mjs --stage <dir> [--key-file <path>] [--only slug,slug]");
  process.exit(2);
}

const jwkText = process.env.VIAPATRUM_PSQR_PUBLISH_JWK || (args["key-file"] ? readFileSync(args["key-file"], "utf8") : "");
if (!jwkText) {
  console.error("no key: set VIAPATRUM_PSQR_PUBLISH_JWK or pass --key-file");
  process.exit(2);
}
const jwk = JSON.parse(jwkText);
if (jwk.kid !== KID || jwk.crv !== "P-384" || !jwk.d) {
  console.error("key is not the P-384 private key for " + KID);
  process.exit(2);
}
const key = createPrivateKey({ key: jwk, format: "jwk" });
// Public half only, carried in the token header as ZWIBook's own sample does (header: alg, jwk, kid, typ).
const publicJwk = { crv: jwk.crv, kty: jwk.kty, x: jwk.x, y: jwk.y };

const b64u = (buf) => Buffer.from(buf).toString("base64url");
const sha1 = (buf) => createHash("sha1").update(buf).digest("hex");

const only = args.only ? new Set(args.only.split(",")) : null;
const slugs = readdirSync(args.stage)
  .filter((s) => !s.startsWith(".") && statSync(join(args.stage, s)).isDirectory())
  .filter((s) => !only || only.has(s))
  .sort();

let n = 0;
for (const slug of slugs) {
  const dir = join(args.stage, slug);
  const iat = Math.floor(Date.now() / 1000);
  const header = { alg: "ES384", jwk: publicJwk, kid: KID, typ: "JWT" };
  const payload = {
    iss: ISS,
    address: ADDRESS,
    iat,
    metadata: sha1(readFileSync(join(dir, "metadata.json"))),
    media: sha1(readFileSync(join(dir, "media.json"))),
  };
  const input = `${b64u(JSON.stringify(header))}.${b64u(JSON.stringify(payload))}`;
  // ES384 JWS signatures are raw r||s (IEEE P1363), 96 bytes, not DER.
  const sig = sign("sha384", Buffer.from(input), { key, dsaEncoding: "ieee-p1363" });
  const updated = new Date(iat * 1000).toISOString().replace(/\.\d{3}Z$/, ".000000");
  const signature = {
    identityName: ISS,
    identityAddress: ADDRESS,
    kid: KID,
    updated,
    alg: "ES384",
    token: `${input}.${b64u(sig)}`,
  };
  writeFileSync(join(dir, "signature.json"), JSON.stringify(signature, null, 2) + "\n");
  n += 1;
}
console.log(JSON.stringify({ signed: n, kid: KID }));
