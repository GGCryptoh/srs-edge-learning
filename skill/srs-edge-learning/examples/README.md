# Example: one full request/response pair

`sample-questions.json` is a valid `questions` response for a topic with category ids `ownership`, `borrowing`, `lifetimes`. Check it with:

```
python3 scripts/learn.py validate examples/sample-questions.json --type questions
```

`sample-brief.json` is a valid `bullets` brief. `sample-topic.json` is a full topic file after three weeks of use (brief, 4 categories, 44 questions, 159 attempts, SRS cards, a protocol). Load it into a hub to see every screen with data:

```
python3 scripts/learn.py restore examples/sample-topic.json
python3 scripts/learn.py open rust-ownership
```
