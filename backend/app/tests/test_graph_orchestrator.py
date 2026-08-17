import pytest

from app.agents.langgraph_agents import AgentOutput


def test_agent_output_constructs_without_execution_time_ms():
    """
    Regression test for a critical bug: AgentOutput.execution_time_ms had
    no default, but every agent's own execute() method constructs
    AgentOutput(...) without it (BaseAgent.run_with_retry sets it
    afterward, from *outside* execute() — it can't be set from inside
    execute() since the agent doesn't know its own wall-clock time until
    the caller measures it). This meant every single agent failed on
    every invocation, in both orchestrators, until execution_time_ms was
    given a default of 0.
    """
    output = AgentOutput(
        agent_name="test_agent",
        success=True,
        data={},
        confidence_score=0.9,
        reasoning_trace="test",
        supporting_evidence=[],
        data_sources=[],
    )
    assert (
        output.execution_time_ms == 0
    )  # default, overwritten by run_with_retry afterward


def test_agent_output_still_accepts_explicit_execution_time_ms():
    output = AgentOutput(
        agent_name="test_agent",
        success=True,
        data={},
        confidence_score=0.9,
        reasoning_trace="test",
        supporting_evidence=[],
        data_sources=[],
        execution_time_ms=150,
    )
    assert output.execution_time_ms == 150


@pytest.mark.asyncio
async def test_investigation_node_skips_crew_when_confidence_high(monkeypatch):
    from app.agents.graph_orchestrator import (
        INVESTIGATION_CONFIDENCE_THRESHOLD,
        LangGraphOrchestrator,
    )

    orch = LangGraphOrchestrator.__new__(
        LangGraphOrchestrator
    )  # bypass __init__ (needs a real DB session)
    from app.agents.crew.investigation_crew import InvestigationCrew

    orch.investigation_crew = InvestigationCrew()

    state = {
        "city": "Pune",
        "ward_id": "W01",
        "confidence_scores": {"attribution": INVESTIGATION_CONFIDENCE_THRESHOLD + 0.1},
        "attribution_result": {"data": {}},
    }
    result = await orch._investigation_node(state)
    assert result["investigation_result"]["data"]["ran"] is False
    assert result["confidence_scores"] == {}  # no adjustment applied


@pytest.mark.asyncio
async def test_investigation_node_runs_crew_when_confidence_low_and_degrades_without_llm(
    monkeypatch,
):
    from app.agents.graph_orchestrator import (
        INVESTIGATION_CONFIDENCE_THRESHOLD,
        LangGraphOrchestrator,
    )
    from app.core.config import settings

    monkeypatch.setattr(
        settings, "ANTHROPIC_API_KEY", ""
    )  # ensure the no-LLM degrade path is exercised

    orch = LangGraphOrchestrator.__new__(LangGraphOrchestrator)
    from app.agents.crew.investigation_crew import InvestigationCrew

    orch.investigation_crew = InvestigationCrew()

    state = {
        "city": "Pune",
        "ward_id": "W03",
        "confidence_scores": {"attribution": INVESTIGATION_CONFIDENCE_THRESHOLD - 0.2},
        "attribution_result": {"data": {"industrial_pct": 40}},
    }
    result = await orch._investigation_node(state)
    assert (
        result["investigation_result"]["success"] is False
    )  # crew didn't actually run (no LLM key)
    assert result["confidence_scores"]["attribution"] == pytest.approx(
        INVESTIGATION_CONFIDENCE_THRESHOLD - 0.2
    )  # unchanged since confidence_adjustment is 0.0 when the crew is skipped


def test_graph_compiles_with_expected_nodes():
    from app.agents.graph_orchestrator import LangGraphOrchestrator

    orch = LangGraphOrchestrator.__new__(LangGraphOrchestrator)
    orch.session = None
    orch.agents = {
        name: None
        for name in (
            "ingestion",
            "forecast",
            "attribution",
            "enforcement",
            "advisory",
            "policy",
        )
    }
    from app.agents.crew.investigation_crew import InvestigationCrew

    orch.investigation_crew = InvestigationCrew()

    # _build_graph only touches self.agents (to close over agent instances
    # in node closures) and doesn't call them, so None placeholders are fine
    # for a structural compile check.
    graph = orch._build_graph()
    node_names = set(graph.get_graph().nodes.keys())
    assert {
        "ingestion",
        "forecast",
        "attribution",
        "investigation",
        "enforcement",
        "advisory",
        "policy",
    }.issubset(node_names)
