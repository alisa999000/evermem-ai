from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field


@dataclass
class EntityCountSummary:
    """Distinct countable items extracted across sessions."""

    category: str
    count: int
    examples: list[str] = field(default_factory=list)


@dataclass
class MemoryEventSummary:
    """Compact dated event for prompt rendering."""

    label: str
    date_iso: str
    days_before_question: int
    category: str = "event"


@dataclass
class TemporalGapSummary:
    """Pre-computed day distance between two dated events."""

    earlier_label: str
    later_label: str
    earlier_date: str
    later_date: str
    days: int


@dataclass
class AggregateResult:
    """How often a topic appears across stored conversation turns."""

    query: str
    matching_sessions: int
    matching_turns: int
    session_ids: list[str] = field(default_factory=list)


@dataclass
class Claim:
    """A single memory claim with temporal validity and trust.

    A claim is `(user_id, subject, predicate, value)` plus lifecycle metadata.
    Exclusive claims (e.g. `location`) supersede previous values; non-exclusive
    claims (e.g. `likes`) coexist and may form open conflicts.
    """

    id: int
    user_id: str
    subject: str
    predicate: str
    value: str
    kind: str = "fact"  # fact | preference | event
    exclusive: bool = False
    support: int = 1
    trust: float = 0.6
    created_at: float = 0.0
    last_seen: float = 0.0
    valid_from: float = 0.0
    invalid_from: float | None = None
    superseded_by: int | None = None
    source: str = "user"
    source_turn_id: int | None = None
    source_session: str | None = None

    @property
    def active(self) -> bool:
        return self.invalid_from is None

    def text(self) -> str:
        return f"{self.subject} {self.predicate} {self.value}"


@dataclass
class ClaimDraft:
    """Claim candidate produced by an extractor, before storage."""

    subject: str
    predicate: str
    value: str
    kind: str = "fact"
    exclusive: bool = False
    confidence: float = 0.7


@dataclass
class Turn:
    id: int
    session_id: str
    user_id: str
    role: str
    text: str
    created_at: float


@dataclass
class Episode:
    id: int
    session_id: str
    user_id: str
    first_at: float
    last_at: float
    turns: int
    topic: str
    summary: str


@dataclass
class EpisodeTouch:
    """Result of extending or opening an episode."""

    episode_id: int
    closed_episode_id: int | None = None


@dataclass
class ScoredClaim:
    claim: Claim
    score: float


@dataclass
class ConflictHint:
    subject: str
    predicate: str
    values: list[str]


@dataclass
class MemoryPack:
    """Everything recall() found, ready to inject into an LLM prompt."""

    query: str
    claims: list[ScoredClaim] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    history: list[Turn] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
    conflicts: list[ConflictHint] = field(default_factory=list)
    aggregation: AggregateResult | None = None
    entity_counts: list[EntityCountSummary] = field(default_factory=list)
    chronology: list[Turn] = field(default_factory=list)
    timeline_events: list[MemoryEventSummary] = field(default_factory=list)
    temporal_gaps: list[TemporalGapSummary] = field(default_factory=list)
    query_profile: str = "general"
    # When set, history renders as a dated timeline with day offsets relative
    # to this moment; pre-computed date math the LLM reader no longer has to do.
    reference_ts: float | None = None

    def as_prompt(
        self,
        *,
        max_claims: int = 12,
        max_history_chars: int | None = None,
        budget_chars: int | None = None,
    ) -> str:
        """Render the pack for prompt injection.

        budget_chars caps the total rendered size: sections are already
        ordered by priority (facts, conflicts, history, episodes, recent
        turns), so trimming drops the least important lines first.
        """
        if max_history_chars is None:
            max_history_chars = 1200 if self.query_profile in {"count", "temporal", "order"} else 600

        lines: list[str] = ["[MEMORY]"]
        if self.query_profile != "general":
            lines.append(f"Query type: {self.query_profile} (use structured blocks below first).")
        if self.claims:
            lines.append("Known facts (most relevant first):")
            for item in self.claims[:max_claims]:
                claim = item.claim
                lines.append(
                    f"- {claim.subject} | {claim.predicate} = {claim.value}"
                    f" (trust {claim.trust:.2f}, seen x{claim.support})"
                )
        if self.conflicts:
            lines.append("Open contradictions (verify with the user):")
            for conflict in self.conflicts:
                joined = " | ".join(conflict.values)
                lines.append(f"- {conflict.subject} | {conflict.predicate}: {joined}")
        if self.entity_counts:
            lines.append("Distinct items counted in memory (use these numbers directly):")
            for item in self.entity_counts[:8]:
                examples = ", ".join(item.examples[:4])
                suffix = f" ({examples})" if examples else ""
                lines.append(f"- {item.category}: {item.count}{suffix}")
        if self.timeline_events:
            lines.append("Dated events index (authoritative timeline):")
            for item in self.timeline_events[:14]:
                lines.append(f"- [{item.date_iso}, {item.days_before_question}d before question] {item.label}")
        if self.temporal_gaps:
            lines.append("Pre-computed day gaps between events (use directly, do not recalculate):")
            for gap in self.temporal_gaps[:15]:
                lines.append(
                    f"- {gap.earlier_date} ({gap.earlier_label}) -> "
                    f"{gap.later_date} ({gap.later_label}) = {gap.days} days"
                )
        if self.aggregation:
            agg = self.aggregation
            lines.append("Conversation mention counts (supporting context):")
            lines.append(
                f"- {agg.matching_turns} matching mention(s)"
                f" across {agg.matching_sessions} separate conversation(s)"
            )
            if agg.session_ids:
                shown = ", ".join(agg.session_ids[:8])
                if len(agg.session_ids) > 8:
                    shown += f", +{len(agg.session_ids) - 8} more"
                lines.append(f"- sessions: {shown}")
        if self.chronology:
            lines.append("Chronological order (earliest first, for which-came-first questions):")
            for turn in self.chronology[:12]:
                when = ""
                if self.reference_ts is not None and turn.created_at > 0:
                    when = _dt.date.fromtimestamp(turn.created_at).isoformat() + " - "
                snippet = turn.text
                if len(snippet) > max_history_chars:
                    snippet = snippet[: max_history_chars - 1] + "\u2026"
                lines.append(f"- [{when}{turn.role}] {snippet}")
        if self.history:
            sessions = sorted({turn.session_id for turn in self.history})
            if len(sessions) > 1:
                lines.append(
                    f"Relevant events found in {len(sessions)} separate conversations:"
                )
            else:
                lines.append("Relevant past messages:")
            ordered = sorted(self.history, key=lambda turn: turn.created_at)
            for turn in ordered:
                text = turn.text
                if len(text) > max_history_chars:
                    text = text[: max_history_chars - 1] + "\u2026"
                prefix = f"- {turn.role}"
                if self.reference_ts is not None and turn.created_at > 0:
                    when = _dt.date.fromtimestamp(turn.created_at).isoformat()
                    offset_days = round((self.reference_ts - turn.created_at) / 86400.0)
                    if offset_days > 0:
                        rel = f"{offset_days} days before the question"
                    elif offset_days < 0:
                        rel = f"{-offset_days} days after the question"
                    else:
                        rel = "same day as the question"
                    prefix = f"- [{when}, {rel}] {turn.role}"
                lines.append(f"{prefix}: {text}")
            if self.reference_ts is not None:
                # Pre-computed gaps between event dates: small reader models
                # consistently fail this arithmetic when left to do it themselves.
                dates = sorted(
                    {
                        _dt.date.fromtimestamp(turn.created_at)
                        for turn in self.history
                        if turn.created_at > 0
                    }
                )
                if len(dates) > 1:
                    if len(dates) <= 6:
                        pairs = [
                            (dates[i], dates[j])
                            for i in range(len(dates))
                            for j in range(i + 1, len(dates))
                        ]
                    else:
                        pairs = list(zip(dates, dates[1:]))
                    lines.append("Day gaps between the dates above (already computed):")
                    for first, second in pairs[:15]:
                        gap = (second - first).days
                        lines.append(
                            f"- {first.isoformat()} -> {second.isoformat()} = {gap} days"
                        )
        if self.episodes:
            lines.append("Earlier episodes:")
            for episode in self.episodes:
                label = episode.summary or episode.topic
                if label:
                    lines.append(f"- {label}")
        if self.turns:
            lines.append("Recent conversation:")
            for turn in self.turns:
                lines.append(f"- {turn.role}: {turn.text}")
        if budget_chars is not None and budget_chars > 0:
            closing = "\n[/MEMORY]"
            kept: list[str] = []
            used = 0
            for line in lines:
                if used + len(line) + 1 + len(closing) > budget_chars:
                    break
                kept.append(line)
                used += len(line) + 1
            if len(kept) < 2:
                kept = lines[:2]
            return "\n".join(kept) + closing
        lines.append("[/MEMORY]")
        return "\n".join(lines)

    def searchable_text(self) -> str:
        """Full untruncated text of everything in the pack (for evaluation)."""
        parts: list[str] = []
        for item in self.claims:
            parts.append(item.claim.text())
        for conflict in self.conflicts:
            parts.append(f"{conflict.subject} {conflict.predicate} " + " ".join(conflict.values))
        for item in self.entity_counts:
            parts.append(f"{item.category} {item.count} " + " ".join(item.examples))
        for item in self.timeline_events:
            parts.append(f"{item.date_iso} {item.label}")
        for gap in self.temporal_gaps:
            parts.append(f"{gap.days} days {gap.earlier_label} {gap.later_label}")
        if self.aggregation:
            parts.append(
                f"{self.aggregation.matching_turns} turns {self.aggregation.matching_sessions} sessions"
            )
        for turn in self.chronology:
            parts.append(turn.text)
        for turn in self.history:
            parts.append(turn.text)
        for episode in self.episodes:
            parts.append(episode.summary or episode.topic)
        for turn in self.turns:
            parts.append(turn.text)
        return "\n".join(parts)


@dataclass
class ObserveReport:
    turn_id: int
    claims_added: int
    claims_reinforced: int
    claims_superseded: int
    topic: str
    events_added: int = 0


@dataclass
class SessionPrimer:
    """Compressed memory snapshot for the start of an agent session.

    Call at session start so the agent knows durable facts, open conflicts
    and stale items that may need verification - without a blind recall().
    """

    user_id: str
    claims: list[Claim] = field(default_factory=list)
    conflicts: list[ConflictHint] = field(default_factory=list)
    stale_claims: list[Claim] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def as_prompt(self, *, max_claims: int = 15, budget_chars: int | None = 4000) -> str:
        lines: list[str] = ["[MEMORY_PRIMER]"]
        if self.claims:
            lines.append("Known facts (highest trust first):")
            for claim in self.claims[:max_claims]:
                prov = ""
                if claim.source_session:
                    prov = f", from {claim.source_session}"
                lines.append(
                    f"- {claim.subject} | {claim.predicate} = {claim.value}"
                    f" (trust {claim.trust:.2f}, seen x{claim.support}{prov})"
                )
        if self.conflicts:
            lines.append("Open contradictions - verify before acting:")
            for conflict in self.conflicts:
                joined = " | ".join(conflict.values)
                lines.append(f"- {conflict.subject} | {conflict.predicate}: {joined}")
        if self.stale_claims:
            lines.append("Possibly stale - confirm with the user if relevant:")
            for claim in self.stale_claims[:5]:
                lines.append(f"- {claim.subject} | {claim.predicate} = {claim.value}")
        if self.stats:
            lines.append(
                f"Store: {self.stats.get('claims_active', 0)} active facts,"
                f" {self.stats.get('turns', 0)} turns,"
                f" {self.stats.get('episodes', 0)} episodes"
            )
        lines.append("[/MEMORY_PRIMER]")
        text = "\n".join(lines)
        if budget_chars is not None and len(text) > budget_chars:
            return text[: budget_chars - 16] + "\n[/MEMORY_PRIMER]"
        return text
