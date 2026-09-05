# Multi-Agent System

A FastAPI-based orchestration system that coordinates multiple specialized agents to process complex queries through a sophisticated pipeline of planning, execution, verification, and aggregation.

## System Overview

The Multi-Agent System is an intelligent query processing platform that breaks down complex user queries into manageable tasks, assigns them to specialized agents, executes them in parallel while respecting dependencies, verifies results, and aggregates them into comprehensive answers with citations.

### Key Features

- **Multi-Agent Coordination**: Specialized agents (Research, Verifier, Planner) work together
- **DAG-Based Execution**: Task dependencies form a directed acyclic graph (DAG) for optimal parallelization
- **Tool Scoping & Security**: Each agent has explicit tool access control and authorization
- **Persistent Tracing**: Complete request tracing from ingestion to response
- **Curated Memory**: Long-term knowledge base built from high-quality aggregated results
- **Evaluation Framework**: Built-in evaluation runner to assess system performance
- **Budget Validation**: Pre-flight validation of plan size and execution constraints

## Project Structure

```
app/
├── agents/                    # Agent implementations
│   ├── base.py               # Abstract BaseAgent class
│   └── baseline.py           # Concrete agents (ResearchAgent, VerifierAgent, PlannerAgent)
├── orchestrator/             # Orchestration logic
│   ├── pipeline.py           # Main Orchestrator class (coordinates full workflow)
│   ├── dag_executor.py       # DAG executor for parallel task execution
│   ├── agent_factory.py      # Factory for creating agent instances with scoped tools
│   ├── agent_registry.py     # Registry of available agent templates
│   └── interfaces.py         # Protocol definitions (IntentClassifier, Planner, Executor)
├── persistence/              # State management
│   ├── base.py              # RunStore protocol definition
│   ├── memory.py            # CuratedMemoryStore for long-term memory
│   └── sqlite_store.py      # SQLite implementation of RunStore
├── schemas/                  # Data models
│   ├── contracts.py         # Core models (TaskSpec, PlanSpec, TaskResult, RunTrace, etc.)
│   ├── query.py             # API request/response models
│   └── eval.py              # Evaluation request/response models
├── runtime/                  # Runtime utilities
│   ├── logging.py           # Structured event logging
│   ├── security.py          # Text sanitization for untrusted content
│   └── tracing.py           # Request tracing and correlation
├── tools/                    # Tool implementations
│   ├── base.py              # WebSearchTool protocol
│   ├── web_search.py        # Stub web search implementation
│   ├── adk_gemini.py        # Google ADK Gemini LLM tool
│   ├── providers.py         # Tool provider registry
│   └── tool_gateway.py      # Tool access gateway
├── eval/                     # Evaluation framework
│   └── runner.py            # EvalRunner for benchmarking system performance
├── main.py                   # FastAPI application entry point
└── __init__.py
```

## Complete Processing Workflow

### 1. **Request Ingestion** (`ingest` stage)
- FastAPI receives a POST request to `/query` with a user query
- Generates unique `trace_id` and `request_id` for request tracking
- Initializes RunTrace to capture all stages of processing

### 2. **Intent Classification** (`classify` stage)
- Determines the type of query (e.g., "general", "research", "coding", "planning")
- Uses LLM-based classification if enabled, falls back to stub classifier
- Intent informs the planning strategy
- Example: "Who won the 2024 Olympics?" → intent="research"

### 3. **Query Planning** (`plan` stage)
- Breaks down the query into an ordered list of tasks (TaskSpec)
- Creates a plan with task dependencies (DAG structure)
- Each task specifies:
  - `task_id`: Unique identifier
  - `description`: What the task does
  - `dependencies`: List of prerequisite task IDs
  - `assigned_agent`: Which agent executes this task (e.g., "research", "verifier")
  - `required_tools`: Tools the agent needs (e.g., "web.search", "llm.adk")
- Example plan for a research query:
  ```
  Task 1 (research-1):
    - description: "Research facts for: Who won the 2024 Olympics?"
    - dependencies: []
    - assigned_agent: research
    - required_tools: [llm.adk]

  Task 2 (verify-1):
    - description: "Verify factual consistency and citation coverage"
    - dependencies: [research-1]
    - assigned_agent: verifier
    - required_tools: []
  ```

### 4. **Execution Planning & Budget Validation** (preflight checks)
- DAGExecutor validates the plan:
  - No duplicate task IDs
  - All dependencies reference existing tasks
  - No circular dependencies (acyclic)
  - No deadlocks possible
- Enforces execution budgets:
  - Max agents: 10
  - Max tool calls: 50
  - Token budget: 10,000
- Per-task timeout: 120 seconds
- Max retries per failed task: 1

### 5. **Parallel Task Execution** (`execute` stage)
The DAGExecutor manages parallel execution:

**Execution Algorithm:**
- Builds dependency graph from tasks
- Maintains sets of:
  - **ready**: Tasks with all dependencies satisfied
  - **running**: Tasks currently executing
  - **completed**: Finished tasks
- Loop until all tasks complete:
  1. Launch ready tasks (up to budget limits) as asyncio Tasks
  2. Wait for first task to complete
  3. Mark task as completed
  4. On failure: Retry once if within retry limit, otherwise fail dependents
  5. Mark dependents of completed tasks as ready

**Agent Execution Details:**
Each agent's `run(task, context)` method receives:
- `task`: TaskSpec with query/context
- `context`: Contains trace_id, request_id, and prior results

**ResearchAgent** execution:
- Retrieves web search and LLM tools from its scoped tool set
- Attempts LLM-based search with Google grounding (if available)
- Falls back to web search + manual fact extraction
- Sanitizes all outputs and citations
- Returns TaskResult with status, output text, and citations

**VerifierAgent** execution:
- Validates factual consistency of results
- Checks citation coverage (stub implementation)

**Error Handling:**
- Failed dependency → downstream tasks fail immediately
- Task timeout → retried once if budget allows
- Unauthorized tool access → ToolScopeError raised
- Deadlock detection → DagExecutionError raised

### 6. **Result Aggregation** (`aggregate` stage)
- Combines outputs from all completed tasks
- Extracts and deduplicates citations across all results
- Creates a "draft" response synthesizing all task outputs
- Produces aggregated dict with:
  - `draft`: Synthesized answer text
  - `citations`: List of unique source URLs

### 7. **Verification & Repair** (post-execution)
- Verifies factual consistency from aggregated results
- Performs quality checks based on verification policies
- Repairs or flags inconsistencies (stub implementation)
- Updates verification status in response

### 8. **Response Formatting** (`respond` stage)
- Formats final answer from aggregated results
- Cleans and sanitizes all output text
- Optionally includes JSON payload with:
  - `verification`: Verification status and details
  - All intermediate results if requested
  - Full trace log
- Generates QueryResponse:
  ```json
  {
    "answer": "The final synthesized answer...",
    "intent": "research",
    "plan": {...},
    "task_results": [...],
    "trace": {...},
    "json_payload": {...} // if include_json=true
  }
  ```

### 9. **Persistence** (parallel to response)
Two parallel persistence operations:
- **Run Storage**: Saves complete run record (query, plan, results, trace, answer)
- **Curated Memory**: Extracts high-quality facts for long-term retrieval

**Memory Curation Policy:**
- Requires citations (unless disabled)
- Minimum content length: 20 characters
- Maximum entries per run: 1
- Sanitizes all content before storage
- Logs success/failure reasons

### 10. **Response Delivery**
- Returns QueryResponse to client
- End-to-end trace visible in response

## Data Models (in `schemas/contracts.py`)

### Core Models

**TaskSpec** - Represents a single unit of work:
```python
- task_id: str          # Unique identifier
- description: str      # Task objective
- dependencies: list[str]  # Prerequisites
- assigned_agent: str   # Agent responsible
- required_tools: list[str]  # Tools needed
```

**TaskResult** - Output of task execution:
```python
- task_id: str          # Which task
- status: "success"|"failed"
- output: str           # Result text
- citations: list[str]  # Source URLs
- error: Optional[str]  # Error message
```

**PlanSpec** - Complete task plan:
```python
- plan_id: str          # Unique plan ID
- tasks: list[TaskSpec] # All tasks (min 1)
```

**AgentSpec** - Agent capabilities:
```python
- agent_id: str         # Runtime agent ID
- role: str             # Agent role
- allowed_tools: list[str]  # Authorized tools
```

**RunTrace** - Request telemetry:
```python
- trace_id: str         # Trace identifier
- request_id: str       # Request identifier
- started_at: datetime  # Start time
- finished_at: Optional[datetime]  # End time
- status: "started"|"completed"|"failed"
- events: list[dict]    # Timestamped stage events
```

## Core Components

### Orchestrator (`orchestrator/pipeline.py`)
**Central coordinator** managing the entire workflow:
- **Main Method**: `async run(query: str) -> QueryResponse`
  - Invokes all 10 stages in sequence
  - Manages trace propagation
  - Handles all persistence

- **Composition**: Uses StubIntentClassifier, StubPlanner, DAGExecutor
- **Tool Management**: Registers available tools (web.search, llm.adk)
- **Storage**: Manages RunStore and CuratedMemoryStore instances

### DAGExecutor (`orchestrator/dag_executor.py`)
**Parallel execution engine** for DAG-based task execution:
- Validates plan structure (no cycles, valid dependencies)
- Manages async task concurrent execution
- Handles retry logic and error propagation
- Enforces execution budgets and timeouts
- Generates detailed execution traces

**Key Methods:**
- `async execute(plan, trace) -> list[TaskResult]`: Main execution method
- `_validate_plan()`: Pre-flight validation
- `_run_task()`: Individual task execution with retry logic
- `_assert_acyclic()`: Cycle detection

### Agent Factory & Registry (`agent_factory.py`, `agent_registry.py`)
**Security-focused agent instantiation**:
- **AgentFactory**: Creates agent instances with scoped tools
  - Validates that agent has required tools
  - Restricts tool access to authorized_tools
  - Raises ToolScopeError on unauthorized access
  
- **AgentRegistry**: Stores agent templates
  - Maps template_id to AgentSpec and agent class
  - Provides `with_defaults()` for built-in agents
  - Load from config in Phase 1+

### BaseAgent (`agents/base.py`)
**Abstract base** for all agents:
- `spec: AgentSpec`: Agent identity and permissions
- `tools: dict[str, Any]`: Scoped tool access
- `async run(task, context)`: Abstract method each agent implements
- **Validation**: Rejects unauthorized tools on instantiation

### Specialized Agents (`agents/baseline.py`)

**ResearchAgent**:
- Searches for facts using web.search or llm.adk tools
- Extracts key claims from search results
- Optionally uses LLM to refine extracted claims
- Returns claims with citations

**VerifierAgent**:
- Validates consistency of research results
- Checks citation coverage
- Currently a stub; to be implemented

**PlannerAgent**:
- Breaks down complex queries (currently stub)
- Creates task DAG

### Persistence Layer (`persistence/`)

**RunStore Protocol** (`base.py`):
- `save_run()`: Persist complete query execution + results
- `insert_curated_memory()`: Add high-quality facts to knowledge base
- `get_run()`: Retrieve historical run
- `list_curated_memory()`: Query knowledge base

**CuratedMemoryStore** (`memory.py`):
- Write-only curated memory manager
- Enforces quality policies:
  - Citations required
  - Minimum content length
  - Max entries per run
- Sanitizes content before persistence
- Logs write outcomes

**SqliteRunStore** (`sqlite_store.py`):
- SQLite3-backed implementation
- Stores runs and curated memory
- Located at `data/mas.sqlite3`

### Tool System (`tools/`)

**Tool Protocol** (`base.py`):
```python
class WebSearchTool(Protocol):
  - async search(query, request_id, trace_id) -> list[SearchResult]
  - async fetch_page_text(url, ...) -> str
```

**Tool Implementations**:
- **StubWebSearchTool**: Mock search for offline testing
- **ADKGeminiTool**: Google ADK Gemini LLM
  - `complete_json()`: Structured output
  - `complete()`: Text output
  - `complete_with_google_search()`: Grounded search

**Tool Gateway** (`tool_gateway.py`):
- Central tool access point
- Request tracking and rate limiting (extensible)

### Runtime Utilities

**Logging** (`runtime/logging.py`):
- Structured event logging to JSON
- Format: `{timestamp, trace_id, stage, message, ...extra}`
- Logs all key orchestrator stages

**Tracing** (`runtime/tracing.py`):
- `new_trace()`: Create RunTrace
- `mark_trace_complete()`: Finalize trace

**Security** (`runtime/security.py`):
- `sanitize_untrusted_text()`: Remove control characters

## API Endpoints

### 1. POST `/query`
**Processes a user query**

Request:
```json
{
  "query": "Who won the 2024 Olympics?",
  "include_json": false
}
```

Response:
```json
{
  "answer": "The Paris 2024 Summer Olympics saw...",
  "intent": "research",
  "plan": {...},
  "task_results": [
    {
      "task_id": "research-1",
      "status": "success",
      "output": "France hosted and won multiple medals...",
      "citations": ["https://olympics.com/..."],
      "error": null
    }
  ],
  "trace": {
    "trace_id": "...",
    "request_id": "...",
    "started_at": "2026-03-21T10:30:00Z",
    "finished_at": "2026-03-21T10:35:00Z",
    "status": "completed",
    "events": [...]
  },
  "json_payload": null
}
```

### 2. POST `/eval`
**Evaluates system performance on test dataset**

Request:
```json
{
  "input_jsonl_path": "test_cases.jsonl",
  "output_report_path": "eval_report.json"
}
```

Response:
```json
{
  "total_cases": 100,
  "report_path": "eval_report.json",
  "metrics": {
    "success_rate": 0.85,
    "avg_latency_ms": 3500,
    "total_tool_calls": 450,
    "citation_hit_rate": 0.92
  }
}
```

## Evaluation Framework (`eval/runner.py`)

**EvalRunner** benchmarks system performance:
- Loads test cases from JSONL file (format: `{"id": "...", "query": "..."}`)
- Runs orchestrator on each case and measures:
  - Success rate (verification status)
  - Latency per query
  - Tool calls used
  - Citation count
- Generates evaluation report with:
  - Per-case details
  - Aggregate metrics (success %, avg latency, total tool calls, citation hits)
- Report saved to JSON for analysis

## Execution Example

**Query**: "What's the capital of France?"

**Stage 1: Ingest**
```
Event: request received
trace_id: abc123, request_id: def456
```

**Stage 2: Classify**
```
Event: intent classified
intent: research
```

**Stage 3: Plan**
```
Event: plan created
Task 1: "Research capital of France" (research agent)
  - dependencies: []
  - required_tools: [llm.adk]
Task 2: "Verify factual consistency" (verifier agent)
  - dependencies: [research-1]
```

**Stage 4: Execute (parallel)**
```
Task 1 starts (ResearchAgent)
  - Uses LLM tool to search for France's capital
  - Finds: "Paris"
  - Citations: [wikipedia.org/France]
  - Status: success

Task 2 starts (VerifierAgent, after Task 1 completes)
  - Verifies: "Paris is France's capital" ✓
  - Status: success
```

**Stage 5-9**:
- Aggregate: "The capital of France is Paris"
- Verify: All facts verified
- Format response
- Persist run
- Add fact to curated memory

**Stage 10: Respond**
```json
{
  "answer": "The capital of France is Paris.",
  "citations": ["https://en.wikipedia.org/wiki/France"],
  ...
}
```

## Workflow Diagram

```
User Query
    ↓ (ingest)
┌─────────────────────────────────────┐
│ 1. Intent Classification            │ ← LLM or Stub
│    "What's the capital of France?" │
│    → intent="research"              │
└─────────────────────────────────────┘
    ↓ (classify)
┌─────────────────────────────────────┐
│ 2. Query Planning                   │ ← LLM or Stub
│    Creates TaskSpec DAG:            │
│    research-1 → verify-1            │
└─────────────────────────────────────┘
    ↓ (plan)
┌─────────────────────────────────────┐
│ 3. Pre-flight Validation            │ ← DAGExecutor
│    • No cycles, valid deps          │
│    • Budget constraints OK          │
└─────────────────────────────────────┘
    ↓ (validate)
┌────────────────────┐   ┌──────────────────┐
│ Task: research-1   │   │ Task: verify-1   │
│ Status: Pending    │   │ Status: Pending  │
└────────────────────┘   └──────────────────┘
          ↓ (execute)             ↓ (blocked)
    ┌──────────────────┐    (waiting for dependency)
    │ ResearchAgent    │
    │ • Search "France"│
    │ • Extract Paris  │
    │ • Citations: [..] →──────────────┐
    └──────────────────┘               ↓
    Output → research-1 complete   ┌──────────────────┐
                                   │ VerifierAgent    │
                                   │ • Verify claims  │
                                   │ • Check citations│
                                   └──────────────────┘
                                   Output → verify-1 complete
                ↓ (execute completes)
┌─────────────────────────────────────┐
│ 4. Result Aggregation               │
│    Combine research + verify results│
│    Citations: [wikiped.org/France]  │
└─────────────────────────────────────┘
    ↓ (aggregate)
┌─────────────────────────────────────┐
│ 5. Verification & Repair            │
│    Final quality checks             │
│    Status: verified                 │
└─────────────────────────────────────┘
    ↓ (verify)
┌─────────────────────────────────────┐
│ 6. Response Formatting              │
│    {"answer": "Paris", ...}         │
└─────────────────────────────────────┘
    ↓ (format)
┌─────────────────────────────────────┐
│ 7. Persistence (parallel)           │
│    • Save run + trace               │
│    • Add fact to curated memory     │
└─────────────────────────────────────┘
    ↓ (persist)
┌─────────────────────────────────────┐
│ 8. Response                         │
│    QueryResponse + citations        │
└─────────────────────────────────────┘
```

## Dependencies

- **FastAPI** (>=0.129.0) - Web framework and async runtime
- **google-adk** (>=1.27.1) - Google ADK Gemini LLM interface
- **pydantic** (>=2.12.5) - Data validation and serialization
- **python** (>=3.12) - Language and async/await support

## Running the System

### Start the server:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Query the API:
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Who won the 2024 Olympics?", "include_json": false}'
```

### Run evaluation:
```bash
curl -X POST http://localhost:8000/eval \
  -H "Content-Type: application/json" \
  -d '{"input_jsonl_path": "test_cases.jsonl", "output_report_path": "results.json"}'
```

## Database

- SQLite3 database at `data/mas.sqlite3`
- Stores: execution runs, curated memory entries
- Auto-initialized on first run
- **Pydantic** (>=2.12.5) - Data validation

Requires Python >=3.12

## Current Status

⚠️ **WIP - Work in Progress**

Several components are in stub/completed form:
- Intent classification always returns "research"
- Executor runs dummy tasks without actual agent invocation
- Aggregation and verification methods are not yet implemented
- Agent implementations (Verifier, Planner) need completion
- SearchResult schema needs definition

## Known Issues

See code review comments for implementation details needed.

## Running the Application

```bash
# Install dependencies
pip install -e .

# Run the server
uvicorn app.main:app --reload
```
