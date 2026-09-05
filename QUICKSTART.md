# Quick Start Guide - Multi-Agent System

This guide walks you through setting up and running the Multi-Agent System with step-by-step terminal commands.

## Prerequisites

### System Requirements
- **Python**: 3.12 or higher
- **OS**: Windows, macOS, or Linux
- **Git**: For cloning the repository
- **uvicorn**: ASGI server (installed via dependencies)

### Required Environment Variables
Create a `.env` file in the project root with your API keys:

```env
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_SEARCH_ENGINE_ID=your_search_engine_id_here
MAS_DB_PATH=data/mas.sqlite3
```

**How to get Google API credentials:**
1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the Google Search API
4. Create an API key credential
5. Set up a Custom Search Engine at [cse.google.com](https://cse.google.com/)

---

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/AVB934/multi-agent-system.git
cd multi-agent-system
```

### Step 2: Create Virtual Environment (Recommended)

Using `venv` (built-in):
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

Using `uv` (faster alternative):
```bash
uv venv
```

Activate it:
```bash
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### Step 3: Install Dependencies

Using pip:
```bash
pip install -e .
```

Or using uv:
```bash
uv sync
```

Or install specific packages manually:
```bash
pip install fastapi>=0.129.0 google-adk>=1.27.1 pydantic>=2.12.5 uvicorn python-dotenv
```

### Step 4: Verify Installation

```bash
python -c "import fastapi; import pydantic; import google.adk; print('All dependencies installed successfully!')"
```

---

## Configuration

### Create Data Directory

```bash
# Windows
mkdir data

# macOS/Linux
mkdir -p data
```

### Initialize Database

The SQLite database will auto-initialize on first run. If you want to manually initialize it:

```bash
python -c "from app.persistence.sqlite_store import SqliteRunStore; SqliteRunStore('data/mas.sqlite3')"
```

### Create .env File

```bash
# Windows
type nul > .env

# macOS/Linux
touch .env
```

Edit `.env` with your credentials:
```env
GOOGLE_API_KEY=your_key_here
GOOGLE_SEARCH_ENGINE_ID=your_engine_id_here
MAS_DB_PATH=data/mas.sqlite3
LOG_LEVEL=INFO
```

---

## Running the Server

### Start FastAPI Development Server

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Command options:**
- `--host 0.0.0.0`: Listen on all network interfaces
- `--port 8000`: Use port 8000 (change as needed)
- `--reload`: Auto-restart on code changes (development only)

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### Access API Documentation

Open your browser and navigate to:
- **Interactive Docs (Swagger UI)**: http://localhost:8000/docs
- **Alternative Docs (ReDoc)**: http://localhost:8000/redoc

---

## Using the API

### Terminal 1: Keep Server Running
```bash
uvicorn app.main:app --reload
```

### Terminal 2: Send Requests

#### Query Example 1: Research Query

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Who won the 2024 Olympics?",
    "include_json": false
  }'
```

#### Query Example 2: With JSON Payload

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the capital of France?",
    "include_json": true
  }'
```

#### Query Example 3: Using PowerShell (Windows)

```powershell
$body = @{
    query = "What is machine learning?"
    include_json = $true
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/query" `
  -Method POST `
  -Headers @{"Content-Type" = "application/json"} `
  -Body $body | ConvertTo-String
```

#### Query Example 4: Using Python Requests

Create `test_query.py`:
```python
import requests
import json

BASE_URL = "http://localhost:8000"

response = requests.post(
    f"{BASE_URL}/query",
    json={
        "query": "What are the latest AI developments?",
        "include_json": True
    }
)

print(json.dumps(response.json(), indent=2))
```

Run it:
```bash
python test_query.py
```

---

## Evaluation

### Step 1: Create Test Dataset

Create `data/eval/test_cases.jsonl`:
```
{"id": "1", "query": "Who is the President of the USA?"}
{"id": "2", "query": "What is the largest planet in our solar system?"}
{"id": "3", "query": "When was Python first released?"}
{"id": "4", "query": "What does AI stand for?"}
{"id": "5", "query": "Which country has the most capital cities?"}
```

### Step 2: Run Evaluation

```bash
curl -X POST http://localhost:8000/eval \
  -H "Content-Type: application/json" \
  -d '{
    "input_jsonl_path": "test_cases.jsonl",
    "output_report_path": "eval_results.json"
  }'
```

### Step 3: View Results

```bash
# Windows
type eval_results.json

# macOS/Linux
cat eval_results.json
```

Or with Python:
```python
import json

with open("data/eval/eval_results.json") as f:
    results = json.load(f)
    print(f"Total Cases: {results['total_cases']}")
    print(f"Metrics: {json.dumps(results['metrics'], indent=2)}")
```

---

## Running Tests

### Create Unit Tests

Create `tests/test_orchestrator.py`:
```python
import pytest
import asyncio
from app.orchestrator import Orchestrator

@pytest.mark.asyncio
async def test_orchestrator_basic():
    orchestrator = Orchestrator()
    response = await orchestrator.run("Test query")
    assert response.answer is not None
    assert response.trace is not None
```

### Run Tests

```bash
# Install pytest and pytest-asyncio
pip install pytest pytest-asyncio

# Run tests
pytest tests/ -v

# Run with coverage
pip install pytest-cov
pytest tests/ --cov=app --cov-report=html
```

---

## Development Workflow

### Enable Hot Reload

Already included in the quickstart command above. Any file changes will automatically restart the server:

```bash
uvicorn app.main:app --reload
```

### Debug Mode

Set Python debugger breakpoint:
```python
# In your code
breakpoint()  # Execution pauses here
```

Or use VS Code debugger with `.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Uvicorn Debug",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload"],
      "jinja": true,
      "justMyCode": true
    }
  ]
}
```

### View Logs

```bash
# Tail real-time logs (macOS/Linux)
uvicorn app.main:app --reload --log-level debug | tail -f

# Filter specific logs
grep "trace_id" server.log
```

---

## Common CLI Tasks

### Check Python Version

```bash
python --version
```

Expected: `Python 3.12.x` or higher

### List Installed Packages

```bash
pip list
```

### Update Dependencies

```bash
pip install --upgrade -e .
```

Or with uv:
```bash
uv sync --upgrade
```

### Deactivate Virtual Environment

```bash
# Windows
deactivate

# macOS/Linux
deactivate
```

### Clean Up

```bash
# Remove virtual environment
# Windows
rmdir /s /q .venv

# macOS/Linux
rm -rf .venv

# Remove cache and build files
pip cache purge
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

---

## Troubleshooting

### Issue: Virtual Environment Not Activating

**Windows:**
```bash
# If `.venv\Scripts\activate` doesn't work:
.venv\Scripts\activate.bat
```

**macOS/Linux:**
```bash
# Make sure script is executable
chmod +x .venv/bin/activate
source .venv/bin/activate
```

### Issue: "ModuleNotFoundError: No module named 'app'"

Ensure you're in the correct directory and virtual environment is active:
```bash
cd multi-agent-system
which python  # macOS/Linux - should show .venv path
```

### Issue: Port 8000 Already In Use

Use a different port:
```bash
uvicorn app.main:app --port 8001
```

Or find and kill the process:
```bash
# macOS/Linux
lsof -i :8000
kill -9 <PID>

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Issue: "Connection Refused" When Calling API

Ensure server is running:
```bash
# If server hasn't started, you'll see:
# curl: (7) Failed to connect to localhost port 8000

# Start the server in a separate terminal
uvicorn app.main:app --reload
```

### Issue: Environment Variables Not Loading

Verify `.env` file exists and is in project root:
```bash
# Check file exists
ls -la .env  # macOS/Linux
dir .env    # Windows

# Check content
cat .env  # macOS/Linux
type .env # Windows
```

Make sure FastAPI is loading dotenv:
```python
# This is already in app/main.py
from dotenv import load_dotenv
load_dotenv()
```

### Issue: Database Errors

Reset the database:
```bash
# Remove old database
rm data/mas.sqlite3  # macOS/Linux
del data\mas.sqlite3 # Windows

# Start server - it will auto-initialize
uvicorn app.main:app --reload
```

### Issue: API Returns 500 Error

Check server logs for detailed error:
```bash
uvicorn app.main:app --reload --log-level debug
```

### Issue: Google API Key Not Working

Verify credentials:
```bash
python -c "import os; print('GOOGLE_API_KEY:', os.getenv('GOOGLE_API_KEY')[:10]+'...' if os.getenv('GOOGLE_API_KEY') else 'NOT SET')"
```

Test API key directly:
```python
from app.tools.adk_gemini import ADKGeminiTool

tool = ADKGeminiTool.from_env()
print(f"Tool enabled: {tool.enabled}")
```

---

## Performance Tips

### 1. Use Production Server

For production deployment, use Gunicorn with Uvicorn workers:
```bash
# Install Gunicorn
pip install gunicorn

# Run with 4 workers
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 2. Monitor Resource Usage

```bash
# macOS/Linux
top  # or
htop

# Windows
tasklist
```

### 3. Enable Query Caching

Implement caching for frequently asked queries (future enhancement).

### 4. Tune Execution Budgets

Edit `app/orchestrator/dag_executor.py`:
```python
@dataclass(frozen=True)
class ExecutionBudget:
    max_agents: int = 10        # Increase if needed
    max_tool_calls: int = 50    # Increase if needed
    token_budget: int = 10000   # Increase if needed
```

---

## Next Steps

1. **Explore API Docs**: Visit http://localhost:8000/docs
2. **Run Sample Queries**: Use the curl examples above
3. **Check Database**: Query runs stored in `data/mas.sqlite3`
4. **Read Main README**: See [README.md](README.md) for full system documentation
5. **Review Code**: Examine `app/orchestrator/pipeline.py` for main logic

---

## Useful Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Pydantic Docs**: https://docs.pydantic.dev/
- **Uvicorn Docs**: https://www.uvicorn.org/
- **Python Async/Await**: https://docs.python.org/3/library/asyncio.html
- **SQLite Docs**: https://www.sqlite.org/docs.html

---

## Additional Help

### Get System Information

```bash
python -c "import platform; import sys; print(f'Python: {sys.version}'); print(f'OS: {platform.system()}')"
```

### Validate Project Structure

```bash
# Windows
tree app /A

# macOS/Linux
tree app -I '__pycache__'
```

### Check File Permissions

```bash
# macOS/Linux
ls -la app/main.py
```

---

## Quick Command Reference

| Task | Command |
|------|---------|
| Activate venv | `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Mac/Linux) |
| Install deps | `pip install -e .` |
| Start server | `uvicorn app.main:app --reload` |
| Test query | `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"query":"test"}'` |
| Run eval | `curl -X POST http://localhost:8000/eval -H "Content-Type: application/json" -d '{"input_jsonl_path":"test_cases.jsonl","output_report_path":"results.json"}'` |
| View logs | `uvicorn app.main:app --reload --log-level debug` |
| Run tests | `pytest tests/ -v` |
| Deactivate venv | `deactivate` |
