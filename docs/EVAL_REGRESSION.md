# Eval Regression Gate

A deterministic retrieval regression suite guards against accidental relevance regressions.

## Running locally
```bash
make eval-regression
```
This runs `pytest backend/tests/test_search_regression_eval.py` against the local Postgres in `DATABASE_URL` with `OPENAI_OFFLINE=1`.

## CI behavior
- `make eval-regression` now runs automatically in the Backend Smoke workflow on every push to `main/develop/feat/**` and every pull request.
- Failures block the workflow just like pytest failures.

## Updating cases
The eval set lives in `backend/tests/evals/retrieval_cases.jsonl`. Keep it deterministic:
- Use existing seeded fixture docs or add new deterministic snippets.
- Avoid external calls or randomness.
- Document any new cases in commit messages so reviewers know why relevance expectations changed.
