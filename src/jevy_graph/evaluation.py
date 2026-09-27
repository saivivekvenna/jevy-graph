"""Claim-level benchmark scoring and stage-loss diagnostics.

Only exhaustive, Codex-reviewed or independently human-reviewed fixtures may satisfy the release gate. Other
fixtures are useful regression probes but cannot establish precision or recall
for an entire document.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Any

from .compiler import Thresholds, rejection_reason, select
from .extract import _source_markers, clean_document
from .jev import _triple_options
from .models import CandidateTriple, RelationFrame, VerifiedTriple


MIN_TEST_CLAIMS_PER_DOMAIN = 30
MIN_TEST_FIXTURES_PER_DOMAIN = 2
MIN_TEST_CLAIMS_PER_INSTRUCTION = 20


def _key(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").casefold()).strip(" .,:;\n\t")


def output_fingerprint(
    fixture_id: str, converted_text: str, candidate: CandidateTriple
) -> str:
    """Identify an accepted output against the exact fixture and source snapshot.

    All candidate fields are included, including qualifiers, evidence, and source
    location. Verification scores are omitted because they are not claim content.
    """
    payload = {
        "schema_version": 1,
        "fixture_id": fixture_id,
        "converted_text_sha256": hashlib.sha256(converted_text.encode("utf-8")).hexdigest(),
        "candidate": asdict(candidate),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _claim_forms(gold: dict[str, Any]) -> list[dict[str, Any]]:
    return [gold, *(gold | alternative for alternative in gold.get("alternatives", []))]


def _form_matches(form: dict[str, Any], values: tuple[str, str, str]) -> bool:
    return all(_key(form[name]) == _key(actual) for name, actual in zip(
        ("subject", "predicate", "object"), values, strict=True
    ))


def _triple_matches(gold: dict[str, Any], claim: CandidateTriple | tuple[str, str, str]) -> bool:
    values = (claim.subject, claim.predicate, claim.object) if isinstance(claim, CandidateTriple) else claim
    return any(_form_matches(form, values) for form in _claim_forms(gold))


def _qualifier_errors(gold: dict[str, Any], claim: CandidateTriple) -> list[str]:
    values = (claim.subject, claim.predicate, claim.object)
    forms = [form for form in _claim_forms(gold) if _form_matches(form, values)] or [gold]
    errors_by_form = []
    for form in forms:
        errors = []
        for name in ("polarity", "modality", "condition"):
            expected = form.get(name, "positive" if name == "polarity" else None)
            if _key(expected) != _key(getattr(claim, name)):
                errors.append(name)
        if form.get("source_unit") and _key(form["source_unit"]) != _key(claim.source_unit):
            errors.append("source_unit")
        if "attribution" in form and _key(form["attribution"]) != _key(claim.attribution):
            errors.append("attribution")
        evidence = form.get("evidence", "")
        if evidence and _key(evidence) not in _key(claim.evidence):
            errors.append("evidence")
        errors_by_form.append(errors)
    return min(errors_by_form, key=len)


def _stage_has_gold(gold: dict[str, Any], claims: list[CandidateTriple]) -> bool:
    return any(
        _triple_matches(gold, item) and not _qualifier_errors(gold, item)
        for item in claims
    )


def _option_has_gold(
    gold: dict[str, Any], frame: RelationFrame, option: tuple[str, str, str]
) -> bool:
    subject, predicate, object_ = option
    candidate = CandidateTriple(
        subject, predicate, object_, frame.evidence, frame.sentence_index,
        frame.start, frame.end, modality=frame.modality, polarity=frame.polarity,
        condition=frame.condition, source_unit=frame.source_unit,
        attribution=frame.attribution,
    )
    return _triple_matches(gold, candidate) and not _qualifier_errors(gold, candidate)


def _forbidden_matches(forbidden: dict[str, Any], candidate: CandidateTriple) -> bool:
    return _triple_matches(forbidden, candidate) and all(
        _key(forbidden[name]) == _key(getattr(candidate, name))
        for name in ("polarity", "modality", "condition", "source_unit", "attribution")
        if name in forbidden
    )


def _frame_covers_evidence(gold: dict[str, Any], frame: RelationFrame) -> bool:
    evidence = _key(gold.get("evidence"))
    return bool(evidence) and (
        evidence in _key(frame.context)
        or evidence in _key(frame.evidence)
        or _key(frame.evidence) in evidence
    )


def score_fixture(
    fixture: dict[str, Any],
    *,
    converted_text: str,
    frames: list[RelationFrame],
    candidates: list[CandidateTriple],
    verified: list[VerifiedTriple],
    thresholds: Thresholds = Thresholds(),
    usage: dict[str, Any] | None = None,
    timing: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Score one fixture; unmatched outputs remain review items until adjudicated."""
    accepted = select(verified, thresholds)
    rejected = [
        {"claim": asdict(item), "reason": rejection_reason(item, thresholds)}
        for item in verified if rejection_reason(item, thresholds)
    ]
    gold = fixture.get("gold", [])
    expected = [item for item in gold if item.get("in_scope", True)]
    matched_indexes: set[int] = set()
    matches: list[dict[str, Any]] = []
    unmatched_outputs: list[dict[str, Any]] = []
    fingerprint_indexes: dict[str, list[int]] = defaultdict(list)
    fingerprints = [output_fingerprint(fixture["id"], converted_text, item.candidate)
                    for item in accepted]
    for index, fingerprint in enumerate(fingerprints):
        fingerprint_indexes[fingerprint].append(index)
    unmatched_by_index: dict[int, dict[str, Any]] = {}
    for output_index, item in enumerate(accepted):
        candidate = item.candidate
        available = [
            (index, target) for index, target in enumerate(expected)
            if index not in matched_indexes and _triple_matches(target, candidate)
        ]
        if not available:
            output = {"claim": asdict(item), "output_fingerprint": fingerprints[output_index],
                      "review": "unmatched_output"}
            unmatched_outputs.append(output)
            unmatched_by_index[output_index] = output
            continue
        index, target = min(available, key=lambda pair: len(_qualifier_errors(pair[1], candidate)))
        errors = _qualifier_errors(target, candidate)
        if errors:
            output = {
                "claim": asdict(item), "output_fingerprint": fingerprints[output_index],
                "gold_id": target["id"],
                "review": "qualifier_or_evidence_error", "errors": errors,
            }
            unmatched_outputs.append(output)
            unmatched_by_index[output_index] = output
        else:
            matched_indexes.add(index)
            matches.append({"gold_id": target["id"], "claim": asdict(item),
                            "output_fingerprint": fingerprints[output_index],
                            "match_type": "exact_or_alternative"})

    if fixture.get("adjudicated_unmatched"):
        raise ValueError(
            f"{fixture['id']}: older adjudicated_unmatched records lack exact output "
            "fingerprints; migrate them to output_adjudications"
        )
    adjudication_audit: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()
    reserved_gold = set(matched_indexes)
    gold_by_id: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(expected):
        gold_by_id[item["id"]].append(index)
    verdicts = {"equivalent", "unsupported", "wrong_boundary", "wrong_qualifier", "out_of_scope"}
    for record in fixture.get("output_adjudications", []):
        fingerprint = record.get("output_fingerprint")
        verdict = record.get("verdict")
        reviewer = record.get("review_status")
        reason = record.get("reason")
        source_evidence = record.get("source_evidence")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError(f"{fixture['id']}: adjudication requires a SHA-256 output_fingerprint")
        if fingerprint in seen_fingerprints:
            raise ValueError(f"{fixture['id']}: duplicate adjudication for {fingerprint}")
        seen_fingerprints.add(fingerprint)
        indices = fingerprint_indexes.get(fingerprint, [])
        if not indices:
            raise ValueError(f"{fixture['id']}: stale adjudication for {fingerprint}")
        if len(indices) != 1 or indices[0] not in unmatched_by_index:
            raise ValueError(f"{fixture['id']}: ambiguous or already matched output {fingerprint}")
        if verdict not in verdicts:
            raise ValueError(f"{fixture['id']}: invalid adjudication verdict {verdict!r}")
        if reviewer not in {"codex_reviewed", "human_reviewed"}:
            raise ValueError(f"{fixture['id']}: adjudication requires explicit review_status")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{fixture['id']}: adjudication requires a reason")
        if (not isinstance(source_evidence, str) or not source_evidence.strip()
                or source_evidence not in converted_text):
            raise ValueError(f"{fixture['id']}: adjudication source_evidence must quote the converted source")
        gold_id = record.get("gold_id")
        if verdict == "equivalent":
            targets = gold_by_id.get(gold_id, []) if isinstance(gold_id, str) else []
            if len(targets) != 1:
                raise ValueError(f"{fixture['id']}: equivalence requires one in-scope gold_id")
            if targets[0] in reserved_gold:
                raise ValueError(f"{fixture['id']}: duplicate match to gold_id {gold_id}")
            reserved_gold.add(targets[0])
        else:
            if not isinstance(record.get("critical"), bool):
                raise ValueError(f"{fixture['id']}: negative adjudication requires critical true or false")
            if gold_id is not None and gold_id not in gold_by_id:
                raise ValueError(f"{fixture['id']}: unknown gold_id {gold_id!r}")
        adjudication_audit.append({**record, "accepted_index": indices[0]})

    for record in adjudication_audit:
        output = unmatched_by_index[record["accepted_index"]]
        output["review"] = record["verdict"]
        output["review_reason"] = record["reason"]
        output["review_status"] = record["review_status"]
        output["source_evidence"] = record["source_evidence"]
        if record["verdict"] == "equivalent":
            gold_id = record["gold_id"]
            gold_index = gold_by_id[gold_id][0]
            matched_indexes.add(gold_index)
            matches.append({
                "gold_id": gold_id, "claim": output["claim"],
                "output_fingerprint": output["output_fingerprint"],
                "match_type": "adjudicated_equivalent",
                "adjudication": {key: record[key] for key in
                                 ("review_status", "reason", "source_evidence")},
            })
    qualifier_counts: Counter[str] = Counter()
    for output in unmatched_outputs:
        if output["review"] != "equivalent":
            qualifier_counts.update(output.get("errors", []))

    options_by_frame = [_triple_options(frame) for frame in frames]
    losses = []
    verified_candidates = [item.candidate for item in verified]
    accepted_candidates = [item.candidate for item in accepted]
    for index, item in enumerate(expected):
        if index in matched_indexes:
            continue
        if item.get("evidence") and _key(item["evidence"]) not in _key(converted_text):
            stage = "source_conversion"
        elif not any(_frame_covers_evidence(item, frame) for frame in frames):
            stage = "frame_generation"
        elif not any(
            _option_has_gold(item, frame, option)
            for frame, options in zip(frames, options_by_frame, strict=True)
            for option in options
        ):
            stage = "candidate_generation"
        elif not _stage_has_gold(item, candidates):
            stage = "jev_selection"
        elif not _stage_has_gold(item, verified_candidates):
            stage = "verification"
        elif not _stage_has_gold(item, accepted_candidates):
            stage = "final_filter"
        else:
            stage = "qualifier_or_evidence"
        losses.append({"gold_id": item["id"], "stage": stage, "gold": item})

    annotations_complete = (
        fixture.get("review_status") in {"human_reviewed", "codex_reviewed"}
        and fixture.get("annotation_scope") == "exhaustive"
    )
    pending_unmatched = [output for output in unmatched_outputs
                         if output["review"] in {"unmatched_output", "qualifier_or_evidence_error"}]
    unmatched_outputs = [output for output in unmatched_outputs
                         if output["review"] != "equivalent"]
    complete = annotations_complete and not pending_unmatched
    precision = len(matches) / len(accepted) if complete and accepted else (1.0 if complete else None)
    recall = len(matches) / len(expected) if expected else (1.0 if complete else None)
    leaked = [
        asdict(item) for item in accepted
        if any(
            _triple_matches(target, item.candidate)
            and not _qualifier_errors(target, item.candidate)
            for target in gold if not target.get("in_scope", True)
        )
    ]
    leaked_fingerprints = {
        output_fingerprint(fixture["id"], converted_text,
                           CandidateTriple(**item["candidate"]))
        for item in leaked
    }
    for record in adjudication_audit:
        if (record["verdict"] == "out_of_scope"
                and record["output_fingerprint"] not in leaked_fingerprints):
            leaked.append(asdict(accepted[record["accepted_index"]]))
            leaked_fingerprints.add(record["output_fingerprint"])
    forbidden_matches = [
        {"claim": asdict(item), "forbidden": forbidden}
        for item in accepted for forbidden in fixture.get("forbidden", [])
        if _forbidden_matches(forbidden, item.candidate)
    ]
    critical_fingerprints = {
        output_fingerprint(fixture["id"], converted_text, CandidateTriple(**item["claim"]["candidate"]))
        for item in forbidden_matches if item["forbidden"].get("critical")
    }
    critical_fingerprints.update(
        record["output_fingerprint"] for record in adjudication_audit
        if record["verdict"] != "equivalent" and record.get("critical")
    )
    unsupported_critical = len(critical_fingerprints)
    excluded_expected = [
        {
            "gold_id": item["id"],
            "gold": item,
            "candidate_generated": any(
                _option_has_gold(item, frame, option)
                for frame, options in zip(frames, options_by_frame, strict=True)
                for option in options
            ),
            "selected": _stage_has_gold(item, candidates),
            "verified": _stage_has_gold(item, verified_candidates),
            "accepted": _stage_has_gold(item, accepted_candidates),
        }
        for item in gold if not item.get("in_scope", True)
    ]
    frames_with_options = sum(bool(options) for options in options_by_frame)
    return {
        "fixture_id": fixture["id"],
        "domain": fixture["domain"],
        "instruction": fixture.get("instruction", ""),
        "split": fixture.get("split", "development"),
        "review_status": fixture.get("review_status", "provisional"),
        "annotation_scope": fixture.get("annotation_scope", "targeted"),
        "annotations_complete": annotations_complete,
        "release_eligible": complete,
        "independent_human_review": (
            fixture.get("review_status") == "human_reviewed"
            and all(record["review_status"] == "human_reviewed"
                    for record in adjudication_audit)
        ),
        "metrics": {
            "frames": len(frames),
            "frames_without_options": len(frames) - frames_with_options,
            "candidate_options": sum(map(len, options_by_frame)),
            "selected_candidates": len(candidates),
            "selection_abstentions": max(0, frames_with_options - len(candidates)),
            "verified": len(verified),
            "accepted": len(accepted),
            "gold_in_scope": len(expected),
            "matched": len(matches),
            "pending_unmatched_review": len(pending_unmatched),
            "precision": precision,
            "recall": recall,
            "scope_leaks": len(leaked),
            "unsupported_critical": unsupported_critical,
            "qualifier_errors": dict(qualifier_counts),
            "rejection_reasons": dict(Counter(item["reason"] for item in rejected)),
            "loss_stages": dict(Counter(item["stage"] for item in losses)),
            **(usage or {}),
            **(timing or {}),
        },
        "matches": matches,
        "losses": losses,
        "rejected": rejected,
        "scope_leaks": leaked,
        "forbidden_matches": forbidden_matches,
        "excluded_expected": excluded_expected,
        "unmatched_outputs": unmatched_outputs,
        "output_adjudications": adjudication_audit,
    }


def constitution_review_coverage(
    source_text: str, fixtures: list[dict[str, Any]]
) -> dict[str, Any]:
    """Require every substantive frozen Constitution unit to have full labels."""
    prepared = clean_document(source_text)
    markers = _source_markers(prepared)
    reviewed: set[str] = set()
    substantive: set[str] = set()
    for index, (start, label) in enumerate(markers):
        start = max(0, start)
        end = markers[index + 1][0] if index + 1 < len(markers) else len(prepared)
        unit_text = prepared[start:end].strip()
        if len(unit_text.split()) < 8:
            continue
        substantive.add(label)
        for fixture in fixtures:
            if (fixture.get("domain") != "legal"
                    or fixture.get("annotation_scope") != "exhaustive"
                    or fixture.get("review_status") not in {"codex_reviewed", "human_reviewed"}):
                continue
            labels = {item.get("source_unit") for item in fixture.get("gold", [])}
            if labels == {label} and _key(unit_text) in _key(fixture.get("text", "")):
                reviewed.add(label)
                break
    return {
        "reviewed_units": len(reviewed),
        "total_units": len(substantive),
        "complete": bool(substantive and reviewed == substantive),
        "unreviewed_units": sorted(substantive - reviewed),
    }


def release_gate(
    reports: list[dict[str, Any]], *, constitution_coverage: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Score untouched test fixtures only; require complete claim review."""
    domains: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for report in reports:
        if report.get("split") == "test":
            domains[report["domain"]].append(report)
    results = {}
    for domain, items in domains.items():
        eligible = bool(items) and all(item["release_eligible"] for item in items)
        human_review = bool(eligible and all(item.get("independent_human_review") for item in items))
        matched = sum(item["metrics"]["matched"] for item in items)
        accepted = sum(item["metrics"]["accepted"] for item in items)
        expected = sum(item["metrics"]["gold_in_scope"] for item in items)
        sample_sufficient = (
            len(items) >= MIN_TEST_FIXTURES_PER_DOMAIN
            and expected >= MIN_TEST_CLAIMS_PER_DOMAIN
        )
        precision = matched / accepted if accepted else 1.0
        recall = matched / expected if expected else 1.0
        results[domain] = {
            "review_complete": eligible,
            "heldout_fixtures": len(items),
            "heldout_claims": expected,
            "sample_sufficient": sample_sufficient,
            "independent_human_review": human_review,
            "precision": precision if eligible else None,
            "recall": recall if eligible else None,
            "passes": bool(eligible and human_review and sample_sufficient and precision >= 0.95 and recall >= 0.95
                           and not any(item["metrics"]["scope_leaks"] or item["metrics"]["unsupported_critical"] for item in items)),
        }
    profiles = {}
    for domain, items in domains.items():
        for instruction in {item["instruction"] for item in items}:
            relevant = [item for item in items if item["instruction"] == instruction]
            eligible = all(item["release_eligible"] for item in relevant)
            human_review = bool(eligible and all(item.get("independent_human_review") for item in relevant))
            matched = sum(item["metrics"]["matched"] for item in relevant)
            accepted = sum(item["metrics"]["accepted"] for item in relevant)
            expected = sum(item["metrics"]["gold_in_scope"] for item in relevant)
            sample_sufficient = expected >= MIN_TEST_CLAIMS_PER_INSTRUCTION
            profiles[f"{domain} | {instruction or 'default'}"] = {
                "review_complete": eligible,
                "heldout_fixtures": len(relevant),
                "heldout_claims": expected,
                "sample_sufficient": sample_sufficient,
                "independent_human_review": human_review,
                "precision": matched / accepted if eligible and accepted else (1.0 if eligible else None),
                "recall": matched / expected if eligible and expected else (1.0 if eligible else None),
                "passes": bool(
                    eligible and human_review and sample_sufficient and
                    (matched / accepted if accepted else 1.0) >= 0.95 and
                    matched / expected >= 0.95 and
                    not any(item["metrics"]["scope_leaks"] or item["metrics"]["unsupported_critical"] for item in relevant)
                ),
            }
    required = {"legal", "biomedical", "general", "structured"}
    return {
        "passes": bool(constitution_coverage and constitution_coverage["complete"])
        and required <= results.keys() and all(results[name]["passes"] for name in required)
        and all(profile["passes"] for profile in profiles.values()),
        "constitution_review": constitution_coverage or {
            "complete": False, "reviewed_units": 0, "total_units": None,
        },
        "domains": results,
        "profiles": profiles,
        "missing_domains": sorted(required - results.keys()),
    }


def quality_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate known-claim recovery without treating partial labels as precision."""
    def aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
        expected = sum(item["metrics"]["gold_in_scope"] for item in items)
        matched = sum(item["metrics"]["matched"] for item in items)
        accepted = sum(item["metrics"]["accepted"] for item in items)
        complete = all(item["release_eligible"] for item in items)
        return {
            "fixtures": len(items),
            "gold_in_scope": expected,
            "matched": matched,
            "accepted": accepted,
            "known_claim_recall": matched / expected if expected else None,
            "precision": matched / accepted if complete and accepted else None,
            "review_complete": complete,
            "independent_human_review": bool(complete and all(item.get("independent_human_review") for item in items)),
            "requests": sum(item["metrics"].get("requests", 0) for item in items),
            "request_bytes": sum(item["metrics"].get("request_bytes", 0) for item in items),
            "input_tokens": sum(item["metrics"].get("input_tokens", 0) for item in items),
            "output_tokens": sum(item["metrics"].get("output_tokens", 0) for item in items),
            "total_seconds": round(sum(item["metrics"].get("total_seconds", 0) for item in items), 4),
            "loss_stages": dict(sum(
                (Counter(item["metrics"]["loss_stages"]) for item in items), Counter()
            )),
        }

    domains: dict[str, list[dict[str, Any]]] = defaultdict(list)
    profiles: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in reports:
        domains[item["domain"]].append(item)
        profiles[f"{item['domain']} | {item['instruction'] or 'default'}"].append(item)
    return {
        "domains": {name: aggregate(items) for name, items in domains.items()},
        "profiles": {name: aggregate(items) for name, items in profiles.items()},
    }
