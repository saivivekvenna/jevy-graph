from __future__ import annotations

from dataclasses import dataclass

from .extract import candidates_from_frames, extract_frames
from .jev import JevClient
from .models import VerifiedTriple
from .normalize import graphable_node
from .rdf import render_turtle


@dataclass(frozen=True, slots=True)
class Thresholds:
    support: float = 0.45
    entity: float = 0.10
    joint: float = 0.70


@dataclass(frozen=True, slots=True)
class Compilation:
    turtle: str
    frames: int
    resolved: int
    accepted: int
    singletons: int = 0


def accepts(item: VerifiedTriple, thresholds: Thresholds = Thresholds()) -> bool:
    floors = {
        "open_verb": Thresholds(0.50, 0.20, 0.80),
    }.get(item.candidate.origin, Thresholds())
    subject = item.candidate.subject
    object_ = item.candidate.object
    return (
        graphable_node(subject)
        and graphable_node(object_)
        and item.support >= max(thresholds.support, floors.support)
        and item.entity_quality >= max(thresholds.entity, floors.entity)
        and item.support + item.entity_quality >= max(thresholds.joint, floors.joint)
    )


def select(
    items: list[VerifiedTriple],
    thresholds: Thresholds = Thresholds(),
    seen: set[tuple[str, str, str, str, str, str]] | None = None,
) -> list[VerifiedTriple]:
    """Filter scores and collapse duplicate readings of one source occurrence."""
    seen = seen if seen is not None else set()
    selected: list[VerifiedTriple] = []
    for item in items:
        candidate = item.candidate
        key = (
            candidate.subject.casefold(),
            candidate.predicate,
            candidate.object.casefold(),
            candidate.evidence.casefold(),
            candidate.modality or "",
            candidate.polarity,
        )
        if accepts(item, thresholds) and key not in seen:
            seen.add(key)
            selected.append(item)
    return selected


def compile_text(
    text: str,
    *,
    client: JevClient | None = None,
    thresholds: Thresholds = Thresholds(),
) -> Compilation:
    """Compile text to Turtle, using Jev when a client is supplied."""
    frames = extract_frames(text)
    if client is None:
        candidates = candidates_from_frames(frames)
        verified = [VerifiedTriple(candidate, 1.0, 1.0) for candidate in candidates]
    else:
        verified = client.score(frames)
    accepted = select(verified, thresholds)
    return Compilation(
        turtle=render_turtle(text, accepted),
        frames=len(frames),
        resolved=len(verified),
        accepted=len(accepted),
        singletons=client.singleton_selections if client else 0,
    )
