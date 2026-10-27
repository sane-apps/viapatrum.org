"""Did Christ die for all? A history of the question (/history/christ-died-for-all/).

Owner approved 2026-10-27 (preview first; going live needs his own yes).
Built from the draft at /workspace/viapatrum/christ-died-for-all-history-DRAFT-2026-10-27.md.

Rules kept here:
* A quotation is shown only if the draft marks it VERIFIED (exact match to a
  public-domain text, or matched to a scanned page). The nine quotations the
  draft marks as needing verification are not in data/history/*.json at all.
  Where a whole topic depends on them, the page says "Under review" instead.
* The words are copied from the draft and never edited. The quotations are from
  public-domain English texts. None is copied from @RefRetrieval.
* No em dashes and no en dashes anywhere on the page (owner rule 2026-10-27).
* The fairness box says what the page claims and does not claim.

Called from build_site.py as build(dist, layout, write); the page sits under the
Timeline (crumbs Home / Timeline / Did Christ die for all?) with no nav item.
"""
import json
from html import escape
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "history" / "christ-died-for-all-quotes.json"
SLUG = "christ-died-for-all"
URL = f"/history/{SLUG}/"
TITLE = "Did Christ die for all?"
SUBTITLE = "A history of the question"
# Under the 158-character snippet limit, so it never ends in "...".
DESCRIPTION = ("How Christians have answered it: Scripture, the early Church, the Reformers and "
               "the Reformed debate, with quotes in their own words and a short timeline.")
OG_CARD = SLUG

# Scripture is the King James Version (public domain). Text copied from the draft.
WIDE = [
    ("John 3:16", "For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life."),
    ("1 John 2:1-2", "And if any man sin, we have an advocate with the Father, Jesus Christ the righteous: And he is the propitiation for our sins: and not for ours only, but also for the sins of the whole world."),
    ("2 Corinthians 5:14-15", "For the love of Christ constraineth us; because we thus judge, that if one died for all, then were all dead: And that he died for all, that they which live should not henceforth live unto themselves, but unto him which died for them, and rose again."),
    ("1 Timothy 2:3-6", "For this is good and acceptable in the sight of God our Saviour; Who will have all men to be saved, and to come unto the knowledge of the truth. For there is one God, and one mediator between God and men, the man Christ Jesus; Who gave himself a ransom for all, to be testified in due time."),
    ("1 Timothy 4:10", "...we trust in the living God, who is the Saviour of all men, specially of those that believe."),
    ("Hebrews 2:9", "But we see Jesus, who was made a little lower than the angels for the suffering of death, crowned with glory and honour; that he by the grace of God should taste death for every man."),
    ("2 Peter 2:1", "...false teachers among you, who privily shall bring in damnable heresies, even denying the Lord that bought them, and bring upon themselves swift destruction."),
]
WIDE_ALSO = "Also often cited: John 1:29 (\u201cthe Lamb of God, which taketh away the sin of the world\u201d), Romans 5:18, Titus 2:11 and 2 Peter 3:9."
PARTICULAR = [
    ("John 10:11 and 10:26-28", "\u201cI am the good shepherd: the good shepherd giveth his life for the sheep.\u201d ... \u201cBut ye believe not, because ye are not of my sheep... And I give unto them eternal life; and they shall never perish.\u201d"),
    ("Ephesians 5:25", "\u201c...Christ also loved the church, and gave himself for it.\u201d"),
    ("Matthew 1:21", "\u201c...thou shalt call his name JESUS: for he shall save his people from their sins.\u201d"),
    ("Matthew 20:28", "\u201c...to give his life a ransom for many.\u201d"),
    ("John 17:9", "\u201cI pray for them: I pray not for the world, but for them which thou hast given me.\u201d"),
    ("Acts 20:28 and Romans 8:32-34", "The church \u201cwhich he hath purchased with his own blood\u201d; \u201cHe that spared not his own Son, but delivered him up for us all... Who shall lay any thing to the charge of God's elect?\u201d"),
    ("Isaiah 53:12 and Hebrews 9:28", "\u201che bare the sin of many\u201d; \u201cChrist was once offered to bear the sins of many.\u201d"),
]

# Timeline. Dates come from the quotation headings, from the site's own author and
# creed pages (data/author-dates.json, data/explore/creeds.json) or are lifespans.
# Nothing the draft marks as needing verification is listed.
TIMELINE = [
    ("Late 1st century", "Clement of Rome writes to the church at Corinth", "#quotes-before"),
    ("2nd century", "Justin Martyr writes his Dialogue with Trypho", "#quotes-before"),
    ("300s and early 400s", "Athanasius, Ambrose and John Chrysostom write", "#quotes-before"),
    ("354 to 430", "Augustine of Hippo", "#augustine"),
    ("428 or 429", "Augustine writes On the Predestination of the Saints", "#augustine"),
    ("1225 to 1274", "Thomas Aquinas, author of the Summa Theologiae", "#aquinas"),
    ("1509 to 1564", "John Calvin", "#calvin"),
    ("1563", "The Heidelberg Catechism", "#heidelberg"),
    ("1566", "The Second Helvetic Confession", "#helvetic"),
    ("1592", "The Saxon Visitation Articles (Lutheran)", "#lutherans"),
    ("1610", "The Remonstrance, the five points of Arminius's followers", "#dort"),
    ("1618 to 1619", "The Synod of Dort answers them", "#dort"),
    ("1643 to 1649", "The Westminster Assembly; the Confession is completed in 1646", "#westminster"),
    ("1647", "John Owen publishes The Death of Death in the Death of Christ", "#owen"),
    ("1650", "John Davenant's Two Dissertations are printed at Cambridge", "#dort"),
]

# Short plain notes where a topic waits on checking. They name no position.
REVIEW = {
    "early": ("Two early debates are still being checked against the original Latin: Prosper of Aquitaine "
              "and the monks of southern Gaul in the fifth century, and the dispute over Gottschalk in the ninth. "
              "We do not quote them yet."),
    "medieval": ("Peter Lombard's own wording of the \u201csufficient for all\u201d saying, in his Sentences (about the 1150s), "
                 "is being checked against a printed edition, so we do not quote it."),
    "luther": ("Martin Luther, Philip Melanchthon, Heinrich Bullinger, Martin Bucer and Girolamo Zanchi: we are "
               "checking their own words and the translations before we quote or summarise them."),
    "reformed": ("Theodore Beza (Calvin's successor in Geneva): we are checking his own words before we say what he taught."),
    "saumur": ("John Cameron, Moïse Amyraut and Jean Daillé at Saumur in France: we are checking the original texts "
               "and the church synods that dealt with them. We do not quote or summarise them yet."),
    "helvetic": ("The Formula Consensus Helvetica (Switzerland, 1675): we are checking it against the Latin."),
    "dominant": ("Why the strict view became the main one in many churches: the reasons historians give are still being checked."),
}


def load_quotes(path: Path = DATA) -> dict[str, dict]:
    qs = json.loads(path.read_text(encoding="utf-8"))["quotes"]
    for q in qs:
        assert q["draft_tag"].startswith("VERIFIED ("), q["id"]
        assert q["url"].startswith("https://"), q["id"]
    return {q["id"]: q for q in qs}


def ext(href: str, label: str) -> str:
    assert href.startswith("https://"), href
    return f'<a href="{escape(href)}" rel="noopener">{escape(label)}</a>'


def quote(q: dict, dist: Path, note: str = "") -> str:
    au = escape(q["author"])
    if q["author_slug"] and (dist / "authors" / q["author_slug"] / "index.html").is_file():
        au = f'<a href="/authors/{escape(q["author_slug"])}/">{au}</a>'
    where = ", ".join(escape(x) for x in (q["work"], q["loc"]) if x)
    ed = escape(q["edition"])
    scan = " Checked against a scan of the printed book." if q["check"] == "scan" else ""
    extra = f" {escape(note)}" if note else ""
    return (f'<figure class="hp-quote" id="{escape(q["id"])}"><blockquote>{escape(q["text"])}</blockquote>'
            f'<figcaption>{au}, <cite>{where}</cite>. {ed}.{scan}{extra} {ext(q["url"], "Read the source")}</figcaption></figure>')


def review(key: str) -> str:
    return f'<aside class="hp-review"><p><strong>Under review.</strong> {escape(REVIEW[key])}</p></aside>'


def passages(rows: list[tuple[str, str]], quoted: bool = False) -> str:
    """Each row is (reference, text). KJV rows are wrapped in quotation marks here;
    the particular-people rows already carry theirs."""
    wrap = (lambda t: "\u201c" + t + "\u201d") if quoted else (lambda t: t)
    return '<ul class="hp-verses">' + "".join(
        f"<li><strong>{escape(ref)}.</strong> {escape(wrap(t))}</li>" for ref, t in rows) + "</ul>"


def build_body(qs: dict[str, dict], dist: Path) -> str:
    def Q(*ids, note=""):
        return "".join(quote(qs[i], dist, note if k == 0 else "") for k, i in enumerate(ids))

    def link_if(path: str, href: str, label: str) -> str:
        return f'<a href="{href}">{escape(label)}</a>' if (dist / path.strip("/") / "index.html").is_file() else escape(label)

    timeline = "".join(
        f'<li><span class="hp-when">{escape(w)}</span><a class="hp-what" href="{href}">{escape(what)}</a></li>'
        for w, what, href in TIMELINE)

    davenant_work = link_if("/works/davenant-dissertationes-duae/", "/works/davenant-dissertationes-duae/",
                            "Davenant\u2019s Two Dissertations (1650)")
    davenant_related = link_if("/works/davenant-dissertationes-duae/", "/works/davenant-dissertationes-duae/",
                               "Davenant\u2019s Two Dissertations (1650): the opening chapters in fresh English")
    related = [
        link_if("/topics/atonement-recapitulation/", "/topics/atonement-recapitulation/", "Christ Undoes Adam\u2019s Fall: what the early Fathers taught about Christ\u2019s work"),
        link_if("/topics/salvation-by-christ/", "/topics/salvation-by-christ/", "Salvation in Christ"),
        link_if("/topics/universal-call/", "/topics/universal-call/", "The gospel call to everyone, and why some turn it down"),
        link_if("/explore/god-want-everyone-saved/", "/explore/god-want-everyone-saved/", "Does God want everyone to be saved? What the early writers said"),
        link_if("/explore/god-choose-will-saved-before/", "/explore/god-choose-will-saved-before/", "Does God choose who will be saved before they are born?"),
        link_if("/creeds/", "/creeds/#c-dort-1619", "The Canons of Dort on the Creeds and churches page"),
        link_if("/creeds/", "/creeds/#c-westminster-1646", "The Westminster Confession on the Creeds and churches page"),
        link_if("/creeds/", "/creeds/#c-heidelberg-1563", "The Heidelberg Catechism on the Creeds and churches page"),
        davenant_related,
    ]
    related_html = "".join(f"<li>{r}</li>" for r in related)

    return f"""
<header class="hp-head">
  <p class="eyebrow">Timeline</p>
  <h1>{escape(TITLE)}</h1>
  <p class="hp-sub">{escape(SUBTITLE)}</p>
  <p class="intro">This page follows one question through church history: for whom did Christ die? It has four parts: Scripture, the early Church, the Reformers, and the Reformed debate after 1550. Each quotation names its author, its work and the place in the work, and links to the text it was checked against.</p>
  <nav class="hp-jump" aria-label="On this page"><a href="#fair">What this page claims</a><a href="#timeline">Short timeline</a><a href="#scripture">1. Scripture</a><a href="#early">2. The early Church</a><a href="#reformers">3. The Reformers</a><a href="#debate">4. The Reformed debate</a><a href="#supports">What the history shows</a></nav>
</header>

<section class="hp-fair" id="fair" aria-labelledby="fair-h">
  <h2 id="fair-h">What this page claims, and what it does not</h2>
  <p><strong>It claims</strong> that many respected Christian teachers, including many Reformed theologians, taught that Christ died for all people in some real sense. They said this while holding that only some are finally saved. Their wording differs, and some of it is careful and technical.</p>
  <p><strong>It does not claim:</strong></p>
  <ul>
    <li>that every Reformed theologian rejected strict limited atonement. Many held it, and it became the main Reformed view;</li>
    <li>that the Synod of Dort (1618 to 1619) or the Westminster Assembly (1643 to 1649) rejected unconditional election or any other of the five points. They kept election, and the Canons of Dort say plainly that Christ&#8217;s saving work was for the elect &#8220;and those only&#8221; (Canons II.8, quoted in Part 4);</li>
    <li>that the writers quoted here were Arminians. Most were not. Several wrote against Arminius.</li>
  </ul>
  <p>The question traced here is narrow. It is about how far Christ&#8217;s death reaches and what God meant by it. It is not about whether election is unconditional.</p>
  <p class="hp-fine">Scripture is quoted from the King James Version. Chapter and section numbers follow the online public-domain texts named under each quotation. Quotations still being checked are left out and marked &#8220;Under review.&#8221;</p>
</section>

<section class="hp-section" id="timeline" aria-labelledby="timeline-h">
  <h2 id="timeline-h">Short timeline</h2>
  <ol class="hp-timeline">{timeline}</ol>
</section>

<section class="hp-section" id="scripture" aria-labelledby="scripture-h">
  <h2 id="scripture-h"><span>Part 1</span> Scripture</h2>
  <h3>Two questions that are easy to confuse</h3>
  <ol class="hp-two">
    <li><strong>Reach.</strong> Did Christ die in some real sense for every person, so that forgiveness is truly offered to every person on the ground of his death?</li>
    <li><strong>Purpose.</strong> Did Christ die with the aim of actually saving every person, or only those whom God has chosen?</li>
  </ol>
  <p>Almost no one in this history says that Christ&#8217;s death saves every person automatically. Nearly everyone agrees that his death has great worth, enough for the whole world. The disagreement is mostly about purpose: what God and Christ meant to accomplish by the cross.</p>

  <h3>Passages that speak of the whole world or all people</h3>
  <p>These are the passages most often cited by those who say Christ died for all.</p>
  {passages(WIDE, quoted=True)}
  <p class="hp-fine">{escape(WIDE_ALSO)}</p>

  <h3>Passages that speak of a particular people</h3>
  <p>These are the passages most often cited by those who say Christ died with the purpose of saving a chosen people.</p>
  {passages(PARTICULAR)}

  <h3>How each side reads the other&#8217;s passages</h3>
  <div class="hp-sides">
    <div><h4>Christ died for all</h4><p>Those who say this point out that &#8220;world&#8221; and &#8220;all&#8221; appear often, that 2 Corinthians 5:14-15 reasons from &#8220;one died for all,&#8221; and that the offer of the gospel to everyone seems to need something real to offer. They answer the particular passages by saying that Christ may die for the whole world and also love his church in a special way. Scripture says the shepherd lays down his life for the sheep, but it does not say he laid it down for the sheep only. Davenant&#8217;s argument in Part 4 is of this kind: the special benefit for the elect is added to the universal remedy.</p></div>
    <div><h4>Christ died for the elect</h4><p>Those who say this point out that the same death is said to secure salvation, to justify and to reconcile, and that it would be strange for Christ to die for people who are in the end lost. They answer the universal passages by saying that &#8220;world&#8221; can mean people from every nation, and &#8220;all&#8221; can mean all kinds of people. Augustine reads 1 Timothy 2:4 this way, and Calvin does too (Parts 2 and 3). John Owen takes up the main texts one by one in <em>The Death of Death</em>.</p></div>
  </div>
  <p>Both sides agree on this: the gospel is to be preached to everyone, and no one who comes in faith will be turned away.</p>
</section>

<section class="hp-section" id="early" aria-labelledby="early-h">
  <h2 id="early-h"><span>Part 2</span> The early Church</h2>
  <p class="hp-summary">In the samples below, the earliest writers use wide language: Christ died &#8220;for all,&#8221; for &#8220;the whole world,&#8221; for &#8220;every man.&#8221; They do not stop to ask whether this includes people who will be lost. The question becomes sharp in the fifth century, because of Augustine&#8217;s teaching on predestination. Augustine is not easy to place. He wrote some of the widest statements and some of the narrowest. Both are given below.</p>

  <h3 id="quotes-before">Before Augustine</h3>
  {Q("q1", "q2", "q3", "q4", "q5")}
  <p>Ambrose has another line, in a different work, that is often used for the opposite view:</p>
  {Q("q6")}
  <p>Both lines are Ambrose&#8217;s. In context the second is spoken to a person who hears the gospel and will not believe it. How to fit the two together is part of the long debate.</p>
  <p class="hp-fine">These are samples, not a full survey of the second to fourth centuries. Irenaeus, Origen and others are still to be added. For what the early writers taught about Christ&#8217;s work, see the related pages at the end.</p>

  <h3 id="augustine">Augustine</h3>
  <p>Augustine matters most here, because later writers on both sides appeal to him.</p>
  <h4>Augustine&#8217;s wide statements</h4>
  {Q("q7", "q8", note="He is arguing against the Donatists, who confined the church to Africa.")}
  {Q("q9")}
  <h4>Augustine&#8217;s narrow statements</h4>
  <p>In his writings against the Pelagians, Augustine reads the universal texts in a limited way. The clearest example is his reading of 1 Timothy 2:4:</p>
  {Q("q10")}
  <p>He goes on to give another sense:</p>
  {Q("q11")}
  <p>He gives the same reading again in <em>On Rebuke and Grace</em>:</p>
  {Q("q12")}
  <p>In his commentary on John 17 he separates two meanings of &#8220;the world&#8221;:</p>
  {Q("q13")}
  <h4>What can be said fairly</h4>
  <p>In <em>On the Spirit and the Letter</em> Augustine says that God truly wishes all men to be saved. In the <em>Enchiridion</em> and <em>On Rebuke and Grace</em> he says the same words in 1 Timothy 2:4 mean that all the predestined are saved, from every kind of person. Readers differ on how these fit together. What the sources do show is that Augustine does not state the later doctrine of &#8220;limited atonement&#8221; in those words. He is speaking mainly about predestination, the gift of grace, and what 1 Timothy 2:4 means.</p>
  {review("early")}
</section>

<section class="hp-section" id="reformers" aria-labelledby="reformers-h">
  <h2 id="reformers-h"><span>Part 3</span> The Middle Ages and the Reformers</h2>

  <h3>&#8220;Sufficient for all, effective for the elect&#8221;</h3>
  <p>Teachers in the Middle Ages summed up the matter in a short saying: Christ&#8217;s death is enough for all, and it actually saves the elect. Calvin knew the saying (see his comment on 1 John 2:2 below) and so did Ursinus. Davenant describes how it spread:</p>
  {Q("q18")}
  {review("medieval")}

  <h3 id="aquinas">Thomas Aquinas</h3>
  <p>Aquinas is a good example of how medieval writers hold the two sides together.</p>
  {Q("q19", "q20", "q21")}
  <p>On the saying that God &#8220;wills all men to be saved&#8221; (1 Timothy 2:4), Aquinas gives three readings. One is Augustine&#8217;s, one is &#8220;all kinds,&#8221; and the third is that God wills it by an <em>antecedent</em> will, a conditional way of willing that is not the last word:</p>
  {Q("q22")}

  <h3>Luther and other early Reformers</h3>
  {review("luther")}

  <h3 id="helvetic">The Second Helvetic Confession</h3>
  <p>The Second Helvetic Confession is Reformed and very firm on election. It also asks us not to judge anyone:</p>
  {Q("q28")}

  <h3 id="heidelberg">The Heidelberg Catechism and Ursinus</h3>
  <p>The Heidelberg Catechism says of Christ&#8217;s suffering:</p>
  {Q("q29")}
  <p>Zacharias Ursinus, traditionally credited as one of its two writers, explained in his commentary how he read it. He uses the same saying, and he is clear that he believes in particular redemption in the matter of effectiveness:</p>
  {Q("q30", "q31")}
  <p>So Ursinus holds both parts together. Christ&#8217;s death is enough for all and is truly offered to all. Its saving effect belongs to the elect. This is the pattern at the heart of Reformed teaching before Dort: <em>sufficient for all, effective for the elect</em>. The disagreements after Dort are about how to read the word &#8220;sufficient.&#8221;</p>

  <h3 id="calvin">Calvin: a disputed case</h3>
  <p>Scholars still disagree about what Calvin believed on the extent of the atonement. This page does not try to settle it. Here is the evidence on both sides, in Calvin&#8217;s own words.</p>
  <h4>Passages used to show that Calvin spoke of Christ dying for all</h4>
  {Q("q32", "q33", "q34", "q35")}
  <h4>Passages used to show that Calvin held Christ&#8217;s work was for the elect</h4>
  {Q("q36", "q37", "q38")}
  <p>In the 1 John 2:2 passage Calvin says the old saying is true, but he does not think it fits John&#8217;s words. He reads &#8220;the whole world&#8221; there as the whole church, believers scattered across the earth. In 1 Timothy 2:4 he reads &#8220;all&#8221; as all ranks and kinds, not each individual. These are choices about how to read a text. The sentences on the other side (John 3:16, Romans 5:18, Mark 14:24) stand in his commentaries too.</p>
  <p>A fair summary is this. Calvin often speaks as if Christ&#8217;s death is offered to and for the world, and he also teaches a strong, particular election. After him, the question had to be settled by others.</p>

  <h3 id="lutherans">The Lutherans, for comparison</h3>
  <p>The Lutheran churches said plainly that Christ died for all. The Saxon Visitation Articles put it first among the points of the &#8220;pure and true doctrine&#8221; on predestination:</p>
  {Q("q39")}
</section>

<section class="hp-section" id="debate" aria-labelledby="debate-h">
  <h2 id="debate-h"><span>Part 4</span> The Reformed debate</h2>
  {review("reformed")}

  <h3 id="dort">The Arminian challenge, and Dort</h3>
  <p>In 1610 the Remonstrants, followers of Arminius, put their views in five articles. The second said:</p>
  {Q("q40")}
  <p>The Synod of Dort (1618 to 1619) answered with the <em>Canons</em>. The Second Head of Doctrine deals with the death of Christ. It holds two things together:</p>
  {Q("q41", "q42", "q43")}
  <p>And on God&#8217;s purpose, the Canons are firm that it is particular:</p>
  {Q("q44")}
  <p>This is the fact to keep in view: <strong>the Canons of Dort teach both a death of infinite worth, enough for the whole world, and a saving purpose that is for the elect &#8220;and those only.&#8221;</strong> They do not say the first is false.</p>

  <h4>John Davenant</h4>
  <p>The Church of England sent delegates to Dort. One was John Davenant (1572 to 1641), a Cambridge theologian and later Bishop of Salisbury. Davenant held that Christ died for all in a sense, and he argued that the Canons allowed this. He explained his view in his <em>Dissertation on the Death of Christ</em>:</p>
  {Q("q45", "q46")}
  <p>Davenant did not deny that Christ had a special purpose for the elect. His point was that this is <em>in addition to</em> the universal remedy, not in place of it. The library holds the opening chapters of his later <em>Two Dissertations</em> in fresh English. Read {davenant_work}.</p>
  <p><strong>The point to be fair about.</strong> Whether the Canons allow Davenant&#8217;s view is itself disputed. Davenant said they did. Others said they did not. This page leaves the Canons&#8217; intent open. It reports that Dort kept unconditional election, and also taught that Christ&#8217;s death is enough for the whole world.</p>

  <h3>Saumur in France</h3>
  {review("saumur")}

  <h3 id="westminster">The Westminster Assembly</h3>
  <p>At the Westminster Assembly (1643 to 1649), English and Scottish ministers drew up the Confession of Faith. It says:</p>
  {Q("q47", "q48", "q49")}
  <p>On the Assembly floor the question was argued. Edmund Calamy, a leading member, said he held the same view as the British at Dort. As recorded by the editor of the Minutes:</p>
  {Q("q50")}
  <p>The editor, Alexander Mitchell, asks whether the ministers left room in the Confession&#8217;s wording for this view. His answer is careful:</p>
  {Q("q51")}

  <h3 id="owen">John Owen, 1647</h3>
  <p>In 1647 John Owen published <em>The Death of Death in the Death of Christ</em>, the fullest defence of strict particular redemption. His best-known argument is a three-way choice:</p>
  {Q("q52")}
  <p>If Christ died for all the sins of all men, Owen says, no one would be lost. If for some sins of all men, everyone would still have sins to answer for. So he concludes that Christ bore all the sins of some. Many have used this argument since.</p>
  <p>Owen also says plainly that Christ&#8217;s death is enough for all:</p>
  {Q("q53")}
  <p>At the same time, he rejects the old saying as it is commonly used:</p>
  {Q("q54")}
  <p>Owen is fair about what he denies. He says the blood of Christ was worth enough, but was not <em>a ransom</em> for those who are lost, since a ransom means a price paid for particular people. This is a main point of difference with Davenant, who held that the price was paid for all on the condition of faith.</p>

  <h3>Later Reformed statements</h3>
  {review("helvetic")}
  {review("dominant")}
</section>

<section class="hp-section" id="supports" aria-labelledby="supports-h">
  <h2 id="supports-h">What this history shows</h2>
  <p>It supports these statements:</p>
  <ol>
    <li>Many respected Christian teachers, from Clement and Ambrose to Aquinas, Ursinus, Davenant, Calamy and others, said that Christ died for all in a sense, or that his death is enough for all, or that the gospel is a real offer to all. Calvin&#8217;s view is disputed, and both sides are shown above.</li>
    <li>Many of those same writers also taught that Christ&#8217;s saving work, in what it actually accomplishes, is for the elect. This was the usual shape of the teaching, not an exception.</li>
    <li>In the early seventeenth century, Reformed teachers disagreed in good faith about whether Dort and the Westminster Confession allowed a universal intention. Some believed they did, and some believed they did not.</li>
    <li>The strict form of limited atonement, as Owen defended it, was one of several Reformed views, and became the main one in many churches.</li>
    <li>Rejecting strict limited atonement was not only an Arminian view. Davenant, for one, defended Christ&#8217;s death for all within a Calvinist frame.</li>
  </ol>
  <p>It does <strong>not</strong> support these statements:</p>
  <ul>
    <li>that all Reformed theologians rejected limited atonement;</li>
    <li>that Dort or Westminster rejected unconditional election, or any other of the five points;</li>
    <li>that Calvin plainly taught a universal atonement. His views are disputed.</li>
  </ul>
</section>

<section class="hp-section" id="related" aria-labelledby="related-h">
  <h2 id="related-h">More on this site</h2>
  <ul class="hp-related">{related_html}</ul>
  <p class="hp-fine">This page is a history of what people taught. It does not rank the churches or tell you what to believe.</p>
</section>
"""


def build(dist: Path, layout, write, data_path: Path = DATA) -> int:
    qs = load_quotes(data_path)
    body = build_body(qs, dist)
    write(dist / "history" / SLUG / "index.html",
          layout(TITLE + " A history", body,
                 crumb=[("Home", "/"), ("Timeline", "/explore/"), (TITLE, "")],
                 active="explore", styles=["/assets/history.css"], og_image=OG_CARD,
                 description=DESCRIPTION))
    return len(qs)
