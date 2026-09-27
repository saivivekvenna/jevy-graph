"""Compile text into source-grounded RDF."""

from .compiler import Compilation, Thresholds, compile_text
from .extract import extract_claims
from .models import (
    CandidateTriple, ClaimFrame, RelationFrame, SCIENTIFIC_CLAIM_TYPES,
    VerifiedTriple,
)

__all__ = [
    "CandidateTriple",
    "ClaimFrame",
    "Compilation",
    "RelationFrame",
    "SCIENTIFIC_CLAIM_TYPES",
    "Thresholds",
    "VerifiedTriple",
    "compile_text",
    "extract_claims",
]
