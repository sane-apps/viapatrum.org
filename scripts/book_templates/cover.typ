// Via Patrum series covers: one look for every book.
//
// Used twice so the covers always match: covers.typ renders the JPEG covers
// (portrait for EPUB/PDF listings, square for audiobooks), and book.typ draws
// the same portrait cover as page 1 of the PDF.
//
// The ground colour follows the author's era (lapis, rubric, green, umber:
// the site palette, deepened). Title, subtitle and author shrink to fit, so
// long titles wrap and never clip.

#let parchment = rgb("#f4ecd9")
#let gold-hi = rgb("#dcbc6e")
#let gold-lo = rgb("#b99554")

#let eras = (
  early: (deep: rgb("#0f1a35"), mid: rgb("#24427c")),
  late: (deep: rgb("#360c08"), mid: rgb("#7a2016")),
  medieval: (deep: rgb("#0b231b"), mid: rgb("#1f5240")),
  modern: (deep: rgb("#17110b"), mid: rgb("#45331f")),
)

#let display = ("Cormorant Garamond", "Literata", "Noto Serif Hebrew")
#let serif = ("Literata", "Noto Serif Hebrew")

// The site mark (favicon cross), drawn as a polygon so it scales cleanly.
#let cross(height, fill) = {
  let k = height / 19.5
  let pts = (
    (6.5, 0), (10.5, 0), (10.5, 6), (17, 6), (17, 10), (10.5, 10),
    (10.5, 19.5), (6.5, 19.5), (6.5, 10), (0, 10), (0, 6), (6.5, 6),
  )
  box(width: 17 * k, height: height, polygon(fill: fill, ..pts.map(p => (p.at(0) * k, p.at(1) * k))))
}

// A gold rule with a diamond at its centre.
#let diamond-rule(width, color, k) = box(width: width, height: 7pt * k, {
  let gap = 7pt * k
  place(horizon + left, line(length: (width - gap) / 2, stroke: 0.55pt * k + color))
  place(horizon + right, line(length: (width - gap) / 2, stroke: 0.55pt * k + color))
  place(center + horizon, rotate(45deg, rect(width: 3.6pt * k, height: 3.6pt * k, fill: color)))
})

// Largest size in [smin, smax] at which make(size, text) fits the box and no
// single word is wider than the box.
#let fit(make, full, words, width, height, smax, smin) = {
  let s = smax
  let step = (smax - smin) / 40
  while s > smin {
    let h = measure(block(width: width, make(s, full))).height
    let wide = words.fold(0pt, (acc, w) => calc.max(acc, measure(make(s, w)).width))
    if h <= height and wide <= width * 0.98 { break }
    s -= step
  }
  calc.max(s, smin)
}

#let words-of(t) = t.split(" ").filter(w => w != "")

// Width that spreads a heading evenly over the fewest lines it needs, so no
// line holds one stray word. Grows until the line count stops rising.
#let balanced(mk, maxw) = {
  let one = measure(mk).height
  let full = measure(mk).width
  if full <= maxw { return maxw }
  let need = measure(block(width: maxw, mk)).height
  let w = calc.min(maxw, full / calc.ceil(full / maxw))
  while w < maxw and measure(block(width: w, mk)).height > need { w += maxw * 0.03 }
  calc.min(w, maxw)
}


// Prefer one line (shrinking down to 72% of the top size); if the text is
// too long for that, wrap at a comfortable size instead.
#let fit-line-first(make, t, width, multi-h, smax, smin) = {
  let s = smax
  let step = smax * 0.01
  while s > smax * 0.72 and measure(make(s, t)).width > width * 0.98 { s -= step }
  if measure(make(s, t)).width <= width * 0.98 { s }
  else { fit(make, t, words-of(t), width, multi-h, smax * 0.86, smin) }
}

// Title size: for each line count n, find the largest size that fits in n
// lines; then pick the n with the best size after a penalty for more lines.
// Similar titles get similar treatment, and short titles stay on few lines.
#let fit-title(make, t, width, height, smax, smin) = {
  let ws = words-of(t)
  let penalty = (1.0, 0.95, 0.85, 0.76, 0.68, 0.6)
  let lines-at(s) = {
    let one = measure(make(s, "Hg")).height
    let h = measure(block(width: width, make(s, t))).height
    calc.round((h - one) / (one + 0.24 * s)) + 1
  }
  let best = smin
  let score = 0pt
  for (i, pen) in penalty.enumerate() {
    let n = i + 1
    let s = smax
    let step = smax / 60
    while s > smin and (lines-at(s) > n or measure(block(width: width, make(s, t))).height > height
        or ws.any(w => measure(make(s, w)).width > width * 0.98)) { s -= step }
    s = calc.max(s, smin)
    if lines-at(s) <= n and s * pen > score { score = s * pen; best = s }
  }
  best
}

#let title-make(fill) = (s, t) => text(
  font: display, weight: 600, size: s, fill: fill, hyphenate: false, number-type: "lining",
  par(leading: 0.24em, justify: false, linebreaks: "simple", t),
)
#let sub-make(fill) = (s, t) => text(
  font: display, style: "italic", weight: 500, size: s, fill: fill, hyphenate: false,
  par(leading: 0.3em, justify: false, t),
)
#let author-make(fill) = (s, t) => text(
  font: display, weight: 600, size: s, fill: fill, tracking: 0.14em, hyphenate: false, number-type: "lining",
  par(leading: 0.35em, justify: false, upper(t)),
)
// Letter-spaced line, centred: tracking adds space after the last letter too,
// so pull it back.
#let spaced(t, track) = [#t#h(-track)]

#let title-stack(d, u, k, tw, title-h, title-max, title-min, sub-max, sub-min, sub-h) = {
  let tm = title-make(parchment)
  let ts = fit-title(tm, d.title, tw, title-h, title-max, title-min)
  let title = align(center, block(width: balanced(tm(ts, d.title), tw), tm(ts, d.title)))
  let parts = (title,)
  if d.at("subtitle", default: "") != "" {
    let sm = sub-make(gold-hi)
    let ss = fit-line-first(sm, d.subtitle, tw * 0.9, sub-h, sub-max, sub-min)
    parts.push(v(0.30 * u))
    parts.push(align(center, diamond-rule(1.5 * u, gold-lo, k)))
    parts.push(v(0.26 * u))
    parts.push(align(center, block(width: tw * 0.9, text(lang: d.at("subtitle_lang", default: "la"), sm(ss, d.subtitle)))))
  } else {
    parts.push(v(0.34 * u))
    parts.push(align(center, diamond-rule(1.5 * u, gold-lo, k)))
  }
  block(width: tw, stack(..parts))
}

#let author-stack(d, u, k, aw, amax, amin) = {
  let am = author-make(parchment)
  let asz = fit-line-first(am, d.author, aw, amax * 2.9, amax, amin)
  let parts = (align(center, block(width: aw, am(asz, d.author))),)
  if d.at("author_dates", default: "") != "" {
    parts.push(v(0.13 * u))
    parts.push(align(center, text(font: display, style: "italic", weight: 500, size: 14.5pt * k, fill: gold-hi, number-type: "lining", d.author_dates)))
  }
  block(width: aw, stack(..parts))
}

#let frame(w, h, u, k, inset1, inset2) = {
  place(top + left, dx: inset1, dy: inset1,
    rect(width: w - 2 * inset1, height: h - 2 * inset1, stroke: 0.9pt * k + gold-lo))
  place(top + left, dx: inset2, dy: inset2,
    rect(width: w - 2 * inset2, height: h - 2 * inset2, stroke: 0.35pt * k + gold-lo.transparentize(40%)))
  for (x, y) in ((inset1, inset1), (w - inset1, inset1), (inset1, h - inset1), (w - inset1, h - inset1)) {
    place(top + left, dx: x - 3.2pt * k, dy: y - 3.2pt * k,
      rotate(45deg, rect(width: 6.4pt * k, height: 6.4pt * k, fill: gold-lo)))
  }
}

#let ground(era, w, h) = rect(
  width: w, height: h, stroke: none,
  fill: gradient.radial(era.mid, era.deep, center: (50%, 40%), radius: 80%),
)

// Portrait cover, 2:3 (6 x 9 in by default).
#let cover-portrait(d, w: 6in, h: 9in) = context {
  let u = w / 6
  let k = u / 1in
  let era = eras.at(d.at("era", default: "early"))
  block(width: w, height: h, clip: true, {
    place(top + left, ground(era, w, h))
    frame(w, h, u, k, 0.30 * u, 0.40 * u)
    place(top + center, dy: 0.80 * u, cross(0.42 * u, gold-hi))
    place(top + center, dy: 1.42 * u,
      text(font: display, weight: 600, size: 12pt * k, fill: gold-hi, tracking: 0.42em, spaced([VIA PATRUM], 0.42em)))
    // Title + subtitle, centred in the band between the mast and the author.
    let tw = 4.4 * u
    let band-top = 2.05 * u
    let band-h = 4.75 * u
    let ts = title-stack(d, u, k, tw, 3.35 * u, 62pt * k, 20pt * k, 19pt * k, 10pt * k, 0.95 * u)
    let th = measure(ts).height
    place(top + center, dy: band-top + calc.max(0pt, (band-h - th) / 2) - 0.1 * u, ts)
    // Author + dates, anchored low.
    let ab = author-stack(d, u, k, 4.6 * u, 17pt * k, 9.5pt * k)
    let ah = measure(ab).height
    place(top + center, dy: 7.95 * u - ah, ab)
  })
}

// Square cover for audiobooks (5.25 in, rendered at 1400 px).
#let cover-square(d, s: 5.25in) = context {
  let u = s / 6
  let k = u / 1in
  let era = eras.at(d.at("era", default: "early"))
  block(width: s, height: s, clip: true, {
    place(top + left, ground(era, s, s))
    frame(s, s, u, k, 0.26 * u, 0.35 * u)
    place(top + center, dy: 0.62 * u, cross(0.36 * u, gold-hi))
    place(top + center, dy: 1.13 * u,
      text(font: display, weight: 600, size: 11pt * k, fill: gold-hi, tracking: 0.42em, spaced([VIA PATRUM], 0.42em)))
    let tw = 4.7 * u
    let band-top = 1.55 * u
    let band-h = 2.75 * u
    let ts = title-stack(d, u, k, tw, 1.95 * u, 50pt * k, 17pt * k, 16pt * k, 9pt * k, 0.55 * u)
    let th = measure(ts).height
    place(top + center, dy: band-top + calc.max(0pt, (band-h - th) / 2), ts)
    let ab = author-stack(d, u, k, 4.8 * u, 15.5pt * k, 9pt * k)
    let ah = measure(ab).height
    place(top + center, dy: 5.35 * u - ah, ab)
  })
}
