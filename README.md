# ContinuityOS

**Your team's knowledge should never leave with a person.**

ContinuityOS rebuilds a project's current state from authorised sources, shows the evidence behind every statement, flags what is missing or contradictory, lets a responsible person correct and approve it, and then shares a handover that respects each recipient's access level.

This is the Round 2 build for the *Prevent Critical Knowledge From Leaving With People* challenge. All data in the demo workspace is **synthetic** (a fictional student-club app, CampusConnect).

## Run it (about 3 minutes)

Requirements: Python 3.10+ and Node.js 18+.

**Windows (PowerShell), from the project root**
```powershell
.\run-windows.ps1
```
**macOS / Linux**
```bash
./run.sh
```
Then open **http://localhost:8000** and click a demo account (password `continuity123`).

If you prefer separate dev servers (hot reload):
```bash
# terminal 1
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# terminal 2
cd frontend
npm install
npm run dev                                              # http://localhost:5173
```

Docker (also what the Render config uses): `docker build -t continuityos . && docker run -p 8000:8000 continuityos`

## Judge walkthrough (5 minutes)

1. Sign in as **Meera Iyer** (approver). The Overview shows the five-step workflow, what blocks approval, and a readiness score with its arithmetic.
2. **Sources**: six synthetic sources are already connected. Click *Add source* and upload `sample_uploads/razorpay-vendor-call-2026-10-30.md`, then *Run reconstruction*. Try `sample_uploads/handover-call-injection-test.txt` too: it contains instructions aimed at an AI; they are treated as data and never obeyed.
3. **Review and approve**: every claim has a label (Verified, Supported, Conflicting, Missing...). Click **Evidence** to see the exact passage highlighted in its source. Open the **Conflicts** tab: the README says the API is in Mumbai, a later chat says Singapore. Resolve it.
4. **Gaps and questions** tab: ownerless tasks, decisions with no recorded reason, and a tool (Firebase) mentioned only in chat. Answer one. The answer is attributed and labelled as having no document evidence.
5. Correct a claim (pencil icon), then **Confirm all supported**, then **Approve handover**. Try approving first: it is blocked while conflicts are open.
6. **Handovers** -> *Share* with Rahul and Nisha. Open a handover and use **Preview as role -> Incoming (restricted)** to see exactly what a volunteer would receive.
7. Sign out, sign in as **Nisha Rao** (restricted volunteer). Some items are withheld and the confidential text is not in the page at all. Acknowledge receipt, then request access. Back as Meera, **Access and roles** lets you grant it.
8. **Activity** shows the audit log of everything above.

## What is real in this build

| Area | Implementation |
|---|---|
| Sources | Upload txt/md/csv/tsv/json and WhatsApp-style chat exports (auto-detected), paste a note, import a public GitHub repo (README + issues/PRs) |
| Protection | Secrets masked **before storage** (API keys, tokens, JWTs, passwords, Aadhaar, PAN, card numbers). Each passage gets its own access level; confidential language and secrets raise it automatically |
| Reconstruction | Deterministic pattern extractor (transparent, reproducible). Optional LLM extractor via any OpenAI-compatible API |
| Verification | Every claim needs a verbatim quote. A deterministic verifier checks it exists in the cited passage and supports the statement. Failures are stored as *Unverified* and never shown as fact |
| Uncertainty | Conflict detection (region, database, hosting, payment provider, deadlines, owners), gap detection (no owner, no rationale, undocumented tools), recurring-problem flag |
| Human control | Confirm, correct, reject, restore, answer gaps, resolve conflicts, bulk confirm, approval gates, version snapshots with diff |
| Permissions | Server-side roles and claim-level access. Withheld content is removed from API responses, exports and evidence context. Access requests with grants |
| Handover | Role-filtered view, continuation plan (overdue / 24h / week / 30 days), acknowledgement, Markdown and JSON export, preview-as-role |
| Audit | Append-only activity log |

## Honest limitations

- The default extractor is rule-based. It is precise on explicit statements ("Decision:", "will test", "blocked by") and will miss implied knowledge. The LLM path exists and is verified, but it was **tested with a mocked model only**; no live LLM call was run in development.
- GitHub import was tested with a mocked API. Live calls are unauthenticated and rate-limited unless `GITHUB_TOKEN` is set. Public repos only.
- Authentication is demo-grade (email + password, bearer sessions). No SSO, no MFA.
- SQLite storage with no encryption at rest. The hosted demo database resets on restart.
- Redaction is pattern-based. It will not catch every secret or personal detail.
- Evidence quotes for CSV rows are the whole row. PDFs and Office files are not parsed yet.

## Tests

```bash
cd backend && pytest                    # 15 API tests: permissions, no-leak checks, gates, verifier, re-run behaviour
```
`frontend/uitest/` holds 4 browser-environment tests (jsdom) that drive the real UI against a running backend (`npm i -D vitest jsdom @testing-library/react @testing-library/user-event` then `npx vitest run`, with a freshly started backend).

## Layout

```
backend/app/    config, db, security, textproc (redact/chunk), extract_rules, extract_llm,
                analysis (verify/conflicts/gaps), pipeline, handover, github_import, seed, main
backend/seed_data/   synthetic CampusConnect sources
frontend/src/   React + Vite, plain CSS, Inter font
sample_uploads/ files to try during the demo
```

## Disclosures

AI assistance (Claude) was used to design and write this code. Third-party libraries: FastAPI, Uvicorn, Pydantic, React, Vite, lucide-react, @fontsource/inter. The uploaded starter frontend (`continuityos-round2.zip`) informed the visual direction (navy sidebar, teal accent); its code was rewritten.
