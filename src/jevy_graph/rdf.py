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

    for index, item in enumerate(triples, start=1):
        candidate = item.candidate
        subject = _resource("entity", candidate.subject)
        object_ = _resource("entity", candidate.object)
        predicate = (
            "rdf:type"
            if candidate.predicate == "type"
            else _resource("relation", candidate.predicate)
        )
        claim_material = (
            f"{document_hash}:{candidate.sentence_index}:{candidate.subject}:"
            f"{candidate.predicate}:{candidate.object}"
        )
        claim_hash = hashlib.sha256(claim_material.encode()).hexdigest()[:16]
        claim = f"<urn:jevy:claim:{claim_hash}>"

        lines.extend(
            [
                f'{subject} jevy:label "{_escape(candidate.subject)}" .',
                f'{object_} jevy:label "{_escape(candidate.object)}" .',
                f"{subject} {predicate} {object_} .",
                f"{claim} a rdf:Statement ;",
                f"    rdf:subject {subject} ;",
                f"    rdf:predicate {predicate} ;",
                f"    rdf:object {object_} ;",
                f"    prov:wasDerivedFrom {document} ;",
                f'    jevy:evidence "{_escape(candidate.evidence)}" ;',
                f"    jevy:sentenceIndex {candidate.sentence_index} ;",
                f'    jevy:support "{item.support:.6f}"^^xsd:decimal ;',
                f'    jevy:factuality "{item.factuality:.6f}"^^xsd:decimal .',
                "",
            ]
        )
    return "\n".join(lines)

