# Changelog

## 0.1.0 — 2026-10-07
- First release. `learn.py` (stdlib): `setup`, `open` (detached hub on 127.0.0.1:4848), `serve`, `add`, `topics`, `status`, `pending --wait`, `fulfil`, `validate`, `misses`, `due`, `export`.
- `assets/app.html`: topics home with new-topic wizard (goal, starting level, cliff / bullets / go deeper); per-topic tabs Brief · Go deeper (adaptive timed quiz: read phase, then four choices with countdown, instant result + why, keyboard 1–4/space) · Train (SRS, SM-2 lite) · Progress (edge per category, level bars, activity, diagnose button) · Protocol (diagnosis, root causes, checklist).
- Agent-as-backend protocol: requests `brief`, `categories`, `questions`, `diagnose` with validated schemas (`references/schemas.md`); the page auto-requests more questions when a category's bank runs low at the target level.
- Agent presence: the listener loop writes a heartbeat; the page shows **agent listening / offline** and only shows the paste-this-prompt card when nobody is listening. Settings switch for automatic question requests. Validator rejects length and slot tells in question batches; choices shuffled on merge.
- Learning-method notes in `references/method.md`.
