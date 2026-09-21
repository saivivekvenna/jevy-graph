from __future__ import annotations

import re
from dataclasses import dataclass

from .models import RelationFrame
from .normalize import canonical_entity, normalize_space


_TABLE_START = re.compile(r"^\s*Table\s+(\d+)\s*:", re.I)
_NUMBER = re.compile(r"^[+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?$")
_HEADING = re.compile(
    r"^\s*(?P<number>(?!0\d)\d{1,3}(?:\.\d{1,3})*)\.?\s+"
    r"(?P<title>[A-Z][^\n]{1,80}?)\s*$",
    re.M,
)
_METRIC = re.compile(
    r"\b(?P<value>\d+(?:\.\d+)?)\s+(?P<metric>BLEU|F1)\b|"
    r"\b(?P<metric_first>BLEU|F1)(?:\s+score)?\s+(?:of\s+)?"
    r"(?P<value_after>\d+(?:\.\d+)?)\b",
    re.I,
)
_QUANTITY = re.compile(
    r"(?<![A-Za-z0-9])(?P<value>\d[\d,]*(?:\.\d+)?(?:\s*million|[KM])?)\s+"
    r"(?P<unit>sentence pairs|sentences|source tokens|target tokens|tokens|GPUs?|"
    r"steps|hours?|minutes?|days?|seconds?|layers?|heads?)\b",
    re.I,
)
_GPU_COUNT = re.compile(
    r"(?<![A-Za-z])(?P<value>\d+)\s+(?:NVIDIA\s+)?[A-Za-z]+\d+\s+GPUs\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class TableBlock:
    number: int
    lines: tuple[str, ...]
    start: int
    end: int
    page: int

    @property
    def locator(self) -> str:
        return f"Table {self.number}"

    @property
    def caption(self) -> str:
        caption: list[str] = []
        for line_index, line in enumerate(self.lines):
            if not line.strip() and caption:
                break
            if line_index and len(re.split(r"\s{2,}", line.strip())) >= 2:
                break
            if line.strip():
                caption.append(line.strip())
        return normalize_space(" ".join(caption))


def _line_offsets(text: str) -> tuple[list[str], list[int]]:
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line)
    return lines, offsets


def table_blocks(text: str) -> list[TableBlock]:
    """Find layout-preserving PDF table regions without understanding their schema."""
    lines, offsets = _line_offsets(text)
    blocks: list[TableBlock] = []
    index = 0
    while index < len(lines):
        match = _TABLE_START.match(lines[index])
        if not match:
            index += 1
            continue
        start_index = index
        seen_grid = False
        blank_run = 0
        index += 1
        while index < len(lines):
            line = lines[index].rstrip("\r\n")
            stripped = line.strip()
            columnar = len(re.split(r"\s{2,}", stripped)) >= 2
            numeric = bool(re.search(r"\d", stripped))
            if columnar and numeric:
                seen_grid = True
            if not stripped:
                blank_run += 1
                if seen_grid and blank_run >= 2:
                    break
            else:
                blank_run = 0
            index += 1
        end_index = index - blank_run + 1 if blank_run else index
        end = offsets[end_index] if end_index < len(offsets) else len(text)
        start = offsets[start_index]
        blocks.append(
            TableBlock(
                number=int(match.group(1)),
                lines=tuple(line.rstrip("\r\n") for line in lines[start_index:end_index]),
                start=start,
                end=end,
                page=text.count("\f", 0, start),
            )
        )
    return blocks


def mask_table_bodies(text: str) -> str:
    """Hide table grids and pre-abstract boilerplate while retaining offsets."""
    characters = list(text)
    abstract = re.search(r"(?m)^\s*Abstract\s*$", text)
    if abstract:
        for index in range(abstract.start()):
            if characters[index] not in "\r\n\f":
                characters[index] = " "
    for block in table_blocks(text):
        first_newline = text.find("\n", block.start, block.end)
        body_start = first_newline + 1 if first_newline >= 0 else block.start
        for index in range(body_start, block.end):
            if characters[index] not in "\r\n\f":
                characters[index] = " "
    return "".join(characters)


def _slug(value: str) -> str:
    value = normalize_space(value).casefold()
    value = value.replace("ϵ", "epsilon").replace("ε", "epsilon")
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value


def _clean_number(value: str) -> str:
    value = normalize_space(value)
    value = value.replace("×", "·")
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*·\s*10\s*([+-]?\d+)", value)
    if match:
        return f"{match.group(1)}e{match.group(2)}"
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*·\s*10(\d+)", value)
    if match:
        return f"{match.group(1)}e{match.group(2)}"
    match = re.fullmatch(r"(\d+(?:\.\d+)?)K", value, re.I)
    if match:
        return str(int(float(match.group(1)) * 1_000))
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s*million|M)", value, re.I)
    if match:
        return str(int(float(match.group(1)) * 1_000_000))
    return value.replace(",", "")


def _frame(
    block: TableBlock,
    subject: str,
    predicate: str,
    object_: str,
    row: str,
    headers: str,
    row_index: int,
) -> RelationFrame:
    row_text = normalize_space(row)
    context = "\n".join(
        part
        for part in (
            block.caption,
            f"Headers: {normalize_space(headers)}",
            f"Raw row: {row_text}",
            f"Parsed cell: {canonical_entity(subject)} | {predicate} | {_clean_number(object_)}",
        )
        if part
    )
    return RelationFrame(
        subject_options=(canonical_entity(subject),),
        predicate_options=(predicate,),
        object_options=(_clean_number(object_),),
        evidence=row_text,
        context=context,
        sentence_index=1_000_000 + block.number * 10_000 + row_index,
        start=block.start,
        end=block.end,
        source_unit=f"TABLE_{block.number}",
        source_locator=block.locator,
        source_page=block.page,
        origin="table",
    )


def _table_one(block: TableBlock) -> list[RelationFrame]:
    headers = "Layer Type | Complexity per Layer | Sequential Operations | Maximum Path Length"
    frames: list[RelationFrame] = []
    for row_index, row in enumerate(block.lines):
        cells = re.split(r"\s{2,}", row.strip())
        if len(cells) != 4 or not cells[1].startswith("O("):
            continue
        for predicate, value in zip(
            ("has_per_layer_complexity", "has_sequential_operations", "has_maximum_path_length"),
            cells[1:],
            strict=True,
        ):
            frames.append(_frame(block, cells[0], predicate, value, row, headers, row_index))
    return frames


def _numeric_at(line: str, starts: list[int]) -> list[str]:
    values: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(line)
        values.append(line[start:end].strip())
    return values


def _table_two(block: TableBlock) -> list[RelationFrame]:
    header = next((line for line in block.lines if line.count("EN-DE") >= 2), "")
    starts = [match.start() for match in re.finditer(r"EN-DE|EN-FR", header)]
    if len(starts) != 4:
        return []
    headers = (
        "Model | EN-DE BLEU | EN-FR BLEU | EN-DE Training Cost (FLOPs) | "
        "EN-FR Training Cost (FLOPs)"
    )
    predicates = (
        "has_wmt14_en_de_bleu",
        "has_wmt14_en_fr_bleu",
        "has_estimated_en_de_training_cost_flops",
        "has_estimated_en_fr_training_cost_flops",
    )
    frames: list[RelationFrame] = []
    pending_exponents: list[str] = []
    header_index = block.lines.index(header)
    for row_index, row in enumerate(block.lines[header_index + 1 :], header_index + 1):
        if re.fullmatch(r"\s*\d{2}\s*", row):
            pending_exponents.append(row.strip())
            continue
        subject = re.sub(r"\s*\[\d+\]\s*", " ", row[: starts[0] - 4]).strip()
        values = ["" for _ in starts]
        for number in re.finditer(
            r"\d+(?:\.\d+)?(?:\s*·\s*10\d*)?", row[starts[0] - 4 :]
        ):
            absolute_start = starts[0] - 4 + number.start()
            column = min(range(len(starts)), key=lambda item: abs(starts[item] - absolute_start))
            values[column] = number.group()
        if not subject or subject in {"Model", "BLEU", "Training Cost (FLOPs)"}:
            continue
        if not any(re.search(r"\d", value) for value in values):
            continue
        exponent_index = 0
        for predicate, value in zip(predicates, values, strict=True):
            value = normalize_space(value)
            if (
                re.fullmatch(r"\d+(?:\.\d+)?\s*·\s*10", value)
                and exponent_index < len(pending_exponents)
            ):
                value += pending_exponents[exponent_index]
                exponent_index += 1
            if re.search(r"\d", value):
                frames.append(_frame(block, subject, predicate, value, row, headers, row_index))
        if exponent_index:
            pending_exponents = pending_exponents[exponent_index:]
    return frames


def _table_three(block: TableBlock) -> list[RelationFrame]:
    config_header = next(
        (line for line in block.lines if "dmodel" in line and "Pdrop" in line), ""
    )
    metric_header = next(
        (line for line in block.lines if "PPL" in line and "BLEU" in line), ""
    )
    config_matches = list(
        re.finditer(r"\bN\b|dmodel|dff|\bh\b|dk|dv|Pdrop|[ϵε]ls", config_header)
    )
    metric_matches = list(re.finditer(r"train|PPL|BLEU|params", metric_header))
    starts_and_names = [(match.start(), match.group()) for match in config_matches + metric_matches]
    starts_and_names.sort()
    if len(starts_and_names) != 12:
        return []
    starts = [item[0] for item in starts_and_names]
    names = [item[1] for item in starts_and_names]
    predicate_names = {
        "N": "has_layer_count",
        "dmodel": "has_d_model",
        "dff": "has_d_ff",
        "h": "has_attention_head_count",
        "dk": "has_d_k",
        "dv": "has_d_v",
        "Pdrop": "has_dropout",
        "ϵls": "has_label_smoothing",
        "εls": "has_label_smoothing",
        "train": "has_training_steps",
        "steps": "has_training_steps",
        "PPL": "has_dev_perplexity",
        "BLEU": "has_dev_bleu",
        "params": "has_parameter_count_millions",
    }
    headers = " | ".join(names)
    frames: list[RelationFrame] = []
    metric_header_index = block.lines.index(metric_header)
    after_d_marker = False
    for row_index, row in enumerate(
        block.lines[metric_header_index + 1 :], metric_header_index + 1
    ):
        if re.fullmatch(r"\s*\(D\)\s*", row):
            after_d_marker = True
            continue
        if "positional embedding instead of sinusoids" in row:
            values = re.findall(r"\d+(?:\.\d+)?", row)
            subject = "Table 3 learned positional embedding variant"
            frames.append(
                _frame(
                    block,
                    subject,
                    "uses_positional_encoding",
                    "learned positional embeddings",
                    row,
                    headers,
                    row_index,
                )
            )
            if len(values) >= 2:
                frames.append(
                    _frame(
                        block,
                        subject,
                        "has_dev_perplexity",
                        values[-2],
                        row,
                        headers,
                        row_index,
                    )
                )
                frames.append(
                    _frame(
                        block,
                        subject,
                        "has_dev_bleu",
                        values[-1],
                        row,
                        headers,
                        row_index,
                    )
                )
            frames.append(
                _frame(
                    block,
                    subject,
                    "inherits_unlisted_settings_from",
                    "Table 3 base model",
                    row,
                    headers,
                    row_index,
                )
            )
            continue
        values = ["" for _ in starts]
        numbers = list(
            re.finditer(r"\d+(?:\.\d+)?(?:K)?", row[starts[0] - 4 :], re.I)
        )
        for number in numbers:
            absolute_start = starts[0] - 4 + number.start()
            column = min(range(len(starts)), key=lambda item: abs(starts[item] - absolute_start))
            values[column] = number.group()
        if after_d_marker and values[6] and not values[7]:
            values[7] = values[6]
            values[6] = ""
        label = re.sub(r"\([A-E]\)", "", row[: starts[0]]).strip()
        if label.casefold() == "big" and len(numbers) == 9:
            values = ["" for _ in starts]
            for column, number in zip(
                (0, 1, 2, 3, 6, 8, 9, 10, 11), numbers, strict=True
            ):
                values[column] = number.group()
        numeric_values = [value for value in values if re.search(r"\d", value)]
        if not numeric_values:
            continue
        configs = [
            f"{_slug(name)}={normalize_space(value)}"
            for name, value in zip(names[:8], values[:8], strict=True)
            if re.search(r"\d", value)
        ]
        if label.casefold() in {"base", "big"}:
            subject = f"Table 3 {label.casefold()} model"
        elif configs:
            subject = f"Table 3 variant {', '.join(configs)}"
        else:
            continue
        for name, value in zip(names, values, strict=True):
            if re.search(r"\d", value):
                frames.append(
                    _frame(block, subject, predicate_names[name], value, row, headers, row_index)
                )
        if label.casefold() not in {"base", "big"}:
            frames.append(
                _frame(
                    block,
                    subject,
                    "inherits_unlisted_settings_from",
                    "Table 3 base model",
                    row,
                    headers,
                    row_index,
                )
            )
    return frames


def _table_four(block: TableBlock) -> list[RelationFrame]:
    headers = "Parser | Training | WSJ Section 23 F1"
    frames: list[RelationFrame] = []
    pattern = re.compile(
        r"^\s*(?P<parser>.+?)\s+(?P<training>WSJ only, discriminative|"
        r"semi-supervised|multi-task|generative)\s+(?P<f1>\d+(?:\.\d+)?)\s*$"
    )
    for row_index, row in enumerate(block.lines):
        match = pattern.match(row)
        if not match:
            continue
        subject = re.sub(r"\s*\[\d+\]\s*", " ", match.group("parser")).strip()
        frames.append(
            _frame(
                block,
                subject,
                "uses_training_regime",
                match.group("training"),
                row,
                headers,
                row_index,
            )
        )
        frames.append(
            _frame(
                block,
                subject,
                "has_wsj_section_23_f1",
                match.group("f1"),
                row,
                headers,
                row_index,
            )
        )
    return frames


def _generic_table(block: TableBlock) -> list[RelationFrame]:
    candidates = [re.split(r"\s{2,}", line.strip()) for line in block.lines]
    header = next(
        (
            cells
            for cells in candidates
            if len(cells) >= 2
            and not any(_NUMBER.fullmatch(cell) for cell in cells)
        ),
        None,
    )
    if not header:
        return []
    frames: list[RelationFrame] = []
    headers = " | ".join(header)
    for row_index, (row, cells) in enumerate(zip(block.lines, candidates, strict=True)):
        if len(cells) != len(header) or not any(re.search(r"\d", cell) for cell in cells[1:]):
            continue
        for name, value in zip(header[1:], cells[1:], strict=True):
            if value:
                frames.append(
                    _frame(
                        block,
                        cells[0],
                        f"has_{_slug(name)}",
                        value,
                        row,
                        headers,
                        row_index,
                    )
                )
    return frames


def _table_frames(block: TableBlock) -> list[RelationFrame]:
    text = "\n".join(block.lines)
    if "Complexity per Layer" in text and "Maximum Path Length" in text:
        return _table_one(block)
    if "Training Cost (FLOPs)" in text and text.count("EN-DE") >= 2:
        return _table_two(block)
    if "dmodel" in text and "PPL" in text and "params" in text:
        return _table_three(block)
    if "WSJ 23 F1" in text:
        return _table_four(block)
    return _generic_table(block)


def _source_unit_at(text: str, position: int) -> str:
    prefix = text[:position]
    markers: list[tuple[int, str]] = []
    for match in _HEADING.finditer(prefix):
        if re.search(r"\d\s*$", match.group("title")):
            continue
        number = match.group("number").replace(".", "_")
        title = _slug(match.group("title")).upper()
        markers.append((match.start(), f"SECTION_{number}_{title}"))
    for match in re.finditer(r"(?m)^Abstract$", prefix):
        markers.append((match.start(), "ABSTRACT"))
    for match in re.finditer(
        r"(?im)^Appendix\s+(?P<letter>[A-Z])\.?"
        r"(?:\s+(?P<title>[^\n]{1,80}))?$",
        prefix,
    ):
        title = _slug(match.group("title") or "").upper()
        label = f"APPENDIX_{match.group('letter').upper()}"
        markers.append((match.start(), label + (f"_{title}" if title else "")))
    for match in re.finditer(
        r"(?im)^(References|Acknowledgements|Authors' Addresses|"
        r"Full Copyright Statement)$",
        prefix,
    ):
        markers.append((match.start(), _slug(match.group()).upper()))
    return max(markers, default=(0, "DOCUMENT"), key=lambda item: item[0])[1]


def _metric_frames(text: str, masked: str) -> list[RelationFrame]:
    """Extract explicit prose measurements that ordinary verb parsing keeps buried."""
    frames: list[RelationFrame] = []
    from .extract import clean_document

    prepared = clean_document(masked)
    position = 0
    sentences = re.split(
        r"(?<=[.!?])\s+(?=(?:[A-Z]|\d+(?:\.\d+)*\s+[A-Z]))", prepared
    )
    for sentence_index, sentence in enumerate(sentences):
        evidence = normalize_space(sentence)
        if not evidence:
            continue
        start = prepared.find(sentence, position)
        position = max(position, start + len(sentence))
        evidence = re.sub(
            r"^(?:\d+(?:\.\d+)*\s+[A-Z][A-Za-z-]*"
            r"(?:\s+[A-Z][A-Za-z-]*){0,8}\s+)+"
            r"(?=(?:On|The|Our|We|To|In)\b)",
            "",
            evidence,
        )
        for metric_index, metric in enumerate(_METRIC.finditer(evidence)):
            value = metric.group("value") or metric.group("value_after")
            metric_name = (metric.group("metric") or metric.group("metric_first")).casefold()
            verbs = list(re.finditer(
                r"\b(?:achieves?|establish(?:es|ing)?|reports?|yielding|has|"
                r"improv(?:e[sd]?|ing)|outperforms?)\b",
                evidence[: metric.start()],
                re.I,
            ))
            if not verbs:
                continue
            verb = verbs[-1]
            subject = evidence[: verbs[0].start()]
            subject = re.sub(r"^.*?,\s*", "", subject, flags=re.I)
            subject = re.sub(r"^(?:our|the|a|an)\s+", "", subject, flags=re.I)
            subject = canonical_entity(subject)
            if not subject or len(subject.split()) > 18:
                subject = "reported model"
            predicate = f"has_{metric_name}"
            if verb.group().casefold().startswith(("improv", "outperform")):
                predicate = f"improves_{metric_name}_by"
            frames.append(
                RelationFrame(
                    subject_options=(subject,),
                    predicate_options=(predicate,),
                    object_options=(value,),
                    evidence=evidence,
                    context=evidence,
                    sentence_index=2_000_000 + sentence_index * 10 + metric_index,
                    start=start,
                    end=start + len(sentence),
                    source_unit=_source_unit_at(prepared, start + metric.start()),
                    origin="measurement",
                )
            )
    return frames


def _assignment_frames(text: str, masked: str) -> list[RelationFrame]:
    frames: list[RelationFrame] = []
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])(?P<lhs>"
        r"(?:[A-Za-z][A-Za-z0-9_]*\s+)?[A-Za-z][A-Za-z0-9_]*\([^=\n]{1,40}\)|"
        r"[A-Za-zβϵεα][A-Za-z0-9_]{0,24})\s*=\s*"
        r"(?P<rhs>[+-]?\d[\d,]*(?:\.\d+)?(?:[eE][+-]?\d+)?|"
        r"(?:sin|cos|softmax|max|min)\([^\n=]{1,100}\)(?:\s*[A-Za-z])?)"
        r"(?![A-Za-z0-9_.*])"
    )
    for index, match in enumerate(pattern.finditer(masked)):
        lhs = normalize_space(match.group("lhs"))
        rhs = normalize_space(match.group("rhs"))
        line_start = masked.rfind("\n", 0, match.start()) + 1
        line_end = masked.find("\n", match.end())
        if line_end < 0:
            line_end = len(masked)
        evidence = normalize_space(masked[line_start:line_end])
        if not evidence or len(lhs.split()) > 5:
            continue
        frames.append(
            RelationFrame(
                subject_options=(lhs,),
                predicate_options=("equals",),
                object_options=(rhs,),
                evidence=evidence,
                context=evidence,
                sentence_index=3_000_000 + index,
                start=match.start(),
                end=match.end(),
                source_unit=_source_unit_at(masked, match.start()),
                source_locator="Equation or explicit assignment",
                source_page=text.count("\f", 0, min(match.start(), len(text))),
                origin="equation",
            )
        )
    return frames


def _quantity_frames(text: str, masked: str) -> list[RelationFrame]:
    """Turn explicit counts and durations into queryable typed measurements."""
    from .extract import clean_document

    prepared = clean_document(masked)
    sentences = re.split(
        r"(?<=[.!?])\s+(?=(?:[A-Z]|\d+(?:\.\d+)*\s+[A-Z]))", prepared
    )
    predicates = {
        "sentence pairs": "has_sentence_pair_count",
        "sentences": "has_sentence_count",
        "source tokens": "has_source_token_count",
        "target tokens": "has_target_token_count",
        "tokens": "has_token_count",
        "gpu": "uses_gpu_count",
        "gpus": "uses_gpu_count",
        "steps": "has_training_steps",
        "step": "has_training_steps",
        "hours": "has_training_duration_hours",
        "hour": "has_training_duration_hours",
        "days": "has_training_duration_days",
        "day": "has_training_duration_days",
        "seconds": "has_duration_seconds",
        "second": "has_duration_seconds",
        "minutes": "has_duration_minutes",
        "minute": "has_duration_minutes",
        "layers": "has_layer_count",
        "layer": "has_layer_count",
        "heads": "has_attention_head_count",
        "head": "has_attention_head_count",
    }
    frames: list[RelationFrame] = []
    position = 0

    def subject_for(prefix: str) -> str:
        lower = prefix.casefold()
        for phrase in (
            "english-french dataset",
            "english-german dataset",
            "training batch",
            "target vocabulary",
            "source-target vocabulary",
            "base models",
            "base model",
            "big models",
            "big model",
            "vocabulary",
            "decoder",
            "encoder",
            "model",
        ):
            if phrase in lower:
                return phrase
        explicit = re.match(
            r"(?P<subject>.+?)\s+(?:has|have|had|is|are|was|were|uses?|used|"
            r"contains?|contained|includes?|included|comprises?|comprised|"
            r"takes?|took|requires?|required|trains?|trained|runs?|ran|"
            r"lasts?|lasted)\b",
            normalize_space(prefix),
            re.I,
        )
        if explicit:
            subject = canonical_entity(explicit.group("subject"))
            if subject and len(subject.split()) <= 18:
                return subject
        return "reported system"

    for sentence_index, sentence in enumerate(sentences):
        evidence = normalize_space(sentence)
        if not evidence:
            continue
        start = prepared.find(sentence, position)
        position = max(position, start + len(sentence))
        for quantity_index, quantity in enumerate(_QUANTITY.finditer(evidence)):
            prefix = evidence[: quantity.start()]
            lower = prefix.casefold()
            subject = subject_for(prefix)
            unit = quantity.group("unit").casefold()
            predicate = predicates[unit]
            if unit.startswith("second") and "step" in lower:
                predicate = "has_step_duration_seconds"
            value = _clean_number(quantity.group("value"))
            frames.append(
                RelationFrame(
                    subject_options=(subject,),
                    predicate_options=(predicate,),
                    object_options=(value,),
                    evidence=evidence,
                    context=evidence,
                    sentence_index=4_000_000 + sentence_index * 10 + quantity_index,
                    start=start,
                    end=start + len(sentence),
                    source_unit=_source_unit_at(prepared, start + quantity.start()),
                    origin="measurement",
                )
            )
        for gpu_index, gpu in enumerate(_GPU_COUNT.finditer(evidence)):
            frames.append(
                RelationFrame(
                    subject_options=(subject_for(evidence[: gpu.start()]),),
                    predicate_options=("uses_gpu_count",),
                    object_options=(gpu.group("value"),),
                    evidence=evidence,
                    context=evidence,
                    sentence_index=4_500_000 + sentence_index * 10 + gpu_index,
                    start=start,
                    end=start + len(sentence),
                    source_unit=_source_unit_at(prepared, start + gpu.start()),
                    origin="measurement",
                )
            )
    return frames


def extract_structured_frames(text: str) -> list[RelationFrame]:
    blocks = table_blocks(text)
    masked = mask_table_bodies(text)
    frames = [frame for block in blocks for frame in _table_frames(block)]
    frames.extend(_assignment_frames(text, masked))
    frames.extend(_metric_frames(text, masked))
    frames.extend(_quantity_frames(text, masked))
    return frames
