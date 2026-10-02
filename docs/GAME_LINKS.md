# Game links (keep through any redesign)

The Fathers game lives at **https://play.viapatrum.org** (repo
`sane-apps/fathers-village`, Cloudflare Pages project `fathers-village`,
custom domain via CNAME `play` -> `fathers-village.pages.dev`, proxied).
Owner asked (2026-10-02) for it to be linked from the official site so
people can see and play it. Any redesign must keep both entry points:

1. **Main nav:** a `Play` item linking to `https://play.viapatrum.org/`
   (currently between Authors and Help in `layout()` in
   `scripts/build_site.py`; committed in 11ed069).
2. **Home page Play section** (currently right after the Via Patrum
   mission section in `scripts/build_site.py`; shipped live 2026-10-02
   but uncommitted, because the mission section above it was not yet
   committed). Current markup, using existing classes only:

```html
<section class="play-promo">
  <h2>Play</h2>
  <p><strong>Fragment of the Day:</strong> restore one torn line from the Fathers each day, in our own new English. <strong>Ten Leopards:</strong> it is AD 110, and you carry Ignatius's letters past the guards on his road to Rome.</p>
  <div class="hero-actions">
    <a class="btn primary" href="https://play.viapatrum.org/daily">Today's fragment</a>
    <a class="btn" href="https://play.viapatrum.org/leopards">Play Ten Leopards</a>
  </div>
</section>
```

Entry URLs: `/` and `/play` redirect to `/daily`; `/leopards` is the
chapter. Do not link `.html` paths (Pages serves `/x` for `x.html`).
The game's "Read the whole work" links point at `https://viapatrum.org/works/...`
so work URLs (`/works/<slug>/<section>/`) must keep resolving.
