"""/zwi/: the signed ZWI archive of every work, and how to check one (owner-approved 2026-11-08).

The archives themselves are made on each ship by scripts/zwi/refresh_zwi.py from the built pages and copied into
dist/zwi/ (one <slug>.zwi per published work). The live set kept between ships is outputs/zwi-live/archives.
Each work page links its own archive from About this text (build_site: zwi_signed_html), only when that archive
exists, so a link never points at a missing file.
"""
from html import escape
from pathlib import Path

LIVE = Path(__file__).resolve().parents[1] / "outputs" / "zwi-live" / "archives"
ZWIBOOK = "https://zwibook.org"
SPEC = "https://docs.encyclosphere.org/#/zwi-format"
KEY = "/.well-known/psqr"


def has_archive(slug: str, live: Path = LIVE) -> bool:
    return (live / f"{slug}.zwi").is_file()


def signed_html(slug: str, live: Path = LIVE) -> str:
    """The About this text line for one work, or "" when it has no archive yet."""
    if not has_archive(slug, live):
        return ""
    name = f"{slug}.zwi"
    # The file name is a slug; readers see plain words (check_catalogue keeps slugs out of visible text).
    return (f'<p class="intro fine zwi-signed">Signed copy: <a href="/zwi/{escape(name)}" download="{escape(name)}">'
            f'download the ZWI file</a> (ZWI 1.5 · <a href="/zwi/">how to verify</a>)</p>')


def body(n: int) -> str:
    return f"""
<p class="eyebrow">Signed archives</p>
  <h1>Signed archives of every work</h1>
  <p class="lede">Each work on Via Patrum is also published as one signed <a href="{SPEC}" rel="noopener">ZWI</a> file: the
  whole work in a ZIP, with the text, its details and a digital signature. Libraries such as
  <a href="{ZWIBOOK}" rel="noopener">ZWIBook</a> import them, and anyone can check that a copy is exactly what
  Via Patrum published. {n} works have a signed archive today; each work page links its own under
  <strong>About this text</strong>.</p>
  <h2>How to check a copy</h2>
  <ol>
    <li>Download the work's <code>.zwi</code> file from its page and open it like any ZIP.</li>
    <li>Get our public key from <a href="{KEY}"><code>viapatrum.org{KEY}</code></a>
        (identity <code>did:psqr:viapatrum.org#publish</code>, ES384).</li>
    <li>Check <code>signature.json</code> against that key with any JWS tool, then check that the hashes it lists
        match <code>metadata.json</code> and each file. Our own checker does all of this:
        <code>scripts/zwi/check_zwi.py</code> in the public
        <a href="https://github.com/sane-apps/viapatrum.org" rel="noopener">viapatrum.org repository</a>.</li>
  </ol>
  <h2>For libraries</h2>
  <p>A machine-readable list of every archive, with its SHA-256, version and Work ID, is at
  <a href="/zwi/catalog.json"><code>/zwi/catalog.json</code></a>. It is rewritten each time the site is published,
  so an importer can fetch only the archives that changed.</p>
  <h2>Versions</h2>
  <p>When a work's text changes, its archive is made and signed again as a new version. The earlier signature,
  details and media list are kept inside the new archive under <code>history/</code>, so the record of every
  published version travels with the file.</p>
  <p>The translations are CC BY 4.0. Please credit "Via Patrum" and link to the work on viapatrum.org.</p>"""


def build(dist: Path, layout, write, live: Path = LIVE) -> int:
    """Write /zwi/index.html. Returns the number of archives in the live set."""
    n = len(list(live.glob("*.zwi"))) if live.is_dir() else 0
    if not n:
        return 0
    write(dist / "zwi" / "index.html",
          layout("Signed archives", body(n), crumb=[("Home", "/"), ("Signed archives", "")],
                 description="Every Via Patrum work as a signed ZWI file, and how to check one."))
    return n
