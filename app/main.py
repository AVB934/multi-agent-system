from __future__ import annotations

from fastapi import FastAPI
from dotenv import load_dotenv

from app.eval import EvalRunner
from app.orchestrator import Orchestrator
from app.runtime.logging import configure_logging
from app.schemas.eval import EvalRequest, EvalResponse
from app.schemas.query import QueryRequest, QueryResponse

load_dotenv()

app = FastAPI(title="Multi-Agent Orchestration Platform")
orchestrator = Orchestrator()
eval_runner = EvalRunner(orchestrator)
configure_logging()


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(payload: QueryRequest) -> QueryResponse:
    return await orchestrator.run(payload.query, include_json=payload.include_json)


@app.post("/eval", response_model=EvalResponse)
async def eval_endpoint(payload: EvalRequest) -> EvalResponse:
    result = await eval_runner.run(
        input_jsonl_path=payload.input_jsonl_path,
        output_report_path=payload.output_report_path,
    )
    return EvalResponse(
        total_cases=int(result["total_cases"]),
        report_path=str(result["report_path"]),
        metrics=dict(result["metrics"]),
    )
