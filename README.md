# Multi-Agent System

A FastAPI service that turns a user query into a small agent workflow. It plans dependent tasks, executes them through scoped tools, verifies the results, stores traces in SQLite, and returns a structured response.

## Features

- DAG-based task planning and asynchronous execution
- Scoped agent tools with authorization checks
- Google ADK Gemini integration when `GOOGLE_API_KEY` is configured
- Stub and web-search fallbacks for local development
- Request tracing, SQLite persistence, and curated memory
- Evaluation endpoint with reports restricted to `data/eval`

## Current Scope

The project is an early working implementation. The default classifier and planner are stubs, and verification is limited. LLM-backed research requires a Google API key; without one, the service uses fallback behavior and may return an unverified response.

## Architecture

```text
POST /query
    -> classify
    -> plan tasks
    -> execute dependency graph
    -> aggregate and verify
    -> persist trace and return response
```

Main packages:

- `app/main.py`: FastAPI application and endpoints
- `app/orchestrator/`: pipeline, agents, and DAG execution
- `app/tools/`: web search, Gemini, and tool gateway
- `app/persistence/`: SQLite run storage and curated memory
- `app/eval/`: JSONL evaluation runner
- `app/schemas/`: request, response, and workflow contracts

## Quick Start

Requirements: Python 3.12+ and `uv` or `pip`.

```bash
git clone https://github.com/AVB934/multi-agent-system.git
cd multi-agent-system
uv sync
```

Copy `.env.example` to `.env` and add `GOOGLE_API_KEY` if Gemini-backed research is needed. Never commit `.env`.

Start the development server locally:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open the API docs at <http://localhost:8000/docs>.

See [QUICKSTART.md](QUICKSTART.md) for Windows, macOS, Linux, API, and evaluation examples.

## API

### `POST /query`

```json
{
  "query": "What is the capital of France?",
  "include_json": true
}
```

The response includes the answer, intent, plan, task results, citations, and trace information.

### `POST /eval`

Evaluation input and output paths must remain inside `data/eval`:

```json
{
  "input_jsonl_path": "test_cases.jsonl",
  "output_report_path": "eval_results.json"
}
```

The JSONL input uses one object per line:

```json
{"id": "1", "query": "What is the largest planet?"}
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `GOOGLE_API_KEY` | Enables Google ADK Gemini calls |
| `MAS_GEMINI_MODEL` | Gemini model name; defaults to `gemini-2.0-flash` |
| `MAS_DB_PATH` | SQLite path; defaults to `data/mas.sqlite3` |
| `LOG_LEVEL` | Application log level |

## Development

```bash
uv run python -m compileall -q app
uv run python -c "import app.main; print('application import ok')"
```
