# Smoke evals

## 1. New topic, brief first
Prompt: `/srs-edge-learning Kubernetes networking --goal "debug prod incidents"`
Expect:
- `learn.py add` ran; `learn.py open <slug>` printed `http://127.0.0.1:4848/#/topic/kubernetes-networking` and opened a browser (or the agent told the user to open the URL).
- Agent entered `learn.py pending --wait 600`; the user clicks **Cliff notes**; the agent fulfils the `brief` request with `as_of`, `sources_live`, 5–7 sections, 3–8 movers, 3–6 dated news items.
- No brief text in chat; chat has ≤ 3 lines.

## 2. Go deeper
Prompt: (user clicks **Build the map**, then **Start a round**)
Expect:
- `categories` fulfilled with 4–12 kebab-case ids and `why` lines, ordered foundations → advanced.
- `questions` fulfilled with `params.n` items at `params.levels`, every `cat` a valid id, four distinct choices, `why` present; `fulfil` printed `N merged`.
- During the round the agent writes nothing in chat; when the page auto-files "bank running low", the agent fulfils it without being asked.

## 3. Diagnose
Prompt: (user clicks **Diagnose my misses**)
Expect: `diagnose` fulfilled with a one-sentence recognisable root cause, 3–7 protocol steps with `how` and `when`, and `next_test` naming categories and levels.

## 4. Status
Prompt: `how am I doing on kubernetes?`
Expect: `learn.py status kubernetes-networking` summarised in plain words (edge per category, due cards); no questions generated.
