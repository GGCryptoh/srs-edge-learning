#!/usr/bin/env python3
"""SRS Edge Learning — local learning hub. Stdlib only. The AGENT is the backend:
the page files requests (brief / categories / questions / diagnose); the agent answers them with `fulfil`.

  learn.py setup                              create $LEARN_HOME, print it
  learn.py open [--port 4848]                 start the hub detached if needed and open the browser
  learn.py serve [--port 4848] [--open]       run the hub in the foreground
  learn.py add "<topic>" [--goal "…"]         create a topic (slug printed)
  learn.py topics                             list topics + progress
  learn.py status [<slug>]                    edge per category, accuracy, cards due, plan
  learn.py pending [--wait SECONDS]           list page requests the agent must answer (JSON)
  learn.py fulfil <req-id> <file.json|->      answer a request (validated, merged, request marked done)
  learn.py validate <file.json> --type T      check a response file without merging
  learn.py misses <slug> [--limit 30]         recent wrong answers (input for a diagnose)
  learn.py due <slug>                         SRS cards due today
  learn.py export <slug>                      write progress.md next to topic.json and print the path
  learn.py rename <slug> "<name>" [--goal …]   rename a topic / change its goal or level (slug stays)
  learn.py archive <slug> | unarchive <slug>   hide a topic from the home page (keeps everything)
  learn.py remove <slug> [--purge]            move a topic to $LEARN_HOME/trash (or delete for good)
  learn.py undelete <slug>                    bring the latest trashed copy back
  learn.py questions <slug> [--retired]       list question ids (for retire)
  learn.py retire <slug> <qid> [--reason …]   retire a bad question: out of the bank, the edge maths and the SRS deck
  learn.py backup [--out file.zip]            zip the whole hub (every topic + settings)
  learn.py restore <file.zip|topic.json> [--overwrite]   import topics from a backup or a single topic file
  learn.py stats <slug>                       per-question stats: leeches (missed 3+ times), slowest, never-right

Home: $LEARN_HOME or ~/.gh-learn. Binds 127.0.0.1 only (falls back to the next free port if 4848 is taken). No network calls, no keys.
Several agents may serve one hub: `pending` claims what it prints, claims expire when the agent goes quiet, and every write takes a cross-process lock.
"""
import argparse, contextlib, datetime as dt, http.server, io, json, os, re, shutil, socket, socketserver, subprocess, sys, threading, time, urllib.parse, uuid, zipfile

HOME = os.path.expanduser(os.environ.get("LEARN_HOME", "~/.gh-learn"))
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "assets", "app.html")
PORT = 4848
VERSION = "0.1.0"
TYPES = ("brief", "categories", "questions", "diagnose")
OPEN = ("pending", "claimed")   # request statuses the page shows as "in progress"
CLAIM_TTL = 900                  # seconds before a claimed request falls back to pending even if the agent still beats
LEVELS = {1: "foundations", 2: "working knowledge", 3: "practitioner", 4: "expert", 5: "edge of the field"}

# ---------- storage
def now(): return dt.datetime.now().isoformat(timespec="seconds")
def today(): return dt.date.today().isoformat()
def slugify(s): return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:48] or "topic"
def jload(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d
def jsave(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    t = p + ".tmp"
    with open(t, "w") as f: json.dump(o, f, indent=1, ensure_ascii=False)
    os.replace(t, p)
def index_path(): return os.path.join(HOME, "index.json")
def index():
    i = jload(index_path(), {"version": 1, "topics": [], "settings": {"read_seconds": 8, "answer_seconds": 20, "block": 5}})
    i.setdefault("settings", {}).setdefault("read_seconds", 8); i["settings"].setdefault("answer_seconds", 20); i["settings"].setdefault("block", 5); i["settings"].setdefault("auto_requests", 1)
    return i
def tdir(slug): return os.path.join(HOME, "topics", slug)
def tpath(slug): return os.path.join(tdir(slug), "topic.json")
def topic(slug):
    t = jload(tpath(slug), None)
    if t is None: sys.exit(f"no topic '{slug}' (learn.py topics)")
    for k, d in (("brief", None), ("categories", []), ("questions", []), ("attempts", []), ("srs", {}), ("plan", None), ("level_hint", 2), ("archived", False)):
        t.setdefault(k, d)
    return t
def live(t): return [q for q in t["questions"] if not q.get("retired")]
def save_topic(t): jsave(tpath(t["slug"]), t)
def rdir(): return os.path.join(HOME, "requests")
def requests_all():
    os.makedirs(rdir(), exist_ok=True)
    rs = [jload(os.path.join(rdir(), f), None) for f in sorted(os.listdir(rdir())) if f.endswith(".json")]
    return [r for r in rs if r]
def rsave(r): jsave(os.path.join(rdir(), r["id"] + ".json"), r)
LOCK = threading.RLock(); _LD = threading.local()
@contextlib.contextmanager
def flock():
    """Cross-process lock ($LEARN_HOME/.lock via flock / msvcrt) around every read-modify-write of topic, index and request files,
    so two agents, or the page and an agent, never clobber each other. Re-entrant within a thread."""
    if getattr(_LD, "depth", 0):
        _LD.depth += 1
        try: yield
        finally: _LD.depth -= 1
        return
    os.makedirs(HOME, exist_ok=True)
    with LOCK:
        f = open(os.path.join(HOME, ".lock"), "a+"); _LD.depth = 1
        try:
            try:
                if os.name == "nt": import msvcrt; f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                else: import fcntl; fcntl.flock(f, fcntl.LOCK_EX)
            except Exception: pass
            yield
        finally:
            _LD.depth = 0
            try:
                if os.name == "nt": import msvcrt; f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else: import fcntl; fcntl.flock(f, fcntl.LOCK_UN)
            except Exception: pass
            f.close()
def age_s(ts):
    try: return (dt.datetime.now() - dt.datetime.fromisoformat(ts)).total_seconds()
    except Exception: return 1e9
AGENT_ID = f"{socket.gethostname().split('.')[0]}-{os.getpid()}"
def adir(): return os.path.join(HOME, "agents")
def agent_beat(state="listening"): jsave(os.path.join(adir(), AGENT_ID + ".json"), {"id": AGENT_ID, "state": state, "ts": now(), "pid": os.getpid()})
def agents_all():
    os.makedirs(adir(), exist_ok=True); out = []
    for f in os.listdir(adir()):
        if not f.endswith(".json"): continue
        a = jload(os.path.join(adir(), f), None)
        if not a or age_s(a.get("ts", "")) > 3600:
            try: os.remove(os.path.join(adir(), f))
            except Exception: pass
            continue
        a["age"] = int(age_s(a["ts"])); a["online"] = a["age"] < 15 and a.get("state") == "listening"; out.append(a)
    return out
def agent_online(aid):
    """For claims: an agent counts as alive for CLAIM_TTL after its last beat (it stops beating while it writes a response)."""
    a = next((x for x in agents_all() if x["id"] == aid), None); return bool(a and a["age"] < CLAIM_TTL)
def agent_status():
    ag = agents_all(); on = [a for a in ag if a["online"] or (a.get("state") == "working" and a["age"] < CLAIM_TTL)]
    last = max((a["ts"] for a in ag), default=None)
    return {"online": bool(on), "count": len(on), "agents": [a["id"] for a in on], "last_seen": last}

# ---------- learning maths
def srs_update(card, correct):
    """SM-2 lite. card: {ease, interval, due, reps, lapses}"""
    c = dict(card or {"ease": 2.5, "interval": 0, "due": today(), "reps": 0, "lapses": 0})
    if correct:
        c["reps"] += 1
        c["interval"] = 1 if c["reps"] == 1 else 3 if c["reps"] == 2 else min(365, round(c["interval"] * c["ease"]))   # a year is the longest gap
        c["ease"] = min(3.0, c["ease"] + 0.1)
    else:
        c["reps"] = 0; c["lapses"] += 1; c["interval"] = 1; c["ease"] = max(1.3, c["ease"] - 0.2)
    c["due"] = (dt.date.today() + dt.timedelta(days=c["interval"])).isoformat()
    return c

def edge(t):
    """Per category: accuracy by level (first attempt per question in quiz mode), the edge level, next level to serve."""
    q = {x["id"]: x for x in live(t)}
    seen, acc = set(), {}
    for a in t["attempts"]:
        if a.get("mode") != "quiz" or a["qid"] in seen or a["qid"] not in q: continue
        seen.add(a["qid"]); x = q[a["qid"]]
        d = acc.setdefault(x["cat"], {}).setdefault(int(x.get("level", 2)), [0, 0])
        d[1] += 1; d[0] += 1 if a["correct"] else 0
    out = {}
    for c in t["categories"]:
        by = acc.get(c["id"], {})
        e = 0
        for L in range(1, 6):
            r, n = by.get(L, [0, 0])
            if n >= 3 and r / n >= 0.6: e = L
            elif n >= 3: break
        n_all = sum(v[1] for v in by.values()); r_all = sum(v[0] for v in by.values())
        hi = max(by) if by else 0; rh, nh = by.get(hi, [0, 0])
        nxt = max(1, min(5, (hi + 1 if nh >= 3 and rh / nh >= 0.8 else hi - 1 if nh >= 3 and rh / nh <= 0.4 else hi) if by else int(t.get("level_hint", 2))))
        rn, nn = by.get(nxt, [0, 0])
        out[c["id"]] = {"edge": e, "next": nxt, "need": max(0, 3 - nn), "answered": n_all, "accuracy": round(r_all / n_all, 2) if n_all else None,
                        "by_level": {str(k): {"right": v[0], "n": v[1]} for k, v in sorted(by.items())}}
    return out

def due_cards(t):
    seen = {a["qid"] for a in t["attempts"]}
    d = []
    for q in live(t):
        if q["id"] not in seen: continue
        c = t["srs"].get(q["id"])
        if not c or c["due"] <= today(): d.append(q["id"])
    return d

def qstats(t):
    """Per live question: times seen, times wrong, mean ms, last seen, wrong streak; `leech` once wrong 3+ times."""
    out = {q["id"]: {"seen": 0, "wrong": 0, "ms": 0, "last": "", "streak": 0} for q in live(t)}
    for a in t["attempts"]:
        x = out.get(a["qid"])
        if not x: continue
        x["seen"] += 1; x["ms"] += int(a.get("ms") or 0); x["last"] = a["ts"]
        if a["correct"]: x["streak"] = 0
        else: x["wrong"] += 1; x["streak"] += 1
    for x in out.values(): x["avg_ms"] = round(x["ms"] / x["seen"]) if x["seen"] else None; x["leech"] = x["wrong"] >= 3; x.pop("ms")
    return out

def leeches(t, limit=10):
    q = {x["id"]: x for x in live(t)}; st = qstats(t)
    rows = sorted(((k, v) for k, v in st.items() if v["wrong"] >= 2), key=lambda kv: (-kv[1]["wrong"], -kv[1]["streak"]))[:limit]
    return [{"q": q[k]["q"], "cat": q[k]["cat"], "level": q[k].get("level"), "answer": q[k]["choices"][q[k]["answer"]], "wrong": v["wrong"], "seen": v["seen"]} for k, v in rows]

def due_all():
    """Every due card across the hub's live topics, oldest-due first: the cross-topic review."""
    out = []
    for e in index()["topics"]:
        t = topic(e["slug"])
        if t.get("archived"): continue
        cats = {c["id"]: c["name"] for c in t["categories"]}; q = {x["id"]: x for x in live(t)}
        for qid in due_cards(t):
            out.append({"slug": t["slug"], "name": t["name"], "cat_name": cats.get(q[qid]["cat"], q[qid]["cat"]), "due": t["srs"].get(qid, {}).get("due", ""), "q": q[qid]})
    return sorted(out, key=lambda x: x["due"])

def summary(t):
    e = edge(t); att = t["attempts"]
    unanswered = {}
    seen = {a["qid"] for a in att}
    lv = live(t); lid = {q["id"] for q in lv}
    for q in lv:
        if q["id"] not in seen: unanswered.setdefault(q["cat"], {}).setdefault(int(q.get("level", 2)), 0); unanswered[q["cat"]][int(q.get("level", 2))] += 1
    activity = {}
    for a in att:
        d0 = activity.setdefault(a["ts"][:10], [0, 0]); d0[1] += 1; d0[0] += 1 if a["correct"] else 0
    days = sorted(activity); streak = 0
    d = dt.date.today()
    if days and days[-1] == (d - dt.timedelta(days=1)).isoformat(): d -= dt.timedelta(days=1)   # a streak survives until the end of today
    while d.isoformat() in activity: streak += 1; d -= dt.timedelta(days=1)
    timed = [a["ms"] for a in att if a.get("ms")]; st = qstats(t)
    return {"slug": t["slug"], "name": t["name"], "goal": t.get("goal", ""), "archived": bool(t.get("archived")), "has_brief": bool(t["brief"]), "categories": len(t["categories"]),
            "avg_ms": round(sum(timed) / len(timed)) if timed else None, "leeches": sum(1 for x in st.values() if x["leech"]),
            "questions": len(lv), "retired": len(t["questions"]) - len(lv), "answered": len(seen & lid), "attempts": len(att), "accuracy": round(sum(a["correct"] for a in att) / len(att), 2) if att else None,
            "due": len(due_cards(t)), "edge": e, "unanswered": {k: {str(l): n for l, n in v.items()} for k, v in unanswered.items()},
            "streak_days": streak, "last_active": att[-1]["ts"] if att else t.get("created"), "plan": bool(t.get("plan")), "activity": activity,
            "overall_edge": round(sum(v["edge"] for v in e.values()) / len(e), 1) if e else 0}

# ---------- validation + merge
def length_tells(q):
    """Length tells in one question's choices. Returns (errors, stats); stats is (right is strictly longest, right is strictly shortest, right length / mean distractor length) or None when the question is malformed.
    A learner who cannot answer picks the longest, most detailed option (or, once they know that trick is being countered, the shortest). The checks are symmetric and ignore tiny absolute gaps so short factual choices (numbers, names) are not flagged."""
    ch = q.get("choices") or []; a = q.get("answer")
    if len(ch) != 4 or not isinstance(a, int) or not 0 <= a < 4: return [], None
    L = [len(str(c).strip()) for c in ch]; r = L[a]; d = sorted(L[i] for i in range(4) if i != a); errs = []
    if r > 1.3 * d[-1] and r - d[-1] > 12: errs.append(f"the right answer is the longest by far ({r} chars; longest distractor {d[-1]}); write every distractor within ~30% of its length and as specific")
    elif r >= 30 and d[1] < 0.65 * r: errs.append(f"two distractors are far shorter than the right answer ({r} chars vs {d[0]}, {d[1]}, {d[2]}); the learner drops them and coin-flips, so all three must match its length and detail")
    if r < 0.6 * d[0] and d[0] - r > 12: errs.append(f"the right answer is the shortest by far ({r} chars; shortest distractor {d[0]}); give it the same detail as the distractors or trim them")
    return errs, (r > d[-1], r < d[0], r / (sum(d) / 3))

def batch_length_tells(qs):
    """Batch-level length tells: even when no single question trips length_tells, 'the longest one is right' can still pay off across a round."""
    st = [s for s in (length_tells(q)[1] for q in qs) if s]; n = len(st); errs = []
    if n < 6: return errs
    lo = sum(1 for s in st if s[0]); sh = sum(1 for s in st if s[1]); ratio = sum(s[2] for s in st) / n
    if lo > 0.45 * n: errs.append(f"the right answer is the longest option in {lo}/{n} questions (chance would be about {n // 4}); lengthen distractors or trim the right answer in some of them")
    if sh > 0.45 * n: errs.append(f"the right answer is the shortest option in {sh}/{n} questions (chance would be about {n // 4}); balance the lengths")
    if ratio > 1.2: errs.append(f"across the batch the right answer averages {ratio:.2f}x the length of its distractors; aim for about 1.0")
    if ratio < 0.8: errs.append(f"across the batch the right answer averages {ratio:.2f}x the length of its distractors; aim for about 1.0")
    return errs

def length_report(qs):
    st = [s for s in (length_tells(q)[1] for q in qs) if s]; n = len(st)
    if not n: return ""
    return f"length check: right answer longest in {sum(1 for s in st if s[0])}/{n}, shortest in {sum(1 for s in st if s[1])}/{n}, mean length ratio {sum(s[2] for s in st) / n:.2f} (1.0 = no tell)"

def validate(kind, body, t=None):
    errs = []
    if kind == "brief":
        for k in ("mode", "summary", "sections"):
            if k not in body: errs.append(f"brief.{k} missing")
        if body.get("mode") not in ("cliff", "bullets"): errs.append("brief.mode must be cliff|bullets")
        for i, s in enumerate(body.get("sections", [])):
            if not s.get("title"): errs.append(f"sections[{i}].title missing")
            if not (s.get("bullets") or s.get("text")): errs.append(f"sections[{i}] needs bullets[] or text")
        for k in ("movers", "news"):
            for i, m in enumerate(body.get(k, [])):
                if not m.get("name" if k == "movers" else "title"): errs.append(f"{k}[{i}] missing name/title")
        if not body.get("as_of"): errs.append("brief.as_of (YYYY-MM-DD) missing — say when this knowledge is from")
    elif kind == "categories":
        cats = body.get("categories") or []
        if not (4 <= len(cats) <= 12): errs.append("categories: give 4–12")
        ids = set()
        for i, c in enumerate(cats):
            if not c.get("id") or not re.match(r"^[a-z0-9-]+$", c["id"]): errs.append(f"categories[{i}].id must be kebab-case")
            if c.get("id") in ids: errs.append(f"duplicate category id {c.get('id')}")
            ids.add(c.get("id"))
            if not c.get("name"): errs.append(f"categories[{i}].name missing")
            if not c.get("why"): errs.append(f"categories[{i}].why missing (one line: why this matters)")
    elif kind == "questions":
        qs = body.get("questions") or []
        if not qs: errs.append("questions[] empty")
        cats = {c["id"] for c in (t["categories"] if t else [])}
        for i, q in enumerate(qs):
            p = f"questions[{i}]"
            if not q.get("q") or len(q["q"]) < 12: errs.append(f"{p}.q too short")
            ch = q.get("choices") or []
            if len(ch) != 4: errs.append(f"{p}.choices must have exactly 4")
            if len(set(map(str, ch))) != len(ch): errs.append(f"{p}.choices has duplicates")
            if not isinstance(q.get("answer"), int) or not (0 <= q.get("answer", -1) < 4): errs.append(f"{p}.answer must be index 0–3")
            if not q.get("why"): errs.append(f"{p}.why missing (one or two lines: why the answer is right)")
            if int(q.get("level", 0)) not in LEVELS: errs.append(f"{p}.level must be 1–5")
            if cats and q.get("cat") not in cats: errs.append(f"{p}.cat '{q.get('cat')}' is not a category id of this topic")
            if any(w in q["q"].lower() for w in ("all of the above", "none of the above")) or any("all of the above" in str(c).lower() for c in ch): errs.append(f"{p}: no all/none-of-the-above")
            errs += [f"{p}: {e}" for e in length_tells(q)[0]]
        if len(qs) >= 6:
            from collections import Counter
            top = Counter(q.get("answer") for q in qs).most_common(1)[0]
            if top[1] > 0.5 * len(qs): errs.append(f"answer index {top[0]} is correct in {top[1]}/{len(qs)} questions; spread the right answer across slots (choices are shuffled on merge anyway, but write them balanced)")
            errs += batch_length_tells(qs)
    elif kind == "diagnose":
        for k in ("diagnosis", "root_causes", "protocol"):
            if not body.get(k): errs.append(f"diagnose.{k} missing")
        for i, s in enumerate(body.get("protocol", [])):
            if not s.get("step"): errs.append(f"protocol[{i}].step missing")
    else: errs.append(f"unknown type {kind}")
    return errs

def merge(kind, body, t):
    if kind == "brief":
        body["generated"] = now(); t["brief"] = body
    elif kind == "categories":
        have = {c["id"]: c for c in t["categories"]}
        for c in body["categories"]: have[c["id"]] = {**have.get(c["id"], {}), **c}
        t["categories"] = list(have.values())
        if body.get("level_hint"): t["level_hint"] = int(body["level_hint"])
    elif kind == "questions":
        norm = lambda s: re.sub(r"\W+", " ", s.lower()).strip()
        seen = {norm(q["q"]) for q in t["questions"]}; added = 0
        for q in body["questions"]:
            if norm(q["q"]) in seen: continue
            seen.add(norm(q["q"]))
            q["id"] = "q" + uuid.uuid4().hex[:8]; q["created"] = now(); q["level"] = int(q["level"])
            import random; order = list(range(4)); random.shuffle(order)   # kill position bias
            q["choices"] = [q["choices"][i] for i in order]; q["answer"] = order.index(q["answer"])
            t["questions"].append(q); added += 1
        return added
    elif kind == "diagnose":
        body["generated"] = now(); t["plan"] = body
    return 1

def fulfil(req_id, body, force=False):
    with flock():
        r = jload(os.path.join(rdir(), req_id + ".json"), None)
        if not r: raise ValueError(f"no request {req_id}")
        if r["status"] == "done": raise ValueError(f"request {req_id} was already fulfilled at {r.get('done')}")
        if r["status"] == "cancelled": raise ValueError(f"request {req_id} was cancelled from the page")
        c = r.get("claimed")
        if c and c.get("by") != AGENT_ID and not force and agent_online(c["by"]) and age_s(c["ts"]) < CLAIM_TTL:
            raise ValueError(f"request {req_id} is claimed by agent {c['by']} ({int(age_s(c['ts']))}s ago); pass --force to take it over")
        t = topic(r["topic"]); errs = validate(r["type"], body, t)
        if errs: raise ValueError("invalid response:\n  " + "\n  ".join(errs))
        n = merge(r["type"], body, t); save_topic(t)
        r["status"] = "done"; r["done"] = now(); r["added"] = n; r["by"] = AGENT_ID; rsave(r)
    return n

def open_requests():
    """Requests the page is still waiting on. Claims by agents that went quiet (no heartbeat for 60 s) or that are older than CLAIM_TTL fall back to pending."""
    with flock():
        out = []
        for r in requests_all():
            if r["status"] == "claimed":
                c = r.get("claimed") or {}
                if age_s(c.get("ts", "")) > CLAIM_TTL or not agent_online(c.get("by", "")):
                    r["status"] = "pending"; r.pop("claimed", None); rsave(r)
            if r["status"] in OPEN: out.append(r)
        return out

def claim(rs):
    with flock():
        for r in rs: r["status"] = "claimed"; r["claimed"] = {"by": AGENT_ID, "ts": now()}; rsave(r)

def cancel_request(req_id):
    with flock():
        r = jload(os.path.join(rdir(), req_id + ".json"), None)
        if not r: raise ValueError(f"no request {req_id}")
        if r["status"] in OPEN: r["status"] = "cancelled"; r["cancelled"] = now(); rsave(r)
        return r

def new_request(slug, kind, params=None, note=""):
    if kind not in TYPES: raise ValueError(f"type must be one of {TYPES}")
    with flock():
        topic(slug)
        # collapse duplicates: one open request of a type per topic
        for r in open_requests():
            if r["topic"] == slug and r["type"] == kind:
                r["params"] = {**r.get("params", {}), **(params or {})}; rsave(r); return r
        r = {"id": dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4], "ts": now(), "topic": slug, "type": kind,
             "params": params or {}, "note": note, "status": "pending"}
        rsave(r); return r

def index_entry(i, slug):
    e = next((x for x in i["topics"] if x["slug"] == slug), None)
    if not e: raise ValueError(f"no topic '{slug}'")
    return e

def update_topic(slug, name=None, goal=None, level=None, archived=None):
    """Rename / re-goal / re-level / archive. The slug (and so every URL and request) stays stable."""
    with flock():
        t = topic(slug); i = index(); e = index_entry(i, slug)
        if name is not None and name.strip(): t["name"] = e["name"] = name.strip()
        if goal is not None: t["goal"] = goal.strip()
        if level: t["level_hint"] = max(1, min(5, int(level)))
        if archived is not None: t["archived"] = e["archived"] = bool(archived)
        save_topic(t); jsave(index_path(), i)
        return t

def delete_topic(slug, purge=False):
    """Moves the topic folder to $LEARN_HOME/trash/<slug>-<stamp> (or deletes it with purge) and cancels its open requests."""
    with flock():
        i = index(); i["topics"] = [e for e in i["topics"] if e["slug"] != slug]; jsave(index_path(), i)
        for r in requests_all():
            if r["topic"] == slug and r["status"] in OPEN: r["status"] = "cancelled"; r["cancelled"] = now(); rsave(r)
        src = tdir(slug); dst = None
        if os.path.isdir(src):
            if purge: shutil.rmtree(src, ignore_errors=True)
            else:
                dst = os.path.join(HOME, "trash", f"{slug}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"); os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.move(src, dst)
        return dst

def undelete_topic(slug):
    with flock():
        tr = os.path.join(HOME, "trash"); cands = sorted(d for d in (os.listdir(tr) if os.path.isdir(tr) else []) if re.match(re.escape(slug) + r"-\d{8}-\d{6}$", d))
        if not cands: raise ValueError(f"nothing in the trash for '{slug}'")
        if os.path.exists(tpath(slug)): raise ValueError(f"topic '{slug}' already exists; remove it first")
        shutil.move(os.path.join(tr, cands[-1]), tdir(slug)); t = topic(slug)
        i = index(); i["topics"].append({"slug": slug, "name": t["name"], "created": t.get("created", now()), "archived": bool(t.get("archived"))}); jsave(index_path(), i)
        return t

def retire_question(slug, qid, reason="", restore=False):
    """A retired question leaves the bank, the edge maths and the SRS deck but stays in the file (so the agent is told not to rewrite it verbatim, and it can be restored)."""
    with flock():
        t = topic(slug); q = next((x for x in t["questions"] if x["id"] == qid), None)
        if not q: raise ValueError("unknown question")
        if restore: q.pop("retired", None)
        else: q["retired"] = {"ts": now(), "reason": (reason or "flagged").strip()[:200]}; t["srs"].pop(qid, None)
        save_topic(t); return q

def flagged(t, limit=10):
    out = [{"q": q["q"], "cat": q["cat"], "level": q.get("level"), "answer": q["choices"][q["answer"]] if 0 <= q.get("answer", -1) < len(q.get("choices", [])) else "", "reason": q["retired"].get("reason", ""), "ts": q["retired"].get("ts", "")}
           for q in t["questions"] if q.get("retired")]
    return sorted(out, key=lambda x: x["ts"])[-limit:]

def backup_zip(out=None):
    """Zip of every topic file plus index.json (settings). Not the request queue, logs or agents: those are runtime."""
    out = out or os.path.join(HOME, "backups", f"srs-edge-learning-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.zip")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with flock():
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            if os.path.exists(index_path()): z.write(index_path(), "index.json")
            for e in index()["topics"]:
                for f in ("topic.json", "progress.md"):
                    pth = os.path.join(tdir(e["slug"]), f)
                    if os.path.exists(pth): z.write(pth, f"topics/{e['slug']}/{f}")
    return out

def restore_from(src, overwrite=False):
    """Import topics from a backup zip or a single topic.json. Existing slugs are skipped unless overwrite. Settings stay local. Returns (added, replaced, skipped)."""
    added, replaced, skipped = [], [], []
    with flock():
        i = index(); have = {e["slug"] for e in i["topics"]}
        def put(t):
            slug = t.get("slug") or slugify(t.get("name", ""))
            if not slug or not isinstance(t.get("questions"), list) or not t.get("name"): raise ValueError("not a topic file (needs slug, name, questions)")
            t["slug"] = slug
            if slug in have and not overwrite: skipped.append(slug); return
            (replaced if slug in have else added).append(slug); jsave(tpath(slug), t)
            if slug not in have: i["topics"].append({"slug": slug, "name": t["name"], "created": t.get("created", now()), "archived": bool(t.get("archived"))}); have.add(slug)
            else: index_entry(i, slug).update({"name": t["name"], "archived": bool(t.get("archived"))})
        if zipfile.is_zipfile(src):
            with zipfile.ZipFile(src) as z:
                names = [n for n in z.namelist() if re.match(r"^topics/[^/]+/topic\.json$", n)]
                if not names: raise ValueError("no topics/<slug>/topic.json entries in that zip")
                for n in names:
                    t = json.loads(z.read(n).decode("utf-8")); t.setdefault("slug", n.split("/")[1]); put(t)
        else:
            with open(src, encoding="utf-8") as f: put(json.load(f))
        jsave(index_path(), i)
    return added, replaced, skipped

def add_attempt(slug, qid, picked, ms, mode):
    with flock():
        t = topic(slug); q = next((x for x in t["questions"] if x["id"] == qid), None)
        if not q: raise ValueError("unknown question")
        if q.get("retired"): raise ValueError("that question was retired")
        correct = (picked == q["answer"])
        t["attempts"].append({"qid": qid, "ts": now(), "picked": picked, "correct": correct, "ms": int(ms or 0), "mode": mode or "quiz"})
        t["srs"][qid] = srs_update(t["srs"].get(qid), correct)
        save_topic(t)
    return {"correct": correct, "answer": q["answer"], "why": q.get("why", ""), "srs": t["srs"][qid]}

# ---------- commands
def cmd_setup(a):
    os.makedirs(os.path.join(HOME, "topics"), exist_ok=True); os.makedirs(rdir(), exist_ok=True)
    i = index(); jsave(index_path(), i)
    print(f"home {HOME}\ntopics {len(i['topics'])}\napp {'ok' if os.path.exists(APP) else 'MISSING ' + APP}")

def cmd_add(a):
    with flock():
        i = index(); slug = slugify(a.name)
        if os.path.exists(tpath(slug)): print(slug); return
        t = {"slug": slug, "name": a.name.strip(), "goal": (a.goal or "").strip(), "created": now(), "level_hint": a.level or 2,
             "brief": None, "categories": [], "questions": [], "attempts": [], "srs": {}, "plan": None, "archived": False}
        save_topic(t); i["topics"].append({"slug": slug, "name": t["name"], "created": t["created"], "archived": False}); jsave(index_path(), i)
    print(slug)

def cmd_topics(a):
    i = index()
    if not i["topics"]: print("no topics yet — learn.py add \"<topic>\""); return
    print(f"{'slug':28} {'edge':>4} {'acc':>5} {'Q':>4} {'due':>4}  last")
    for e in i["topics"]:
        s = summary(topic(e["slug"]))
        if s["archived"] and not a.all: continue
        print(f"{s['slug']:28} {s['overall_edge']:>4} {('' if s['accuracy'] is None else f'{int(s['accuracy']*100)}%'):>5} {s['questions']:>4} {s['due']:>4}  {str(s['last_active'])[:16]}{'  (archived)' if s['archived'] else ''}")

def cmd_status(a):
    slugs = [a.slug] if a.slug else [e["slug"] for e in index()["topics"]]
    for slug in slugs:
        t = topic(slug); s = summary(t)
        print(f"# {t['name']}  ({slug})\n goal: {t.get('goal') or '-'}\n brief: {'yes' if s['has_brief'] else 'no'}   categories: {s['categories']}   questions: {s['questions']} ({s['answered']} answered)   attempts: {s['attempts']}   accuracy: {s['accuracy']}   due: {s['due']}   streak: {s['streak_days']}d")
        for c in t["categories"]:
            e = s["edge"][c["id"]]
            print(f"  {c['name']:34} edge L{e['edge']} ({LEVELS.get(e['edge'], 'not yet measured')})  next L{e['next']}  answered {e['answered']}  acc {e['accuracy']}  bank {s['unanswered'].get(c['id'], {})}")
        if t.get("plan"): print(f" plan: {t['plan']['diagnosis'][:120]}…")
        pend = [r for r in requests_all() if r["status"] == "pending" and r["topic"] == slug]
        if pend: print(f" pending requests: {', '.join(r['type'] + ':' + r['id'] for r in pend)}")

def cmd_pending(a):
    """Prints open requests with their context. Unless --peek, it claims them for this agent so a second agent serving the same hub skips them."""
    end = time.time() + (a.wait or 0)
    while True:
        if a.wait: agent_beat("listening")
        rs = [r for r in open_requests() if r["status"] == "pending" or (r.get("claimed") or {}).get("by") == AGENT_ID]
        if rs or time.time() >= end:
            if a.wait: agent_beat("working" if rs else "away")
            if rs and not a.peek: claim(rs); agent_beat("working")
            out = []
            for r in rs:
                t = topic(r["topic"]); s = summary(t)
                ctx = {"name": t["name"], "goal": t.get("goal", ""), "level_hint": t.get("level_hint", 2), "categories": t["categories"], "edge": s["edge"], "unanswered": s["unanswered"]}
                if r["type"] == "questions":
                    ctx["existing_questions"] = [q["q"] for q in t["questions"]][-60:]
                    fl = flagged(t)
                    if fl: ctx["flagged"] = fl
                if r["type"] == "diagnose":
                    ctx["misses"] = misses(t, 30); ctx["leeches"] = leeches(t)
                out.append({**r, "context": ctx})
            print(json.dumps(out, indent=1, ensure_ascii=False)); return
        time.sleep(2)

def misses(t, limit):
    q = {x["id"]: x for x in live(t)}; out = []
    for a in reversed(t["attempts"]):
        if a["correct"] or a["qid"] not in q: continue
        x = q[a["qid"]]; out.append({"cat": x["cat"], "level": x["level"], "q": x["q"], "picked": x["choices"][a["picked"]] if isinstance(a["picked"], int) and 0 <= a["picked"] < 4 else "(timeout)", "answer": x["choices"][x["answer"]], "ts": a["ts"]})
        if len(out) >= limit: break
    return out

def cmd_misses(a): print(json.dumps(misses(topic(a.slug), a.limit), indent=1, ensure_ascii=False))

def read_body(src):
    raw = sys.stdin.read() if src == "-" else open(src).read()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(raw)

def cmd_fulfil(a):
    body = read_body(a.file); n = fulfil(a.req_id, body, force=a.force); rep = length_report(body.get("questions") or [])
    print(f"ok {a.req_id} ({n} merged)" + (" · " + rep if rep else ""))

def cmd_validate(a):
    body = read_body(a.file); t = topic(a.topic) if a.topic else None
    errs = validate(a.type, body, t)
    rep = length_report(body.get("questions") or []) if a.type == "questions" else ""
    print(("OK" + (" · " + rep if rep else "")) if not errs else "\n".join(errs + ([rep] if rep else []))); sys.exit(1 if errs else 0)

def cmd_due(a):
    t = topic(a.slug); q = {x["id"]: x for x in t["questions"]}
    for d in due_cards(t): print(f"[{q[d]['cat']} L{q[d]['level']}] {q[d]['q']}")

def cmd_export(a):
    t = topic(a.slug); s = summary(t); L = [f"# {t['name']} — progress ({today()})", "", f"Goal: {t.get('goal') or '-'}", "",
         f"- questions answered: {s['answered']} / {s['questions']}  · accuracy {s['accuracy']}  · streak {s['streak_days']} days  · cards due {s['due']}", "", "| category | edge | next | answered | accuracy |", "|---|---|---|---|---|"]
    for c in t["categories"]:
        e = s["edge"][c["id"]]; L.append(f"| {c['name']} | L{e['edge']} {LEVELS.get(e['edge'], '')} | L{e['next']} | {e['answered']} | {e['accuracy']} |")
    if t.get("plan"):
        L += ["", "## Training protocol", t["plan"]["diagnosis"], ""] + [f"{i+1}. {p['step']}" for i, p in enumerate(t["plan"]["protocol"])]
    p = os.path.join(tdir(a.slug), "progress.md"); open(p, "w").write("\n".join(L) + "\n"); print(p)

def cmd_rename(a):
    t = update_topic(a.slug, name=a.name, goal=a.goal, level=a.level); print(f"{t['slug']}: {t['name']}" + (f" — {t['goal']}" if t.get("goal") else "") + f" (L{t['level_hint']})")
def cmd_archive(a): update_topic(a.slug, archived=(a.cmd == "archive")); print(f"{a.slug} {'archived' if a.cmd == 'archive' else 'back on the home page'}")
def cmd_remove(a):
    if not a.yes and sys.stdin.isatty():
        if input(f"{'Delete for good' if a.purge else 'Move to trash'}: {a.slug}? [y/N] ").strip().lower() != "y": print("kept"); return
    dst = delete_topic(a.slug, purge=a.purge); print(f"deleted {a.slug}" if a.purge else f"moved to {dst}  (learn.py undelete {a.slug} brings it back)")
def cmd_undelete(a): t = undelete_topic(a.slug); print(f"restored {t['slug']}: {t['name']}")
def cmd_questions(a):
    t = topic(a.slug)
    for q in t["questions"]:
        r = q.get("retired")
        if bool(r) != a.retired: continue
        print(f"{q['id']}  [{q['cat']} L{q.get('level')}] {q['q'][:90]}" + (f"   retired: {r.get('reason')}" if r else ""))
def cmd_retire(a):
    q = retire_question(a.slug, a.qid, a.reason, restore=a.restore); print(f"{'restored' if a.restore else 'retired'} {q['id']}: {q['q'][:80]}")
def cmd_stats(a):
    t = topic(a.slug); q = {x["id"]: x for x in live(t)}; st = qstats(t); seen = [(k, v) for k, v in st.items() if v["seen"]]
    s = summary(t); print(f"# {t['name']}: {len(seen)} questions met, avg {round((s['avg_ms'] or 0) / 1000, 1)}s to answer, {s['leeches']} leeches")
    for title, rows in (("leeches (wrong 3+ times)", [x for x in seen if x[1]["leech"]]), ("wrong on last try", [x for x in seen if x[1]["streak"] and not x[1]["leech"]]), ("slowest", sorted((x for x in seen if x[1]["avg_ms"]), key=lambda x: -x[1]["avg_ms"])[:5])):
        if not rows: continue
        print(f"\n## {title}")
        for k, v in rows: print(f"  {k}  [{q[k]['cat']} L{q[k].get('level')}] wrong {v['wrong']}/{v['seen']}  {round((v['avg_ms'] or 0) / 1000, 1)}s  {q[k]['q'][:80]}")
def cmd_backup(a): print(backup_zip(a.out))
def cmd_restore(a):
    added, replaced, skipped = restore_from(a.file, overwrite=a.overwrite)
    print(f"added {len(added)} {added}\nreplaced {len(replaced)} {replaced}\nskipped {len(skipped)} {skipped}" + ("  (pass --overwrite to replace existing topics)" if skipped else ""))

# ---------- server
def hub_path(): return os.path.join(HOME, "hub.json")
def hub_info(port):
    """What is on this port? Our hub for this LEARN_HOME returns its ping; anything else returns None."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=0.6) as r: i = json.load(r)
        return i if i.get("app") == "srs-edge-learning" else None
    except Exception: return None
def ours(i): return bool(i) and os.path.realpath(i.get("home", "")) == os.path.realpath(HOME)
def find_port(want):
    """(port, already_running). Prefer the port the last hub for this home recorded, then `want`, then the next ten."""
    h = jload(hub_path(), None)
    if h and h.get("port") and ours(hub_info(h["port"])): return h["port"], True
    for p in [want] + [q for q in range(want + 1, want + 11) if q != want]:
        if not port_open(p): return p, False
        if ours(hub_info(p)): return p, True
    raise ValueError(f"no free port between {want} and {want + 10}")

def make_handler():
    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
        def _json(self, code, o):
            b = json.dumps(o, ensure_ascii=False).encode(); self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
        def _body(self):
            n = int(self.headers.get("Content-Length") or 0); return json.loads(self.rfile.read(n) or b"{}")
        def do_GET(self):
            u = urllib.parse.urlparse(self.path); p = u.path; qs = urllib.parse.parse_qs(u.query)
            try:
                if p in ("/", "/index.html"):
                    b = open(APP, "rb").read(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
                elif p == "/api/index":
                    i = index(); self._json(200, {"settings": i["settings"], "home": HOME, "port": self.server.server_address[1], "version": VERSION, "levels": LEVELS, "agent": agent_status(), "topics": [summary(topic(e["slug"])) for e in i["topics"]],
                                                 "pending": [{"id": r["id"], "topic": r["topic"], "type": r["type"], "ts": r["ts"], "status": r["status"]} for r in open_requests()]})
                elif p == "/api/due": self._json(200, {"due": due_all()})
                elif p == "/api/ping": self._json(200, {"app": "srs-edge-learning", "version": VERSION, "home": HOME, "port": self.server.server_address[1]})
                elif p == "/api/backup":
                    tmp = os.path.join(HOME, "backups", "_download.zip"); backup_zip(tmp); b = open(tmp, "rb").read(); os.remove(tmp)
                    self.send_response(200); self.send_header("Content-Type", "application/zip"); self.send_header("Content-Disposition", f'attachment; filename="srs-edge-learning-{today()}.zip"'); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
                elif p.startswith("/api/topic/") and p.endswith("/export"):
                    t = topic(p.split("/")[3]); b = json.dumps(t, indent=1, ensure_ascii=False).encode()
                    self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Disposition", f'attachment; filename="{t["slug"]}.json"'); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
                elif p.startswith("/api/topic/"):
                    t = topic(p.split("/")[3]); open_requests(); self._json(200, {**t, "summary": summary(t), "due": due_cards(t), "qstats": qstats(t), "agent": agent_status(),
                                                               "requests": [r for r in requests_all() if r["topic"] == t["slug"]][-20:]})
                else: self._json(404, {"error": "not found"})
            except SystemExit as e: self._json(404, {"error": str(e)})
            except Exception as e: self._json(500, {"error": str(e)})
        def do_POST(self):
            u = urllib.parse.urlparse(self.path); p = u.path; qs = urllib.parse.parse_qs(u.query)
            try:
                if p == "/api/restore":
                    n = int(self.headers.get("Content-Length") or 0); raw = self.rfile.read(n)
                    os.makedirs(os.path.join(HOME, "backups"), exist_ok=True); tmp = os.path.join(HOME, "backups", "_upload.bin"); open(tmp, "wb").write(raw)
                    try: added, replaced, skipped = restore_from(tmp, overwrite=qs.get("overwrite", ["0"])[0] == "1")
                    finally: os.remove(tmp)
                    self._json(200, {"added": added, "replaced": replaced, "skipped": skipped}); return
                b = self._body()
                if p == "/api/topic":
                    a = argparse.Namespace(name=b["name"], goal=b.get("goal"), level=int(b.get("level") or 2))
                    import io, contextlib; buf = io.StringIO()
                    with contextlib.redirect_stdout(buf): cmd_add(a)
                    self._json(200, {"slug": buf.getvalue().strip()})
                elif p == "/api/request":
                    self._json(200, new_request(b["topic"], b["type"], b.get("params"), b.get("note", "")))
                elif p == "/api/attempt":
                    self._json(200, add_attempt(b["topic"], b["qid"], b.get("picked"), b.get("ms"), b.get("mode")))
                elif p == "/api/settings":
                    i = index(); i["settings"].update({k: int(v) for k, v in b.items() if k in ("read_seconds", "answer_seconds", "block", "auto_requests")}); jsave(index_path(), i); self._json(200, i["settings"])
                elif p == "/api/topic/delete": self._json(200, {"ok": True, "trash": delete_topic(b["slug"], purge=bool(b.get("purge")))})
                elif p == "/api/topic/undelete": self._json(200, {"ok": True, "slug": undelete_topic(b["slug"])["slug"]})
                elif p == "/api/topic/update":
                    t = update_topic(b["slug"], name=b.get("name"), goal=b.get("goal"), level=b.get("level"), archived=b.get("archived")); self._json(200, {"ok": True, "name": t["name"], "goal": t["goal"], "archived": t["archived"], "level_hint": t["level_hint"]})
                elif p == "/api/question/retire":
                    q = retire_question(b["topic"], b["qid"], b.get("reason", ""), restore=bool(b.get("restore")))
                    if b.get("replace") and not b.get("restore"): new_request(b["topic"], "questions", {"cats": [q["cat"]], "levels": [q.get("level", 2)], "n": 3}, f"replace a flagged question ({b.get('reason') or 'flagged'})")
                    self._json(200, {"ok": True, "retired": q.get("retired")})
                elif p == "/api/request/cancel": self._json(200, {"ok": True, "status": cancel_request(b["id"])["status"]})
                else: self._json(404, {"error": "not found"})
            except Exception as e: self._json(400, {"error": str(e)})
    return H

def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.3); return s.connect_ex(("127.0.0.1", port)) == 0

def cmd_serve(a):
    cmd_setup(argparse.Namespace())
    port, running = find_port(a.port)
    if running: print(f"already serving this hub at http://127.0.0.1:{port}/"); return
    if port != a.port: print(f"port {a.port} is taken by something else; using {port}")
    class S(socketserver.ThreadingMixIn, http.server.HTTPServer): daemon_threads = True; allow_reuse_address = True
    srv = S(("127.0.0.1", port), make_handler())
    url = f"http://127.0.0.1:{port}/"; jsave(hub_path(), {"port": port, "pid": os.getpid(), "ts": now(), "home": HOME, "version": VERSION})
    print(f"serving {url}  (ctrl-c to stop)"); sys.stdout.flush()
    if a.open: open_browser(url)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        h = jload(hub_path(), None)
        if h and h.get("pid") == os.getpid():
            try: os.remove(hub_path())
            except Exception: pass

def open_browser(url):
    try:
        if sys.platform == "darwin": subprocess.Popen(["open", url])
        elif os.name == "nt": os.startfile(url)  # type: ignore
        else: subprocess.Popen(["xdg-open", url])
    except Exception: print(f"open this in your browser: {url}")

def cmd_open(a):
    port, running = find_port(a.port)
    if not running:
        os.makedirs(HOME, exist_ok=True); log = open(os.path.join(HOME, "hub.log"), "ab")
        kw = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "serve", "--port", str(port)], stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kw)
        for _ in range(40):
            if ours(hub_info(port)): break
            time.sleep(0.25)
        h = jload(hub_path(), None); port = h["port"] if h and h.get("port") else port
    url = f"http://127.0.0.1:{port}/"
    if a.slug: url += "#/topic/" + a.slug
    if not a.no_browser: open_browser(url)
    print(url)

def main():
    ap = argparse.ArgumentParser(prog="learn.py", description="SRS Edge Learning hub"); sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("setup"); p.set_defaults(fn=cmd_setup)
    p = sp.add_parser("serve"); p.add_argument("--port", type=int, default=PORT); p.add_argument("--open", action="store_true"); p.set_defaults(fn=cmd_serve)
    p = sp.add_parser("open"); p.add_argument("slug", nargs="?"); p.add_argument("--port", type=int, default=PORT); p.add_argument("--no-browser", action="store_true"); p.set_defaults(fn=cmd_open)
    p = sp.add_parser("add"); p.add_argument("name"); p.add_argument("--goal"); p.add_argument("--level", type=int, choices=[1, 2, 3, 4, 5]); p.set_defaults(fn=cmd_add)
    p = sp.add_parser("topics"); p.add_argument("--all", action="store_true", help="include archived"); p.set_defaults(fn=cmd_topics)
    p = sp.add_parser("status"); p.add_argument("slug", nargs="?"); p.set_defaults(fn=cmd_status)
    p = sp.add_parser("pending"); p.add_argument("--wait", type=int, default=0); p.add_argument("--peek", action="store_true", help="look without claiming"); p.set_defaults(fn=cmd_pending)
    p = sp.add_parser("fulfil", aliases=["fulfill"]); p.add_argument("req_id"); p.add_argument("file"); p.add_argument("--force", action="store_true", help="take over a request another live agent claimed"); p.set_defaults(fn=cmd_fulfil)
    p = sp.add_parser("validate"); p.add_argument("file"); p.add_argument("--type", required=True, choices=TYPES); p.add_argument("--topic"); p.set_defaults(fn=cmd_validate)
    p = sp.add_parser("misses"); p.add_argument("slug"); p.add_argument("--limit", type=int, default=30); p.set_defaults(fn=cmd_misses)
    p = sp.add_parser("due"); p.add_argument("slug"); p.set_defaults(fn=cmd_due)
    p = sp.add_parser("export"); p.add_argument("slug"); p.set_defaults(fn=cmd_export)
    p = sp.add_parser("rename"); p.add_argument("slug"); p.add_argument("name", nargs="?"); p.add_argument("--goal"); p.add_argument("--level", type=int, choices=[1, 2, 3, 4, 5]); p.set_defaults(fn=cmd_rename)
    for c in ("archive", "unarchive"): p = sp.add_parser(c); p.add_argument("slug"); p.set_defaults(fn=cmd_archive)
    p = sp.add_parser("remove"); p.add_argument("slug"); p.add_argument("--purge", action="store_true", help="delete instead of moving to trash"); p.add_argument("--yes", "-y", action="store_true"); p.set_defaults(fn=cmd_remove)
    p = sp.add_parser("undelete"); p.add_argument("slug"); p.set_defaults(fn=cmd_undelete)
    p = sp.add_parser("questions"); p.add_argument("slug"); p.add_argument("--retired", action="store_true"); p.set_defaults(fn=cmd_questions)
    p = sp.add_parser("retire"); p.add_argument("slug"); p.add_argument("qid"); p.add_argument("--reason", default=""); p.add_argument("--restore", action="store_true"); p.set_defaults(fn=cmd_retire)
    p = sp.add_parser("stats"); p.add_argument("slug"); p.set_defaults(fn=cmd_stats)
    p = sp.add_parser("backup"); p.add_argument("--out"); p.set_defaults(fn=cmd_backup)
    p = sp.add_parser("restore"); p.add_argument("file"); p.add_argument("--overwrite", action="store_true"); p.set_defaults(fn=cmd_restore)
    a = ap.parse_args()
    try: a.fn(a)
    except ValueError as e: sys.exit(f"error: {e}")

if __name__ == "__main__": main()
