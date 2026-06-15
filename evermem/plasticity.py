"""Online retrieval-path plasticity.

Hebbian-style edge learning over retrieval routes:
- every recall traverses a path of symbolic nodes (query topic -> subject -> predicate),
- edges along helpful paths are reinforced, contradicted paths decay,
- per-source normalization keeps weights bounded.

This is what makes memory *learn from feedback* instead of being a static index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def _clip(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


@dataclass
class PathEdge:
    src: str
    dst: str
    weight: float
    hits: int = 0


class PathPlasticity:
    def __init__(
        self,
        *,
        default_weight: float = 0.70,
        decay: float = 0.01,
        eta_pos: float = 0.18,
        eta_neg: float = 0.12,
        min_weight: float = 0.05,
        max_weight: float = 2.50,
        write_confidence_threshold: float = 0.30,
        source_avg_cap: float = 1.60,
    ) -> None:
        self.default_weight = default_weight
        self.decay = decay
        self.eta_pos = eta_pos
        self.eta_neg = eta_neg
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.write_confidence_threshold = write_confidence_threshold
        self.source_avg_cap = source_avg_cap
        self._edges: dict[tuple[str, str], PathEdge] = {}

    @staticmethod
    def _pairs(nodes: list[str]) -> list[tuple[str, str]]:
        if len(nodes) < 2:
            return []
        return [(nodes[idx], nodes[idx + 1]) for idx in range(len(nodes) - 1)]

    def path_score(self, nodes: Iterable[str]) -> float:
        clean = [node for node in nodes if node]
        pairs = self._pairs(clean)
        if not pairs:
            return self.default_weight
        score = 0.0
        for key in pairs:
            edge = self._edges.get(key)
            score += edge.weight if edge is not None else self.default_weight
        return score / len(pairs)

    def update_path(
        self,
        nodes: Iterable[str],
        *,
        reward: float,
        confidence: float,
        contradiction: float = 0.0,
    ) -> bool:
        clean = [node for node in nodes if node]
        pairs = self._pairs(clean)
        if not pairs:
            return False

        reward = _clip(reward, 0.0, 1.0)
        confidence = _clip(confidence, 0.0, 1.0)
        contradiction = _clip(contradiction, 0.0, 1.0)
        if confidence < self.write_confidence_threshold and reward < 0.55:
            return False

        touched_sources: set[str] = set()
        for src, dst in pairs:
            key = (src, dst)
            edge = self._edges.get(key)
            if edge is None:
                edge = PathEdge(src=src, dst=dst, weight=self.default_weight, hits=0)
                self._edges[key] = edge
            delta = self.eta_pos * reward * confidence
            penalty = self.eta_neg * contradiction
            updated = (1.0 - self.decay) * edge.weight + delta - penalty
            edge.weight = _clip(updated, self.min_weight, self.max_weight)
            edge.hits += 1
            touched_sources.add(src)

        for src in touched_sources:
            self._normalize_source(src)
        return True

    def _normalize_source(self, src: str) -> None:
        outgoing = [edge for edge in self._edges.values() if edge.src == src]
        if not outgoing:
            return
        avg = sum(edge.weight for edge in outgoing) / len(outgoing)
        if avg <= self.source_avg_cap:
            return
        scale = self.source_avg_cap / max(avg, 1e-9)
        for edge in outgoing:
            edge.weight = _clip(edge.weight * scale, self.min_weight, self.max_weight)

    def edge_count(self) -> int:
        return len(self._edges)

    def export_state(self) -> list[dict[str, object]]:
        rows = []
        for key in sorted(self._edges):
            edge = self._edges[key]
            rows.append(
                {
                    "src": edge.src,
                    "dst": edge.dst,
                    "weight": round(edge.weight, 6),
                    "hits": edge.hits,
                }
            )
        return rows

    def load_state(self, rows: Iterable[dict[str, object]], merge: bool = False) -> int:
        if not merge:
            self._edges = {}
        added = 0
        for row in rows:
            src = str(row.get("src", "")).strip()
            dst = str(row.get("dst", "")).strip()
            if not src or not dst:
                continue
            weight = float(row.get("weight", self.default_weight))
            hits = int(row.get("hits", 0))
            key = (src, dst)
            edge = self._edges.get(key)
            if edge is None:
                self._edges[key] = PathEdge(
                    src=src,
                    dst=dst,
                    weight=_clip(weight, self.min_weight, self.max_weight),
                    hits=max(0, hits),
                )
                added += 1
            else:
                edge.weight = _clip((edge.weight + weight) / 2.0, self.min_weight, self.max_weight)
                edge.hits = max(edge.hits, hits)
        return added
