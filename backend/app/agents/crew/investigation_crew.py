"""
Investigation Crew (CrewAI).

Extends the existing LangGraph-orchestrated agent pipeline rather than
replacing it — this crew is invoked as one node within
app.agents.graph_orchestrator's real langgraph.graph.StateGraph, only when
the Attribution Agent's confidence falls below a threshold. LangGraph
handles the fixed, deterministic pipeline (ingest -> forecast/attribute ->
enforce -> advise -> analyze); CrewAI handles this one genuinely
open-ended, exploratory sub-task — gathering and weighing corroborating
evidence from several independent sources, which benefits from CrewAI's
agent-to-agent task delegation rather than a fixed graph edge.

Requires an LLM (ANTHROPIC_API_KEY) — unlike every other feature added in
this codebase, autonomous multi-agent reasoning genuinely can't be done for
free. `InvestigationCrew.is_available` gates this cleanly: when no key is
configured, the graph node skips the crew and proceeds with the
Attribution Agent's own confidence unchanged, exactly like the
Firebase/Twilio/satellite integrations degrade when their credentials
aren't configured.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import logger

MAX_RETRIES = 2


@dataclass
class InvestigationResult:
    ward_id: str
    ran: bool
    corroboration_score: (
        float  # 0..1 — how strongly independent evidence supports the attribution
    )
    confidence_adjustment: (
        float  # added to (or subtracted from) the Attribution Agent's confidence
    )
    summary: str
    reasoning_trace: list[str] = field(default_factory=list)
    sources_consulted: list[str] = field(default_factory=list)


class InvestigationCrew:
    @property
    def is_available(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    async def investigate(
        self,
        ward_id: str,
        city: str,
        attribution_summary: dict,
    ) -> InvestigationResult:
        if not self.is_available:
            logger.info(
                "investigation_crew.skipped", reason="ANTHROPIC_API_KEY not configured"
            )
            return InvestigationResult(
                ward_id=ward_id,
                ran=False,
                corroboration_score=0.5,
                confidence_adjustment=0.0,
                summary="Investigation crew not run (no LLM configured) — attribution confidence unchanged.",
                reasoning_trace=[
                    "ANTHROPIC_API_KEY not set; skipping autonomous investigation."
                ],
            )

        last_error: str | None = None
        for attempt in range(MAX_RETRIES):
            try:
                # crewai's Crew.kickoff() is a blocking call (it runs its
                # own internal LLM/tool loop synchronously) — run it off
                # the event loop so it doesn't block other agents/requests.
                result = await asyncio.to_thread(
                    self._run_crew_sync, ward_id, city, attribution_summary
                )
                return result
            except (
                Exception
            ) as e:  # noqa: BLE001 - crew failures shouldn't take down the enforcement pipeline
                last_error = str(e)
                logger.warning(
                    "investigation_crew.retry",
                    ward_id=ward_id,
                    attempt=attempt + 1,
                    error=last_error,
                )

        logger.error("investigation_crew.failed", ward_id=ward_id, error=last_error)
        return InvestigationResult(
            ward_id=ward_id,
            ran=False,
            corroboration_score=0.5,
            confidence_adjustment=0.0,
            summary=f"Investigation crew failed after {MAX_RETRIES} attempts: {last_error}",
            reasoning_trace=[f"Error: {last_error}"],
        )

    def _run_crew_sync(
        self, ward_id: str, city: str, attribution_summary: dict
    ) -> InvestigationResult:
        from crewai import LLM, Agent, Crew, Process, Task

        from app.agents.crew.tools import (get_citizen_alert_history,
                                           get_enforcement_history,
                                           get_satellite_evidence,
                                           get_sensor_health)

        llm = LLM(
            model="anthropic/claude-sonnet-4-6",
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.2,
        )

        investigator = Agent(
            role="Field Pollution Investigator",
            goal=(
                f"Gather independent evidence for or against the pollution attribution finding "
                f"in ward {ward_id}, {city}: {attribution_summary}"
            ),
            backstory=(
                "A meticulous municipal air-quality investigator who never accepts a single "
                "sensor's reading at face value and always cross-checks against satellite data, "
                "citizen reports, enforcement history, and sensor health before drawing a conclusion."
            ),
            tools=[
                get_satellite_evidence,
                get_citizen_alert_history,
                get_enforcement_history,
                get_sensor_health,
            ],
            llm=llm,
            verbose=False,
        )

        verifier = Agent(
            role="Evidence Verifier",
            goal="Weigh the investigator's gathered evidence and produce a calibrated corroboration score.",
            backstory=(
                "A skeptical reviewer whose job is to catch overconfident conclusions — "
                "distinguishes genuine multi-source corroboration from a single strong-sounding "
                "but uncorroborated claim, and is explicit about uncertainty."
            ),
            llm=llm,
            verbose=False,
        )

        investigate_task = Task(
            description=(
                f"Using your tools, gather satellite evidence, citizen alert history, enforcement "
                f"history, and sensor health for ward {ward_id} in {city}. The current attribution "
                f"finding to investigate is: {attribution_summary}. Summarize what each source shows "
                "and whether it supports, contradicts, or is silent on the finding."
            ),
            expected_output="A structured summary of findings from each of the four data sources.",
            agent=investigator,
        )

        verify_task = Task(
            description=(
                "Review the investigator's findings. Produce: (1) a corroboration_score from 0.0 "
                "(no independent support, possibly a sensor artifact) to 1.0 (strongly corroborated "
                "by multiple independent sources), (2) a one-paragraph summary explaining the score, "
                "and (3) which sources were actually consulted. "
                "Respond ONLY as JSON: "
                '{"corroboration_score": <float>, "summary": "<text>", "sources_consulted": ["<source>", ...]}'
            ),
            expected_output="A JSON object with corroboration_score, summary, and sources_consulted.",
            agent=verifier,
            context=[investigate_task],
        )

        crew = Crew(
            agents=[investigator, verifier],
            tasks=[investigate_task, verify_task],
            process=Process.sequential,
            memory=True,  # shared memory across the crew's tasks within this run
            verbose=False,
        )

        crew_output = crew.kickoff()
        return self._parse_crew_output(ward_id, crew_output)

    def _parse_crew_output(self, ward_id: str, crew_output) -> InvestigationResult:
        import json
        import re

        raw = str(crew_output)
        reasoning_trace = [f"Crew raw output: {raw[:500]}"]

        try:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else {}
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(
                "investigation_crew.parse_failed", ward_id=ward_id, error=str(e)
            )
            parsed = {}

        corroboration_score = float(parsed.get("corroboration_score", 0.5))
        corroboration_score = max(0.0, min(1.0, corroboration_score))
        summary = parsed.get(
            "summary",
            "Crew output could not be parsed as structured JSON; treating as neutral.",
        )
        sources_consulted = parsed.get("sources_consulted", [])

        # Confidence adjustment: corroboration above the neutral midpoint
        # (0.5) increases confidence, below it decreases it — capped at
        # +/-0.15 so one crew run can't swing the Attribution Agent's
        # confidence more than a moderate amount.
        confidence_adjustment = round((corroboration_score - 0.5) * 0.3, 3)

        return InvestigationResult(
            ward_id=ward_id,
            ran=True,
            corroboration_score=corroboration_score,
            confidence_adjustment=confidence_adjustment,
            summary=summary,
            reasoning_trace=reasoning_trace,
            sources_consulted=sources_consulted,
        )
