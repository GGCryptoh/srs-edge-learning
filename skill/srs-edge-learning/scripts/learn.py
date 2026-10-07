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

Home: $LEARN_HOME or ~/.gh-learn. Binds 127.0.0.1 only. No network calls, no keys.
"""
import argparse, datetime as dt, http.server, json, os, re, socket, socketserver, subprocess, sys, threading, time, urllib.parse, uuid

HOME = os.path.expanduser(os.environ.get("LEARN_HOME", "~/.gh-learn"))
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "assets", "app.html")
PORT = 4848
TYPES = ("brief", "categories", "questions", "diagnose")
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
    for k, d in (("brief", None), ("categories", []), ("questions", []), ("attempts", []), ("srs", {}), ("plan", None), ("level_hint", 2)):
        t.setdefault(k, d)
    return t
def save_topic(t): jsave(tpath(t["slug"]), t)
def rdir(): return os.path.join(HOME, "requests")
def requests_all():
    os.makedirs(rdir(), exist_ok=True)
    rs = [jload(os.path.join(rdir(), f), None) for f in sorted(os.listdir(rdir())) if f.endswith(".json")]
    return [r for r in rs if r]
def rsave(r): jsave(os.path.join(rdir(), r["id"] + ".json"), r)
LOCK = threading.Lock()
def agent_path(): return os.path.join(HOME, "agent.json")
def agent_beat(state="listening"): jsave(agent_path(), {"state": state, "ts": now(), "pid": os.getpid(), "host": socket.gethostname().split(".")[0]})
def agent_status():
    a = jload(agent_path(), None)
    if not a: return {"online": False}
    try: age = (dt.datetime.now() - dt.datetime.fromisoformat(a["ts"])).total_seconds()
    except Exception: age = 1e9
    return {"online": age < 15 and a.get("state") == "listening", "last_seen": a["ts"], "state": a.get("state"), "age": int(age)}

# ---------- learning maths
def srs_update(card, correct):
    """SM-2 lite. card: {ease, interval, due, reps, lapses}"""
    c = dict(card or {"ease": 2.5, "interval": 0, "due": today(), "reps": 0, "lapses": 0})
    if correct:
        c["reps"] += 1
        c["interval"] = 1 if c["reps"] == 1 else 3 if c["reps"] == 2 else round(c["interval"] * c["ease"])
        c["ease"] = min(3.0, c["ease"] + 0.1)
    else:
        c["reps"] = 0; c["lapses"] += 1; c["interval"] = 1; c["ease"] = max(1.3, c["ease"] - 0.2)
    c["due"] = (dt.date.today() + dt.timedelta(days=c["interval"])).isoformat()
    return c

def edge(t):
    """Per category: accuracy by level (first attempt per question in quiz mode), the edge level, next level to serve."""
    q = {x["id"]: x for x in t["questions"]}
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
    for q in t["questions"]:
        if q["id"] not in seen: continue
        c = t["srs"].get(q["id"])
        if not c or c["due"] <= today(): d.append(q["id"])
    return d

def summary(t):
    e = edge(t); att = t["attempts"]
    unanswered = {}
    seen = {a["qid"] for a in att}
    for q in t["questions"]:
        if q["id"] not in seen: unanswered.setdefault(q["cat"], {}).setdefault(int(q.get("level", 2)), 0); unanswered[q["cat"]][int(q.get("level", 2))] += 1
    days = sorted({a["ts"][:10] for a in att}); streak = 0
    d = dt.date.today()
    while d.isoformat() in days: streak += 1; d -= dt.timedelta(days=1)
    return {"slug": t["slug"], "name": t["name"], "goal": t.get("goal", ""), "has_brief": bool(t["brief"]), "categories": len(t["categories"]),
            "questions": len(t["questions"]), "answered": len(seen), "attempts": len(att), "accuracy": round(sum(a["correct"] for a in att) / len(att), 2) if att else None,
            "due": len(due_cards(t)), "edge": e, "unanswered": {k: {str(l): n for l, n in v.items()} for k, v in unanswered.items()},
            "streak_days": streak, "last_active": att[-1]["ts"] if att else t.get("created"), "plan": bool(t.get("plan")),
            "overall_edge": round(sum(v["edge"] for v in e.values()) / len(e), 1) if e else 0}

# ---------- validation + merge
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
            if len(ch) == 4 and isinstance(q.get("answer"), int) and 0 <= q["answer"] < 4:
                L = [len(str(c)) for c in ch]; r = L[q["answer"]]; others = sorted(L[i] for i in range(4) if i != q["answer"])
                if r > 40 and r > 1.35 * others[-1]: errs.append(f"{p}: the right answer is the longest by far ({r} chars vs {others[-1]}); write at least one distractor as long and as specific")
                if r > 40 and others[-1] < 0.5 * r: errs.append(f"{p}: distractors are one-liners next to a detailed right answer; match length and specificity")
        if len(qs) >= 6:
            from collections import Counter
            top = Counter(q.get("answer") for q in qs).most_common(1)[0]
            if top[1] > 0.5 * len(qs): errs.append(f"answer index {top[0]} is correct in {top[1]}/{len(qs)} questions; spread the right answer across slots (choices are shuffled on merge anyway, but write them balanced)")
            longest = sum(1 for q in qs if len(q.get("choices", [])) == 4 and isinstance(q.get("answer"), int) and 0 <= q["answer"] < 4 and len(str(q["choices"][q["answer"]])) == max(len(str(c)) for c in q["choices"]))
            if longest > 0.6 * len(qs): errs.append(f"the right answer is the longest option in {longest}/{len(qs)} questions; make distractors as long and detailed as the right one (or shorten the right one)")
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

def fulfil(req_id, body):
    with LOCK:
        r = jload(os.path.join(rdir(), req_id + ".json"), None)
        if not r: raise ValueError(f"no request {req_id}")
        t = topic(r["topic"]); errs = validate(r["type"], body, t)
        if errs: raise ValueError("invalid response:\n  " + "\n  ".join(errs))
        n = merge(r["type"], body, t); save_topic(t)
        r["status"] = "done"; r["done"] = now(); r["added"] = n; rsave(r)
    return n

def new_request(slug, kind, params=None, note=""):
    if kind not in TYPES: raise ValueError(f"type must be one of {TYPES}")
    topic(slug)
    # collapse duplicates: one pending request of a type per topic
    for r in requests_all():
        if r["status"] == "pending" and r["topic"] == slug and r["type"] == kind:
            r["params"] = {**r.get("params", {}), **(params or {})}; rsave(r); return r
    r = {"id": dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4], "ts": now(), "topic": slug, "type": kind,
         "params": params or {}, "note": note, "status": "pending"}
    rsave(r); return r

def add_attempt(slug, qid, picked, ms, mode):
    with LOCK:
        t = topic(slug); q = next((x for x in t["questions"] if x["id"] == qid), None)
        if not q: raise ValueError("unknown question")
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
    i = index(); slug = slugify(a.name)
    if os.path.exists(tpath(slug)): print(slug); return
    t = {"slug": slug, "name": a.name.strip(), "goal": (a.goal or "").strip(), "created": now(), "level_hint": a.level or 2,
         "brief": None, "categories": [], "questions": [], "attempts": [], "srs": {}, "plan": None}
    save_topic(t); i["topics"].append({"slug": slug, "name": t["name"], "created": t["created"]}); jsave(index_path(), i)
    print(slug)

def cmd_topics(a):
    i = index()
    if not i["topics"]: print("no topics yet — learn.py add \"<topic>\""); return
    print(f"{'slug':28} {'edge':>4} {'acc':>5} {'Q':>4} {'due':>4}  last")
    for e in i["topics"]:
        s = summary(topic(e["slug"]))
        print(f"{s['slug']:28} {s['overall_edge']:>4} {('' if s['accuracy'] is None else f'{int(s['accuracy']*100)}%'):>5} {s['questions']:>4} {s['due']:>4}  {str(s['last_active'])[:16]}")

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
    end = time.time() + (a.wait or 0)
    while True:
        if a.wait: agent_beat("listening")
        rs = [r for r in requests_all() if r["status"] == "pending"]
        if rs or time.time() >= end:
            if a.wait: agent_beat("working" if rs else "away")
            out = []
            for r in rs:
                t = topic(r["topic"]); s = summary(t)
                ctx = {"name": t["name"], "goal": t.get("goal", ""), "level_hint": t.get("level_hint", 2), "categories": t["categories"], "edge": s["edge"], "unanswered": s["unanswered"]}
                if r["type"] == "questions":
                    ctx["existing_questions"] = [q["q"] for q in t["questions"]][-60:]
                if r["type"] == "diagnose":
                    ctx["misses"] = misses(t, 30)
                out.append({**r, "context": ctx})
            print(json.dumps(out, indent=1, ensure_ascii=False)); return
        time.sleep(2)

def misses(t, limit):
    q = {x["id"]: x for x in t["questions"]}; out = []
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
    n = fulfil(a.req_id, read_body(a.file)); print(f"ok {a.req_id} ({n} merged)")

def cmd_validate(a):
    body = read_body(a.file); t = topic(a.topic) if a.topic else None
    errs = validate(a.type, body, t)
    print("OK" if not errs else "\n".join(errs)); sys.exit(1 if errs else 0)

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

# ---------- server
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
                    i = index(); self._json(200, {"settings": i["settings"], "home": HOME, "levels": LEVELS, "agent": agent_status(), "topics": [summary(topic(e["slug"])) for e in i["topics"]],
                                                 "pending": [{"id": r["id"], "topic": r["topic"], "type": r["type"], "ts": r["ts"]} for r in requests_all() if r["status"] == "pending"]})
                elif p.startswith("/api/topic/"):
                    t = topic(p.split("/")[3]); self._json(200, {**t, "summary": summary(t), "due": due_cards(t), "agent": agent_status(),
                                                               "requests": [r for r in requests_all() if r["topic"] == t["slug"]][-20:]})
                else: self._json(404, {"error": "not found"})
            except SystemExit as e: self._json(404, {"error": str(e)})
            except Exception as e: self._json(500, {"error": str(e)})
        def do_POST(self):
            p = urllib.parse.urlparse(self.path).path
            try:
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
                elif p == "/api/topic/delete":
                    i = index(); i["topics"] = [e for e in i["topics"] if e["slug"] != b["slug"]]; jsave(index_path(), i)
                    import shutil; shutil.rmtree(tdir(b["slug"]), ignore_errors=True); self._json(200, {"ok": True})
                else: self._json(404, {"error": "not found"})
            except Exception as e: self._json(400, {"error": str(e)})
    return H

def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.3); return s.connect_ex(("127.0.0.1", port)) == 0

def cmd_serve(a):
    cmd_setup(argparse.Namespace())
    class S(socketserver.ThreadingMixIn, http.server.HTTPServer): daemon_threads = True; allow_reuse_address = True
    srv = S(("127.0.0.1", a.port), make_handler())
    url = f"http://127.0.0.1:{a.port}/"
    print(f"serving {url}  (ctrl-c to stop)"); sys.stdout.flush()
    if a.open: open_browser(url)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

def open_browser(url):
    try:
        if sys.platform == "darwin": subprocess.Popen(["open", url])
        elif os.name == "nt": os.startfile(url)  # type: ignore
        else: subprocess.Popen(["xdg-open", url])
    except Exception: print(f"open this in your browser: {url}")

def cmd_open(a):
    url = f"http://127.0.0.1:{a.port}/"
    if not port_open(a.port):
        os.makedirs(HOME, exist_ok=True); log = open(os.path.join(HOME, "hub.log"), "ab")
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "serve", "--port", str(a.port)], stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        for _ in range(30):
            if port_open(a.port): break
            time.sleep(0.2)
    if a.slug: url += "#/topic/" + a.slug
    if not a.no_browser: open_browser(url)
    print(url)

def main():
    ap = argparse.ArgumentParser(prog="learn.py", description="SRS Edge Learning hub"); sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("setup"); p.set_defaults(fn=cmd_setup)
    p = sp.add_parser("serve"); p.add_argument("--port", type=int, default=PORT); p.add_argument("--open", action="store_true"); p.set_defaults(fn=cmd_serve)
    p = sp.add_parser("open"); p.add_argument("slug", nargs="?"); p.add_argument("--port", type=int, default=PORT); p.add_argument("--no-browser", action="store_true"); p.set_defaults(fn=cmd_open)
    p = sp.add_parser("add"); p.add_argument("name"); p.add_argument("--goal"); p.add_argument("--level", type=int, choices=[1, 2, 3, 4, 5]); p.set_defaults(fn=cmd_add)
    p = sp.add_parser("topics"); p.set_defaults(fn=cmd_topics)
    p = sp.add_parser("status"); p.add_argument("slug", nargs="?"); p.set_defaults(fn=cmd_status)
    p = sp.add_parser("pending"); p.add_argument("--wait", type=int, default=0); p.set_defaults(fn=cmd_pending)
    p = sp.add_parser("fulfil", aliases=["fulfill"]); p.add_argument("req_id"); p.add_argument("file"); p.set_defaults(fn=cmd_fulfil)
    p = sp.add_parser("validate"); p.add_argument("file"); p.add_argument("--type", required=True, choices=TYPES); p.add_argument("--topic"); p.set_defaults(fn=cmd_validate)
    p = sp.add_parser("misses"); p.add_argument("slug"); p.add_argument("--limit", type=int, default=30); p.set_defaults(fn=cmd_misses)
    p = sp.add_parser("due"); p.add_argument("slug"); p.set_defaults(fn=cmd_due)
    p = sp.add_parser("export"); p.add_argument("slug"); p.set_defaults(fn=cmd_export)
    a = ap.parse_args()
    try: a.fn(a)
    except ValueError as e: sys.exit(f"error: {e}")

if __name__ == "__main__": main()
