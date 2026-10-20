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
- `questions` fulfilled with `params.n` items at `params.levels`, every `cat` a valid id, four distinct choices, `why` present; `fulfil` printed `N merged` and a length report with the mean ratio between 0.8 and 1.2 and the right answer longest in no more than 45% of questions.
- During the round the agent writes nothing in chat; when the page auto-files "bank running low", the agent fulfils it without being asked.

## 3. Diagnose
Prompt: (user clicks **Diagnose my misses**)
Expect: `diagnose` fulfilled with a one-sentence recognisable root cause, 3–7 protocol steps with `how` and `when`, and `next_test` naming categories and levels.

## 4. Status
Prompt: `how am I doing on kubernetes?`
Expect: `learn.py status kubernetes-networking` summarised in plain words (edge per category, due cards); no questions generated.

## 5. Manage a topic and flag a question
Prompt: (user renames a topic from the ⋯ menu, archives another, flags a question during a round with "the marked answer is wrong")
Expect: the rename shows on the page and in `learn.py topics` with the same slug; the archived topic leaves the home grid and appears under "archived"; the flagged question disappears from the round, `learn.py questions <slug> --retired` lists it with the reason, and the next `questions` request carries it in `context.flagged` with the note "replace a flagged question"; the agent's replacement is on the same idea and does not repeat the retired text.

## 6. Backup, new machine, two agents
Prompt: `back up my learning data` then, on another machine, `restore it`
Expect: `learn.py backup` prints a zip path; `learn.py restore <zip>` on a fresh `LEARN_HOME` adds every topic and `topics` lists them; running it again skips them. With two agents in the `pending --wait` loop on one hub, each request is fulfilled exactly once (the second agent's `pending` does not print requests the first one claimed; `fulfil` on a live claim refuses without `--force`). If port 4848 is busy, `open` prints the port it took and the agent passes that URL on.

## 7. Cross-topic review and hammer
Prompt: (user clicks **Review all due** on the home page with two topics due; later **Hammer my weakest** on one topic)
Expect: one session walks the due cards of both topics, each attempt lands in its own `topic.json` with `mode: "all"`, and the edge of neither topic changes. The hammer round names the weakest category, re-asks previously missed questions first, and `status` shows the edge unchanged while `due` moves.
