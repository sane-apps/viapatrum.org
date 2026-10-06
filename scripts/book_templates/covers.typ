// JPEG covers for one book: page 1 portrait (6 x 9 in), page 2 square
// (5.25 in). build_ebooks.py renders both at 266.67 ppi = 1600x2400 and 1400x1400.
#import "cover.typ": cover-portrait, cover-square
#let d = json(sys.inputs.data)
#set text(lang: "en")
#page(width: 6in, height: 9in, margin: 0pt, cover-portrait(d))
#page(width: 5.25in, height: 5.25in, margin: 0pt, cover-square(d))
