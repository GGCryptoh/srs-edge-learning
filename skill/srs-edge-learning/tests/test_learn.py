"""Unit tests for learn.py. Stdlib unittest, so `python3 -m unittest discover -s skill/srs-edge-learning/tests` works without installing anything; pytest runs them too."""
import datetime as dt, importlib, json, os, shutil, sys, tempfile, threading, unittest, zipfile

HERE = os.path.dirname(os.path.abspath(__file__)); SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))

def load_learn(home):
    os.environ["LEARN_HOME"] = home
    import learn; importlib.reload(learn); return learn

def q(choices, answer, cat="a", level=2, text="What is the thing in this concrete situation?"):
    return {"cat": cat, "level": level, "q": text, "choices": choices, "answer": answer, "why": "because"}

SAMPLE_Q = os.path.join(SKILL, "examples", "sample-questions.json")
SAMPLE_T = os.path.join(SKILL, "examples", "sample-topic.json")


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="srs-test-"); self.L = load_learn(self.home)
        self.L.cmd_setup(type("A", (), {})())
    def tearDown(self): shutil.rmtree(self.home, ignore_errors=True)
    def add(self, name="Rust ownership", cats=("ownership", "borrowing", "lifetimes")):
        import io, contextlib; buf = io.StringIO()
        with contextlib.redirect_stdout(buf): self.L.cmd_add(type("A", (), {"name": name, "goal": "g", "level": 2})())
        slug = buf.getvalue().strip(); t = self.L.topic(slug); t["categories"] = [{"id": c, "name": c, "why": "x"} for c in cats]; self.L.save_topic(t); return slug


class TestLengthTells(unittest.TestCase):
    def setUp(self): self.L = load_learn(tempfile.mkdtemp())
    def tell(self, *a, **k): return self.L.length_tells(q(*a, **k))[0]
    def test_longest_by_far_rejected(self):
        self.assertTrue(self.tell(["Short wrong", "Also short", "Wrong too", "The long correct answer that explains the exact mechanism in detail"], 3))
    def test_two_short_distractors_rejected(self):
        errs = self.tell(["A long distractor that is roughly as long as the right one is", "Nope", "Wrong", "The long correct answer that explains the exact mechanism"], 3)
        self.assertTrue(errs and "two distractors" in errs[0])
    def test_shortest_by_far_rejected(self):
        self.assertTrue(self.tell(["A long distractor that explains a plausible but wrong mechanism", "Another long distractor with a real feature in the wrong place", "A third long distractor that is true but does not answer it", "Yes"], 3))
    def test_numbers_and_balanced_pass(self):
        self.assertEqual(self.tell(["42", "17", "1024", "3.14"], 0), [])
        self.assertEqual(self.tell(["Compiles cleanly because the borrow ends early", "Error: conflicting mutable and immutable borrow", "Error: the vector type is not Send here", "Compiles with a warning about unused iterator"], 1), [])
    def test_batch_longest_rejected(self):
        qs = [q([f"Wrong option number {i} here ok", f"Other wrong option {i} here", f"Third wrong one {i} here ok", f"Right option {i} that is a bit longer"], 3) for i in range(8)]
        errs = self.L.batch_length_tells(qs); self.assertTrue(any("longest option in" in e for e in errs))
    def test_shipped_samples_pass(self):
        body = json.load(open(SAMPLE_Q)); self.assertEqual(self.L.validate("questions", body, None), [])
        t = json.load(open(SAMPLE_T)); qs = [{k: v for k, v in x.items() if k not in ("id", "created")} for x in t["questions"]]
        self.assertEqual(self.L.validate("questions", {"questions": qs}, t), [])


class TestValidator(unittest.TestCase):
    def setUp(self): self.L = load_learn(tempfile.mkdtemp())
    def test_structural_rules(self):
        bad = q(["a", "b", "c"], 0); self.assertTrue(any("exactly 4" in e for e in self.L.validate("questions", {"questions": [bad]})))
        bad = q(["a", "b", "c", "all of the above"], 0); self.assertTrue(any("all/none" in e for e in self.L.validate("questions", {"questions": [bad]})))
        bad = q(["a", "a", "c", "d"], 0); self.assertTrue(any("duplicates" in e for e in self.L.validate("questions", {"questions": [bad]})))
        bad = q(["a", "b", "c", "d"], 0); bad["cat"] = "nope"; self.assertTrue(any("not a category" in e for e in self.L.validate("questions", {"questions": [bad]}, {"categories": [{"id": "a"}]})))
    def test_categories_and_diagnose(self):
        self.assertTrue(self.L.validate("categories", {"categories": [{"id": "Bad Id", "name": "x", "why": "y"}] * 4}))
        self.assertEqual(self.L.validate("diagnose", {"diagnosis": "d", "root_causes": ["r"], "protocol": [{"step": "s"}]}), [])


class TestLearningMaths(unittest.TestCase):
    def setUp(self): self.L = load_learn(tempfile.mkdtemp())
    def test_srs_intervals(self):
        c = self.L.srs_update(None, True); self.assertEqual(c["interval"], 1)
        c = self.L.srs_update(c, True); self.assertEqual(c["interval"], 3)
        c = self.L.srs_update(c, True); self.assertGreater(c["interval"], 3)
        c = self.L.srs_update(c, False); self.assertEqual((c["interval"], c["reps"], c["lapses"]), (1, 0, 1)); self.assertLess(c["ease"], 2.8)
        for _ in range(80): c = self.L.srs_update(c, True)
        self.assertLessEqual(c["interval"], 365)   # never overflows a date
    def test_edge_rule_and_retired_questions_ignored(self):
        t = {"categories": [{"id": "c"}], "level_hint": 2, "attempts": [], "srs": {}, "questions": [{"id": f"q{i}", "cat": "c", "level": 2, "choices": ["a", "b", "c", "d"], "answer": 0} for i in range(4)]}
        for i, ok in enumerate([True, True, False]): t["attempts"].append({"qid": f"q{i}", "ts": "2026-10-01T10:00:00", "picked": 0 if ok else 1, "correct": ok, "ms": 1, "mode": "quiz"})
        e = self.L.edge(t)["c"]; self.assertEqual(e["edge"], 2); self.assertEqual(e["next"], 2)
        t["questions"][0]["retired"] = {"ts": "x", "reason": "bad"}   # drop a right answer: 1/2 right is no longer 3 answers, so the level is not held
        e = self.L.edge(t)["c"]; self.assertEqual(e["edge"], 0)
        self.assertEqual(len(self.L.due_cards(t)), 2)   # q0 retired, q3 never seen


class TestStats(Base):
    def test_qstats_leeches_and_due_all(self):
        self.L.restore_from(SAMPLE_T); t = self.L.topic("rust-ownership"); st = self.L.qstats(t)
        self.assertEqual(len(st), len(self.L.live(t))); seen = [v for v in st.values() if v["seen"]]; self.assertTrue(seen)
        self.assertTrue(all(v["avg_ms"] is None or v["avg_ms"] > 0 for v in st.values()))
        qid = next(k for k, v in st.items() if v["seen"])
        for _ in range(3): self.L.add_attempt("rust-ownership", qid, (t["questions"][0]["answer"] + 1) % 4 if False else -1, 900, "train")   # three wrong answers (picked -1 never matches)
        st = self.L.qstats(self.L.topic("rust-ownership")); self.assertTrue(st[qid]["leech"]); self.assertEqual(st[qid]["streak"], 3)
        lz = self.L.leeches(self.L.topic("rust-ownership")); self.assertEqual(lz[0]["wrong"], st[qid]["wrong"])
        self.assertGreaterEqual(self.L.summary(self.L.topic("rust-ownership"))["leeches"], 1)
        d = self.L.due_all(); self.assertTrue(d and all(x["slug"] == "rust-ownership" and x["q"]["id"] for x in d)); self.assertEqual([x["due"] for x in d], sorted(x["due"] for x in d))
        self.L.update_topic("rust-ownership", archived=True); self.assertEqual(self.L.due_all(), [])   # archived topics are not reviewed

class TestTopicLifecycle(Base):
    def test_rename_archive_trash_undelete(self):
        slug = self.add()
        self.L.update_topic(slug, name="Rust ownership & borrowing", goal="ship a CLI", level=3, archived=True)
        t = self.L.topic(slug); self.assertEqual((t["name"], t["goal"], t["level_hint"], t["archived"]), ("Rust ownership & borrowing", "ship a CLI", 3, True))
        self.assertTrue(self.L.index_entry(self.L.index(), slug)["archived"])
        self.L.new_request(slug, "brief", {"mode": "cliff"})
        dst = self.L.delete_topic(slug); self.assertTrue(os.path.isdir(dst)); self.assertFalse(os.path.exists(self.L.tpath(slug)))
        self.assertEqual([r["status"] for r in self.L.requests_all()], ["cancelled"])
        self.assertEqual([e["slug"] for e in self.L.index()["topics"]], [])
        self.L.undelete_topic(slug); self.assertEqual(self.L.topic(slug)["name"], "Rust ownership & borrowing")
        self.L.delete_topic(slug, purge=True); self.assertFalse(os.path.exists(self.L.tpath(slug)))
        with self.assertRaises(ValueError): self.L.undelete_topic("never-existed")

    def test_retire_question_leaves_bank_and_deck(self):
        slug = self.add(); r = self.L.new_request(slug, "questions", {"n": 4}); self.L.fulfil(r["id"], json.load(open(SAMPLE_Q)))
        t = self.L.topic(slug); qid = t["questions"][0]["id"]
        self.L.add_attempt(slug, qid, t["questions"][0]["answer"], 1000, "quiz"); self.assertIn(qid, self.L.topic(slug)["srs"])
        self.L.retire_question(slug, qid, "answer key wrong")
        t = self.L.topic(slug); s = self.L.summary(t)
        self.assertNotIn(qid, t["srs"]); self.assertEqual(s["questions"], 3); self.assertEqual(s["retired"], 1); self.assertEqual(s["answered"], 0)
        self.assertEqual(self.L.flagged(t)[0]["reason"], "answer key wrong")
        with self.assertRaises(ValueError): self.L.add_attempt(slug, qid, 0, 1, "quiz")
        self.L.retire_question(slug, qid, restore=True); self.assertEqual(self.L.summary(self.L.topic(slug))["retired"], 0)


class TestRequestsAndClaims(Base):
    def test_duplicate_requests_collapse_and_claims(self):
        slug = self.add(); a = self.L.new_request(slug, "questions", {"n": 4}); b = self.L.new_request(slug, "questions", {"n": 6})
        self.assertEqual(a["id"], b["id"]); self.assertEqual(b["params"]["n"], 6)
        self.L.claim([b]); self.L.agent_beat("working")
        self.assertEqual(self.L.open_requests()[0]["status"], "claimed")
        mine = self.L.AGENT_ID; self.L.AGENT_ID = "elsewhere-1"   # a second agent on the same hub
        try:
            with self.assertRaises(ValueError): self.L.fulfil(b["id"], json.load(open(SAMPLE_Q)))
            self.assertEqual(self.L.fulfil(b["id"], json.load(open(SAMPLE_Q)), force=True), 4)
            with self.assertRaises(ValueError): self.L.fulfil(b["id"], json.load(open(SAMPLE_Q)))   # already done
        finally: self.L.AGENT_ID = mine
    def test_stale_claim_falls_back_to_pending(self):
        slug = self.add(); r = self.L.new_request(slug, "brief"); self.L.claim([r])
        p = os.path.join(self.L.rdir(), r["id"] + ".json"); r = self.L.jload(p, None); r["claimed"]["ts"] = (dt.datetime.now() - dt.timedelta(seconds=self.L.CLAIM_TTL + 5)).isoformat(timespec="seconds"); self.L.rsave(r)
        self.assertEqual(self.L.open_requests()[0]["status"], "pending")
    def test_cancel(self):
        slug = self.add(); r = self.L.new_request(slug, "brief"); self.L.cancel_request(r["id"])
        self.assertEqual(self.L.open_requests(), [])
        with self.assertRaises(ValueError): self.L.fulfil(r["id"], {})
    def test_flock_serialises_writers(self):
        slug = self.add(); r = self.L.new_request(slug, "questions"); self.L.fulfil(r["id"], json.load(open(SAMPLE_Q)))
        qid = self.L.topic(slug)["questions"][0]["id"]; errs = []
        def hammer():
            try:
                for _ in range(15): self.L.add_attempt(slug, qid, 0, 1, "train")
            except Exception as e: errs.append(e)
        ts = [threading.Thread(target=hammer) for _ in range(4)]; [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(errs, []); self.assertEqual(len(self.L.topic(slug)["attempts"]), 60)


class TestBackupRestore(Base):
    def test_roundtrip_and_single_topic(self):
        slug = self.add("Kubernetes networking"); r = self.L.new_request(slug, "questions"); self.L.fulfil(r["id"], json.load(open(SAMPLE_Q)))
        out = self.L.backup_zip(os.path.join(self.home, "b.zip"))
        with zipfile.ZipFile(out) as z: self.assertEqual(sorted(z.namelist()), ["index.json", f"topics/{slug}/topic.json"])
        self.assertEqual(self.L.restore_from(out), ([], [], [slug]))
        self.L.delete_topic(slug, purge=True); self.assertEqual(self.L.restore_from(out), ([slug], [], []))
        self.assertEqual(len(self.L.topic(slug)["questions"]), 4)
        self.assertEqual(self.L.restore_from(out, overwrite=True), ([], [slug], []))
        self.assertEqual(self.L.restore_from(SAMPLE_T), (["rust-ownership"], [], []))
        self.assertEqual(self.L.summary(self.L.topic("rust-ownership"))["categories"], 4)
        bad = os.path.join(self.home, "bad.json"); json.dump({"hello": 1}, open(bad, "w"))
        with self.assertRaises(ValueError): self.L.restore_from(bad)


class TestPorts(Base):
    def test_find_port_skips_foreign_server_and_reuses_own(self):
        import http.server, socketserver
        srv = socketserver.TCPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler); port = srv.server_address[1]
        th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
        try:
            p, running = self.L.find_port(port); self.assertNotEqual(p, port); self.assertFalse(running)
            self.assertIsNone(self.L.hub_info(port))
            hub = type("S", (socketserver.ThreadingMixIn, http.server.HTTPServer), {"daemon_threads": True})(("127.0.0.1", 0), self.L.make_handler()); hp = hub.server_address[1]
            th2 = threading.Thread(target=hub.serve_forever, daemon=True); th2.start()
            try:
                self.assertTrue(self.L.ours(self.L.hub_info(hp))); self.assertEqual(self.L.find_port(hp), (hp, True))
                self.assertFalse(self.L.ours({"app": "srs-edge-learning", "home": tempfile.mkdtemp()}))   # a hub for another LEARN_HOME is not ours
            finally: hub.shutdown()
        finally: srv.shutdown()


if __name__ == "__main__": unittest.main()
