# Example: one full request/response pair

`sample-questions.json` is a valid `questions` response for a topic with category ids `ownership`, `borrowing`, `lifetimes`. Check it with:

```
python3 scripts/learn.py validate examples/sample-questions.json --type questions
```

`sample-brief.json` is a valid `bullets` brief. A full topic file after a few rounds looks like `sample-topic.json` (brief, categories, questions, attempts, srs, plan).
