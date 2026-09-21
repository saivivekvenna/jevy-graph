from __future__ import annotations

import hashlib
import re

from .models import VerifiedTriple
from .normalize import normalize_space

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _resource(kind: str, value: str) -> str:
    normalized = normalize_space(value).casefold()
    slug = _NON_SLUG.sub("-", normalized).strip("-")[:48] or kind
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:10]
    return f"<urn:jevy:{kind}:{slug}-{digest}>"


def _predicate_resource(value: str) -> str:
    slug = _NON_SLUG.sub("-", normalize_space(value).casefold()).strip("-")
    return f"<urn:jevy:relation:{slug}>"


def _object_value(value: str, kind: str) -> str:
    if kind == "integer":
        return f'"{value.replace(",", "")}"^^xsd:integer'
    if kind == "decimal":
        return f'"{value.replace(",", "")}"^^xsd:decimal'
    if kind == "double":
        return f'"{value.replace(",", "")}"^^xsd:double'
    if kind in {"percent", "string"}:
        return f'"{_escape(value.strip("\\\"\'“”"))}"'
    return _resource("entity", value)


def render_turtle(text: str, triples: list[VerifiedTriple]) -> str:
    document_hash = hashlib.sha256(text.encode()).hexdigest()
    document = f"<urn:jevy:document:{document_hash}>"
    lines = [
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "@prefix prov: <http://www.w3.org/ns/prov#> .",
        "@prefix jevy: <urn:jevy:vocabulary:> .",
        "",
        f'{document} a jevy:Document ; jevy:sha256 "{document_hash}" .',
        "",
    ]

    declared_entities: set[str] = set()
    emitted_assertions: set[tuple[str, str, str]] = set()
    for item in triples:
        candidate = item.candidate
        subject = _resource("entity", candidate.subject)
        object_ = _object_value(candidate.object, candidate.object_kind)
        predicate = (
            "rdf:type"
            if candidate.predicate == "type"
            else _predicate_resource(candidate.predicate)
        )
        claim_material = (
            f"{document_hash}:{candidate.start}:{candidate.end}:{candidate.subject}:"
            f"{candidate.predicate}:{candidate.object}:{candidate.modality}:"
            f"{candidate.polarity}"
        )
        claim_hash = hashlib.sha256(claim_material.encode()).hexdigest()[:16]
        claim = f"<urn:jevy:claim:{claim_hash}>"

        if subject not in declared_entities:
            lines.append(f'{subject} jevy:label "{_escape(candidate.subject)}" .')
            declared_entities.add(subject)
        if candidate.object_kind == "entity" and object_ not in declared_entities:
            lines.append(f'{object_} jevy:label "{_escape(candidate.object)}" .')
            declared_entities.add(object_)
        assertion = (subject, predicate, object_)
        if candidate.polarity == "positive" and assertion not in emitted_assertions:
            lines.append(f"{subject} {predicate} {object_} .")
            emitted_assertions.add(assertion)
        lines.extend(
            [
                f"{claim} a rdf:Statement ;",
                f"    rdf:subject {subject} ;",
                f"    rdf:predicate {predicate} ;",
                f"    rdf:object {object_} ;",
                f"    prov:wasDerivedFrom {document} ;",
                f'    jevy:evidence "{_escape(candidate.evidence)}" ;',
                f"    jevy:sentenceIndex {candidate.sentence_index} ;",
                f"    jevy:normalizedStartOffset {candidate.start} ;",
                f"    jevy:normalizedEndOffset {candidate.end} ;",
                f'    jevy:polarity "{candidate.polarity}" ;',
                f'    jevy:modality "{candidate.modality or "none"}" ;',
                *(
                    [f'    jevy:sourceUnit "{_escape(candidate.source_unit)}" ;']
                    if candidate.source_unit
                    else []
                ),
                *(
                    [f'    jevy:sourceLocator "{_escape(candidate.source_locator)}" ;']
                    if candidate.source_locator
                    else []
                ),
                *(
                    [f"    jevy:sourcePage {candidate.source_page} ;"]
                    if candidate.source_page is not None
                    else []
                ),
                *(
                    [f'    jevy:condition "{_escape(candidate.condition)}" ;']
                    if candidate.condition
                    else []
                ),
                f'    jevy:extractionOrigin "{candidate.origin}" ;',
                "    jevy:selectionConfidence "
                f'"{candidate.selection_confidence:.6f}"^^xsd:decimal ;',
                "    jevy:selectionProbability "
                f'"{candidate.selection_probability:.6f}"^^xsd:decimal ;',
                f'    jevy:support "{item.support:.6f}"^^xsd:decimal ;',
                f'    jevy:entityQuality "{item.entity_quality:.6f}"^^xsd:decimal .',
                "",
            ]
        )
    return "\n".join(lines)
