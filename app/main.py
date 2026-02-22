from fastapi import FastAPI

from app.orchestrator import Orchestrator
from app.runtime.logging import configure_logging
from app.schemas.query import QueryRequest, QueryResponse

app = FastAPI(title="Multi-Agent Orchestrator API")
orchestrator = Orchestrator()
configure_logging()

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(payload: QueryRequest) -> QueryResponse:
    return await orchestrator.run(payload.query)
