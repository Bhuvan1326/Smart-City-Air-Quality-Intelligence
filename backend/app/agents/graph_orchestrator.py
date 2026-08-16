"""
Real LangGraph orchestration.

app.agents.langgraph_agents.AirQualityOrchestrator (despite its module's
name) never actually used the `langgraph` package — it's a hand-rolled
sequential/parallel async orchestrator that mimics LangGraph's state-passing
style. That implementation is left completely untouched here per this
change's scope ("extend, don't replace" / "never remove features") — it's
still a working, tested orchestrator and remains the default at
POST /api/v1/agents/run.

This module adds a *second*, additive orchestrator built on the real
`langgraph.graph.StateGraph`, exposed separately at
POST /api/v1/agents/run-graph, reusing every existing agent class
unchanged. It also adds one genuinely new node — an Investigation step
that delegates to a CrewAI crew (see app.agents.crew.investigation_crew)
when the Attribution Agent's confidence is low — demonstrating the
LangGraph-orchestrates / CrewAI-executes-autonomous-subtasks split the
spec asks for.

Graph shape (mirrors AirQualityOrchestrator's dependency order, with
forecast and attribution both routed through the investigation node so it
acts as a single proper join point rather than two edges arriving at
enforcement at different graph depths — see the comment on graph
construction below for why that matters):

    START -> ingestion -> forecast -----\\
                       \\-> attribution -> investigation -> enforcement -> policy -> END
                                                         \\-> advisory -----/
"""

from __future__ import annotations

import operator
import uuid
from datetime import UTC, datetime
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.crew.investigation_crew import InvestigationCrew
from app.agents.langgraph_agents import (AttributionAgent,
                                         CitizenAdvisoryAgent,
                                         DataIngestionAgent, EnforcementAgent,
                                         ForecastAgent, PolicyAnalyticsAgent)
from app.core.logging import logger

# Confidence below which the Attribution Agent's finding gets routed
# through the Investigation Crew for independent corroboration before
# Enforcement acts on it.
INVESTIGATION_CONFIDENCE_THRESHOLD = 0.65


def _merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}


class GraphState(TypedDict):
    city: str
    ward_id: str | None
    query: str
    user_role: str
    session_id: str

    ingestion_result: dict | None
    forecast_result: dict | None
    attribution_result: dict | None
    investigation_result: dict | None
    enforcement_result: dict | None
    advisory_result: dict | None
    policy_result: dict | None

    # Accumulator fields: parallel branches (forecast+attribution,
    # enforcement+advisory) each return partial updates to these, and
    # LangGraph merges them via the reducers below rather than one branch
    # clobbering the other's write — the standard fan-out/fan-in pattern.
    confidence_scores: Annotated[dict, _merge_dicts]
    reasoning_traces: Annotated[dict, _merge_dicts]
    supporting_evidence: Annotated[list, operator.add]
    data_sources: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]


class LangGraphOrchestrator:
    """Additive alternative to AirQualityOrchestrator, built on a real langgraph.graph.StateGraph."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.agents = {
            "ingestion": DataIngestionAgent(session),
            "forecast": ForecastAgent(session),
            "attribution": AttributionAgent(session),
            "enforcement": EnforcementAgent(session),
            "advisory": CitizenAdvisoryAgent(session),
            "policy": PolicyAnalyticsAgent(session),
        }
        self.investigation_crew = InvestigationCrew()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(GraphState)

        graph.add_node("ingestion", self._make_agent_node("ingestion"))
        graph.add_node("forecast", self._make_agent_node("forecast"))
        graph.add_node("attribution", self._make_agent_node("attribution"))
        graph.add_node("investigation", self._investigation_node)
        graph.add_node("enforcement", self._make_agent_node("enforcement"))
        graph.add_node("advisory", self._make_agent_node("advisory"))
        graph.add_node("policy", self._make_agent_node("policy"))

        graph.add_edge(START, "ingestion")
        graph.add_edge("ingestion", "forecast")
        graph.add_edge("ingestion", "attribution")
        # Both forecast and attribution feed into investigation (not
        # directly into enforcement) so investigation is a proper
        # single join point at equal graph depth from both branches —
        # investigation only *uses* attribution's data, but including
        # forecast as a second incoming edge here means enforcement and
        # advisory each get exactly one incoming edge (from investigation),
        # avoiding the double-execution that occurs when a node has
        # incoming edges arriving at different superstep depths (forecast
        # is 1 hop from ingestion; attribution->investigation is 2 hops —
        # without this, enforcement would fire once per predecessor as
        # each becomes ready in its own superstep, running the agent twice).
        graph.add_edge("forecast", "investigation")
        graph.add_edge("attribution", "investigation")
        graph.add_edge("investigation", "enforcement")
        graph.add_edge("investigation", "advisory")
        graph.add_edge("enforcement", "policy")
        graph.add_edge("advisory", "policy")
        graph.add_edge("policy", END)

        return graph.compile()

    def _make_agent_node(self, agent_name: str):
        agent = self.agents[agent_name]

        async def node(state: GraphState) -> dict:
            output = await agent.run_with_retry(state)  # type: ignore[arg-type]
            update: dict = {
                f"{agent_name}_result": {
                    "success": output.success,
                    "data": output.data,
                },
                "confidence_scores": {agent_name: output.confidence_score},
                "reasoning_traces": {agent_name: output.reasoning_trace},
                "supporting_evidence": output.supporting_evidence[:3],
                "data_sources": [d for d in output.data_sources],
                "errors": [f"{agent_name}: {output.error}"] if output.error else [],
            }
            return update

        return node

    async def _investigation_node(self, state: GraphState) -> dict:
        """
        Runs the CrewAI Investigation Crew only when the Attribution
        Agent's confidence is below threshold — otherwise this is a fast
        no-op pass-through, so the extra node doesn't add latency to the
        common (confident-attribution) case.
        """
        attribution_confidence = state["confidence_scores"].get("attribution", 1.0)
        ward_id = state.get("ward_id") or "unknown"
        city = state["city"]

        if attribution_confidence >= INVESTIGATION_CONFIDENCE_THRESHOLD:
            return {
                "investigation_result": {
                    "success": True,
                    "data": {
                        "ran": False,
                        "reason": "attribution confidence already high enough",
                    },
                },
                "confidence_scores": {},
                "reasoning_traces": {
                    "investigation": (
                        f"Skipped — attribution confidence {attribution_confidence:.2f} already "
                        f">= threshold {INVESTIGATION_CONFIDENCE_THRESHOLD}."
                    )
                },
                "supporting_evidence": [],
                "data_sources": [],
                "errors": [],
            }

        attribution_data = (state.get("attribution_result") or {}).get("data", {})
        result = await self.investigation_crew.investigate(
            ward_id=ward_id, city=city, attribution_summary=attribution_data
        )

        logger.info(
            "graph.investigation_complete",
            ward_id=ward_id,
            ran=result.ran,
            corroboration_score=result.corroboration_score,
            confidence_adjustment=result.confidence_adjustment,
        )

        return {
            "investigation_result": {
                "success": result.ran,
                "data": {
                    "corroboration_score": result.corroboration_score,
                    "confidence_adjustment": result.confidence_adjustment,
                    "sources_consulted": result.sources_consulted,
                },
            },
            # Confidence propagation: the crew's corroboration adjusts the
            # Attribution Agent's own confidence score in shared state,
            # which flows into the final aggregated overall_confidence and
            # is visible to Enforcement's own reasoning via attribution_result.
            "confidence_scores": {
                "attribution": round(
                    max(
                        0.0,
                        min(1.0, attribution_confidence + result.confidence_adjustment),
                    ),
                    3,
                ),
                "investigation": result.corroboration_score,
            },
            "reasoning_traces": {"investigation": result.summary},
            "supporting_evidence": [
                {"source": "investigation_crew", "detail": result.summary}
            ],
            "data_sources": result.sources_consulted,
            "errors": [],
        }

    async def run(
        self,
        city: str,
        query: str = "",
        ward_id: str | None = None,
        user_role: str = "city_administrator",
    ) -> dict:
        initial_state: GraphState = {
            "city": city,
            "ward_id": ward_id,
            "query": query,
            "user_role": user_role,
            "session_id": str(uuid.uuid4()),
            "ingestion_result": None,
            "forecast_result": None,
            "attribution_result": None,
            "investigation_result": None,
            "enforcement_result": None,
            "advisory_result": None,
            "policy_result": None,
            "confidence_scores": {},
            "reasoning_traces": {},
            "supporting_evidence": [],
            "data_sources": [],
            "errors": [],
        }

        final_state = await self.graph.ainvoke(initial_state)

        scores = list(final_state["confidence_scores"].values())
        overall_confidence = sum(scores) / max(len(scores), 1) if scores else 0.0

        return {
            "session_id": final_state["session_id"],
            "city": city,
            "ward_id": ward_id,
            "overall_confidence": round(overall_confidence, 3),
            "confidence_scores": final_state["confidence_scores"],
            "reasoning_traces": final_state["reasoning_traces"],
            "supporting_evidence": final_state["supporting_evidence"],
            "data_sources": list(set(final_state["data_sources"])),
            "errors": final_state["errors"],
            "agents_executed": [
                "ingestion",
                "forecast",
                "attribution",
                "investigation",
                "enforcement",
                "advisory",
                "policy",
            ],
            "ingestion": final_state.get("ingestion_result"),
            "forecast": final_state.get("forecast_result"),
            "attribution": final_state.get("attribution_result"),
            "investigation": final_state.get("investigation_result"),
            "enforcement": final_state.get("enforcement_result"),
            "advisory": final_state.get("advisory_result"),
            "policy": final_state.get("policy_result"),
            "orchestrator": "langgraph_stategraph",
            "generated_at": datetime.now(UTC).isoformat(),
        }
