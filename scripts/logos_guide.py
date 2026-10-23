"""How to add the Via Patrum Word files to Logos: one text, three places.

The /downloads/logos/ page, the guide inside the all-books Word zip, and the
README in each book's zip all read from here, so the steps cannot drift
apart (the old README and the Downloads FAQ named different menus).
Menu names checked in Logos 54 on the Mini, 2026-10-14: the Tools button
in the left toolbar opens a panel with a search box; Personal Books has
"Add book", and each row shows "Last built" once built. Logos support
(article 360015926452) gives the same path. Personal Books need the
desktop app (Mac or Windows); they cannot be built on mobile or the web.
"""
from __future__ import annotations

import csv
import html
import io
import zipfile
from pathlib import Path

PAGE_URL = "https://viapatrum.org/downloads/logos/"
CSV_NAME = "books.csv"
GUIDE_NAME = "HOW TO ADD TO LOGOS.txt"

OPEN_TOOL = ("In Logos, click Tools in the toolbar and open Personal Books. "
             "You can type \"Personal Books\" in the box at the top of the Tools panel.")

ONE_BOOK = [
    "Unzip the book. Its folder holds the Word file, cover.jpg and description.txt.",
    OPEN_TOOL,
    "Click Add book.",
    "Fill in Title and Authors as the folder name shows them (Author - Title). "
    "Paste the text of description.txt into Description, and choose cover.jpg as the cover image.",
    "Add the Word file from the folder as the book's file.",
    "Click Build book. Logos builds it in about a minute and opens it. "
    "The row then says \"Last built today\".",
]

UPLOAD = ("Optional: click Upload on a built book to have it in Logos on your other "
          "devices signed in to the same account.")

COLLECTION = [
    "Unzip the big zip, then unzip each book's zip inside it. "
    f"{CSV_NAME} lists every book: its zip, folder, Word file, title, authors and description.",
    "Work down the list a few books at a time. Each takes about two minutes by hand.",
    "The Personal Books list re-sorts itself after a build. Find each book by its title and author, "
    "not by its place in the list.",
    "Some titles belong to more than one writer, such as Fragments on John. "
    "Check the author before you build.",
    "A book is done when its row says \"Last built\". If you stop, start again at the first row "
    "that does not.",
]

PROBLEMS = [
    ("Clicking a book opens a different one",
     "The list moved while you clicked. Close it, wait a second for the list to settle, "
     "and click the right row again."),
    ("Rows stop opening when you click them",
     "Quit Logos and open it again. This happens after many edits in one session."),
    ("There is no Build book button",
     "The book has no file yet. Add the Word file from its folder."),
    ("A Scripture reference does not open",
     "Bible references open in your preferred Bible, so you need at least one Bible in your Logos library."),
]


def books(n: int) -> str:
    return f"{n} book" if n == 1 else f"{n} books"


def ai_prompt(n_books: int) -> str:
    """One block a reader can paste to an AI assistant that can use their computer."""
    return f"""Please add the Via Patrum books to Logos Bible Software for me as Personal Books.

Files: a folder with {CSV_NAME} and one zip per book ({books(n_books)}). Unzip every book zip.
Each row of {CSV_NAME} gives: zip, folder, word_file, title, authors, description.

For each row, in order:
1. {OPEN_TOOL}
2. If a row in the Personal Books list already shows this title AND these authors with "Last built", skip it.
3. Click Add book. Set Title = title, Authors = authors, Description = description.
   Set the cover image to cover.jpg in the book's folder. Add word_file from the folder as the book's file.
4. Click Build book and wait until the row shows "Last built" (about a minute).
5. Write the row number to a log file, so the work can resume where it stopped.

Rules:
- Match a book by title and authors together: some titles appear more than once.
- The list re-sorts after each build. Find rows by text, never by remembered position.
- If a click opens the wrong book, close it, wait two seconds and find the row again.
- If rows stop opening, quit Logos, reopen it and continue from the log.
- Do not change or retype the Word files. Do not click Upload unless I ask.
- When done, report how many books were built and list any that failed with the reason.

Guide and help: {PAGE_URL}"""


def guide_text(n_books: int) -> str:
    """The plain-text guide that goes inside the all-books Word zip."""
    def numbered(items):
        return "\n".join(f"{i}. {s}" for i, s in enumerate(items, 1))
    probs = "\n".join(f"- {q}: {a}" for q, a in PROBLEMS)
    return f"""Adding Via Patrum to Logos Bible Software
{PAGE_URL}

You need the Logos desktop app (Mac or Windows). Personal Books cannot be built on mobile or the web.

ONE BOOK (about 2 minutes)
{numbered(ONE_BOOK)}
{UPLOAD}

THE WHOLE COLLECTION ({books(n_books)})
{numbered(COLLECTION)}

LET AN AI ASSISTANT DO IT
If you use an AI assistant that can operate your computer, give it this:

{ai_prompt(n_books)}

PROBLEMS
{probs}

Questions: hi@saneapps.com
"""


def readme_text() -> str:
    """The README inside each book's zip."""
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(ONE_BOOK[1:], 1))
    return f"""Word file for Logos Bible Software, from Via Patrum (viapatrum.org).

To add this book to Logos (desktop app, Mac or Windows):

{steps}

{UPLOAD}
Adding many books, or letting an AI assistant do it: {PAGE_URL}

The English is the same as on the site. Scripture references are linked, so
a click opens the passage in your Bible in Logos. Each passage is a Headword
article, so it can be found by its title.

The fresh English translation is copyright 2026 SaneApps (CC BY 4.0). The
source text is public domain.
"""


def books_csv(zips: list[tuple[Path, str]]) -> str:
    """books.csv for the all-books zip, read from the book zips themselves so
    every name matches what the reader unzips."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["zip", "folder", "word_file", "title", "authors", "description"])
    for path, arc in sorted(zips, key=lambda x: x[1].lower()):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            docx = next((n for n in names if n.endswith(".docx")), "")
            folder = docx.split("/")[0] if "/" in docx else ""
            desc_name = next((n for n in names if n.endswith("/description.txt")), "")
            desc = z.read(desc_name).decode("utf-8").strip() if desc_name else ""
        authors, _, title = folder.partition(" - ")
        w.writerow([arc, folder, docx.split("/")[-1], title or folder, authors, desc])
    return out.getvalue()


def page_body(n_books: int, bundle: str = "") -> str:
    """Body HTML for /downloads/logos/. bundle: the all-Word zip's button text
    on the shelf, so the guide names the button readers see (2026-10-23:
    it named "Every book for Logos (Word)" while the shelf said "All 263
    Word books for Logos")."""
    e = html.escape
    def ol(items):
        return "<ol>" + "".join(f"<li>{e(s)}</li>" for s in items) + "</ol>"
    probs = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in PROBLEMS)
    return f"""<div class="dl-guide">
<section class="hero">
  <p class="kicker">Downloads</p>
  <h1>Add Via Patrum to Logos</h1>
  <p class="lede">Every Word file is ready to build as a Logos Personal Book, with its cover, description and linked
  Scripture. You need the Logos desktop app (Mac or Windows); Personal Books cannot be built on mobile or the web.</p>
</section>

<section aria-labelledby="lg-one">
  <h2 id="lg-one">One book, about two minutes</h2>
  {ol(ONE_BOOK)}
  <p>{e(UPLOAD)}</p>
</section>

<section aria-labelledby="lg-all">
  <h2 id="lg-all">The whole collection, {books(n_books)}</h2>
  <p>{f"Download <strong>{e(bundle)}</strong> from the" if bundle else "Download the Word books from the"} <a href="/downloads/#shelf">shelf</a>. By hand it takes
  about two minutes a book, so most people spread it over several sittings.</p>
  {ol(COLLECTION)}
</section>

<section aria-labelledby="lg-ai">
  <h2 id="lg-ai">Let an AI assistant do it</h2>
  <p>An AI assistant that can operate your computer can work through the list for you. Unzip the files, then paste
  this to it. The same text is in <code>{e(GUIDE_NAME)}</code> inside the zip.</p>
  <div class="lg-prompt">
    <button type="button" class="dl-textbtn" data-copy-prompt>Copy instructions</button>
    <pre id="lg-prompt-text">{e(ai_prompt(n_books))}</pre>
  </div>
</section>

<section class="dl-faq" aria-labelledby="lg-help">
  <h2 id="lg-help">Problems</h2>
  {probs}
  <details><summary>Something else</summary><p>Write to hi@saneapps.com and say which book and what you see.</p></details>
</section>
</div>
"""
