# NL Data Analyst — English → SQL → Answer + Chart

Ask a question in plain English about a relational dataset. The app generates SQL,
runs it safely, and returns a written answer plus an interactive chart — in a
couple of seconds.

**Status:** 🚧 In development. See [Roadmap](#roadmap) below.

## What this project demonstrates

- Schema-aware SQL generation using the Claude API (the model is given the real
  table structure, not guessing blind)
- A safety layer that enforces **read-only** database access — the app can only
  run `SELECT` statements, full stop, even if the LLM generates something else
- Graceful error handling and self-repair when a generated query fails
- Interactive charting (Plotly) driven by natural-language questions

## Why read-only, not read/write

This app lets an LLM generate and auto-execute SQL against a real database with
no human reviewing the query first. That's fine for reads — a wrong `SELECT`
just shows a wrong number. It is not fine for writes: an LLM-generated `DELETE`
or `UPDATE` with a subtly wrong `WHERE` clause could silently damage real data
before anyone notices. Enforcing read-only access at the database connection
level (not just asking the LLM nicely) removes that risk by construction. See
[Future Work](#future-work) for how role-based write access could be added
safely later.

## Stack

- **Database:** SQLite for the demo (portable, zero-setup), written to also work
  with Postgres
- **LLM:** Claude, via the Anthropic API
- **App:** Streamlit + Plotly

## Project structure

```
data/              # dataset (gitignored — see Setup)
notebooks/         # exploratory work
src/
  db/              # database connection and query execution
  sql_generation/  # English -> SQL generation
  safety/          # read-only enforcement, error handling
  charting/        # query results -> Plotly charts
app/               # Streamlit UI
```
## Setup

```bash
git clone https://github.com/SwarnaAnugu/NL_DATA_ANALYST.git
cd NL_DATA_ANALYST
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then add your own Anthropic API key
```

## Roadmap

- [x] Repo + environment setup
- [ ] Load a multi-table e-commerce dataset into SQLite
- [ ] Schema-aware English → SQL generation
- [ ] Safe, read-only query execution with error handling
- [ ] Answer + interactive chart rendering
- [ ] Streamlit UI
- [ ] Hardening and edge cases
- [ ] Deploy + final writeup

## Future work

- Role-based access control (RBAC) — e.g. a "manager" role permitted
  transactional writes with explicit commit/rollback, kept separate from the
  default read-only mode
- Accepting user-uploaded CSVs instead of only the shipped dataset

## License

MIT — see [LICENSE](LICENSE)