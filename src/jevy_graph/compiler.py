from __future__ import annotations

from dataclasses import dataclass
import re

from .extract import candidates_from_frames, extract_frames
from .jev import JevClient
from .models import ClaimFrame, GraphIntent, VerifiedTriple
from .normalize import graphable_node
from .rdf import render_turtle


@dataclass(frozen=True, slots=True)
class Thresholds:
    support: float = 0.45
    entity: float = 0.10
    joint: float = 0.70
    scope: float = 0.50
    qualifiers: float = 0.50
    atomicity: float = 0.50


DEFAULT_THRESHOLDS = Thresholds()
EVENT_THRESHOLDS = Thresholds(0.15, 0.25, 0.40, 0.50, 0.10, 0.20)
ORIGIN_THRESHOLD_FLOORS = {
    "open_verb": Thresholds(0.50, 0.20, 0.80),
}


@dataclass(frozen=True, slots=True)
class Compilation:
    turtle: str
    frames: int
    resolved: int
    accepted: int
    singletons: int = 0
    group_by: str = "none"
    claims: tuple[ClaimFrame, ...] = ()


def rejection_reason(
    item: VerifiedTriple, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> str | None:
    # Event records already passed deterministic span, atomicity, and
    # required-context checks. Jev's scores are a final backstop.
    if item.candidate.origin == "event":
        effective = EVENT_THRESHOLDS
    else:
        floors = ORIGIN_THRESHOLD_FLOORS.get(
            item.candidate.origin,
            DEFAULT_THRESHOLDS,
        )
        effective = Thresholds(
            max(thresholds.support, floors.support),
            max(thresholds.entity, floors.entity),
            max(thresholds.joint, floors.joint),
            max(thresholds.scope, floors.scope),
            max(thresholds.qualifiers, floors.qualifiers),
            max(thresholds.atomicity, floors.atomicity),
        )
    subject = item.candidate.subject
    object_ = item.candidate.object
    if re.fullmatch(r"(?:result|results|finding|findings)", subject, re.I):
        return "invalid_node"
    if re.match(r"^(?:only\s+)?\d+\s*/\s*\d+\s+of\s+", subject, re.I):
        return "invalid_node"
    if (
        item.candidate.origin == "open_verb"
        and item.candidate.predicate in {"associated", "related"}
        and re.search(
            r"\b(?:associated|related)\s+"
            r"(?:proteins?|genes?|factors?|markers?)\s+"
            r"(?:is|are|was|were)\b",
            item.candidate.evidence,
            re.I,
        )
    ):
        return "attributive_modifier"
    provision_nodes_are_graphable = (
        item.candidate.origin == "provision"
        and all(
            value.strip()
            and len(value) <= 240
            and len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’./+_-]*", value)) <= 28
            for value in (subject, object_)
        )
    )
    if not provision_nodes_are_graphable and (
        not graphable_node(subject) or not graphable_node(object_)
    ):
        return "invalid_node"
    if item.support < effective.support:
        return "low_support"
    if item.entity_quality < effective.entity:
        return "low_entity_quality"
    if item.support + item.entity_quality < effective.joint:
        return "low_joint_score"
    if item.scope_relevance < effective.scope:
        return "outside_instruction_scope"
    if item.qualifier_quality < effective.qualifiers:
        return "incomplete_qualifiers"
    if item.atomicity < effective.atomicity:
        return "non_atomic_claim"
    return None


def accepts(
    item: VerifiedTriple,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> bool:
    return rejection_reason(item, thresholds) is None


def select(
    items: list[VerifiedTriple],
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    seen: set[tuple[str, ...]] | None = None,
) -> list[VerifiedTriple]:
    """Filter scores and collapse duplicate readings of one source occurrence."""
    seen = seen if seen is not None else set()
    selected: list[VerifiedTriple] = []
    for item in items:
        candidate = item.candidate
        evidence_key = "" if candidate.origin == "event" else candidate.evidence.casefold()
        key = (
            candidate.subject.casefold(),
            candidate.predicate,
            candidate.object.casefold(),
            evidence_key,
            candidate.modality or "",
            candidate.polarity,
            candidate.condition or "",
            candidate.source_unit or "",
            candidate.attribution or "",
            candidate.claim_type or "",
            candidate.comparison or "",
            "\x1f".join(candidate.conditions),
            "\x1f".join(candidate.measurements),
        )
        if accepts(item, thresholds) and key not in seen:
            seen.add(key)
            selected.append(item)
    return selected


def _accepted_claims(
    extracted: list[ClaimFrame], accepted: list[VerifiedTriple]
) -> tuple[ClaimFrame, ...]:
    """Return canonical claim records for accepted typed scientific output."""
    def key(subject: str, relation: str, object_: str) -> tuple[str, str, str]:
        return (
            subject.casefold().strip(),
            relation.casefold().strip(),
            object_.casefold().strip(),
        )

    indexed: dict[tuple[str, str, str], list[ClaimFrame]] = {}
    for claim in extracted:
        claim_key = key(claim.subject, claim.relation, claim.object)
        indexed.setdefault(claim_key, []).append(claim)
    claims: list[ClaimFrame] = []
    for item in accepted:
        candidate = item.candidate
        if not candidate.claim_type:
            continue
        candidate_key = key(
            candidate.subject,
            candidate.predicate,
            candidate.object,
        )
        matches = indexed.get(candidate_key, [])
        if matches:
            claims.append(matches.pop(0))
            continue
        claims.append(
            ClaimFrame(
                claim_type=candidate.claim_type,
                subject=candidate.subject,
                relation=candidate.predicate,
                object=candidate.object,
                comparison=candidate.comparison,
                conditions=candidate.conditions,
                measurements=candidate.measurements,
                modality=candidate.modality,
                polarity=candidate.polarity,
                negated=candidate.polarity == "negative",
                evidence=candidate.evidence,
                sentence_index=candidate.sentence_index,
                start=candidate.start,
                end=candidate.end,
                source_unit=candidate.source_unit,
                source_locator=candidate.source_locator,
                source_page=candidate.source_page,
                origin=candidate.origin,
                attribution=candidate.attribution,
            )
        )
    return tuple(claims)


def compile_text(
    text: str,
    *,
    client: JevClient | None = None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    instruction: str | None = None,
    scientific_dependency_compiler: object | None = None,
) -> Compilation:
    """Compile text to Turtle, using Jev when a client is supplied."""
    instruction = (instruction or "").strip()
    if instruction and client is None:
        raise ValueError("An instruction requires a Jev client")
    intent = (
        client.interpret_instruction(instruction)
        if instruction and client
        else GraphIntent()
    )
    structured_claims: list[ClaimFrame] = []
    frames = extract_frames(
        text,
        scientific_dependency_compiler=scientific_dependency_compiler,
        scientific_claims=structured_claims,
    )
    if client is None:
        candidates = candidates_from_frames(frames)
        verified = [VerifiedTriple(candidate, 1.0, 1.0) for candidate in candidates]
    else:
        verified = (
            client.score(frames, instruction=instruction)
            if instruction
            else client.score(frames)
        )
    accepted = select(verified, thresholds)
    return Compilation(
        turtle=render_turtle(text, accepted, group_by=intent.group_by),
        frames=len(frames),
        resolved=len(verified),
        accepted=len(accepted),
        singletons=client.singleton_selections if client else 0,
        group_by=intent.group_by,
        claims=_accepted_claims(structured_claims, accepted),
    )
