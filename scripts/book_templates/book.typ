// Via Patrum PDF book, 6 x 9 in trim.
//
// Reads one book's data (written by scripts/build_ebooks.py) from
// sys.inputs.data. Order: cover, half-title, title page, copyright page,
// contents, About this text, then the text. Running heads carry the author
// (verso) and title (recto); opening pages carry none.

#import "cover.typ": cover-portrait, cross, diamond-rule, fit, words-of, balanced, display, serif

#let d = json(sys.inputs.data)

#let ink = rgb("#1e1a15")
#let soft = rgb("#4a4238")
#let rubric = rgb("#a3261b")
#let gold = rgb("#8a6a1f")

#let first-para = d.about.find(b => b.kind == "para")
#set document(
  title: d.title,
  author: d.author,
  keywords: ("Via Patrum", "Church Fathers", d.author),
  description: if first-para != none { first-para.text } else { none },
)
#set text(font: serif, size: 10.5pt, fill: ink, lang: "en", region: "us", hyphenate: true)
#set par(justify: true, leading: 0.66em, spacing: 0.66em, first-line-indent: (amount: 1.25em, all: false))
#set page(
  width: 6in, height: 9in, binding: left,
  margin: (inside: 0.85in, outside: 0.72in, top: 0.92in, bottom: 0.95in),
  header: none, footer: none,
)

#let measure-width = 6in - 0.85in - 0.72in

// ------------------------------------------------------------ headings

#show heading: set text(hyphenate: false, number-type: "lining")
#show heading: set par(linebreaks: "simple")
#show heading.where(level: 1): it => {
  if it.outlined {
    pagebreak(weak: true)
  } else {
    pagebreak(to: "odd", weak: true)
  }
  [#metadata("open") <chapter-open>]
  v(0.95in)
  align(center, cross(0.2in, rubric))
  v(0.22in)
  context {
    let mk = text(font: display, weight: 600, size: 23pt, fill: ink,
      par(justify: false, leading: 0.35em, first-line-indent: 0pt, it.body))
    align(center, block(width: balanced(mk, measure-width * 0.9), mk))
  }
  v(0.16in)
  align(center, diamond-rule(1.1in, gold, 0.9))
  v(0.42in)
}

#show heading.where(level: 2): it => {
  let untitled = it.has("label") and it.label == <untitled>
  let rng = it.supplement
  block(above: 2.2em, below: 1.05em, sticky: true, breakable: false, width: 100%, {
    set align(center)
    set par(justify: false, first-line-indent: 0pt)
    if untitled {
      text(size: 7.8pt, fill: gold, tracking: 0.16em, number-type: "lining", rng)
    } else {
      // Balance the lines so a long title does not leave one word alone.
      context {
        let mk = text(font: display, weight: 600, size: 13.5pt, fill: ink, par(leading: 0.42em, it.body))
        block(width: balanced(mk, measure-width * 0.88), mk)
      }
      if rng != [] {
        v(0.42em, weak: true)
        text(size: 7.2pt, fill: gold, tracking: 0.14em, number-type: "lining", rng)
      }
    }
  })
}

// Section number at the start of a section's first paragraph.
#let sn(n) = box(text(size: 6.6pt, fill: gold, number-type: "lining", baseline: -0.34em, n)) + h(0.3em)

// --------------------------------------------------------- running heads

#let head-text(t) = {
  let mk(s, tr, x) = text(size: s, tracking: tr, fill: soft, number-type: "lining", upper(x))
  let w = measure-width * 0.92
  if measure(mk(7.6pt, 0.14em, t)).width <= w { mk(7.6pt, 0.14em, t) }
  else if measure(mk(7pt, 0.06em, t)).width <= w { mk(7pt, 0.06em, t) }
  else {
    let ws = words-of(t)
    let n = ws.len()
    while n > 1 and measure(mk(7pt, 0.06em, ws.slice(0, n).join(" ") + "…")).width > w { n -= 1 }
    mk(7pt, 0.06em, ws.slice(0, n).join(" ") + "…")
  }
}

#let running = context {
  let p = here().page()
  let opening = query(<chapter-open>).any(m => m.location().page() == p)
  if not opening {
    align(center, head-text(if calc.even(p) { d.author } else { d.title }))
  }
}

#let folio = context align(center, text(size: 8.5pt, fill: soft, number-type: "lining",
  counter(page).display("1")))

// ----------------------------------------------------------- front matter

#page(margin: 0pt, cover-portrait(d))
#page[]

// Half-title.
#page[
  #v(2.2in)
  #align(center, block(width: 80%, text(font: display, weight: 600, size: 18pt,
    par(justify: false, leading: 0.4em, first-line-indent: 0pt, d.title))))
]
#page[]

// Title page.
#page[
  #set par(justify: false, first-line-indent: 0pt)
  #align(center)[
    #v(0.2in)
    #cross(0.24in, rubric)
    #v(0.1in)
    #text(font: display, weight: 600, size: 10pt, tracking: 0.42em, fill: gold)[VIA PATRUM#h(-0.42em)]
  ]
  #v(1.15in)
  #context {
    let tw = measure-width
    let tm(s, t) = text(font: display, weight: 600, size: s, fill: ink, par(leading: 0.3em, t))
    let ts = fit(tm, d.title, words-of(d.title), tw, 2.1in, 34pt, 17pt)
    align(center, block(width: tw, tm(ts, d.title)))
    if d.subtitle != "" {
      v(0.16in)
      align(center, block(width: tw * 0.9, text(font: display, style: "italic", weight: 500, size: 14pt,
        fill: soft, lang: d.subtitle_lang, d.subtitle)))
    }
  }
  #v(0.3in)
  #align(center, diamond-rule(1.3in, gold, 1))
  #v(0.3in)
  #align(center)[
    #text(font: display, weight: 600, size: 13pt, tracking: 0.14em, upper(d.author))
    #if d.author_dates != "" [
      #v(0.04in)
      #text(font: display, style: "italic", weight: 500, size: 12pt, fill: soft, number-type: "lining", d.author_dates)
    ]
  ]
  #v(1fr)
  #align(center, text(size: 8.5pt, fill: soft, tracking: 0.08em)[viapatrum.org])
]

// Copyright page: same lines as the EPUB colophon.
#page[
  #set par(justify: false, first-line-indent: 0pt, spacing: 0.5em, leading: 0.5em)
  #set text(size: 8.3pt, fill: soft)
  #v(1fr)
  #text(font: display, weight: 600, size: 12pt, fill: ink, number-type: "lining", d.title)
  #if d.subtitle != "" [ \ #text(style: "italic", lang: d.subtitle_lang, d.subtitle) ]
  #v(0.3em)
  #(d.author + if d.author_dates != "" { " (" + d.author_dates + ")" } else { "" }) \
  #if d.period != "" [Date of the work: #d.period \ ]
  #if d.edition != "" [Source: #d.edition \ ]
  #if d.original_english != "" [#d.original_english \ ]
  #v(0.9em)
  #for n in d.notes [#n #parbreak()]
  #v(0.6em)
  Read this work free online: \
  #link(d.url)[#text(fill: ink, d.url)]
  #v(0.9em)
  Via Patrum · viapatrum.org · this edition built #d.built \
  #text(size: 7.4pt)[Set in Literata and Cormorant Garamond, both under the SIL Open Font License.]
]

// Contents.
#page[
  #[#metadata("open") <chapter-open>]
  #v(0.5in)
  #align(center, text(font: display, weight: 600, size: 20pt)[Contents])
  #v(0.1in)
  #align(center, diamond-rule(0.9in, gold, 0.9))
  #v(0.3in)
  #set par(justify: false, first-line-indent: 0pt)
  #set text(hyphenate: false, number-type: "lining")
  #show outline.entry: it => {
    let size = if it.level == 1 { 11.5pt } else { 8.8pt }
    let row(body) = link(it.element.location(), grid(columns: (1fr, 2.1em), align: (left, right + bottom),
      par(hanging-indent: 1.1em, leading: 0.5em,
        [#body#box(width: 1fr, inset: (left: 0.35em), repeat(gap: 0.2em)[.])]),
      text(font: serif, weight: 400, size: 8.8pt, it.page())))
    if it.level == 1 {
      block(above: 1.1em, below: 0.7em, text(font: display, weight: 600, size: size, row(it.body())))
    } else {
      block(spacing: 0.62em, pad(left: 0.9em, text(size: size,
        row(it.body()))))
    }
  }
  #outline(title: none, depth: 2, indent: 1em)
]

// About this text.
#heading(level: 1, outlined: false, bookmarked: true)[About this text]
#{
  set par(first-line-indent: 0pt, spacing: 0.75em)
  let sub(t) = {
    v(0.9em)
    align(center, text(size: 7.8pt, tracking: 0.16em, fill: gold, upper(t)))
    v(0.35em)
  }
  for b in d.about {
    if b.kind == "banner" {
      align(center, block(width: 88%, par(justify: false, text(style: "italic", fill: soft, b.text))))
      v(0.4em)
    } else if b.kind == "heading" {
      sub(b.text)
    } else if b.kind == "list" {
      list(indent: 0.3em, spacing: 0.55em, marker: text(fill: gold)[◆],
        ..b.items.map(it => {
          if it.role != "" { text(fill: soft, smallcaps(it.role)); h(0.4em) }
          it.text
          if it.extra != "" { h(0.3em); text(size: 9pt, fill: soft, it.extra) }
        }))
    } else {
      par(b.text)
    }
  }
  if d.intro.len() > 0 {
    sub("Introduction")
    for p in d.intro { par(p) }
  }
  if d.author_bio != "" {
    sub("About the author")
    par[#smallcaps(d.author)#if d.author_dates != "" [ (#d.author_dates)]. #d.author_bio]
  }
}

// ------------------------------------------------------------------ text

#pagebreak(to: "odd")
#set page(numbering: "1", header: running, footer: folio)
#counter(page).update(1)

#for (pi, part) in d.parts.enumerate() {
  heading(level: 1, if part.title != "" { part.title } else { d.title })
  for ch in part.chunks {
    if ch.title == "" {
      [#heading(level: 2, supplement: [#ch.range], ch.label) <untitled>]
    } else {
      heading(level: 2, supplement: [#ch.range], ch.title)
    }
    if ch.supplied.len() > 0 and ch.supplied.dedup().len() == 1 {
      par(first-line-indent: 0pt, text(style: "italic", size: 9.5pt, fill: soft, ch.supplied.at(0)))
    }
    for s in ch.sections {
      for (i, p) in s.paras.enumerate() {
        if i == 0 { sn(s.n) }
        p
        parbreak()
      }
    }
  }
}
