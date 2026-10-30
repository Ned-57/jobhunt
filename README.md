# JobHunt

Answer a set of questions once, or upload a couple of old CVs. The app turns
that into tailored CVs, tailored prompts for whichever AI assistant you already
use, and a tracker for what comes back.

Two things it deliberately does not do:

- **It does not call an AI provider.** No API keys, no per-token cost. The Hunt
  button builds a prompt, hands it to Claude / ChatGPT / Perplexity, and you
  paste the reply back.
- **It does not write your CV.** The CV builder only ever re-arranges text you
  wrote, so it cannot invent a claim. What it can do is tell you what it could
  not evidence.

## Running it

```bash
pip install -r requirements.txt
```

```bash
python -m uvicorn app.main:app --reload --port 8121
```

Then open <http://127.0.0.1:8121>. On Windows, `.\run.ps1` does the same thing.

Create an account on first load. Everything is stored under `data/` as JSON.

## Getting a profile in

Three routes, in descending order of effort:

**Upload CVs you already have.** Profile → *"Start from a CV you already
have"*. Up to ten `.docx` at a time. It pulls out contact details, the
technologies mentioned, and the bullets themselves, then offers them for review
— everything is opt-in one line at a time, because only you know which claims
are still true. Mined technologies are recorded at *hands-on project work* and
never higher; the app does not upgrade a claim on your behalf. PDFs are refused,
because a PDF has no reliable structure to read and guessing produces bullets
that are subtly wrong.

The same extraction runs from the command line over a whole folder:

```bash
python -m scripts.mine_cvs --dir "C:/path/to/your/CVs" --email you@example.com
```

**Seed from a file.** `scripts/seed_profile.py` loads a YAML profile. Create the
account in the app first — the script never creates users and never touches
passwords.

```bash
copy scripts\seed_data.example.yaml scripts\seed_data.yaml
python -m scripts.seed_profile --email you@example.com
```

`--dry-run` validates and prints without writing, `--force` overwrites a filled
profile, `--file` reads a different seed. An export from the app's Account page
(JSON) works as a seed file directly, so the round trip is lossless.

`scripts/seed_data.yaml` holds real personal details and is **gitignored — keep
it that way**. Only the placeholder example is committed.

**Answer the questionnaire.** Ten steps, grouped into three phases: the
essentials that get you a CV, the steps that make tailoring work at all, and
optional refinement. Each step says what it feeds, and a banner appears once the
essentials are in so nobody assumes all ten are required.

## How it works

```
Questionnaire / CV upload  ->  Profile  ->  CV builder      ->  tailored CV
                                        ->  Prompt builder  ->  your AI tool
                                                                     |
                              Tracker   <-  Importer  <-  paste the reply back
```

### The CV builder

`app/cvgen.py`. No AI call — it scores every claim in your profile against what
the advert actually asks for, keeps the strongest, orders sections by relevance
and renders the result. Evidence-bank lines and bullets written under a job
compete on merit for the same space, so where you happened to type something
does not decide whether it appears.

It reports what it could not evidence, which is usually the part that matters.
For a role asking about analysis it will surface your own boundary — *"do not
claim formal analyst experience"* — rather than quietly writing around it.

Export is **.docx**, built with the standard library alone - a .docx is a zip
of XML - in the house style from the profile: your font, your accent colour, a
rule under each heading, and real hyperlink relationships rather than blue
text. It stays editable, because the last pass on a CV is always by hand.
Markdown and print-to-PDF are there too.

Output is trimmed to a page budget calibrated against real one-page CVs
(~4,500 characters of visible text, markdown syntax not counted). Over budget it
drops the weakest content first rather than overflowing.

`app/taxonomy.py` does the matching. Multi-word and symbol-bearing terms are
matched as phrases, because token splitting destroys `c#`, `ci/cd` and
`spring boot` — the terms carrying the most signal. Requirements are judged by
weighted coverage, so a named technology counts for more than a word like
"production" that appears in every advert ever written.

### The prompt builder

`app/prompts.py` assembles the profile into one of six prompts. Five are in the
dropdown on **Hunt for jobs**:

| Kind | What it asks for |
| --- | --- |
| Hunt for jobs | Live vacancies that fit, returned as JSON this app can import |
| Assess one advert | Honest fit assessment with the gaps named |
| Tailor a CV | A full CV draft, when you want the model to write the whole thing |
| Draft a cover letter | Short, role-specific, in your style rules |
| Interview prep | Likely questions, the evidence for each, your weak spots |

The sixth, `tailor`, is reached from **Build a CV → "Tailor with AI first"**,
and it is the one worth knowing about. The CV is assembled locally, so that
prompt asks only for the parts a language model is genuinely better at — a
role-specific opening paragraph, and which evidence should lead. It comes back
as a small JSON object that can only re-order evidence, never add to it.

### The importer

`app/importer.py` reads the fenced ```json block back out of a reply, tolerates
paraphrased key names and trailing commas, drops rows missing a title or
company, skips anything already tracked, and rejects rows that echoed the schema
template instead of filling it in.

## The two things that make this different from a form

**The technology profile is graded by strength of claim** — production, project
work, training, exposure, or never-claim. Prompts receive those as separate
labelled groups, and the CV builder excludes anything below project level from
Key Skills. A flat skills list gets a bootcamp module described as commercial
experience; this does not.

**Accuracy boundaries go in verbatim.** Rules like *"do not claim production
Rust experience — it is project work only"* are passed word for word into
every prompt, with an instruction to leave a gap open rather than fill it. They
also surface beside a generated CV whenever an advert triggers one.

## Tracking applications

Four stages — **Saved → Applied → Interviewing → Closed** — with `outcome`
carrying how something ended (rejected, no response, withdrawn, declined,
accepted). Stages describe live states only. Records from the older six-stage
set migrate on read.

- Per-column filters, plus clickable stat tiles
- Moving a row to *Applied* fills in the applied date, a "Chase" action and a
  due date two weeks out, without overwriting anything already set
- Rows go **stale** after 30 days with no change — a derived flag, not a stage,
  because a role can be applied and stale at once
- Every import is stamped with a batch, so "remove everything from that bad
  hunt" is: filter to the batch, select all, delete
- Click a row to select, shift-click for a range, or filter and delete the whole
  shown set. CSV export respects the current filter.

## Pasted text

Text arrives in this app by pasting — out of Word, out of PDF adverts, out of
other CVs. `app/custard.py` normalises it centrally: smart quotes, dashes,
non-breaking and zero-width characters, CRLF, control characters, PDF ligatures.

Two jobs kept deliberately apart. Normalising is shape-preserving and runs over
every string. Splitting a pasted block into a list applies only to fields
declared as lists, because guessing from the text alone would cut a paragraph in
half.

## Storage

Local JSON files by default:

```
data/
  users.json                 email -> id, password hash
  profiles/<user-id>.json    the questionnaire answers
  applications/<user-id>.json
  .secret_key                generated; signs session cookies
```

Writes go through a temp file and `os.replace`, so an interrupted write cannot
leave a half-written profile behind. Back it up by copying the folder.

### Switching to Supabase

Both backends implement the same interface (`app/storage/base.py`), so this is
configuration rather than a rewrite:

1. Run `supabase/schema.sql` in the Supabase SQL editor.
2. `pip install supabase`
3. Set the environment (see `.env.example`):

```
JOBHUNT_STORAGE=supabase
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_SERVICE_KEY=...
```

The service key bypasses row-level security, so `SupabaseStore` scopes every
query by `user_id` itself. Keep that key server-side; it must never reach the
browser. The RLS policies in the schema are written against `auth.uid()`, so
they are already correct if you later move auth to Supabase Auth and talk to the
database from the browser with the anon key.

## Layout

```
app/
  main.py          FastAPI routes; serves web/ as static files
  models.py        pydantic schema for profile and applications
  cvgen.py         deterministic CV generation - the core of the app
  cvmine.py        reads a profile out of existing .docx CVs
  taxonomy.py      keyword matching, skill categories, coverage scoring
  prompts.py       prompt construction
  importer.py      parses an assistant's reply into applications
  custard.py       normalises pasted text; splits pasted bullet blocks
  security.py      pbkdf2 password hashing, signed session cookies
  config.py        env-driven settings with local defaults
  storage/         base.py (interface), local_files.py, supabase_store.py
web/
  index.html       auth gate + app shell
  assets/app.css
  js/data.js       constants, question copy, wizard phases
  js/ui.js         DOM helpers, modals, toasts
  js/api.js        fetch wrappers
  js/app.js        the whole frontend; the questionnaire is schema-driven
scripts/
  seed_profile.py  fill a profile from a YAML (or JSON) seed
  mine_cvs.py      batch CV mining over a folder
supabase/
  schema.sql
```

Adding a question is a line in the `SCHEMA` object in `web/js/app.js` plus a
field on the matching model in `app/models.py`. One generic renderer handles
text, textarea, select, checkbox, chip lists, line lists and repeating groups.

Nothing the app serves is cacheable — the frontend is read off disk and edited
live, and API responses are per-user state.

API docs, if useful: <http://127.0.0.1:8121/api/docs>

## Honest limits

- **Auth is sized for a personal tool.** pbkdf2 hashing and signed cookies, no
  rate limiting, no email verification, no password reset. Fine on localhost; do
  not expose it to the internet as-is.
- **The app cannot verify a vacancy exists.** The prompt tells the assistant not
  to invent listings and to flag ones it could not confirm, but an assistant can
  still be wrong. Open the advert before you spend an afternoon on it.
- **A generated CV is a draft.** It selects and orders honestly, but the prose is
  whatever you wrote. Read it before you send it.
- **`save_applications` replaces the whole list.** Correct at one person's
  scale, wasteful beyond it.
- **CV mining reads `.docx` only.** No PDF, by choice.
