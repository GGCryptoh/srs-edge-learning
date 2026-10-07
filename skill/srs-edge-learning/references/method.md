# The method

How the learning loop works and which role the agent plays at each step. Grounded in spaced repetition and timed recall as used for language levelling (Geoff: ~2 years of Mandarin progression in 11 months). Read §Question craft before writing a first batch.

## Core idea
- **Consumption vs production.** Reading, watching and having things explained *feels* like learning. Only producing (answering, explaining back, being corrected) moves what you'll still know in a month. The brain avoids production because it is harder; the tool's job is to make production the default.
- **The zone of proximal development.** Learning happens just beyond what you can do alone. Too easy → nothing sticks; too hard → you stall. The page's *edge* (the hardest level you still get ≥60% at) is that zone made measurable; `next` is where to pitch the next questions.
- **Drill first, then learn.** Don't ask "help me learn X". Ask "drill me on everything under the sun to find how much I already know about X, then build me a map of what I'm missing". The categories + first quiz round are exactly that.
- **Be specific.** "Learn statistics" is shapeless. The goal field and the categories turn it into a shape. Time-boxing per question is deliberate: it reproduces the pressure of the real situation (an interview answer, a client question).

## The AI roles (map to request types)
| role | what it does | here |
|---|---|---|
| roadmap builder | maps concepts in dependency order, from your current state | `categories` (ordered foundations → advanced, `level_hint`) |
| explainer | explains *only the part you got stuck on*, at your level | `why` on every question; briefs pitched at the stated level |
| examiner | asks questions, timed, gets harder, finds what you don't know | `questions` at `edge.next` and one above |
| checker | checks your reasoning/process, finds the recurring mistake behind many wrong answers | `diagnose` → `root_causes` |
| sparring partner | reps under realistic pressure | the timer, blocks per category |
| clerk | organises messy notes/results into higher-level abstractions | `brief` sections, the progress table, `export` |
| flashcard writer / SRS | re-tests just before you forget | `train` tab, SM-2 lite scheduling |

## Spaced repetition
Memory strength decays; a test right before the forgetting point resets it higher and stretches the next gap. Cards: every question the learner has met. Right → 1 day, 3 days, then interval × ease. Wrong → back to 1 day, ease down. The page handles this; the agent just keeps the bank fresh.

## Brief (what a good one does)
- Pitch to the learner's **goal** and **level**. A cliff-notes brief for "explain it to a client" is mostly "where it shows up in business" and "what people get wrong"; for "pass an interview" it is mostly "how it works" and glossary.
- **Movers**: 3–8 named companies, people, projects or standards bodies with one line each on *why they matter now*. **News**: 3–6 dated items, newest first, each with why it matters *to this learner*. If web search is unavailable, say so (`sources_live:false`) and date the knowledge (`as_of`).
- No filler. Every bullet is a fact the learner can be questioned on later.

## Question craft
- One idea per question. The stem states a concrete situation; the choices are plausible to someone at the level *below*. Wrong choices are the mistakes people actually make, not nonsense.
- Levels (see `schemas.md` ladder). Pitch to `edge.next`; add ~30% at one level higher so the ladder keeps climbing.
- Never repeat `existing_questions` or paraphrase one. Vary the angle: definition → scenario → cause → trade-off → recent change.
- `why` is the explainer role: one or two lines on why the right answer is right and why the tempting wrong one is wrong. That text is what the learner reads 2–5 seconds after answering; make it the lesson.
- Keep stems ≤ 45 words (the read timer scales with length) and choices ≤ 20 words.
- **No length tell.** Learners spot that the longest, most specific option is the right one. Every distractor must be as long and as concrete as the right answer: a plausible mechanism, a real feature used in the wrong place, a true statement that doesn't answer the question. If the right answer needs 18 words, write two distractors of 15–20 words. The validator rejects batches where the right answer is the longest by far, or the longest in >60% of questions.
- **No position tell.** Choices are shuffled on merge, so write them in any order, but don't make slot 2 the answer every time out of habit.

## Diagnose (the checker role)
Look at the misses as a set. The question is not "what did they get wrong" but "what single misunderstanding would produce *these* misses?" Name it in one sentence a learner would recognise. Then a protocol of 3–7 production tasks away from the screen (write it out, explain it aloud, draw it, do the exercise), each with `how` and `when`, and a `next_test` that says which categories and levels to re-run. Use more than one mode of demonstrating knowledge — verbal, visual, written — in the protocol.

## Guardrails
- AI that agrees with you, half-right answers and invented sources turn learning into note-collecting. Hence: four fixed choices, one answer, a stated `as_of`, and `sources_live` honesty.
- Don't remove the hump entirely; struggling *a bit* is the mechanism. The timer and the stretch level are the hump.
