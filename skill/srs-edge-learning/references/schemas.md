# Request → response schemas

The page writes a request; `learn.py pending` prints it with a `context` block; the agent answers with one JSON file per request via `learn.py fulfil <id> <file>`. Fenced ```json blocks are tolerated. Validation errors name the field.

## Request (what `pending` prints)
```json
{"id":"20261007-141502-a1b2","ts":"…","topic":"rust-ownership","type":"questions","params":{"cats":["borrowing","lifetimes"],"levels":[2,3],"n":10},"note":"auto: bank running low","status":"pending",
 "context":{"name":"Rust ownership","goal":"pass a systems interview","level_hint":2,
   "categories":[{"id":"borrowing","name":"Borrowing & references","why":"…"}],
   "edge":{"borrowing":{"edge":2,"next":3,"answered":9,"accuracy":0.67,"by_level":{"2":{"right":6,"n":7},"3":{"right":0,"n":2}}}},
   "unanswered":{"borrowing":{"3":1}},
   "existing_questions":["…"],          // questions only
   "misses":[{"cat":"…","level":3,"q":"…","picked":"…","answer":"…","ts":"…"}]   // diagnose only
 }}
```

## `brief`
```json
{"mode":"cliff",                       // or "bullets" (params.mode)
 "as_of":"2026-10-07",                 // date the knowledge is from; your training date if no web
 "sources_live":true,                  // did you check the web?
 "summary":"Two or three sentences: what it is and why anyone cares.",
 "sections":[
   {"title":"What it is","bullets":["…","…"]},               // bullets mode: 3–6 bullets per section, ≤ 20 words each
   {"title":"How it works","text":"…"},                       // cliff mode: text paragraphs (or bullets) — 120–250 words each
   {"title":"Where it shows up in business","bullets":["…"]},
   {"title":"Where it shows up in life","bullets":["…"]},
   {"title":"What people get wrong","bullets":["…"]}
 ],
 "movers":[{"name":"…","role":"company / person / project","why":"one line"}],   // 3–8
 "news":[{"date":"2026-09","title":"…","why":"why it matters to this learner","url":"optional"}],   // 3–6, newest first
 "glossary":[{"term":"…","means":"…"}],   // 5–12, optional
 "sources":["https://…","Book, author, year"]   // optional
}
```
Cliff = 5–7 sections, ~900–1400 words total. Bullets = 4–6 sections, ~250–400 words total. Both are written for the learner's stated goal and level.

## `categories`
```json
{"level_hint":2,
 "categories":[
   {"id":"memory-model","name":"Memory model","why":"everything else assumes you can picture the stack and heap"},
   …   // 4–12, ordered foundations → advanced, kebab-case ids, stable across re-requests
 ]}
```

## `questions`
```json
{"questions":[
  {"cat":"borrowing","level":3,
   "q":"A function takes `&mut Vec<i32>` and, inside, calls `v.iter()` then `v.push(1)` in the same scope. What does the compiler say?",
   "choices":["Compiles; iter() ends before push","Error: cannot borrow as mutable while immutably borrowed, if the iterator is still used after the push","Error: Vec is not Send","Compiles with a warning about unused iterator"],
   "answer":1,
   "why":"The immutable borrow from iter() lives as long as the iterator is used; a push while it is alive is a conflicting mutable borrow (NLL ends it only once the iterator is no longer used).",
   "tags":["nll","aliasing"]}
]}
```
Rules the validator enforces: exactly 4 distinct choices, `answer` 0–3, `why` present, `level` 1–5, `cat` is a category id of this topic, no "all/none of the above". Duplicates of existing question text are dropped silently (the `fulfil` output says how many merged).

## `diagnose`
```json
{"diagnosis":"Two paragraphs max: what the misses have in common, in plain words.",
 "root_causes":["You treat a borrow as ending at the closing brace rather than at last use","…"],   // 1–4
 "protocol":[
   {"step":"Rewrite 5 borrow-checker errors by hand, predicting the error before compiling","how":"use rustlings 'move_semantics' 1–5","when":"today, 20 min"},
   {"step":"…","how":"…","when":"…"}
 ],   // 3–7 steps, each doable away from the page
 "next_test":"After the protocol, re-run Go deeper on borrowing and lifetimes at L3–L4."}
```

## Level ladder (what L1–L5 mean when writing questions)
| L | name | a question at this level asks for |
|---|---|---|
| 1 | foundations | a definition or the purpose of a thing |
| 2 | working knowledge | the right term/tool for a plain situation |
| 3 | practitioner | the outcome of a concrete scenario with one twist |
| 4 | expert | the cause behind a surprising outcome, or a trade-off between two correct-looking options |
| 5 | edge of the field | a current open question, a recent change, or a subtle interaction most practitioners get wrong |
