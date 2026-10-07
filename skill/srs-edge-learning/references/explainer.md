# SRS Edge Learning — get smart at anything, with the AI you already have

## The problem
Most of us "learn" by consuming: read the article, watch the video, ask ChatGPT to explain it, nod, move on. A week later it's gone. Memory research has known for a century why: knowledge sticks when you **produce** it under a bit of pressure (answer, get corrected, try again), not when you passively take it in. And it sticks best when the questions land just past the edge of what you already know — hard enough to make you think, not so hard that you stall.

AI makes the consuming side effortless, which is exactly the trap. This skill flips it: your AI agent becomes the examiner, the roadmap builder, the explainer and the flashcard clerk, and you do the producing.

## What it is
A skill for AI coding agents (Claude Code, Codex, GitHub Copilot CLI) plus a small local web page. You pick a topic. The page and the agent then work through four stages:

1. **Brief.** Cliff notes or short bullets: what the thing is, how it shows up in business and in life, who the movers are, what happened recently, the words to know. Written for *your* goal ("pass an interview", "explain it to a client").
2. **Map.** The agent splits the topic into 4–12 categories, foundations first.
3. **Find your edge.** Timed multiple-choice rounds. You get a few seconds to read the question, then four choices and a countdown. Right or wrong shows instantly with a one-line explanation. Questions get harder as you get them right. Per category, the page works out your *edge*: the hardest level you still hold at 60%+.
4. **Push it outward.** Press *Diagnose my misses* and the agent reads what you got wrong, names the one misunderstanding behind most of it, and writes a training protocol: 3–7 things to do away from the screen, with a date to re-test. Meanwhile every question you've met goes into a spaced-repetition deck, so it comes back right before you'd forget it.

Run the skill again next week and it opens the same page with every topic, your edge per category, a day streak, and what's due for review.

## Why it works
- **Production, not consumption.** Every minute on the page is you answering, not reading.
- **Zone of proximal development.** Questions are pitched at your measured edge plus one level, so they're always just out of reach.
- **Drill first, then learn.** The first round is a diagnosis. You find out what you don't know before you spend a minute studying.
- **Spaced repetition.** Right answers come back in 1 day, 3 days, then stretching gaps. Wrong answers come back tomorrow.
- **A checker, not a cheerleader.** Four fixed choices and one answer. The AI can't agree with you, and the brief says what date its knowledge is from.

## What you need
- A Mac, Windows or Linux machine with Python 3 (Macs have it).
- An AI coding agent that reads skills: Claude Code, Codex CLI, or GitHub Copilot CLI. No API key is needed by the skill itself; it uses the agent you already pay for.
- Five minutes to install.

## Five-minute walkthrough
1. Install (see below). In your agent, type `/srs-edge-learning Kubernetes networking` (or whatever you want to get smart at).
2. The hub opens in your browser. Pick **Cliff notes**. Within a minute the brief appears.
3. Click **Go deeper → Build the map**, then **Start a round**. Answer with the number keys. Stop when you like.
4. Open **Progress** to see your edge per category. Press **Diagnose my misses**.
5. Tomorrow, open **Train** and review what's due. Repeat.

## Honest limits
- Multiple choice only. That keeps the timer fair and the edge maths honest, but it won't grade an essay. The training protocol is where the free-form work lives.
- The agent writes questions in batches of 10–12. When the bank runs low mid-round the page asks for more and you wait a minute.
- News and "movers" are only as fresh as your agent's web access. The brief states the date and whether the web was checked.
- Everything stays on your machine in one folder. Nothing is uploaded.

## Where this comes from
I built this because it already worked on me. I've been learning Mandarin with spaced repetition and timed recall, and compressed almost two years of language levelling into 11 months. The pattern is simple: test before you study, keep every question just past your edge, and let scheduling decide what comes back. This skill applies the same pattern to any topic, with an AI agent writing the questions instead of a textbook.

Built by Geoff Hopkins. MIT licensed.
