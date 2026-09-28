from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from .auth import get_current_user
from .db import User
from .evaluation_metrics import answer_f1, citation_scores, mean, retrieval_recall
from .evaluation_model import EvaluationCase, EvaluationDataset, EvaluationResult, EvaluationRun

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


class DatasetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class CaseRequest(BaseModel):
    question: str = Field(min_length=1)
    expected_answer: str = Field(min_length=1)
    expected_document_ids: list[str] = Field(default_factory=list)


def _owned(dataset: EvaluationDataset | None, user: User | None, auth_required: bool) -> bool:
    return bool(dataset) and ((not auth_required and user is None) or (user is not None and dataset.owner_id == user.id))


@router.post("/datasets")
async def create_dataset(request: Request, body: DatasetRequest, user: Annotated[User | None, Depends(get_current_user)]):
    async with request.app.state.session_factory() as session:
        dataset = EvaluationDataset(owner_id=user.id if user else None, name=body.name, description=body.description)
        session.add(dataset)
        await session.commit()
        await session.refresh(dataset)
        return {"id": dataset.id, "name": dataset.name, "description": dataset.description}


@router.post("/datasets/{dataset_id}/cases")
async def create_case(request: Request, dataset_id: str, body: CaseRequest, user: Annotated[User | None, Depends(get_current_user)]):
    async with request.app.state.session_factory() as session:
        dataset = await session.get(EvaluationDataset, dataset_id)
        if not _owned(dataset, user, request.app.state.settings.auth_required):
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        case = EvaluationCase(dataset_id=dataset_id, question=body.question, expected_answer=body.expected_answer, expected_document_ids_json=json.dumps(body.expected_document_ids))
        session.add(case)
        await session.commit()
        await session.refresh(case)
        return {"id": case.id, "dataset_id": dataset_id}


@router.post("/datasets/{dataset_id}/run")
async def run_dataset(request: Request, dataset_id: str, user: Annotated[User | None, Depends(get_current_user)]):
    async with request.app.state.session_factory() as session:
        dataset = await session.get(EvaluationDataset, dataset_id)
        if not _owned(dataset, user, request.app.state.settings.auth_required):
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        cases = (await session.scalars(select(EvaluationCase).where(EvaluationCase.dataset_id == dataset_id).order_by(EvaluationCase.created_at))).all()
        run = EvaluationRun(dataset_id=dataset_id, status="running", case_count=len(cases))
        session.add(run)
        await session.flush()
        run_id = run.id
        semaphore = asyncio.Semaphore(max(1, request.app.state.settings.evaluation_concurrency))

        async def evaluate_case(case: EvaluationCase) -> EvaluationResult:
            expected_documents = json.loads(case.expected_document_ids_json or "[]")
            document_id = expected_documents[0] if len(expected_documents) == 1 else None
            async with semaphore:
                started = time.perf_counter()
                retrieved = await asyncio.to_thread(request.app.state.pipeline.search, case.question, 6, document_id, user.id if user else None)
                response = await asyncio.to_thread(request.app.state.answer_engine.answer, case.question, 6, document_id, user.id if user else None)
                elapsed_ms = (time.perf_counter() - started) * 1000
            retrieved_ids = [str(source.metadata.get("document_id")) for source in retrieved if source.metadata.get("document_id")]
            cited_ids = [str(source.get("metadata", {}).get("document_id")) for source in response.get("sources", []) if source.get("metadata", {}).get("document_id")]
            precision, recall = citation_scores(cited_ids, expected_documents)
            return EvaluationResult(run_id=run_id, case_id=case.id, answer=response.get("answer", ""), retrieved_document_ids_json=json.dumps(retrieved_ids), citations_json=json.dumps(response.get("citations", [])), retrieval_recall=retrieval_recall(retrieved_ids, expected_documents), citation_precision=precision, citation_recall=recall, answer_f1=answer_f1(response.get("answer", ""), case.expected_answer), latency_ms=elapsed_ms)

        results = list(await asyncio.gather(*(evaluate_case(case) for case in cases)))
        metrics = {"retrieval_recall": mean([r.retrieval_recall for r in results]), "citation_precision": mean([r.citation_precision for r in results]), "citation_recall": mean([r.citation_recall for r in results]), "answer_f1": mean([r.answer_f1 for r in results]), "latency_ms": mean([r.latency_ms for r in results])}
        run.status, run.metrics_json, run.completed_at = "completed", json.dumps(metrics), datetime.now(timezone.utc)
        session.add_all(results)
        await session.commit()
        return {"run_id": run_id, "status": run.status, "case_count": len(cases), "metrics": metrics}


@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str, user: Annotated[User | None, Depends(get_current_user)]):
    async with request.app.state.session_factory() as session:
        run = await session.get(EvaluationRun, run_id)
        dataset = await session.get(EvaluationDataset, run.dataset_id) if run else None
        if not run or not _owned(dataset, user, request.app.state.settings.auth_required):
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        results = (await session.scalars(select(EvaluationResult).where(EvaluationResult.run_id == run_id))).all()
        return {"run_id": run.id, "status": run.status, "case_count": run.case_count, "metrics": json.loads(run.metrics_json or "{}"), "results": [{"case_id": item.case_id, "answer": item.answer, "retrieved_document_ids": json.loads(item.retrieved_document_ids_json), "citations": json.loads(item.citations_json), "retrieval_recall": item.retrieval_recall, "citation_precision": item.citation_precision, "citation_recall": item.citation_recall, "answer_f1": item.answer_f1, "latency_ms": item.latency_ms} for item in results]}
