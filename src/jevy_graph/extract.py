from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from .models import CandidateTriple, RelationFrame
from .normalize import (
    MAX_NODE_WORDS,
    canonical_entity,
    find_aliases,
    graphable_node,
    normalize_space,
    object_kind,
)
from .structured import extract_structured_frames, mask_table_bodies


@dataclass(frozen=True, slots=True)
class RelationPattern:
    expression: re.Pattern[str]
    predicates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RelationHit:
    start: int
    end: int
    predicates: tuple[str, ...]
    modality: str | None = None
    polarity: str = "positive"
    priority: int = 0


@dataclass(frozen=True, slots=True)
class Clause:
    text: str
    context: str
    sentence_index: int
    start: int
    end: int
    continuation: bool = False
    source_unit: str | None = None
    condition: str | None = None


_MODALS = r"shall|may|must|can|could|will|would|should"
_STATIC_RELATIONS: tuple[RelationPattern, ...] = (
    RelationPattern(
        re.compile(r"\b(?:has|have|had)\s+to\b", re.I),
        ("required_to",),
    ),
    RelationPattern(
        re.compile(
            r"\b(?:is|are|was|were)\s+based\s+(?:solely\s+|entirely\s+)?on\b",
            re.I,
        ),
        ("based_on",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?be\s+"
            r"Commander\s+in\s+Chief\s+of\b",
            re.I,
        ),
        ("commander_in_chief_of",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?:{_MODALS})\s+)?(?:not\s+)?(?:is|are|was|were|be\s+)?vested\s+in\b",
            re.I,
        ),
        ("vested_in",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?:{_MODALS})\s+)?(?:not\s+)?consists?\s+of\b", re.I
        ),
        ("consists_of",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?:{_MODALS})\s+)?(?:not\s+)?(?:is|are|was|were|be)\s+composed\s+of\b",
            re.I,
        ),
        ("composed_of",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?:{_MODALS})\s+)?(?:not\s+)?(?:is|are|was|were|be)\s+"
            r"(?:directly\s+)?(?:located|based)\s+in\b",
            re.I,
        ),
        ("located_in", "based_in"),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?:{_MODALS})\s+)?(?:not\s+)?(?:is|are|was|were|be)\s+part\s+of\b",
            re.I,
        ),
        ("part_of",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?have\s+"
            r"(?:(?:the\s+)?sole\s+)?power\s+to\b",
            re.I,
        ),
        ("authorized_to",),
    ),
    RelationPattern(
        re.compile(r"\bworks?\s+for\b", re.I),
        ("works_for", "employed_by"),
    ),
    RelationPattern(
        re.compile(r"\b(?:was|were)\s+founded\s+by\b", re.I),
        ("founded_by",),
    ),
    RelationPattern(
        re.compile(r"\b(?:was|were)\s+created\s+by\b", re.I),
        ("created_by",),
    ),
    RelationPattern(
        re.compile(r"\b(?:was|were)\s+acquired\s+by\b", re.I),
        ("acquired_by",),
    ),
    RelationPattern(
        re.compile(r"\b(?:acquires?|acquired|acquiring)\b", re.I),
        ("acquired", "purchased"),
    ),
    RelationPattern(
        re.compile(r"\b(?:activates?|activated|activating)\b", re.I),
        ("activates", "increases_activity_of"),
    ),
    RelationPattern(
        re.compile(r"\b(?:affects?|affected|affecting)\b", re.I),
        ("affects", "influences"),
    ),
    RelationPattern(
        re.compile(r"\b(?:causes?|caused|causing)\b", re.I),
        ("causes", "contributes_to"),
    ),
    RelationPattern(
        re.compile(r"\b(?:contains?|contained|containing)\b", re.I),
        ("contains", "includes"),
    ),
    RelationPattern(
        re.compile(r"\b(?:creates?|created|creating)\b", re.I),
        ("created", "produced"),
    ),
    RelationPattern(
        re.compile(r"\b(?:develops?|developed|developing)\b", re.I),
        ("developed", "created"),
    ),
    RelationPattern(
        re.compile(r"\b(?:employs?|employed|employing)\b", re.I),
        ("employs", "uses"),
    ),
    RelationPattern(
        re.compile(r"\b(?:founds?|founded|founding)\b", re.I),
        ("founded", "created"),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?)?"
            r"(?:has|have|had)\b(?!\s+(?:been|become|becomes|becoming|[A-Za-z'-]+(?:ed|en))\b)",
            re.I,
        ),
        ("has", "possesses", "authorized_to"),
    ),
    RelationPattern(
        re.compile(r"\b(?:inhibits?|inhibited|inhibiting)\b", re.I),
        ("inhibits", "decreases_activity_of"),
    ),
    RelationPattern(
        re.compile(r"\b(?:knows?|knew)\b", re.I),
        ("knows", "aware_of"),
    ),
    RelationPattern(
        re.compile(r"\b(?:owns?|owned|owning)\b", re.I),
        ("owns", "possesses"),
    ),
    RelationPattern(
        re.compile(r"\b(?:produces?|produced|producing)\b", re.I),
        ("produces", "creates"),
    ),
    RelationPattern(
        re.compile(r"\b(?:provides?|provided|providing)\b", re.I),
        ("provides", "supplies"),
    ),
    RelationPattern(
        re.compile(r"\b(?:requires?|required|requiring)\b", re.I),
        ("requires", "depends_on"),
    ),
    RelationPattern(
        re.compile(r"\b(?:supports?|supported|supporting)\b", re.I),
        ("supports", "enables"),
    ),
    RelationPattern(
        re.compile(r"\b(?:uses?|used|using)\b", re.I),
        ("uses", "applies", "used_with", "used_for", "encoded_with"),
    ),
)

_PASSIVE = re.compile(
    rf"\b(?:(?P<modal>{_MODALS})\s+)?(?P<negative>not\s+)?"
    r"(?:is|are|was|were|be)\s+(?:(?:also|hereby|thereby|otherwise)\s+)*"
    r"(?P<verb>vested|composed|chosen|elected|appointed|removed|divided|"
    r"determined|made|passed|held|admitted|prohibited|deprived|required|"
    r"provided|established|called|accused|convicted|attainted|questioned|"
    r"diminished|increased|denied|abridged|construed|taxed|vacated|entitled|"
    r"apportioned|bound|directed|obliged|presented|approved|disapproved|entered|"
    r"reconsidered|sent|published|suspended|assembled|infringed|repealed|"
    r"imposed|inflicted|discharged|assumed|paid|enforced|executed|counted|"
    r"compelled|taken|subjected|formed|erected|joined|obliged|given)"
    r"(?:\s+(?P<prep>in|by|of|to|from|into|upon|on|with|for|as))?\b",
    re.I,
)
_PERFECT_MODAL = re.compile(
    rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?have\s+"
    r"(?P<verb>[A-Za-z][A-Za-z'-]*(?:ed|en))"
    r"(?:\s+(?P<prep>in|by|of|to|from|into|upon|on|with|for|as))?\b",
    re.I,
)
_MODAL_ACTIVE = re.compile(
    rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?"
    r"(?:(?:then|also|thereupon|immediately|by\s+law)\s+){0,2}"
    r"(?P<verb>[A-Za-z][A-Za-z'-]*)"
    r"(?:\s+(?:only\s+)?(?P<prep>in|of|to|by|from|with|for|on|at))?\b",
    re.I,
)
_MODAL_COPULA_BARE = re.compile(
    rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?be\s+"
    r"(?=(?-i:[A-Z])[A-Za-z'-]*\b)",
    re.I,
)
_TYPE_RELATION = re.compile(r"\b(?:is|are|was|were)\s+(?:an?|the)\b", re.I)
_MODAL_TYPE = re.compile(
    rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?"
    r"(?:,\s*[^,]{1,60},\s*)?be\s+(?:an?|the)\b",
    re.I,
)
_GENERIC_ACTIVE = re.compile(
    r"\b(?P<verb>[A-Za-z][A-Za-z'-]*(?:ed|ing|ates|izes|ifies|ects|uces|"
    r"ains|ires))"
    r"(?:\s+(?P<prep>in|on|by|of|to|from|into|upon|with|for|as|around))?\b",
    re.I,
)
_RIGHT_TO = re.compile(
    r"\b(?:the\s+)?right\s+of\s+(?P<holder>.+?)"
    r"(?:\s+[A-Za-z'-]+ly)?\s+to\s+(?P<actions>.+?)"
    rf"(?=(?:,\s*|\s+)(?:{_MODALS})\b|[.;]|$)",
    re.I,
)
_PURPOSE = re.compile(
    r"^(?P<subject>.+?)\s+in\s+[Oo]rder\s+to\s+(?P<purposes>.+?),\s*"
    r"do\s+(?P<declaration>ordain\s+and\s+establish)\s+(?P<object>.+)$",
    re.I,
)
_NECESSARY_TO = re.compile(
    r"^(?P<subject>[^,]+),\s*being\s+necessary\s+to\s+(?P<object>[^,]+)",
    re.I,
)
_NO_LAW = re.compile(
    rf"^(?P<subject>.+?)\s+(?P<modal>{_MODALS})\s+make\s+no\s+law\s+"
    r"respecting\s+(?P<respecting>.+?)(?:,\s*or\s+prohibiting\s+"
    r"(?P<prohibiting>.+))?$",
    re.I,
)
_NEITHER_EXISTS = re.compile(
    r"^Neither\s+(?P<first>.+?)\s+nor\s+(?P<second>.+?)"
    r"(?:,\s*except\s+(?P<exception>.+?))?,\s*"
    rf"(?P<modal>{_MODALS})\s+(?P<verb>exist|remain|apply)\s+"
    r"(?P<object>.+)$",
    re.I,
)
_ENJOYS_RIGHT = re.compile(
    rf"^(?P<holder>.+?)\s+(?P<modal>{_MODALS})\s+(?:enjoy|retain|have)\s+"
    r"(?:the\s+)?right\s+to\s+(?P<actions>.+)$",
    re.I,
)
_CONSTRUED_TO = re.compile(
    rf"^(?P<subject>.+?)\s+(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?be\s+"
    r"construed\s+to\s+(?P<actions>.+)$",
    re.I,
)
_WARRANT_RULE = re.compile(
    rf"(?P<subject>[^,;]+?)\s+(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?issue"
    r"(?P<requirements>.+)$",
    re.I,
)
_NOMINAL_PROHIBITION = re.compile(
    r"^(?P<subject>.+?)\s+(?:is|are|was|were)\s+"
    r"(?:(?:hereby|thereby)\s+)*(?P<verb>prohibited|repealed)"
    r"(?:\s+(?P<prep>in|into|from|by|to|within)\s+(?P<object>.+?))?\.?$",
    re.I,
)
_MODAL_ACTION_LIST = re.compile(
    rf"^(?P<subject>.+?)\s+(?P<modal>{_MODALS})\s*,?\s*"
    r"(?P<actions>.+)$",
    re.I,
)
_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n|$)")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’./+_-]*")
_CAPITALIZED = re.compile(
    r"\b[A-Z][A-Za-z0-9'’_-]*(?:\s+[A-Z][A-Za-z0-9'’_-]*){0,6}\b"
)
_LEADING = re.compile(
    r"^(?:however|therefore|then|also|instead|accordingly|according to [^,]+),?\s*",
    re.I,
)
_TRAILING_AUXILIARY = re.compile(
    rf"\s+(?:(?:do|does|did|{_MODALS}|has|have|had|is|are|was|were|be|been|being)"
    r"(?:\s+not|\s+n't)?|not)$",
    re.I,
)
_TRAILING_FUNCTION_WORD = re.compile(
    r"\s+(?:a|an|the|and|or|to|of|in|on|for|with|by|from)$", re.I
)
_LEADING_COMPLEMENT = re.compile(
    r"^(?:(?:in\s+)?conjunction\s+with|with|to|of|in|on|for|by|from|as)\s+",
    re.I,
)
_PRONOUN = re.compile(
    r"^(?:he|she|it|they|this|that|these|those|which|who)$", re.I
)
_BAD_ENTITY = re.compile(
    r"^(?:he|she|it|they|we|i|you|this|that|these|those|who|which|there)$",
    re.I,
)
_BAD_STANDALONE = re.compile(
    rf"^(?:a|an|the|and|or|to|of|in|on|for|with|by|from|{_MODALS}|"
    r"is|are|was|were|be|been|being|first|second|third|another|one|all|each|"
    r"previously|highly|different|usual|as|when|before|after|only|left|right)$",
    re.I,
)
_BAD_ENTITY_START = re.compile(
    rf"^(?:{_MODALS}|do|does|did|is|are|was|were|be|been|being|previously|"
    r"highly|usually|typically|when|before|after|as|if|unless|hereunto|"
    r"therein|thereof|whereof|here|once|yet)\b|"
    r"^(?:in\s+fact|for\s+(?:example|instance)|about\s+in\s+all\s+directions)\b|"
    r"^(?:left|right)\s*\)",
    re.I,
)
_GENERIC_VERB_STOP = {
    "united",
    "states",
    "representatives",
    "years",
    "members",
    "powers",
    "rights",
    "amendments",
    "persons",
    "things",
    "proceedings",
    "buildings",
    "according",
    "including",
    "excluding",
    "following",
    "during",
    "being",
    "hundred",
    "regulated",
}
_MODAL_VERB_STOP = {
    "after",
    "any",
    "at",
    "before",
    "by",
    "during",
    "for",
    "from",
    "hereafter",
    "if",
    "in",
    "nevertheless",
    "of",
    "on",
    "otherwise",
    "thereafter",
    "therein",
    "thereof",
    "thereupon",
    "to",
    "unless",
    "when",
    "where",
    "with",
}
_IRREGULAR_VERBS = {
    "has": "has",
    "have": "has",
    "had": "has",
    "be": "type",
    "chuse": "chooses",
    "choose": "chooses",
    "chosen": "chosen_by",
    "made": "makes",
    "make": "makes",
    "laid": "lays",
    "lay": "lays",
    "held": "holds",
    "hold": "holds",
    "met": "meets",
    "meet": "meets",
    "paid": "pays",
    "pay": "pays",
    "receive": "receives",
    "consist": "consists_of",
    "appoint": "appoints",
    "nominate": "nominates",
    "establish": "establishes",
    "ordain": "ordains",
    "direct": "directs",
    "declare": "declares",
    "provide": "provides",
    "borrow": "borrows",
    "regulate": "regulates",
    "coin": "coins",
    "punish": "punishes",
    "define": "defines",
    "exercise": "exercises",
    "issue": "issues",
    "fill": "fills",
    "sign": "signs",
    "vote": "votes",
    "return": "returns",
    "pass": "passes",
    "originate": "originates",
    "extend": "extends_to",
    "having": "has",
    "chusing": "chooses",
    "taking": "takes",
    "take": "takes",
    "acting": "acts",
    "voting": "votes",
    "holding": "holds",
    "implemented": "implements",
    "designed": "designs",
    "evaluated": "evaluates",
    "experimented": "experiments_with",
    "replaced": "replaces",
    "reduced": "reduces",
    "computed": "computes",
    "optimized": "optimizes",
    "generated": "generates",
    "depicted": "depicted_in",
    "applied": "applied_to",
    "centered": "centered_around",
    "averaged": "averaged",
    "compared": "compared_to",
    "trained": "trained",
    "described": "described_in",
    "represented": "represented_as",
    "running": "runs",
    "using": "uses",
    "replacing": "replaces",
    "improving": "improves",
    "involving": "involves",
    "setting": "sets",
    "encoding": "encodes",
    "making": "makes",
    "parsing": "parses",
    "embedding": "embeds",
    "computing": "computes",
    "beginning": "begins",
    "reducing": "reduces",
    "averaging": "averages",
    "relating": "relates_to",
    "consisting": "consists_of",
    "abridging": "abridges",
    "denying": "denies",
    "giving": "gives",
    "imposing": "imposes",
    "inflicting": "inflicts",
    "prohibiting": "prohibits",
    "respecting": "respects",
    "receiving": "receives",
    "arising": "arises_from",
    "invading": "invades",
    "occurring": "occurs",
    "tumbling": "tumbles",
}
_ACTION_VERBS = {
    "appoint",
    "borrow",
    "call",
    "coin",
    "collect",
    "constitute",
    "declare",
    "define",
    "dispose",
    "establish",
    "exercise",
    "fix",
    "govern",
    "grant",
    "lay",
    "maintain",
    "make",
    "organize",
    "pay",
    "promote",
    "provide",
    "punish",
    "raise",
    "regulate",
    "support",
    "bear",
    "form",
    "insure",
    "keep",
    "petition",
    "assemble",
    "secure",
    "execute",
    "suppress",
    "repel",
    "arm",
    "discipline",
    "train",
    "emit",
    "enter",
    "engage",
    "accept",
    "publish",
    "prescribe",
    "pass",
}


def _action_phrases(value: str) -> tuple[str, ...]:
    """Split coordinated action phrases while retaining each verb."""
    verbs = "|".join(sorted(_ACTION_VERBS, key=len, reverse=True))
    shared_object = re.fullmatch(
        rf"(?P<first>{verbs})\s+and\s+(?P<second>{verbs})\s+(?P<object>.+)",
        normalize_space(value).strip(" ,"),
        re.I,
    )
    if shared_object:
        object_ = shared_object.group("object").strip(" ,")
        return (
            f"{shared_object.group('first')} {object_}",
            f"{shared_object.group('second')} {object_}",
        )
    matches = list(
        re.finditer(
            rf"(?:^|,\s*|\s+and\s+|\s+or\s+)(?:to\s+)?"
            rf"(?P<verb>{verbs})\b",
            normalize_space(value),
            re.I,
        )
    )
    if not matches:
        return ()
    phrases: list[str] = []
    normalized = normalize_space(value)
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        phrase = normalize_space(f"{match.group('verb')} {normalized[match.end():end]}")
        phrase = re.sub(r"(?:,|\b(?:and|or))\s*$", "", phrase, flags=re.I).strip()
        if phrase:
            phrases.append(phrase)
    return tuple(phrases)


def _gerund_base(value: str) -> str:
    irregular = {
        "arming": "arm",
        "disciplining": "discipline",
        "governing": "govern",
        "organizing": "organize",
    }
    word = value.casefold()
    if word in irregular:
        return irregular[word]
    stem = word[:-3] if word.endswith("ing") else word
    if len(stem) > 2 and stem[-1:] == stem[-2:-1]:
        stem = stem[:-1]
    if stem.endswith(("at", "iz", "lin")):
        stem += "e"
    return stem


def _compact_action(value: str) -> str:
    """Remove subordinate detail while preserving the main action boundary."""
    value = normalize_space(value).strip(" ,")
    value = re.sub(r"\([^()]*\)", "", value)
    value = re.split(
        r"\s+(?=(?:as\s+(?:may|shall|must|can|could|will|would|should)|"
        r"(?:purchased|chosen|employed|prescribed|required)\s+by)\b)",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    value = re.split(
        r",\s*(?=(?:by|reserving|provided|except|unless|which|who|that)\b)",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    return canonical_entity(value)


def _compact_authority_actions(value: str) -> tuple[str, ...]:
    """Atomize long power clauses into compact action-valued graph nodes."""
    value = normalize_space(value).strip(" ,")
    punishment = re.match(
        r"^provide\s+for\s+(?:the\s+)?Punishment\s+of\s+(?P<object>.+)$",
        value,
        re.I,
    )
    if punishment:
        action = f"punish {canonical_entity(punishment.group('object'))}"
        return (action,) if graphable_node(action) else ()

    gerunds = re.match(
        r"^provide\s+for\s+"
        r"(?P<gerunds>[A-Za-z'-]+ing(?:\s*,\s*[A-Za-z'-]+ing)*"
        r"\s*,?\s*and\s+[A-Za-z'-]+ing)\s*,\s*"
        r"(?P<object>[^,]+)(?P<tail>.*)$",
        value,
        re.I,
    )
    if gerunds:
        object_ = canonical_entity(gerunds.group("object"))
        actions = [
            f"{_gerund_base(word)} {object_}"
            for word in re.findall(r"[A-Za-z'-]+ing", gerunds.group("gerunds"), re.I)
        ]
        governing = re.search(
            r"\band\s+for\s+(?P<verb>[A-Za-z'-]+ing)\s+"
            r"(?P<object>.+?)(?=\s+as\s+(?:may|shall)\b|,|$)",
            gerunds.group("tail"),
            re.I,
        )
        if governing:
            governed = canonical_entity(governing.group("object"))
            if re.fullmatch(r"(?:such\s+)?Part\s+of\s+them", governed, re.I):
                governed = f"part of {object_}"
            actions.append(f"{_gerund_base(governing.group('verb'))} {governed}")
        return tuple(action for action in actions if graphable_node(action))

    shared_verb = re.match(
        r"^(?P<verb>[A-Za-z'-]+)\s+(?P<first>[^,]+),\s*and\s+"
        r"(?P<second>.+)$",
        value,
        re.I,
    )
    if shared_verb and not re.match(
        r"(?:to\s+)?(?:" + "|".join(sorted(_ACTION_VERBS)) + r")\b",
        shared_verb.group("second"),
        re.I,
    ):
        actions = tuple(
            _compact_action(f"{shared_verb.group('verb')} {object_}")
            for object_ in (shared_verb.group("first"), shared_verb.group("second"))
        )
        if all(graphable_node(action) for action in actions):
            return actions

    compact = _compact_action(value)
    return (compact,) if graphable_node(compact) else ()


def _right_actions(value: str) -> tuple[str, ...]:
    """Atomize common coordinated right descriptions."""
    value = normalize_space(value).strip(" ,")
    explicit_actions = _action_phrases(value)
    if explicit_actions:
        return explicit_actions
    secure = re.match(
        r"be\s+secure\s+in\s+(?P<items>.+?),\s*against\s+(?P<threat>.+)$",
        value,
        re.I,
    )
    if secure:
        items = [
            canonical_entity(re.sub(r"^(?:and|or)\s+", "", item, flags=re.I))
            for item in re.split(r"\s*,\s*|\s+and\s+|\s+or\s+", secure.group("items"), flags=re.I)
            if canonical_entity(re.sub(r"^(?:and|or)\s+", "", item, flags=re.I))
        ]
        return tuple(
            f"be secure in {item} against {secure.group('threat')}" for item in items
        )

    actions: list[str] = []
    paired = re.match(
        r"(?:an?\s+)?(?P<first>[A-Za-z'-]+)\s+and\s+"
        r"(?P<second>[A-Za-z'-]+)\s+(?P<noun>[A-Za-z'-]+)",
        value,
        re.I,
    )
    if paired:
        actions.extend(
            (
                f"{paired.group('first')} {paired.group('noun')}",
                f"{paired.group('second')} {paired.group('noun')}",
            )
        )
    jury = re.search(r"\bby\s+(?:an?\s+)?(?P<jury>[^,]+)", value, re.I)
    if jury:
        actions.append(jury.group("jury"))
    actions.extend(
        normalize_space(match.group(1))
        for match in re.finditer(
            r"(?:^|,\s*(?:and\s+)?|\s+and\s+)to\s+"
            r"(.+?)(?=,\s*(?:and\s+)?to\s+|$)",
            value,
            re.I,
        )
    )
    return tuple(dict.fromkeys(action for action in actions if action)) or (value,)


def clean_document(text: str) -> str:
    """Remove common PDF extraction noise while preserving paragraph boundaries."""
    gutenberg_start = re.search(
        r"(?m)^\*{3}\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*$",
        text,
        re.I,
    )
    if gutenberg_start:
        gutenberg_end = re.search(
            r"(?m)^\*{3}\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*$",
            text[gutenberg_start.end() :],
            re.I,
        )
        end = (
            gutenberg_start.end() + gutenberg_end.start()
            if gutenberg_end
            else len(text)
        )
        text = text[gutenberg_start.end() : end]
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"(?<=[a-z])-\s+(?=[a-z])", "", text)
    raw_lines = [normalize_space(line.replace("\f", "")) for line in text.splitlines()]
    counts = Counter(line.casefold() for line in raw_lines if line)
    lines: list[str] = []
    for line in raw_lines:
        repeated_header = (
            line
            and counts[line.casefold()] >= 3
            and (
                line.isupper()
                or "literal print" in line.casefold()
                or bool(re.search(r"\brfc\s+\d+\b", line, re.I))
                or "standards track [page" in line.casefold()
            )
        )
        if re.fullmatch(r"\d{1,4}", line) or repeated_header:
            continue
        lines.append(line)

    stitched_lines: list[str] = []
    line_index = 0
    while line_index < len(lines):
        line = lines[line_index]
        standalone_number = re.fullmatch(r"(\d+(?:\.\d+)*)\.", line)
        if standalone_number:
            next_index = line_index + 1
            while next_index < len(lines) and not lines[next_index]:
                next_index += 1
            if (
                next_index < len(lines)
                and re.fullmatch(r"[A-Z][^.!?]{1,80}", lines[next_index])
            ):
                stitched_lines.append(
                    f"{standalone_number.group(1)}. {lines[next_index]}"
                )
                line_index = next_index + 1
                continue
        stitched_lines.append(line)
        line_index += 1

    paragraphs: list[str] = []
    current: list[str] = []
    heading = re.compile(
        r"^(?:Abstract|Acknowledgements|References|"
        r"Authors' Addresses|Full Copyright Statement|"
        r"Appendix\s+[A-Z]\.?(?:\s+[^\n]{1,80})?|"
        r"\d+(?:\.\d+)*\.?\s+[A-Z][^\n]{1,80}|"
        r"CHAPTER\s+[IVXLC]+\.?(?:\s+[^\n]{1,80})?)$",
        re.I,
    )
    for line in stitched_lines:
        if line and heading.fullmatch(line):
            if current:
                paragraphs.append(normalize_space(" ".join(current)))
                current = []
            paragraphs.append(line)
            continue
        if line:
            current.append(line)
        elif current:
            paragraphs.append(normalize_space(" ".join(current)))
            current = []
    if current:
        paragraphs.append(normalize_space(" ".join(current)))
    merged: list[str] = []
    for paragraph in paragraphs:
        if (
            merged
            and not re.search(r"[.!?:;][\"'”’)]?$", merged[-1])
            and re.match(r"[a-z]", paragraph)
        ):
            merged[-1] = f"{merged[-1]} {paragraph}"
        else:
            merged.append(paragraph)
    return "\n".join(merged)


def _roman_number(value: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = previous = 0
    for character in reversed(value.upper()):
        current = values[character]
        total += -current if current < previous else current
        previous = max(previous, current)
    return total


def _source_markers(text: str) -> list[tuple[int, str]]:
    """Infer document-local provision labels without assuming a legal schema."""
    markers: list[tuple[int, str]] = [(-1, "DOCUMENT")]
    article: int | None = None
    amendment: int | None = None
    expression = re.compile(
        r"(?i)\bArticle\.\s*([IVXLC]+)\.|"
        r"\bAmendment\s+([IVXLC]+)\.|"
        r"\bSection\.\s*(\d+)\.|\bSection\s+(\d+)\."
    )
    for match in expression.finditer(text):
        if match.group(1):
            article = _roman_number(match.group(1))
            amendment = None
            label = f"ARTICLE_{article}"
        elif match.group(2):
            amendment = _roman_number(match.group(2))
            article = None
            label = f"AMENDMENT_{amendment}"
        else:
            section = int(match.group(3) or match.group(4))
            if article is None and amendment is None:
                continue
            parent = (
                f"ARTICLE_{article}"
                if article is not None
                else f"AMENDMENT_{amendment}"
            )
            label = f"{parent}_SECTION_{section}"
        markers.append((match.start(), label))
    for match in re.finditer(
        r"(?m)^(Abstract|(?P<number>(?!0\d)\d{1,3}(?:\.\d{1,3})*)\.?\s+"
        r"(?P<title>[A-Z][^\n]{1,80})|"
        r"CHAPTER\s+(?P<chapter>[IVXLC]+)\.?(?:\s+(?P<chapter_title>[^\n]{1,80}))?|"
        r"Appendix\s+(?P<appendix>[A-Z])\.?(?:\s+(?P<appendix_title>[^\n]{1,80}))?|"
        r"(?P<named>References|Acknowledgements|Authors' Addresses|"
        r"Full Copyright Statement))$",
        text,
        re.I,
    ):
        if match.group(1).casefold() == "abstract":
            label = "ABSTRACT"
        elif match.group("chapter"):
            chapter = _roman_number(match.group("chapter"))
            title = re.sub(
                r"[^A-Z0-9]+",
                "_",
                (match.group("chapter_title") or "").upper(),
            ).strip("_")
            label = f"CHAPTER_{chapter}" + (f"_{title}" if title else "")
        elif match.group("appendix"):
            title = re.sub(
                r"[^A-Z0-9]+",
                "_",
                (match.group("appendix_title") or "").upper(),
            ).strip("_")
            label = f"APPENDIX_{match.group('appendix').upper()}" + (
                f"_{title}" if title else ""
            )
        elif match.group("named"):
            label = re.sub(
                r"[^A-Z0-9]+", "_", match.group("named").upper()
            ).strip("_")
        else:
            if re.search(r"\d\s*$", match.group("title")):
                continue
            number = match.group("number").replace(".", "_")
            title = re.sub(
                r"[^A-Z0-9]+", "_", match.group("title").upper()
            ).strip("_")
            label = f"SECTION_{number}_{title}"
        markers.append((match.start(), label))
    markers.sort()
    return markers


def _condition(value: str) -> str | None:
    conditions: list[str] = []
    leading = re.match(
        r"^(?P<condition>(?:if|when|whenever|unless|until|after|before)\b.+?),\s*",
        value,
        re.I,
    )
    if leading:
        conditions.append(normalize_space(leading.group("condition")))
    for match in re.finditer(
        r"(?:,|;)\s*(?P<condition>(?:unless|except|provided\s+that|"
        r"on\s+condition\s+that|without)\b.+?)(?=;|$)",
        value,
        re.I,
    ):
        conditions.append(normalize_space(match.group("condition")))
    return "; ".join(dict.fromkeys(conditions)) or None


def _clauses(text: str) -> list[Clause]:
    prepared = clean_document(text)
    markers = _source_markers(prepared)
    clauses: list[Clause] = []
    sentence_index = 0
    for sentence_match in _SENTENCE.finditer(prepared):
        sentence = normalize_space(sentence_match.group())
        if not sentence:
            continue
        parts = list(re.finditer(r"(?:^|;|—)\s*([^;—]+)", sentence))
        for part_index, part in enumerate(parts):
            clause = normalize_space(part.group(1))
            if not clause:
                continue
            clauses.append(
                Clause(
                    text=clause,
                    context=sentence,
                    sentence_index=sentence_index,
                    start=sentence_match.start() + part.start(1),
                    end=sentence_match.start() + part.end(1),
                    continuation=part_index > 0,
                    source_unit=max(
                        (item for item in markers if item[0] <= sentence_match.start()),
                        key=lambda item: item[0],
                    )[1],
                    condition=_condition(sentence),
                )
            )
        sentence_index += 1
    return clauses


def _modal_and_polarity(value: str) -> tuple[str | None, str]:
    modal_match = re.search(rf"\b({_MODALS})\b", value, re.I)
    negative = bool(re.search(r"\b(?:not|never|no)\b", value, re.I))
    return (
        modal_match.group(1).casefold() if modal_match else None,
        "negative" if negative else "positive",
    )


def _predicate_for(verb: str, prep: str | None = None) -> str:
    word = verb.casefold().replace("’", "'")
    predicate = _IRREGULAR_VERBS.get(word)
    if predicate is None:
        if word.endswith("ing"):
            predicate = word[:-3] or word
            if len(predicate) > 2 and predicate[-1] == predicate[-2]:
                predicate = predicate[:-1]
            elif predicate.endswith(("at", "iz", "ur", "crib", "clud")):
                predicate += "e"
        else:
            predicate = word
    if word in {"consist", "consists"} and prep:
        predicate = f"consists_{prep.casefold()}"
        prep = None
    predicate = re.sub(r"[^a-z0-9]+", "_", predicate).strip("_")
    if prep and not predicate.endswith(f"_{prep.casefold()}"):
        predicate = f"{predicate}_{prep.casefold()}"
    return predicate


def _overlaps(hit: RelationHit, accepted: list[RelationHit]) -> bool:
    return any(hit.start < other.end and other.start < hit.end for other in accepted)


def _relation_hits(clause: str) -> list[RelationHit]:
    proposed: list[RelationHit] = []
    for pattern in _STATIC_RELATIONS:
        for match in pattern.expression.finditer(clause):
            modality, polarity = _modal_and_polarity(match.group())
            if modality is None:
                prefix = re.search(
                    rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?$",
                    clause[: match.start()],
                    re.I,
                )
                if prefix:
                    modality = prefix.group("modal").casefold()
                    polarity = "negative" if prefix.group("negative") else "positive"
            proposed.append(
                RelationHit(
                    match.start(),
                    match.end(),
                    pattern.predicates,
                    modality,
                    polarity,
                    4,
                )
            )
    for match in _PASSIVE.finditer(clause):
        predicate = _predicate_for(match.group("verb"), match.group("prep"))
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                (predicate,),
                match.group("modal").casefold() if match.group("modal") else None,
                "negative" if match.group("negative") else "positive",
                3,
            )
        )
    for match in _PERFECT_MODAL.finditer(clause):
        if match.group("verb").casefold() == "been":
            continue
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                (_predicate_for(match.group("verb"), match.group("prep")),),
                match.group("modal").casefold(),
                "negative" if match.group("negative") else "positive",
                3,
            )
        )
    for match in _MODAL_TYPE.finditer(clause):
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                ("type",),
                match.group("modal").casefold(),
                "negative" if match.group("negative") else "positive",
                3,
            )
        )
    for match in _MODAL_COPULA_BARE.finditer(clause):
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                ("type",),
                match.group("modal").casefold(),
                "negative" if match.group("negative") else "positive",
                2,
            )
        )
    for match in _TYPE_RELATION.finditer(clause):
        proposed.append(
            RelationHit(
                match.start(), match.end(), ("type", "equivalent_to"), priority=2
            )
        )
    for match in _MODAL_ACTIVE.finditer(clause):
        verb = match.group("verb")
        if (
            len(verb) < 3
            or verb.casefold() == "be"
            or verb.casefold() in _MODAL_VERB_STOP
        ):
            continue
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                (_predicate_for(verb, match.group("prep")),),
                match.group("modal").casefold(),
                "negative" if match.group("negative") else "positive",
                2,
            )
        )
    for match in _GENERIC_ACTIVE.finditer(clause):
        verb = match.group("verb")
        predicate = _predicate_for(verb, match.group("prep"))
        followed_by_relation = re.match(
            rf"\s+(?:(?:{_MODALS})\b|(?:is|are|was|were)\b)",
            clause[match.end() :],
            re.I,
        )
        inside_hyphenated_word = (
            (match.start() > 0 and clause[match.start() - 1] == "-")
            or (match.end() < len(clause) and clause[match.end()] == "-")
        )
        if (
            verb.casefold() in _GENERIC_VERB_STOP
            or len(predicate) < 3
            or (verb[0].isupper() and match.start() > 0)
            or followed_by_relation
            or inside_hyphenated_word
        ):
            continue
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                (predicate,),
                priority=1,
            )
        )

    accepted: list[RelationHit] = []
    for hit in sorted(
        proposed,
        key=lambda item: (-item.priority, item.start, -(item.end - item.start)),
    ):
        if not _overlaps(hit, accepted):
            accepted.append(hit)
    ordered = sorted(accepted, key=lambda item: item.start)
    filtered: list[RelationHit] = []
    for hit in ordered:
        gap = clause[filtered[-1].end : hit.start] if filtered else ""
        if (
            hit.priority == 1
            and filtered
            and (filtered[-1].modality or filtered[-1].priority >= 4)
            and re.fullmatch(r"\s*(?:a|an|the)?\s*", gap, re.I)
        ):
            continue
        filtered.append(hit)
    return filtered


def _trim_left(value: str) -> str:
    value = _LEADING.sub("", normalize_space(value))
    value = re.sub(
        r"^(?:if|when|whenever|unless|until|after|before)\b[^,]*,\s*",
        "",
        value,
        flags=re.I,
    )
    value = re.split(r"[;:]", value)[-1]
    value = re.split(r"\b(?:and|but)\b", value, flags=re.I)[-1]
    value = _TRAILING_AUXILIARY.sub("", value)
    value = re.sub(r",?\s+(?:which|who)$", "", value, flags=re.I)
    return canonical_entity(value)


def _trim_right(value: str) -> str:
    value = normalize_space(value)
    value = re.split(
        r"[;:]|\b(?:but|because|although|while|when)\b",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    value = re.split(r",\s*(?:which|who)\b", value, maxsplit=1, flags=re.I)[0]
    value = re.split(
        rf"\s+(?:who|which|that)\s+(?:{_MODALS}|has|have|is|are)\b",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    return canonical_entity(value)


@lru_cache(maxsize=131_072)
def _valid_entity(value: str) -> bool:
    canonical = canonical_entity(value)
    if not value or not canonical or _BAD_ENTITY.fullmatch(value):
        return False
    words = value.split()
    canonical_words = canonical.split()
    return (
        graphable_node(canonical)
        and not (len(words) == 1 and _BAD_STANDALONE.fullmatch(value))
        and not (
            len(canonical_words) == 1
            and _BAD_STANDALONE.fullmatch(canonical_words[0])
        )
        and not (
            _BAD_ENTITY.fullmatch(words[0])
            and not re.match(r"^we\s+the\b", value, re.I)
        )
        and not _BAD_ENTITY.fullmatch(words[-1])
        and not _BAD_ENTITY_START.match(value)
        and any(character.isalnum() for character in value)
    )


def _unique(values: list[str], limit: int = 64) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = normalize_space(value).strip(" \t\n\r.,;:!?()[]{}\"'“”‘’")
        key = canonical_entity(value).casefold()
        if not key or key in seen or not _valid_entity(value):
            continue
        seen.add(key)
        result.append(value)
        if len(result) == limit:
            break
    return tuple(result)


def _tokens(value: str) -> list[str]:
    return _TOKEN.findall(value)


def _subject_options(
    value: str,
    aliases: dict[str, str],
    context_entities: tuple[str, ...],
) -> tuple[str, ...]:
    primary = _trim_left(value)
    values = [canonical_entity(primary, aliases)]
    segment = re.split(
        r"[,;:]|\b(?:and|but)\b", normalize_space(value), flags=re.I
    )[-1]
    tokens = _tokens(segment)
    values.extend(
        canonical_entity(match.group(), aliases)
        for match in _CAPITALIZED.finditer(value)
    )
    for width in range(min(14, len(tokens)), 0, -1):
        phrase = " ".join(tokens[-width:])
        values.extend((phrase, canonical_entity(phrase, aliases)))
        without_auxiliary = _TRAILING_AUXILIARY.sub("", phrase)
        values.extend(
            (without_auxiliary, canonical_entity(without_auxiliary, aliases))
        )
    for width in range(1, min(8, len(tokens)) + 1):
        for offset in range(len(tokens) - width + 1):
            phrase = " ".join(tokens[offset : offset + width])
            values.extend((phrase, canonical_entity(phrase, aliases)))
    if not primary or _PRONOUN.fullmatch(primary):
        values.extend(context_entities)
    return tuple(
        value
        for value in _unique(values)
        if not re.match(r"^\d+(?:\.\d+)?(?:\s+|$)", value)
    )


def _object_options(value: str, aliases: dict[str, str]) -> tuple[str, ...]:
    primary = _trim_right(value)
    values = [canonical_entity(primary, aliases)]
    complement = _LEADING_COMPLEMENT.sub("", primary)
    if complement != primary:
        values.extend((complement, canonical_entity(complement, aliases)))
    tokens = _tokens(value)
    for width in range(1, min(18, len(tokens)) + 1):
        phrase = " ".join(tokens[:width])
        if not _TRAILING_FUNCTION_WORD.search(phrase):
            values.extend((phrase, canonical_entity(phrase, aliases)))
        without_power = re.sub(
            r"^(?:the\s+)?power\s+to\s+", "", phrase, flags=re.I
        )
        if without_power != phrase:
            values.extend((without_power, canonical_entity(without_power, aliases)))
    for width in range(1, min(14, len(tokens)) + 1):
        phrase = " ".join(tokens[-width:])
        if not _TRAILING_FUNCTION_WORD.search(phrase):
            values.extend((phrase, canonical_entity(phrase, aliases)))
    for width in range(1, min(8, len(tokens)) + 1):
        for offset in range(len(tokens) - width + 1):
            phrase = " ".join(tokens[offset : offset + width])
            if not _TRAILING_FUNCTION_WORD.search(phrase):
                values.extend((phrase, canonical_entity(phrase, aliases)))
    options = _unique(values)
    if graphable_node(primary) and re.match(r"^(?:be|have|do)\s+", primary, re.I):
        primary = normalize_space(primary)
        options = (primary,) + tuple(
            option for option in options if option.casefold() != primary.casefold()
        )
    return options[:64]


def _context_entities(text: str) -> tuple[str, ...]:
    values = [
        canonical_entity(match.group()) for match in _CAPITALIZED.finditer(text)
    ]
    return _unique(list(reversed(values)), limit=24)


def _looks_clause_like(value: str) -> bool:
    words = {word.casefold() for word in _TOKEN.findall(value)}
    bare_verbs = set(_IRREGULAR_VERBS) - {"be", "has", "have", "had"}
    return bool(
        re.search(rf"\b(?:{_MODALS}|is|are|was|were|has|have|had)\b", value, re.I)
        or words.intersection(bare_verbs)
        or _PASSIVE.search(value)
    )


def _split_list(value: str) -> tuple[str, ...]:
    value = canonical_entity(value)
    if re.search(r"\b(?:but|unless|except|provided)\b", value, re.I):
        return (value,)
    if not re.search(r",|\band\b", value, re.I):
        return (value,)
    if "," not in value and re.search(
        r"\b(?:of|in|on|to|from|with|for|by)\b.*\band\b", value, re.I
    ):
        return (value,)
    parts = [
        canonical_entity(re.sub(r"^(?:and|or)\s+", "", part, flags=re.I))
        for part in re.split(r"\s*,\s*|\s+and\s+", value, flags=re.I)
        if canonical_entity(part)
    ]
    if any(_PRONOUN.fullmatch(part) for part in parts):
        return (value,)
    if (
        2 <= len(parts) <= 8
        and len(value.split()) <= 16
        and all(len(part.split()) <= 8 for part in parts)
        and not _looks_clause_like(value)
    ):
        return tuple(parts)
    return (value,)


def _subject_branches(value: str) -> tuple[str, ...]:
    primary = _trim_left(value)
    branches = _split_list(primary)
    return branches if len(branches) > 1 else (primary,)


def _object_branches(value: str, predicate: str) -> tuple[str, ...]:
    primary = _trim_right(value)
    suffix = predicate.rsplit("_", 1)[-1]
    if suffix in {"in", "of", "to", "by", "from", "with", "for", "on", "at"}:
        primary = re.sub(rf"^{suffix}\s+", "", primary, flags=re.I)
    if predicate == "has_right_to" and re.search(r",?\s+and\s+to\s+", primary, re.I):
        actions = [
            normalize_space(re.sub(r"^to\s+", "", item, flags=re.I))
            for item in re.split(r",?\s+and\s+(?=to\s+)", primary, flags=re.I)
        ]
        if all(actions):
            return tuple(actions)
    if predicate == "authorized_to":
        if len(primary.split()) > MAX_NODE_WORDS:
            compact_actions = _compact_authority_actions(primary)
            if compact_actions:
                return compact_actions
        action = re.match(
            r"^(?P<first>[A-Za-z'-]+)\s+and\s+(?P<second>[A-Za-z'-]+)\s+"
            r"(?P<objects>.+)$",
            primary,
            re.I,
        )
        if action:
            shared_objects = re.split(
                r",\s+to\s+", action.group("objects"), maxsplit=1, flags=re.I
            )[0]
            objects = _split_list(shared_objects)
            if len(objects) <= 8:
                return tuple(
                    f"{verb} {object_}"
                    for verb in (action.group("first"), action.group("second"))
                    for object_ in objects
                )
        verbs = "|".join(sorted(_ACTION_VERBS, key=len, reverse=True))
        matches = list(
            re.finditer(
                rf"(?:^|,\s*|\s+and\s+(?:to\s+)?)(?P<verb>{verbs})\b",
                primary,
                re.I,
            )
        )
        if len(matches) > 1:
            actions: list[str] = []
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(primary)
                phrase = normalize_space(f"{match.group('verb')} {primary[match.end():end]}")
                phrase = re.sub(r"(?:,|\b(?:and|or))\s*$", "", phrase, flags=re.I).strip()
                if phrase:
                    actions.append(phrase)
            if actions:
                return tuple(actions)
        scoped = re.match(
            r"^(?P<verb>[A-Za-z'-]+)\s+(?P<head>[^,]+?)\s+"
            r"(?P<scopes>(?:with|among|in|against)\s+.+)$",
            primary,
            re.I,
        )
        if scoped and re.search(
            r",\s*(?:and\s+)?(?:with|among|in|against)\s+",
            scoped.group("scopes"),
            re.I,
        ):
            scopes = re.split(
                r",\s*(?:and\s+)?(?=(?:with|among|in|against)\s+)",
                scoped.group("scopes"),
                flags=re.I,
            )
            return tuple(
                normalize_space(
                    f"{scoped.group('verb')} {scoped.group('head')} {scope}"
                )
                for scope in scopes
            )
        single = re.match(r"^(?P<verb>[A-Za-z'-]+)\s+(?P<objects>.+)$", primary)
        if single:
            objects = _split_list(single.group("objects"))
            if len(objects) > 1:
                return tuple(f"{single.group('verb')} {object_}" for object_ in objects)
    return _split_list(primary)


def _semantic_frames(clause: Clause, aliases: dict[str, str]) -> list[RelationFrame]:
    """Emit exact frames for semantic structures that surface parsing obscures."""
    frames: list[RelationFrame] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    def add(
        subject: str,
        predicate: str,
        object_: str,
        *,
        modality: str | None = None,
        polarity: str = "positive",
    ) -> None:
        subject = canonical_entity(subject, aliases)
        object_ = canonical_entity(object_, aliases)
        key = (
            subject.casefold(),
            predicate,
            object_.casefold(),
            modality or "",
            polarity,
        )
        action_object = predicate in {"has_right_to", "authorized_to"} and bool(
            re.match(r"^(?:be|have|do)\s+", object_, re.I)
        )
        if (
            key in seen
            or not _valid_entity(subject)
            or (not _valid_entity(object_) and not action_object)
        ):
            return
        seen.add(key)
        frames.append(
            RelationFrame(
                subject_options=(subject,),
                predicate_options=(predicate,),
                object_options=(object_,),
                evidence=clause.text,
                context=clause.context,
                sentence_index=clause.sentence_index,
                start=clause.start,
                end=clause.end,
                modality=modality,
                polarity=polarity,
                source_unit=clause.source_unit,
                condition=clause.condition,
                origin="semantic",
            )
        )

    purpose = _PURPOSE.match(clause.text)
    if purpose:
        declaration_object = re.sub(
            r"^(?:this|that)\s+", "", purpose.group("object"), flags=re.I
        )
        add(
            purpose.group("subject"),
            "ordains_and_establishes",
            declaration_object,
        )
        purpose_subject = re.sub(
            r"\s+for\s+.+$", "", declaration_object, flags=re.I
        )
        for action in _action_phrases(purpose.group("purposes")):
            add(purpose_subject, "has_purpose", action)

    necessary = _NECESSARY_TO.match(clause.text)
    if necessary:
        add(
            necessary.group("subject"),
            "necessary_to",
            necessary.group("object"),
        )

    no_law = _NO_LAW.match(clause.text)
    if no_law:
        add(
            no_law.group("subject"),
            "respects",
            no_law.group("respecting"),
            modality=no_law.group("modal").casefold(),
            polarity="negative",
        )
        if no_law.group("prohibiting"):
            add(
                no_law.group("subject"),
                "prohibits",
                no_law.group("prohibiting"),
                modality=no_law.group("modal").casefold(),
                polarity="negative",
            )

    enjoys_right = _ENJOYS_RIGHT.match(clause.text)
    if enjoys_right:
        holder = normalize_space(enjoys_right.group("holder")).rsplit(",", 1)[-1]
        for action in _right_actions(enjoys_right.group("actions")):
            add(
                holder,
                "has_right_to",
                action,
                modality=enjoys_right.group("modal").casefold(),
            )

    construed = _CONSTRUED_TO.match(clause.text)
    if construed:
        for action in re.split(r"\s+or\s+|\s+and\s+", construed.group("actions"), flags=re.I):
            add(
                construed.group("subject"),
                "construed_to",
                action,
                modality=construed.group("modal").casefold(),
                polarity="negative" if construed.group("negative") else "positive",
            )

    warrant = _WARRANT_RULE.search(clause.text)
    if warrant and re.search(
        r"\b(?:probable\s+cause|particularly\s+describ)",
        warrant.group("requirements"),
        re.I,
    ):
        subject = _trim_left(warrant.group("subject"))
        requirements = warrant.group("requirements")
        probable = re.search(r"\b(?:but\s+)?upon\s+([^,]+)", requirements, re.I)
        if probable:
            add(
                subject,
                "issues_upon",
                probable.group(1),
                modality=warrant.group("modal").casefold(),
            )
        supported = re.search(r"\bsupported\s+by\s+([^,]+)", requirements, re.I)
        if supported:
            add("probable cause", "supported_by", supported.group(1))
        described = re.search(
            r"\bdescribing\s+the\s+place\s+to\s+be\s+searched,\s+and\s+"
            r"the\s+persons\s+or\s+things\s+to\s+be\s+seized",
            requirements,
            re.I,
        )
        if described:
            modality = warrant.group("modal").casefold()
            add(subject, "describes", "place to be searched", modality=modality)
            add(subject, "describes", "persons to be seized", modality=modality)
            add(subject, "describes", "things to be seized", modality=modality)

    nominal_text = re.sub(
        r"^(?:after|before)\s+.+?\b(?=(?:the\s+)?(?:manufacture|sale|"
        r"transportation|importation|exportation)\b)",
        "",
        clause.text,
        flags=re.I,
    )
    nominal = _NOMINAL_PROHIBITION.match(nominal_text)
    if nominal:
        subject = canonical_entity(nominal.group("subject"))
        predicate = (
            "prohibited_in"
            if nominal.group("verb").casefold() == "prohibited"
            else "repeals"
        )
        if nominal.group("verb").casefold() == "repealed":
            add(clause.source_unit or "containing provision", predicate, subject)
        elif nominal.group("object"):
            add(subject, predicate, nominal.group("object"))
        else:
            add(subject, "type", "prohibited")
        nominal_items = [
            match.group(1)
            for match in re.finditer(
                r"(?:^|,\s*(?:or\s+)?|\s+or\s+)(?:the\s+)?([A-Za-z][A-Za-z'-]+)",
                subject,
                re.I,
            )
            if match.group(1).casefold()
            in {
                "manufacture",
                "sale",
                "transportation",
                "importation",
                "exportation",
                "distribution",
                "production",
            }
        ]
        common = re.search(r"\bof\s+([^,]+?)(?:\s+within)?(?:,|$)", subject, re.I)
        location = re.search(
            r"\bfrom\s+(.+?)(?:\s+for\s+[^,]+\s+purposes)?$", subject, re.I
        )
        purpose = re.search(r"\bfor\s+([^,]+\s+purposes)\b", subject, re.I)
        if len(nominal_items) >= 3 and common and location:
            for item in nominal_items:
                item_subject = f"{item} of {common.group(1)}"
                if purpose:
                    item_subject += f" for {purpose.group(1)}"
                add(item_subject, "prohibited_in", location.group(1))

    modal_list = _MODAL_ACTION_LIST.match(clause.text)
    if modal_list and not re.match(
        r"(?:have|has)\s+(?:(?:the\s+)?sole\s+)?power\s+to\b",
        modal_list.group("actions"),
        re.I,
    ):
        actions_text = re.sub(
            r"^(?:without|with)\s+[^,]+,\s*",
            "",
            modal_list.group("actions"),
            flags=re.I,
        )
        actions = _action_phrases(actions_text)
        if len(actions) > 1:
            polarity = (
                "negative"
                if re.match(r"\s*(?:no|neither)\b", modal_list.group("subject"), re.I)
                or re.search(r"\bnot\b", clause.text[: modal_list.start("actions")], re.I)
                else "positive"
            )
            for action in actions:
                relation = re.match(r"(?P<verb>[A-Za-z'-]+)\s+(?P<object>.+)", action)
                if relation:
                    objects = (relation.group("object"),)
                    if relation.group("verb").casefold() == "keep":
                        branches = _split_list(relation.group("object"))
                        if len(branches) > 1:
                            objects = branches
                    for object_ in objects:
                        add(
                            modal_list.group("subject"),
                            _predicate_for(relation.group("verb")),
                            object_,
                            modality=modal_list.group("modal").casefold(),
                            polarity=polarity,
                        )

    first_passive = _PASSIVE.search(clause.text)
    if first_passive and first_passive.group("modal") and ", nor " in clause.text.lower():
        for segment in re.split(r",\s*nor\s+", clause.text, flags=re.I)[1:]:
            elliptical = re.fullmatch(
                r"(?P<subject>.+?)\s+"
                r"(?P<verb>required|imposed|inflicted|denied|abridged|taken)\.?",
                normalize_space(segment),
                re.I,
            )
            if elliptical:
                add(
                    elliptical.group("subject"),
                    "type",
                    elliptical.group("verb").casefold(),
                    modality=first_passive.group("modal").casefold(),
                    polarity=(
                        "negative" if first_passive.group("negative") else "positive"
                    ),
                )

    neither = _NEITHER_EXISTS.match(clause.text)
    if neither:
        object_ = re.sub(r"^within\s+", "", neither.group("object"), flags=re.I)
        for subject in (neither.group("first"), neither.group("second")):
            add(
                subject,
                "exists_in",
                object_,
                modality=neither.group("modal").casefold(),
                polarity="negative",
            )
        if neither.group("exception"):
            add(
                neither.group("second"),
                "has_exception",
                re.sub(r"^as\s+", "", neither.group("exception"), flags=re.I),
            )

    for right in _RIGHT_TO.finditer(clause.text):
        holder = right.group("holder")
        actions = _right_actions(right.group("actions"))
        for action in actions or (right.group("actions"),):
            add(holder, "has_right_to", action)
        passive = re.search(
            rf",\s*(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?be\s+"
            r"(?P<verb>denied|abridged|infringed)\b",
            clause.text[right.end() :],
            re.I,
        )
        if passive:
            right_label = normalize_space(right.group())
            add(
                right_label,
                "type",
                passive.group("verb").casefold(),
                modality=passive.group("modal").casefold(),
                polarity="negative" if passive.group("negative") else "positive",
            )
    return frames


def extract_frames(text: str) -> list[RelationFrame]:
    """Build relation frames from clauses using open modal and verb discovery."""
    prose_text = mask_table_bodies(text)
    prepared = clean_document(prose_text)
    aliases = find_aliases(prepared)
    clauses = _clauses(prose_text)
    frames: list[RelationFrame] = extract_structured_frames(text)
    seen: set[tuple[str, str, str, int, str, str]] = set()
    for frame in frames:
        seen.add(
            (
                canonical_entity(frame.subject_options[0]).casefold(),
                "/".join(frame.predicate_options),
                canonical_entity(frame.object_options[0]).casefold(),
                frame.sentence_index,
                frame.modality or "",
                frame.polarity,
            )
        )
    recent_subjects: tuple[str, ...] = ()
    carried_authority = False
    authority_subjects: tuple[str, ...] = ()
    active_sentence = -1
    sentence_subjects: tuple[str, ...] = ()
    sentence_predicates: tuple[str, ...] = ()
    sentence_modality: str | None = None
    sentence_polarity = "positive"

    for clause in clauses:
        if clause.sentence_index != active_sentence:
            active_sentence = clause.sentence_index
            sentence_subjects = ()
            sentence_predicates = ()
            sentence_modality = None
            sentence_polarity = "positive"
        if re.match(r"^(?:Section|Article|Amendment)\b", clause.text, re.I):
            carried_authority = False
            authority_subjects = ()

        semantic_frames = _semantic_frames(clause, aliases)
        for semantic in semantic_frames:
            key = (
                canonical_entity(semantic.subject_options[0]).casefold(),
                "/".join(semantic.predicate_options),
                canonical_entity(semantic.object_options[0]).casefold(),
                semantic.sentence_index,
                semantic.modality or "",
                semantic.polarity,
            )
            if key not in seen:
                seen.add(key)
                frames.append(semantic)

        right_frames = [
            frame for frame in semantic_frames if frame.predicate_options[0] == "has_right_to"
        ]
        if right_frames and not sentence_subjects:
            sentence_subjects = right_frames[0].subject_options[:1]
            sentence_predicates = ("has_right_to",)
            sentence_modality = right_frames[0].modality
            sentence_polarity = right_frames[0].polarity

        if _PURPOSE.match(clause.text) or _NEITHER_EXISTS.match(clause.text):
            continue

        hits = _relation_hits(clause.text)
        authority_hit = next(
            (hit for hit in hits if hit.predicates[0] == "authorized_to"), None
        )
        if authority_hit:
            action_verbs = "|".join(sorted(_ACTION_VERBS, key=len, reverse=True))
            for match in re.finditer(
                rf"\bto\s+(?P<verb>{action_verbs})\b", clause.text, re.I
            ):
                candidate_hit = RelationHit(
                    match.start(),
                    match.start() + 2,
                    ("authorized_to",),
                    authority_hit.modality,
                    authority_hit.polarity,
                    5,
                )
                if not _overlaps(candidate_hit, hits):
                    hits.append(candidate_hit)
            hits.sort(key=lambda item: item.start)
            # Verbs inside a granted power describe that power's action, not a
            # second subject relation. The authority frames atomize them below.
            hits = [hit for hit in hits if hit.predicates == ("authorized_to",)]
        continuation = re.match(r"^(?:and\s+)?to\s+", clause.text, re.I)
        if carried_authority and continuation:
            hits = [
                RelationHit(
                    continuation.start(),
                    continuation.end(),
                    ("authorized_to",),
                    "shall",
                    "positive",
                    5,
                )
            ]
        elif continuation and sentence_subjects and sentence_predicates:
            hits = [
                RelationHit(
                    continuation.start(),
                    continuation.end(),
                    sentence_predicates,
                    sentence_modality,
                    sentence_polarity,
                    5,
                )
            ]
        elif clause.continuation and sentence_subjects and sentence_predicates:
            bare_action = re.match(
                r"^(?:and\s+|or\s+|nor\s+)?(?P<verb>[A-Za-z][A-Za-z'-]*)\b",
                clause.text,
                re.I,
            )
            if (
                bare_action
                and bare_action.group("verb").casefold()
                in (_ACTION_VERBS | set(_IRREGULAR_VERBS))
            ):
                verb = bare_action.group("verb")
                hits.insert(
                    0,
                    RelationHit(
                        bare_action.start("verb"),
                        bare_action.end("verb"),
                        (
                            sentence_predicates
                            if sentence_predicates == ("has_right_to",)
                            else (_predicate_for(verb),)
                        ),
                        sentence_modality,
                        sentence_polarity,
                        5,
                    ),
                )
        if not hits:
            continue

        context_entities = recent_subjects + _context_entities(clause.context)
        prior_hit_end = 0
        local_antecedents = recent_subjects
        clause_subjects: tuple[str, ...] = ()
        for hit_index, hit in enumerate(hits):
            subject_text = clause.text[prior_hit_end : hit.start]
            inherits_sentence_subject = bool(
                sentence_subjects
                and (
                    (
                        clause.continuation
                        and re.match(r"^(?:and|or|nor|to)\b", clause.text, re.I)
                    )
                    or (hit_index > 0 and hit.modality is None and hit.priority <= 1)
                    or (
                        hit_index > 0
                        and re.search(
                            r"(?:,|\b)(?:and|or|nor)\s*$", subject_text, re.I
                        )
                    )
                )
            )
            if hit.priority == 5 and authority_subjects and hit.predicates == ("authorized_to",):
                raw_subjects = authority_subjects
            elif inherits_sentence_subject:
                raw_subjects = sentence_subjects
            elif clause_subjects and re.match(
                r"^\s*,?\s*and\s+(?:by|with|after|before|in|on|at|from)\b",
                subject_text,
                re.I,
            ):
                raw_subjects = clause_subjects
            else:
                raw_subjects = _subject_branches(subject_text)
            if not any(_valid_entity(value) for value in raw_subjects):
                fallback = (
                    authority_subjects
                    if hit.priority == 5
                    else clause_subjects or local_antecedents or recent_subjects
                )
                raw_subjects = fallback[:1]
            next_start = (
                hits[hit_index + 1].start
                if hit_index + 1 < len(hits)
                else len(clause.text)
            )
            object_text = clause.text[hit.end : next_start]
            if hit_index + 1 < len(hits) and re.match(r"^\s*,", object_text):
                shared_object = clause.text[hits[hit_index + 1].end :]
                if normalize_space(shared_object):
                    object_text = shared_object
            if not normalize_space(object_text):
                prior_hit_end = hit.end
                continue

            subjects = tuple(value for value in raw_subjects if _valid_entity(value))
            if not subjects:
                subjects = recent_subjects[:1]
            primary_predicate = hit.predicates[0]
            if subjects and not clause_subjects:
                clause_subjects = subjects[:1]
            object_branches = _object_branches(object_text, primary_predicate)[:16]
            for subject_branch in subjects[:8]:
                subject_options = _subject_options(
                    subject_branch, aliases, context_entities
                )
                if not subject_options:
                    continue
                for object_branch in object_branches:
                    object_options = _object_options(object_branch, aliases)
                    if not object_options:
                        continue
                    polarity = hit.polarity
                    modality = hit.modality
                    if inherits_sentence_subject:
                        modality = modality or sentence_modality
                        if polarity == "positive" and sentence_polarity == "negative":
                            polarity = "negative"
                    if re.match(r"^(?:no|not|never)\b", subject_branch, re.I) or re.match(
                        r"^(?:no|not|never)\b", object_branch, re.I
                    ) or re.search(
                        r"\b(?:not|never)\s*$", subject_text, re.I
                    ) or re.match(
                        r"^\s*(?:no|not|never)\b", object_text, re.I
                    ) or re.match(
                        r"^\s*no\b", subject_text, re.I
                    ):
                        polarity = "negative"
                    key = (
                        canonical_entity(subject_options[0]).casefold(),
                        "/".join(hit.predicates),
                        canonical_entity(object_options[0]).casefold(),
                        clause.sentence_index,
                        modality or "",
                        polarity,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    frames.append(
                        RelationFrame(
                            subject_options=subject_options,
                            predicate_options=hit.predicates,
                            object_options=object_options,
                            evidence=clause.text,
                            context=clause.context,
                            sentence_index=clause.sentence_index,
                            start=clause.start,
                            end=clause.end,
                            modality=modality,
                            polarity=polarity,
                            source_unit=clause.source_unit,
                            condition=clause.condition,
                            origin=(
                                "open_verb"
                                if hit.priority == 1
                                else "modal"
                                if hit.priority == 2
                                else "pattern"
                            ),
                        )
                    )
            if subjects and not sentence_subjects and hit.modality:
                sentence_subjects = subjects[:1]
                sentence_predicates = hit.predicates
                sentence_modality = hit.modality
                _, sentence_polarity = _modal_and_polarity(clause.text)
            if primary_predicate == "authorized_to":
                carried_authority = True
                if subjects:
                    authority_subjects = subjects[:1]
            if object_branches:
                local_antecedents = tuple(
                    value for value in object_branches if _valid_entity(value)
                )[:4]
            prior_hit_end = hit.end

            first_subjects = _subject_options(subject_text, aliases, context_entities)
            if first_subjects and not _PRONOUN.fullmatch(first_subjects[0]):
                recent_subjects = first_subjects[:4]
    return [
        frame
        for frame in frames
        if not (
            frame.predicate_options[0] == "makes"
            and canonical_entity(frame.object_options[0]).casefold() == "law"
            and re.search(
                r"\bmake\s+no\s+law\s+(?:respecting|prohibiting|abridging)\b",
                frame.evidence,
                re.I,
            )
        )
    ]


def candidates_from_frames(frames: list[RelationFrame]) -> list[CandidateTriple]:
    """Return the deterministic first choice from relation frames."""
    return [
        CandidateTriple(
            subject=canonical_entity(frame.subject_options[0]),
            predicate=frame.predicate_options[0],
            object=canonical_entity(frame.object_options[0]),
            evidence=frame.evidence,
            sentence_index=frame.sentence_index,
            start=frame.start,
            end=frame.end,
            modality=frame.modality,
            polarity=frame.polarity,
            object_kind=object_kind(frame.object_options[0]),
            source_unit=frame.source_unit,
            source_locator=frame.source_locator,
            source_page=frame.source_page,
            condition=frame.condition,
            origin=frame.origin,
            context=frame.context,
        )
        for frame in frames
    ]


def extract_candidates(text: str) -> list[CandidateTriple]:
    """Return deterministic candidates without calling Jev."""
    return candidates_from_frames(extract_frames(text))
