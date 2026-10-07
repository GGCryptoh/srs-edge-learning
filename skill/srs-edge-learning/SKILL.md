---
name: srs-edge-learning
version: 0.1.0
description: SRS Edge Learning — get smart at any topic by finding the edge of what you know and pushing it outward. Spins up a local hub (127.0.0.1:4848) that remembers every topic; for a new topic it writes a curated brief (cliff notes or short bullets — what it is, how it applies in business and life, the movers, recent news), then maps the topic into categories, drills you with timed multiple-choice questions that get harder until it finds your edge, diagnoses your misses into a training protocol, and schedules spaced-repetition reviews so you get smarter over time. The agent is the backend (no API key), so it runs in Claude Code, Codex and Copilot CLI alike. Use when the user says "/srs-edge-learning", "learn something", "get smart at X", "teach me X", "quiz me on X", "find my edge", "what's due for review", "SRS", "spaced repetition", "serve my pending requests", or asks to continue a topic they started earlier.
owner: geoff
audience: [geoff, business, family]
category: agents
harness:
  cli: [python3]
  mcp: []
  fallback: "no MCP needed; web search is optional (news/movers fall back to model knowledge with an as_of date)"
requires_capabilities: [search.web]
requires_secrets: []
constraints:
  - "local only: the hub binds 127.0.0.1 and never uploads anything"
  - "the brief says what date its knowledge is from (as_of) and whether the web was checked"
  - "questions are the agent's own writing, four distinct choices, one right, never all/none-of-the-above, distractors as long and specific as the right answer (the validator checks)"
  - "never tell the learner the answer before they pick; the page reveals it"
provenance: geoff
license: MIT
examples: [examples/README.md]
---

# SRS Edge Learning (`srs-edge-learning`)

Learning sticks when you **produce** (answer, explain, get corrected) rather than consume. This skill turns the agent into roadmap builder, explainer, examiner, checker and flashcard clerk, and a small local web page into the examiner's desk. It is the same spaced-repetition and timed-recall pattern Geoff used to compress almost two years of Mandarin levelling into 11 months, applied to any topic. The learner picks a topic; the page files requests; the agent answers them with structured JSON; the page times the questions, scores them, finds the **edge** (the hardest level at which the learner still gets ≥60% right, per category), and schedules spaced-repetition reviews. Every run reopens the same hub with all topics and progress.

Everything lives in `$LEARN_HOME` (default `~/.gh-learn/`): `index.json`, `topics/<slug>/topic.json` (brief, categories, question bank, attempts, SRS cards, protocol), `requests/*.json` (the page→agent queue), `hub.log`.

## When to use
- "/srs-edge-learning", "/srs-edge-learning Rust ownership", "get smart at MiFID II", "teach me how LLM inference works", "quiz me on Kubernetes".
- "what's due for review", "continue my Rust topic", "how am I doing on statistics", "find my edge".
- "/srs-edge-learning serve my pending requests" (the page's copy-paste prompt) → skip to Procedure step 3 and stay in the loop.
- Not for: writing a course or a deck (gh-build-in-public-assistant), flashcards for a language vocabulary list (works, but the brief step is overkill), anything that needs grading free-text essays (this is multiple-choice by design so the timer and the edge maths are honest).

## Setup (once per user)
1. Nothing to install: `python3 scripts/learn.py setup` creates `~/.gh-learn/` and checks the page is present.
2. No keys. If the harness has web search, the brief's "movers" and "recent news" are checked live; otherwise they come from model knowledge and the brief says so.
3. Test: `python3 scripts/learn.py open` prints `http://127.0.0.1:4848/` and opens it.

## Inputs
- A topic name (from the slash command argument, the conversation, or the page's **New topic** form). Optional goal ("interview next month", "explain it to a client") and starting level 1–4.
- Nothing else. The learner steers from the page; the agent only answers requests.

## Procedure
1. **Open the hub.** `python3 scripts/learn.py open` (starts the server detached if port 4848 is free, opens the browser). If the harness cannot open a browser, print the URL and tell the user to open it. If the user named a topic, `learn.py add "<topic>" --goal "…"` first, then `learn.py open <slug>`.
2. **Tell the user what to do on the page** in two lines: pick a topic or create one; choose Cliff notes / Short bullets / Go deeper. Then say you are now waiting for requests.
3. **Serve requests until the user stops.** Loop:
   ```
   python3 scripts/learn.py pending --wait 600
   ```
   It prints a JSON list (empty when the wait expires). **Back off while idle to save tokens:** after serving a request wait 600 s; on an empty wake double it (1200, 2400, 3600); after an hour with no request, stop the loop and tell the user in one line that the hub is still running and the page's Copy prompt re-summons you. Run the wait in the background where the harness allows it. Each request carries `type`, `params`, `note` and a `context` block (topic name, goal, level hint, categories, per-category edge, how many unanswered questions exist per level, existing question texts, and recent misses for a diagnose). Answer **each** request by writing a JSON file in the scratchpad and running:
   ```
   python3 scripts/learn.py fulfil <req-id> <file.json>
   ```
   The schemas are in `references/schemas.md`; `fulfil` validates and refuses with the exact field that is wrong. Fix and re-run. Do not paste the content into chat — the page shows it.
   - `brief` → `references/method.md` §Brief. Resolve `search.web` per capabilities.yaml for movers and news; if nothing is available, write from model knowledge, set `as_of` to your knowledge date and `sources_live: false`.
   - `categories` → 4–12 kebab-case ids with a one-line `why`, ordered foundations → advanced; set `level_hint` from the learner's stated level.
   - `questions` → `params.n` questions (default 10) spread over `params.cats` at `params.levels`. Use `context.edge[cat].next` as the target level, add one level above for stretch. Never repeat `context.existing_questions`. Read `references/method.md` §Question craft before writing the first batch.
   - `diagnose` → read `context.misses`, name the **root cause** behind the misses (the thing that makes several different questions go wrong), and write a training protocol of 3–7 steps the learner can do away from the page, plus `next_test`.
4. **While waiting, say nothing.** The hub shows "waiting for your agent" with the request id; when `fulfil` lands, the page updates itself within 3 seconds. Only speak when a request fails validation twice or the user asks something.
5. **When the user asks "how am I doing"**: `python3 scripts/learn.py status <slug>` and summarise the edge per category in plain words; offer the Diagnose button or run `learn.py misses <slug>` and file a diagnose yourself.
6. **Ending:** `python3 scripts/learn.py export <slug>` writes `progress.md`; mention the path and that the hub stays running (`open` reuses it next time).

## Capabilities
- `search.web` (optional) — freshness for movers/news. MCP web search in Claude Code; `WebSearch` tool; otherwise skip and mark `sources_live: false`.

## Output format
- Hub: `http://127.0.0.1:4848/` with `#/topic/<slug>/{brief|learn|train|progress|plan}` routes.
- Files: `topic.json` per topic (see `references/schemas.md`), `progress.md` on export.
- Chat: at most a few lines per turn. Content goes to the page, not the transcript.

## Verification
- `learn.py status <slug>` shows the brief present, ≥4 categories, a question bank with unanswered items at the learner's `next` level in every selected category, and no pending requests.
- After a round, each answered category's `by_level` counts grew and `edge` is set once ≥3 questions at a level were answered.
- `learn.py validate <file> --type questions --topic <slug>` prints `OK` for any batch before it is merged.

## Smoke
1. `/srs-edge-learning Kubernetes networking` → `add` ran, hub opened, the agent is in the `pending --wait` loop; after the user clicks Cliff notes, a `brief` request is fulfilled within one turn and the page shows it; no brief text in chat.
2. `what's due for review?` → `learn.py topics` table, then the topic with due cards named and the Train tab suggested; no new questions written unless asked.

## Constraints
- Local only, no uploads, no keys. The brief carries its `as_of` date. Questions have four distinct choices and one answer; the agent never reveals answers in chat during a round.

## Examples
- In: `/srs-edge-learning "how LLM inference works" --goal "explain it to clients"` → Out: hub at `#/topic/how-llm-inference-works`, a cliff-notes brief with 5 sections, movers (labs, chips, serving stacks), news with dates; then 8 categories and a 12-question first batch at L2–L3. See `examples/README.md` for a full request/response pair.

## Notes
- The learning method, condensed, is in `references/method.md`: consumption vs production, the agent roles, the zone of proximal development, SRS, and "drill me to find what I don't know first".
- `pending` collapses duplicates: one open request of each type per topic. The page auto-files a `questions` request when a category's bank drops below 4 unanswered items at the target level, so keep the loop running during a round.
- Edge rule: a level counts as held when ≥3 first-attempt quiz answers at that level are ≥60% right; `next` moves up after ≥80% at the current top level and down after ≤40%.
- SRS is SM-2 lite (intervals 1, 3, then ×ease; ease 1.3–3.0). `train` mode attempts never change the edge.
- Set `LEARN_HOME` to keep a topic's data inside a project folder.
