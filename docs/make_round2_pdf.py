import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                                Table, TableStyle, PageBreak, KeepTogether)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

TEAM_NAME = "TEAM BATON"
AUTHOR = "Shaik Asad Ahmed"
import argparse
ap = argparse.ArgumentParser()
ap.add_argument("--live", default="(add your deployed link)")
ap.add_argument("--repo", default="(add your repository link)")
ap.add_argument("--team", default="TEAM BATON")
ap.add_argument("--out", default="ContinuityOS_Round2.pdf")
ARGS = ap.parse_args()
TEAM_NAME = ARGS.team
OUT = ARGS.out

import os
FD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts") + os.sep   # bundled DejaVu Sans (free licence)
pdfmetrics.registerFont(TTFont("DV", FD + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DV-B", FD + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DV-I", FD + "DejaVuSans-Oblique.ttf"))
pdfmetrics.registerFont(TTFont("DV-BI", FD + "DejaVuSans-BoldOblique.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-BI")

NAVY = colors.HexColor("#14213D")
TEAL = colors.HexColor("#0F766E")
AMBER = colors.HexColor("#B45309")
LIGHT = colors.HexColor("#F1F5F9")
MID = colors.HexColor("#CBD5E1")
INK = colors.HexColor("#1E293B")

def S(name, **kw):
    base = dict(fontName="DV", fontSize=9, leading=13, textColor=INK, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(name, **base)

body = S("body", spaceAfter=4)
small = S("small", fontSize=7.8, leading=10.5)
cell = S("cell", fontSize=8, leading=10.5)
cellb = S("cellb", fontSize=8, leading=10.5, fontName="DV-B")
cellw = S("cellw", fontSize=8, leading=10.5, fontName="DV-B", textColor=colors.white)
h1 = S("h1", fontName="DV-B", fontSize=15, leading=19, textColor=NAVY, spaceBefore=4, spaceAfter=6)
h2 = S("h2", fontName="DV-B", fontSize=10.5, leading=14, textColor=TEAL, spaceBefore=7, spaceAfter=3)
bul = S("bul", leftIndent=12, bulletIndent=2, spaceAfter=2)
quote = S("quote", fontName="DV-I", fontSize=9.5, leading=14, textColor=NAVY, leftIndent=8, spaceAfter=6)

def P(t, st=body): return Paragraph(t, st)
def B(items): return [Paragraph(i, bul, bulletText="•") for i in items]

def T(rows, widths, header=True, zebra=True):
    data = []
    for r, row in enumerate(rows):
        data.append([Paragraph(str(c), cellw if (header and r == 0) else cell) for c in row])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("GRID", (0, 0), (-1, -1), 0.4, MID),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebra:
        for i in range(1, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(style))
    return t

def callout(text, color=TEAL):
    t = Table([[Paragraph(text, S("co", fontSize=9, leading=13, textColor=INK))]], colWidths=[174 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t

def box(d, x, y, w, h, title, sub, fill):
    d.add(Rect(x, y, w, h, rx=5, ry=5, fillColor=fill, strokeColor=NAVY, strokeWidth=0.8))
    d.add(String(x + w / 2, y + h - 14, title, fontName="DV-B", fontSize=8, fillColor=colors.white, textAnchor="middle"))
    for i, line in enumerate(sub):
        d.add(String(x + w / 2, y + h - 27 - i * 9, line, fontName="DV", fontSize=6.6, fillColor=colors.white, textAnchor="middle"))

def arrow(d, x1, y1, x2, y2):
    d.add(Line(x1, y1, x2, y2, strokeColor=NAVY, strokeWidth=1.2))
    if abs(y2 - y1) < 1:
        s = 1 if x2 > x1 else -1
        d.add(Polygon([x2, y2, x2 - 5 * s, y2 + 3, x2 - 5 * s, y2 - 3], fillColor=NAVY, strokeColor=NAVY))
    else:
        s = 1 if y2 > y1 else -1
        d.add(Polygon([x2, y2, x2 - 3, y2 - 5 * s, x2 + 3, y2 - 5 * s], fillColor=NAVY, strokeColor=NAVY))


def architecture():
    d = Drawing(494, 250)
    w, h = 112, 64
    xs = [2, 128, 254, 380]
    y1, y2 = 168, 76
    box(d, xs[0], y1, w, h, "1 CONNECT", ["Upload txt/md/csv/json", "Chat export, pasted note", "Public GitHub repo", "Redaction before storage"], TEAL)
    box(d, xs[1], y1, w, h, "2 NORMALISE", ["Detect type, chunk", "Per-passage access level", "(secrets/confidential", "language raise it)"], NAVY)
    box(d, xs[2], y1, w, h, "3 EXTRACT", ["Rules extractor (default)", "Optional LLM extractor", "Every claim = statement", "+ verbatim quote"], AMBER)
    box(d, xs[3], y1, w, h, "4 VERIFY", ["Quote must exist in the", "cited passage and support", "the statement; else it is", "stored as Unverified"], TEAL)
    box(d, xs[3], y2, w, h, "5 ANALYSE", ["Merge duplicates", "Conflicts: region, DB,", "provider, deadline, owner", "Gaps, recurring problems"], NAVY)
    box(d, xs[2], y2, w, h, "6 REVIEW", ["Confirm / correct /", "reject / answer gaps", "Resolve conflicts", "Approval gates"], AMBER)
    box(d, xs[1], y2, w, h, "7 VERSION", ["Frozen snapshot per", "approval, diff vs prior", "Explicit share step", "Audit log"], NAVY)
    box(d, xs[0], y2, w, h, "8 HANDOVER", ["Role-filtered on server", "Plan: overdue/24h/week/", "30 days, acknowledge,", "access request, export"], TEAL)
    for i in range(3):
        arrow(d, xs[i] + w, y1 + h / 2, xs[i + 1], y1 + h / 2)
    arrow(d, xs[3] + w / 2, y1, xs[3] + w / 2, y2 + h)
    for i in range(3, 0, -1):
        arrow(d, xs[i], y2 + h / 2, xs[i - 1] + w, y2 + h / 2)
    d.add(Rect(2, 6, 490, 52, rx=5, ry=5, fillColor=LIGHT, strokeColor=MID))
    d.add(String(247, 42, "FastAPI (REST, bearer sessions, role checks on every route)  ·  SQLite (claims, evidence, versions, audit)",
                 fontName="DV-B", fontSize=7.4, fillColor=NAVY, textAnchor="middle"))
    d.add(String(247, 28, "React + Vite single-page app, served by the same FastAPI process in production",
                 fontName="DV", fontSize=7.2, fillColor=INK, textAnchor="middle"))
    d.add(String(247, 14, "Source text is only ever treated as data; secrets never reach the database or a model",
                 fontName="DV-I", fontSize=7.2, fillColor=INK, textAnchor="middle"))
    d.add(String(247, 238, "Data flow of one reconstruction run", fontName="DV-I", fontSize=7.4, fillColor=INK, textAnchor="middle"))
    return d


def footer(canv, doc):
    canv.saveState()
    canv.setFont("DV", 7.5)
    canv.setFillColor(colors.HexColor("#64748B"))
    canv.drawString(18 * mm, 10 * mm, "ContinuityOS · Round 2 – The Build · %s" % TEAM_NAME)
    canv.drawRightString(A4[0] - 18 * mm, 10 * mm, "Page %d" % doc.page)
    canv.setStrokeColor(MID)
    canv.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
    canv.restoreState()


def cover(canv, doc):
    canv.saveState()
    canv.setFillColor(NAVY)
    canv.rect(0, A4[1] - 92 * mm, A4[0], 92 * mm, stroke=0, fill=1)
    canv.setFillColor(TEAL)
    canv.rect(0, A4[1] - 95 * mm, A4[0], 3 * mm, stroke=0, fill=1)
    canv.restoreState()


from reportlab.platypus import NextPageTemplate
doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
                      title="ContinuityOS – Round 2 Build Document", author=AUTHOR,
                      subject="Prevent Critical Knowledge From Leaving With People")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
doc.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=cover), PageTemplate(id="main", frames=[frame], onPage=footer)])
W = doc.width
st = []

# ---- cover
st.append(Spacer(1, 6 * mm))
st.append(P("ROUND 2 · THE BUILD · KNOWLEDGE HANDOVER CHALLENGE", S("c0", fontName="DV-B", fontSize=8.5, textColor=colors.HexColor("#99F6E4"))))
st.append(Spacer(1, 4 * mm))
st.append(P("ContinuityOS", S("c1", fontName="DV-B", fontSize=36, leading=42, textColor=colors.white)))
st.append(P("Your team's knowledge should never leave with a person.", S("c2", fontSize=12.5, leading=17, textColor=colors.white)))
st.append(P("Round 1 working name: Baton", S("c3", fontSize=9, textColor=colors.HexColor("#99F6E4"))))
st.append(Spacer(1, 38 * mm))
st.append(T([["Team", "%s (solo)" % TEAM_NAME],
             ["Author / Team Leader", "%s · B.Tech CSE (AI), GPCET Kurnool" % AUTHOR],
             ["Working project link", ARGS.live],
             ["Source repository", ARGS.repo],
             ["Demo accounts", "Meera Iyer (approver) · Nisha Rao (restricted volunteer) · more on the login page. Password: continuity123"],
             ["Data", "All demo data is synthetic (fictional student-club app, CampusConnect)"]],
            [40 * mm, W - 40 * mm], header=False))
st.append(Spacer(1, 6 * mm))
st.append(callout("<b>Where the build stands.</b> The core workflow runs end to end: connect sources, reconstruct, verify, review and approve, then share a "
                  "role-filtered handover that a recipient acknowledges. Permission checks are enforced on the server and covered by automated tests. "
                  "The default extractor is rule-based; the language-model extractor exists but has only been tested against a mocked model. Section 8 lists every limitation."))
st.append(NextPageTemplate("main"))
st.append(PageBreak())

# ---- 1 summary and changes
st.append(P("1. What changed since Round 1", h1))
st.append(P("The Round 1 plan promised a focused workflow rather than a long feature list. Round 2 delivers that workflow working end to end, "
            "and pulls forward several items that were scheduled for Round 3. Where we deviated from the plan, the reason is stated."))
st.append(T([
    ["Round 1 plan", "Round 2 reality", "Why"],
    ["Product name Baton", "Renamed <b>ContinuityOS</b>", "Clearer product identity; same concept and claim-ledger design"],
    ["Claim ledger with quote, label, status, versions", "<b>Delivered</b> as designed: claims carry evidence quotes, 8 labels, review status, versioned frozen snapshots with diff", "Core of the plan"],
    ["Quote-or-nothing verifier", "<b>Delivered</b>: deterministic quote check plus a statement-support check; failures stored as Unverified", "Core of the plan"],
    ["Connectors: GitHub, notes, task CSV, chat export", "<b>Delivered</b>: file upload (txt/md/csv/tsv/json), WhatsApp-style chat parser, pasted note, public GitHub repo import", "As planned. PDF/DOCX parsing deferred"],
    ["Redaction with Microsoft Presidio", "Pattern-based redaction (keys, tokens, JWT, passwords, Aadhaar, PAN, card numbers with Luhn check), applied before storage", "Presidio adds heavy install and model downloads; patterns cover the demo risks. Presidio stays on the roadmap"],
    ["Supabase Postgres with Row-Level Security", "SQLite with permission checks in the API layer, plus tests that assert no restricted text leaves the server", "Judges can run it with zero setup. RLS comes with the Postgres migration"],
    ["pgvector / Qdrant retrieval", "Not used yet", "Rule-based conflict detection was enough for the core workflow; semantic retrieval is a Round 3 improvement"],
    ["Groq LLM extraction", "Optional, off by default; any OpenAI-compatible endpoint; always verified", "Keeps the demo reproducible and free. Tested with a mocked model only"],
    ["Gap Radar + Last-mile Interview (Round 3)", "<b>Gaps are detected and can be answered now</b>; the guided interview is still Round 3", "Gap detection was needed for the Missing label"],
    ["Claim-level permission engine + access requests (Round 3)", "<b>Delivered now</b>: per-passage access levels, claim clearance, role preview, access requests and grants", "Needed for the trust requirements, so it was pulled forward"],
    ["Continuation plan + comprehension check (Round 3)", "Plan and acknowledgement <b>delivered</b>; comprehension check moves to Round 3", "Plan is the handover's end goal; the check needs interview data"],
    ["React + Vite + Tailwind", "React + Vite with hand-written CSS (Inter font)", "Smaller bundle, consistent design tokens"],
], [44 * mm, 82 * mm, W - 126 * mm]))

# ---- 2 features
st.append(P("2. Completed features", h1))
st.append(T([
    ["Workflow step", "Feature", "Status"],
    ["Connect", "Upload files, auto-detect task board / chat / document; paste a note; import a public GitHub repo; duplicate and binary-file rejection; size limit", "Working"],
    ["Connect", "Per-source sensitivity (General / Internal / Confidential) and automatic raising of individual passages", "Working"],
    ["Reconstruct", "Extraction of decisions, ownership, actions, risks, dependencies, project state, open questions, contacts; recurring-problem flag; de-duplication across sources", "Working (rules)"],
    ["Reconstruct", "Language-model extraction through any OpenAI-compatible API", "Built, mock-tested only"],
    ["Verify", "Verbatim-quote verifier; Unverified bin for unsupported model output; evidence panel with highlighted passage and neighbouring context", "Working"],
    ["Verify", "Conflict detection (deployment region, database, hosting, payment provider, deadlines, owners) with both sources and dates", "Working"],
    ["Verify", "Gap detection: no owner, no recorded reason for a decision, tool mentioned only in chat, open questions", "Working"],
    ["Review", "Confirm, correct (original preserved), reject, restore; bulk confirm of supported claims; resolve or accept-as-unresolved conflicts; answer gaps with attribution", "Working"],
    ["Review", "Review decisions survive re-running reconstruction", "Working, tested"],
    ["Review", "Readiness score with its arithmetic shown; approval blocked by open conflicts; explicit acceptance needed to approve unreviewed claims", "Working, tested"],
    ["Handover", "Immutable versions with diff, explicit share step, role-filtered handover, continuation plan, acknowledgement of receipt", "Working"],
    ["Handover", "Preview-as-role for approvers; access requests and grants; Markdown and JSON export (filtered the same way)", "Working, tested"],
    ["Trust", "Append-only audit log; demo-grade authentication with hashed passwords; session expiry", "Working"],
    ["Usability", "Five-step overview, label legend, empty and error states, keyboard-closable panels, responsive layout", "Working"],
], [26 * mm, W - 26 * mm - 30 * mm, 30 * mm]))
st.append(P("<b>Demo workspace.</b> The synthetic CampusConnect project loads 6 sources (43 passages) and produces 41 claims: 9 actions, 8 risks, 7 decisions, 7 gaps, 3 dependencies, 3 ownership, 2 project-state, 1 question, 1 contact. "
            "It deliberately contains two conflicts (API region: README says Mumbai, a later chat says Singapore; a webhook deadline of 15 Nov versus 8 Nov), "
            "an ownerless domain renewal, decisions with no recorded reason, a tool documented only in chat, a masked password, and a confidential budget message.", small))

# ---- 3 architecture
st.append(P("3. Architecture and data flow", h1))
st.append(architecture())
st.append(P("3.1 How a claim earns its label", h2))
st.append(T([
    ["Label", "How it is produced", "Where it can appear"],
    ["Verified", "Quote verified in the source, then confirmed or corrected by a reviewer", "Counts as organisational fact"],
    ["Supported", "Quote verified in the source; no human has reviewed it", "Shown with that wording; never called verified"],
    ["Conflicting", "Another claim disagrees on the same attribute", "Blocks approval until resolved or accepted as unresolved"],
    ["Missing", "A gap the sources cannot answer", "Shown as an open question with owner unknown"],
    ["Stated", "A person answered a gap", "Attributed and dated, with the note that no document backs it"],
    ["Inferred", "Model reasoning across passages (supported by the data model, not produced by the rules extractor)", "Dashed; cannot become Verified without a reviewer"],
    ["Unverified / Rejected", "Model quote not found in the source / reviewer removed it", "Hidden by default; never in a handover"],
], [32 * mm, 84 * mm, W - 116 * mm]))
st.append(P("3.2 Why verification is deterministic", h2))
st.append(P("The verifier does not ask another model whether a claim is right. It checks that the quoted text exists in the cited passage (whitespace and case tolerant), "
            "and that at least 40% of the statement's content words appear in the quote. This makes the rule inspectable and means a model that invents or misquotes cannot produce a Supported claim. "
            "A test feeds a fake model an invented quote and asserts it is rejected."))

# ---- 4 permissions
st.append(P("4. Permissions and privacy", h1))
st.append(T([
    ["Role", "Access level", "Can do"],
    ["Project admin", "Confidential", "Everything, including deleting sources and managing access"],
    ["Approver", "Confidential", "Review, resolve, approve, share, preview as another role, decide access requests"],
    ["Departing member", "Confidential", "Add sources, run reconstruction, answer gaps, read the draft. Cannot approve or confirm"],
    ["Incoming (peer)", "Internal", "Read the shared handover, acknowledge, request access"],
    ["Incoming (restricted)", "General", "Same, with the least visible content"],
], [38 * mm, 32 * mm, W - 70 * mm]))
st.extend(B([
    "<b>Claim-level access.</b> Each passage has an access level (the source's level, raised automatically for secrets, confidential language, or contact details). A claim takes the highest level of its evidence.",
    "<b>Server-side withholding.</b> The handover endpoint, evidence context and both export formats filter on the server. Hidden items are reported only as counts by type. Tests assert that confidential strings are absent from the restricted roles' JSON and exports.",
    "<b>Secrets never stored.</b> Redaction runs before storage and before any model call. A test scans the database file and write-ahead log for the demo password.",
    "<b>Access requests.</b> A recipient can ask for one level more for one handover; an approver decides. Even a granted internal level never reveals confidential items (tested).",
    "<b>Prompt-injection stance.</b> Source text is data. The rules extractor ignores instructions; the LLM prompt marks excerpts as untrusted, the model has no tools, and its output goes through the verifier. A sample file with injected instructions is included and tested.",
]))

# ---- 5 tech
st.append(P("5. Technology, APIs, models and data", h1))
st.append(T([
    ["Layer", "What we used"],
    ["Frontend", "React 18, Vite 6, lucide-react icons, @fontsource/inter; hand-written CSS with design tokens"],
    ["Backend", "Python 3.12, FastAPI, Pydantic, Uvicorn, python-multipart; SQLite via the standard library"],
    ["AI", "None required. Optional language-model extraction through any OpenAI-compatible chat-completions API (default endpoint and model: Groq, llama-3.3-70b-versatile). Not exercised against a live endpoint in development"],
    ["External APIs", "GitHub REST API for public repository import (unauthenticated, or GITHUB_TOKEN). Exercised through mocks; a live call from the build environment was rate-limited"],
    ["Data", "Synthetic CampusConnect sources written for this project (README, architecture note, two meeting notes, task board CSV, chat export) and two sample upload files"],
    ["Tests", "pytest (15 API tests), vitest + jsdom (4 UI tests against a running backend)"],
    ["Deployment", "Single Docker image (builds the frontend and serves it from FastAPI); render.yaml included; run scripts for Windows and Unix"],
    ["AI assistance", "Claude (Anthropic) was used to design and write the code and this document"],
], [30 * mm, W - 30 * mm]))
st.append(P("<b>Reuse disclosure.</b> A starter frontend zip supplied by the team informed the visual direction (navy sidebar, teal accent). Its code was not reused: it was a single file with hard-coded statistics and was rewritten as structured components wired to the real API.", small))

# ---- 6 testing
st.append(P("6. Testing and evidence", h1))
st.append(T([
    ["Area", "What is asserted"],
    ["Authentication", "Anonymous requests are refused; wrong passwords fail; staff-only routes return 403 for incoming roles; a departing member cannot confirm claims"],
    ["No leakage", "Restricted and peer handover JSON never contain the budget message or the password; contact details appear for peers only; exports follow the same rules; unshared users get 404"],
    ["Approval gates", "Approval is refused while conflicts are open and while unreviewed claims exist unless explicitly accepted"],
    ["Review integrity", "Verified claims and edits survive re-running reconstruction"],
    ["Verifier", "A fake model's invented quote is rejected; a real quote is accepted; unknown chunk ids are dropped"],
    ["Ingestion failures", "Binary files, empty files and duplicate uploads are rejected with clear messages; a file containing injected instructions yields no Verified claim"],
    ["Secrets", "A password in the chat export is not present anywhere in the database files"],
    ["Access flow", "Request, approve, view with raised access, still no confidential content; acknowledgement works only for recipients"],
    ["UI journeys", "Login, overview, evidence highlight, conflicts tab, blocked approval, restricted recipient view, acknowledgement, access request, role preview"],
], [32 * mm, W - 32 * mm]))
st.append(P("<b>Not yet tested:</b> live language-model extraction, live GitHub import, behaviour with large repositories, concurrent editing by several reviewers, and accessibility with a screen reader (keyboard closing and labelled controls are in place).", small))

# ---- 7 round 3
st.append(P("7. Three major improvements committed for Round 3", h1))
st.append(T([
    ["#", "Improvement", "What it adds beyond Round 2", "How we will show it"],
    ["1", "<b>Last-mile Interview and Day-1 comprehension check</b>",
     "A guided interview for the departing person built from the Gap Radar: each question shows the evidence that triggered it, accepts typed or dictated answers, asks one grounded follow-up, and stores answers as attributed claims that are checked against existing claims for contradictions. The incoming person then completes a short check on the highest-risk claims; scores feed readiness and the audit log.",
     "Complete an interview on the demo project; show contradictions caught; show a recipient's comprehension result"],
    ["2", "<b>Live connectors with incremental sync and permission mapping</b>",
     "OAuth or token-based connectors for private GitHub repositories, Slack channels, Jira projects and Google Drive. Sync cursors fetch only changes; changed passages re-open affected claims as needing re-review; source-system permissions map onto access levels instead of manual labelling.",
     "Connect a real or sandbox account, edit a source, show the claim flagged for re-review and the access level mapped automatically"],
    ["3", "<b>Semantic evidence engine with measured accuracy</b>",
     "Embedding-based retrieval and semantic conflict and duplicate detection beyond keyword lexicons, language-model extraction run live with calibrated confidence, and PDF/DOCX ingestion. A labelled benchmark (synthetic plus public repositories) reports precision and recall for claims, conflicts and gaps, and the report ships in the repository.",
     "Publish the benchmark table; show cases the rules missed that the semantic engine catches, with the verifier still gating them"],
], [8 * mm, 36 * mm, 86 * mm, W - 130 * mm]))
st.append(P("Beyond Round 3 (roadmap): Postgres with Row-Level Security, SSO and MFA, encryption at rest, Presidio-based redaction, policy packs for retention, multilingual handovers.", small))

# ---- 8 limitations
st.append(P("8. Known limitations", h1))
st.extend(B([
    "The default extractor is pattern-based. It is accurate on explicit statements and misses implied knowledge, sarcasm and anything written in an unexpected style. The reviewer step exists because of this.",
    "Conflict detection covers a fixed set of attributes (region, database, hosting, payments, deadlines, owners). Other contradictions are not found yet.",
    "Redaction is pattern-based and will not catch every secret or personal detail. Treat connected sources as sensitive.",
    "Authentication is demo-grade. The hosted demo database resets when the service restarts. SQLite data is not encrypted at rest.",
    "Passage-level access is automatic, but a claim that merges evidence from several sources takes the strictest level, so some information is hidden more than strictly necessary.",
    "Only text-based files are parsed. Large repositories are sampled (first 40 issues and pull requests).",
]))
st.append(Spacer(1, 4 * mm))
st.append(callout("<b>Contribution.</b> %s built everything in this submission alone: product design, backend, extraction and verification pipeline, permission model, frontend, synthetic dataset, tests and documentation." % AUTHOR, AMBER))
doc.build(st)
print("built", OUT)
