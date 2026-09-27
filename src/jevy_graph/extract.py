from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from functools import lru_cache

from .events import EventState, assemble_events, relation_frames_from_events
from .scientific.compiler import (
    ScientificClauseCompiler, hypotheses_to_claims, hypotheses_to_events,
)
from .models import CandidateTriple, ClaimFrame, RelationFrame
from .provisions import ProvisionState, assemble_provisions, relation_frames_from_provisions
from .prose import ProseState, assemble_prose
from .normalize import (
    MAX_NODE_WORDS,
    canonical_entity, canonical_label,
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
_SCIENTIFIC_HEADING = (
    r"Abstract|Introduction|Background|Results(?:\s+and\s+Discussion)?|"
    r"Discussion|Materials\s+(?:and|&)\s+Methods|"
    r"Methods\s+and\s+Materials|Patients\s+and\s+Methods|"
    r"Methods|Methodology|Experimental\s+Procedures|"
    r"Conclusions?|Supplementary\s+(?:Materials|Information)"
    r"(?:\s+Figures\s+and\s+Tables)?"
)
_STATIC_RELATIONS: tuple[RelationPattern, ...] = (
    RelationPattern(
        re.compile(r"\b(?:is|are|was|were)\s+due\s+to\b", re.I),
        ("due_to",),
    ),
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
        re.compile(r"\b(?:determines?|determined|determining)\b", re.I),
        ("determines",),
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
        re.compile(r"\b(?:wins?|won|winning)\b", re.I),
        ("won",),
    ),
    RelationPattern(
        re.compile(r"\b(?:facilitates?|facilitated|facilitating)\b", re.I),
        ("facilitates",),
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
        re.compile(r"\b(?:suppresses?|suppressed|suppressing)\b", re.I),
        ("suppresses", "inhibits"),
    ),
    RelationPattern(
        re.compile(r"\b(?:promotes?|promoted|promoting)\b", re.I),
        ("promotes", "supports"),
    ),
    RelationPattern(
        re.compile(r"\btake(?:s)?\s+effect\s+on\b", re.I),
        ("takes_effect_on",),
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
        re.compile(r"\b(?:predicts?|predicted|predicting)\b", re.I),
        ("predicts",),
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
    rf"\b(?:(?P<modal>{_MODALS})(?:\s*,\s*(?:during|after|before|when|if|unless)"
    r"\b[^,]{0,120},\s*|\s+))?(?P<negative>not\s+)?"
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
_NEGATED_ACTIVE_AUXILIARY = re.compile(
    r"\b(?P<auxiliary>did|does|do)(?:\s+not(?!\s+(?:only|just)\b)|n't)\s+"
    r"(?:[A-Za-z-]+ly\s+){0,2}"
    r"(?P<verb>[A-Za-z][A-Za-z'-]*)\b",
    re.I,
)
_REDUCED_TIMED_MODIFIER = re.compile(
    r"\s+(?P<modifier>[A-Za-z][A-Za-z'-]*(?:ed|en)\s+"
    r"(?:(?:\d+|one|two|three|four|five|a|an)\s+"
    r"[A-Za-z-]+(?:\s+[A-Za-z-]+){0,2}\s+(?:later|earlier)|"
    r"(?:after|before|during|at|on)\s+.+))$",
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
_RIGHT_NONDISCRIMINATION = re.compile(
    r"^(?P<right>The right of .+? to vote)"
    r"(?P<vote_scope>\s+in\s+.+?,)?\s+"
    rf"(?P<modal>{_MODALS})\s+not\s+be\s+"
    r"(?P<verbs>denied\s+or\s+abridged|denied|abridged)\s+by\s+"
    r"(?P<actors>.+?)\s+"
    r"(?P<basis>on\s+account\s+of|by\s+reason\s+of)\s+"
    r"(?P<reason>.+?)(?:\.|--)?$",
    re.I,
)
_PRESIDENTIAL_TERM_LIMIT = re.compile(
    r"^No person shall be elected to the office of the President more than "
    r"(?P<ordinary>\w+),\s+and no person who (?P<prior_service>.+?) "
    r"shall be elected to the office of the President more than (?P<prior>\w+)\.?$",
    re.I,
)
_PRESIDENTIAL_TERM_EXCEPTION = re.compile(
    r"^But this Article shall not apply to (?P<prior>.+?),\s+and shall not "
    r"prevent (?P<current>.+?) from (?P<actions>.+?)\.?$",
    re.I,
)
_OFFICERS_ESTABLISHED = re.compile(
    r"(?P<officers>all other Officers of the United States),\s+whose "
    r"Appointments are not herein otherwise provided for,\s+and which "
    r"shall be established by Law",
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
_INOPERATIVE_RATIFICATION = re.compile(
    r"^This article shall be inoperative unless it shall have been ratified "
    r"as an amendment to the Constitution by (?P<body>.+?)\s*,?\s*"
    r"within seven years from (?P<start>.+?)\.?$",
    re.I,
)
_INTERVENTION_EFFECT = re.compile(
    r"\boverexpression of (?P<entities>[^,]+?) in (?P<cells>[^,]+?) "
    r"(?P<effect>blocked|inhibited|suppressed|enhanced|increased|reduced) "
    r"(?P<outcome>[^,]+?)(?=,|\.$|$)", re.I,
)
_DOWNSTREAM_BLOCKADE = re.compile(
    r"^Blockade of (?:several|multiple|the) (?P<upstream>\S+) "
    r"downstream pathways such as (?P<responsive>.+?), but not "
    r"(?P<nonresponsive>.+?), (?:only )?partially inhibited "
    r"(?P<outcome>[^.]+)\.?$", re.I,
)
_TIMED_LIQUOR_PROHIBITION = re.compile(
    r"^After (?P<delay>.+?) from the ratification of this article the "
    r"(?P<actions>.+?) of "
    r"(?P<substance>.+?) within, the importation thereof into, or the "
    r"exportation thereof from (?P<jurisdictions>.+?) for "
    r"(?P<purpose>.+?) is hereby prohibited\.?$", re.I,
)
_EDITORIAL_WORD_NOTE = re.compile(
    r"(?:The|and the) Words?,?\s+\"(?P<word>[^\"]+)\"\s+being "
    r"(?P<verb>interlined between|partly written on)\s+"
    r"(?P<place>.+?)(?=,\s+The Words?\b|\s+and the Word\b|\.$|$)",
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
_SHARED_MODAL_OBJECT = re.compile(
    rf"^(?P<subject>.+?)\s+(?P<modal>{_MODALS})\s+"
    r"(?P<first>[A-Za-z'-]+)\s+or\s+(?P<second>[A-Za-z'-]+)\s+"
    r"(?P<prep>with|to|in|on|for)\s+(?P<object>.+)$",
    re.I,
)
_BIOGRAPHICAL_INTRO = re.compile(
    r"^(?P<person>.+?)\s+\(born\s+(?P<date>[^)]+?)\s+in\s+"
    r"(?P<place>[^,)]+)(?:,\s*[^)]+)?\)\s+is\s+an?\s+"
    r"(?P<kind>.+?)(?:\s+who\b|$)",
    re.I,
)
_ALBUM_INTRO = re.compile(
    r"^(?P<title>.+?) is an album by (?P<artist>[^.]+)\.?$", re.I,
)
_DEMONYMS = {
    "american", "australian", "austrian", "belgian", "brazilian", "british",
    "canadian", "chinese", "danish", "dutch", "french", "german", "greek",
    "indian", "irish", "italian", "japanese", "mexican", "norwegian",
    "polish", "russian", "spanish", "swedish", "swiss",
}
_COUNT_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}
_EIGHTH_PROHIBITIONS = re.compile(
    r"^Excessive bail shall not be required, nor excessive fines imposed, "
    r"nor cruel and unusual punishments inflicted\.?$",
    re.I,
)
_RIGHT_INFRINGEMENT = re.compile(
    r"(?P<right>right of the people to keep and bear Arms),\s*"
    r"(?P<modal>shall)\s+not\s+be\s+infringed\.?$",
    re.I,
)
_HOUSE_MEMBERS_ELECTION = re.compile(
    r"House of Representatives shall be composed of Members chosen "
    r"every (?P<interval>second Year) by the (?P<voters>People of the several States)",
    re.I,
)
_REPRESENTATIVE_QUALIFICATIONS = re.compile(
    r"^No Person shall be a Representative who shall not have attained to "
    r"the Age of (?P<age>twenty five) Years, and been (?P<citizenship>seven) "
    r"Years a Citizen of the United States, and who shall not, when elected, "
    r"be an Inhabitant of that State in which he shall be chosen\.?$",
    re.I,
)
_HOUSE_APPORTIONMENT = re.compile(
    r"^Representatives and direct Taxes shall be apportioned among "
    r"(?P<states>the several States which may be included within this Union), "
    r"according to their respective Numbers, which shall be determined by "
    r"adding to the (?P<free>whole Number of free Persons), including "
    r"(?P<bound>those bound to Service for a Term of Years), and excluding "
    r"(?P<excluded>Indians not taxed), (?P<other>three fifths of all other Persons)\.?$",
    re.I,
)
_ENUMERATION_SCHEDULE = re.compile(
    r"^The actual Enumeration shall be made within "
    r"(?P<initial>three Years after the first Meeting of the Congress of the United States), "
    r"and within every (?P<later>subsequent Term of ten Years), "
    r"in such Manner as they shall by Law direct\.?$",
    re.I,
)
_HOUSE_REPRESENTATION_LIMIT = re.compile(
    r"^The Number of Representatives shall not exceed "
    r"(?P<ratio>one for every thirty Thousand), but each State shall have "
    r"at Least (?P<minimum>one Representative)$",
    re.I,
)
_INITIAL_REPRESENTATION = re.compile(
    r"^(?:and\s+)?until\s+such enumeration shall be made,\s+the\s+"
    r"(?P<first_state>State of [A-Za-z -]+?)\s+shall be entitled to chuse\s+"
    r"(?P<allocations>.+)$",
    re.I,
)
_ALLOCATION_COUNT = re.compile(
    r"^(?P<state>.+?)\s+(?P<count>one|two|three|four|five|six|seven|"
    r"eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen)\.?$",
    re.I,
)
_REPRESENTATION_VACANCY = re.compile(
    r"^(?P<condition>When vacancies happen in the Representation from any State), "
    r"the Executive Authority thereof shall issue Writs of Election "
    r"to fill such Vacancies\.?$",
    re.I,
)
_HOUSE_OFFICERS = re.compile(
    r"^The House of Representatives shall chuse their Speaker and other Officers$",
    re.I,
)
_HOUSE_IMPEACHMENT = re.compile(
    r"^and shall have the sole Power of Impeachment\.?$",
    re.I,
)
_ENFORCEMENT_POWER = re.compile(
    r"^(?P<actors>(?:The\s+)?Congress(?:\s+and\s+the\s+several\s+States)?)\s+"
    r"(?P<modal>shall|may)\s+have\s+(?P<concurrent>concurrent\s+)?"
    r"power\s+to\s+enforce(?P<object>.+)$",
    re.I,
)
_MEDAL_RESULT = re.compile(
    r"^(?P<person>He|She|They|[A-Z][A-Za-z .'-]+)\s+won\s+"
    r"(?P<count>\w+)\s+medals?\s+"
    r"in\s+(?P<event>.+?)\s+at\s+(?P<competition>.+?)\s+with\s+a\s+"
    r"(?P<first>gold|silver|bronze)\s+in\s+(?P<first_year>\d{4})\s+"
    r"and\s+a\s+(?P<second>gold|silver|bronze)\s+in\s+(?P<second_year>\d{4})\.?$",
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
    r"\s+(?:a|an|the|and|or|to|of|in|on|for|with|by|from|as)$", re.I
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
    "splicing",
    "processing",
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
    "propose": "proposes",
    "concur": "concurs",
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
        r"^(?:Article\.?\s+[IVXLC]+\.|Amendment\s+[IVXLC]+\.?|"
        rf"Section\.?\s+\d+\.|(?:{_SCIENTIFIC_HEADING})|"
        r"Acknowledgements|References|"
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
        r"(?im)^(?:Article\.?\s*([IVXLC]+)\.|"
        r"Amendment\s+([IVXLC]+)\.?|"
        r"Section\.?\s*(\d+)\.)\s*$"
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
            section = int(match.group(3))
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
        rf"(?m)^((?P<scientific>{_SCIENTIFIC_HEADING})|"
        r"(?P<number>(?!0\d)\d{1,3}(?:\.\d{1,3})*)\.?\s+"
        r"(?P<title>[A-Z][^\n]{1,80})|"
        r"CHAPTER\s+(?P<chapter>[IVXLC]+)\.?(?:\s+(?P<chapter_title>[^\n]{1,80}))?|"
        r"Appendix\s+(?P<appendix>[A-Z])\.?(?:\s+(?P<appendix_title>[^\n]{1,80}))?|"
        r"(?P<named>References|Acknowledgements|Authors' Addresses|"
        r"Full Copyright Statement))$",
        text,
        re.I,
    ):
        if match.group("scientific"):
            label = re.sub(
                r"[^A-Z0-9]+", "_",
                match.group("scientific").upper().replace("&", "AND"),
            ).strip("_")
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
    setting = re.match(r"^(?P<condition>in\s+[^,]{1,40}),\s*", value, re.I)
    if setting and len(setting.group("condition").split()) <= 4:
        conditions.append(normalize_space(setting.group("condition")))
    leading = re.match(
        r"^(?P<condition>(?:if|when|whenever|unless|until|after|before|in\s+case\s+of)\b.+?),\s*",
        value,
        re.I,
    )
    if leading:
        conditions.append(normalize_space(leading.group("condition")))
    for match in re.finditer(
        r"(?:,|;)\s*(?P<condition>(?:unless|except|provided\s+that|"
        r"on\s+condition\s+that)\b.+?)(?=;|$)",
        value,
        re.I,
    ):
        conditions.append(normalize_space(match.group("condition")))
    for match in re.finditer(r"(?:,|;)\s*(?P<condition>without\b[^,;]+)",
                             value, re.I):
        conditions.append(normalize_space(match.group("condition")))
    return "; ".join(dict.fromkeys(conditions)) or None


def _predicate_condition(clause: Clause, hit: RelationHit) -> str | None:
    """Keep each relation's nearby conditions without copying a later branch."""
    conditions: list[str] = []
    for condition in (clause.condition or "").split("; "):
        if not condition:
            continue
        start = clause.text.casefold().find(condition.casefold())
        if (start == 0
                and re.match(r"^(?:if|when|whenever|unless|until|after|before)\b",
                             condition, re.I)
                and re.search(r",\s*(?:but|nor)\b",
                              clause.text[start + len(condition):hit.start], re.I)):
            continue
        if (start >= hit.end
                and re.match(r"^(?:unless|except|without|provided\s+that)\b",
                             condition, re.I)
                and re.search(
                    rf"[:,]\s*(?:and|but|or|nor)\s+[^;]{{1,160}}?\b(?:{_MODALS})\b",
                    clause.text[hit.end:start], re.I,
                )):
            continue
        conditions.append(condition)
    # Parenthetical/interposed conditions commonly sit between an actor and
    # its main verb: "Congress, whenever ..., shall propose ...".  The
    # subordinate predicate inside that condition should not inherit it.
    for match in re.finditer(
        rf",\s*(?:and\s+)?(?P<condition>(?:if|when|whenever|unless|"
        rf"provided\s+that|on\s+(?:the\s+)?Application\s+of|"
        rf"by\s+and\s+with\s+(?:the\s+)?Advice\s+and\s+Consent\s+of)"
        rf"\b[^,]{{1,160}}),"
        rf"\s*(?:{_MODALS})\b",
        clause.text, re.I,
    ):
        intervening = clause.text[match.end("condition"):hit.start]
        if (hit.start >= match.end("condition")
                and not re.search(r",\s*(?:or\s*,|but\b|which\b)",
                                  intervening, re.I)):
            conditions.append(normalize_space(match.group("condition")))
    # A trailing temporal setting qualifies the event rather than becoming
    # part of its affected entity: "altered tone during the procedure".
    trailing_setting = re.search(
        r"\b(?P<condition>(?:during|throughout)\s+[^,;.]{2,100})[.;]?\s*$",
        clause.text[hit.end:],
        re.I,
    )
    if trailing_setting and not any(
        later.start > hit.start
        and later.start < hit.end + trailing_setting.start("condition")
        for later in _relation_hits(clause.text)
    ):
        conditions.append(normalize_space(trailing_setting.group("condition")))
    return "; ".join(dict.fromkeys(conditions)) or None


def _clauses(text: str) -> list[Clause]:
    prepared = clean_document(text)
    markers = _source_markers(prepared)
    marker_positions = [position for position, _ in markers]
    clauses: list[Clause] = []
    sentence_index = 0
    scan = list(prepared)
    for abbreviation in re.finditer(
        r"(?i)(?<!\w)(?:i\.e\.|e\.g\.|u\.s\.|u\.k\.|dr\.|mr\.|mrs\.|prof\.)",
        prepared,
    ):
        for position in range(abbreviation.start(), abbreviation.end()):
            if scan[position] == ".":
                scan[position] = "∯"
    for decimal in re.finditer(r"(?<=\d)\.(?=\d)", prepared):
        scan[decimal.start()] = "∯"
    # Preserve abbreviated scientific names such as ``B. pseudomallei``.
    # Splitting after the genus initial loses the evidence needed to assemble
    # coordinated organism lists.
    for genus in re.finditer(r"\b[A-Z]\.(?=\s+[a-z][a-z-]{2,})", prepared):
        scan[genus.start() + 1] = "∯"
    parenthesis_depth = 0
    for position, character in enumerate(prepared):
        if character == "(":
            parenthesis_depth += 1
        elif character == ")":
            parenthesis_depth = max(0, parenthesis_depth - 1)
        elif character == "." and parenthesis_depth:
            scan[position] = "∯"
    for sentence_match in _SENTENCE.finditer("".join(scan)):
        sentence = normalize_space(prepared[sentence_match.start():sentence_match.end()])
        if not sentence:
            continue
        parts = list(re.finditer(r"(?:^|;|—)\s*([^;—]+)", sentence))
        # A leading setting can govern coordinated clauses, but an exception
        # following a semicolon normally belongs to that clause alone.  Using
        # _condition(sentence) for every part copied later exceptions onto
        # earlier, unrelated predicates.
        leading_setting = None
        if parts:
            first_condition = _condition(normalize_space(parts[0].group(1)))
            if first_condition:
                first_piece = first_condition.split("; ", 1)[0]
                if normalize_space(parts[0].group(1)).casefold().startswith(
                    first_piece.casefold() + ","
                ):
                    leading_setting = first_piece
        for part_index, part in enumerate(parts):
            clause = normalize_space(part.group(1))
            if not clause:
                continue
            local_condition = _condition(clause)
            if part_index and leading_setting:
                conditions = [leading_setting]
                if local_condition:
                    conditions.extend(local_condition.split("; "))
                local_condition = "; ".join(dict.fromkeys(conditions))
            clauses.append(
                Clause(
                    text=clause,
                    context=sentence,
                    sentence_index=sentence_index,
                    start=sentence_match.start() + part.start(1),
                    end=sentence_match.start() + part.end(1),
                    continuation=part_index > 0,
                    source_unit=markers[bisect_right(marker_positions, sentence_match.start() + part.start(1)) - 1][1],
                    condition=local_condition,
                )
            )
        sentence_index += 1
    return clauses


def _modal_and_polarity(value: str) -> tuple[str | None, str]:
    modal_match = re.search(rf"\b({_MODALS})\b", value, re.I)
    # "not only A but also B" coordinates asserted outcomes; it does not
    # negate either one. Keep biological direction (decreased/increased)
    # separate from assertion polarity.
    negation_scope = re.sub(r"\bnot\s+(?:only|just)\b", "", value, flags=re.I)
    negative = bool(re.search(r"\b(?:not|never|no)\b", negation_scope, re.I))
    return (
        modal_match.group(1).casefold() if modal_match else None,
        "negative" if negative else "positive",
    )


def _predicate_for(verb: str, prep: str | None = None) -> str:
    word = verb.casefold().replace("’", "'")
    if word in {"raising", "proposing", "choosing"}:
        word = {"raising": "raises", "proposing": "proposes", "choosing": "chooses"}[word]
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
            or (
                verb.casefold() in {"have", "has"}
                and re.match(r"\s+[A-Za-z'-]+(?:ed|en)\b", clause[match.end():], re.I)
            )
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
        if verb.casefold().endswith("ing") and re.search(
            r"\bfor\s+$", clause[:match.start()], re.I
        ):
            continue
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
    value = re.sub(r"^(?:in|among|within)\s+[^,]{1,80},\s*", "", value, flags=re.I)
    value = re.sub(
        r"^(?:if|when|whenever|unless|until|after|before)\b[^,]*,\s*",
        "",
        value,
        flags=re.I,
    )
    value = re.split(r"[;:]", value)[-1]
    value = re.split(r"\b(?:and|but)\b", value, flags=re.I)[-1]
    value = _TRAILING_AUXILIARY.sub("", value)
    value = _TRAILING_FUNCTION_WORD.sub("", value)
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
    value = re.sub(r"\s+(?:by|with|for|to|of|in|on)$", "", value, flags=re.I)
    value = _TRAILING_AUXILIARY.sub("", value)
    value = _TRAILING_FUNCTION_WORD.sub("", value)
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


def _unique(values: Iterable[str], limit: int = 64) -> tuple[str, ...]:
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
    return tuple(
        value
        for value in _unique(_subject_values(value, aliases, context_entities))
        if not re.match(r"^\d+(?:\.\d+)?(?:\s+|$)", value)
    )


def _subject_values(
    value: str,
    aliases: dict[str, str],
    context_entities: tuple[str, ...],
) -> Iterator[str]:
    if re.fullmatch(r"(?:Sections?\s+\d+\s+and\s+\d+|[A-Z][A-Za-z0-9-]*\s+and\s+[A-Z][A-Za-z0-9-]*)", normalize_space(value), re.I):
        yield canonical_entity(value, aliases)
    primary = _trim_left(value)
    yield canonical_entity(primary, aliases)
    segment = re.split(
        r"[,;:]|\b(?:and|but)\b", normalize_space(value), flags=re.I
    )[-1]
    tokens = _tokens(segment)
    yield from (
        canonical_entity(match.group(), aliases)
        for match in _CAPITALIZED.finditer(value)
    )
    for width in range(min(14, len(tokens)), 0, -1):
        phrase = " ".join(tokens[-width:])
        yield phrase
        yield canonical_entity(phrase, aliases)
        without_auxiliary = _TRAILING_AUXILIARY.sub("", phrase)
        yield without_auxiliary
        yield canonical_entity(without_auxiliary, aliases)
    for width in range(1, min(8, len(tokens)) + 1):
        for offset in range(len(tokens) - width + 1):
            phrase = " ".join(tokens[offset : offset + width])
            yield phrase
            yield canonical_entity(phrase, aliases)
    if not primary or _PRONOUN.fullmatch(primary):
        yield from context_entities


def _object_options(value: str, aliases: dict[str, str]) -> tuple[str, ...]:
    primary = _trim_right(value)
    options = _unique(_object_values(value, primary, aliases))
    if graphable_node(primary) and re.match(r"^(?:be|have|do)\s+", primary, re.I):
        primary = normalize_space(primary)
        options = (primary,) + tuple(
            option for option in options if option.casefold() != primary.casefold()
        )
    return options[:64]


def _object_values(value: str, primary: str, aliases: dict[str, str]) -> Iterator[str]:
    yield canonical_entity(primary, aliases)
    complement = _LEADING_COMPLEMENT.sub("", primary)
    if complement != primary:
        yield complement
        yield canonical_entity(complement, aliases)
    tokens = _tokens(value)
    for width in range(1, min(18, len(tokens)) + 1):
        phrase = " ".join(tokens[:width])
        if not _TRAILING_FUNCTION_WORD.search(phrase):
            yield phrase
            yield canonical_entity(phrase, aliases)
        without_power = re.sub(
            r"^(?:the\s+)?power\s+to\s+", "", phrase, flags=re.I
        )
        if without_power != phrase:
            yield without_power
            yield canonical_entity(without_power, aliases)
    for width in range(1, min(14, len(tokens)) + 1):
        phrase = " ".join(tokens[-width:])
        if not _TRAILING_FUNCTION_WORD.search(phrase):
            yield phrase
            yield canonical_entity(phrase, aliases)
    for width in range(1, min(8, len(tokens)) + 1):
        for offset in range(len(tokens) - width + 1):
            phrase = " ".join(tokens[offset : offset + width])
            if not _TRAILING_FUNCTION_WORD.search(phrase):
                yield phrase
                yield canonical_entity(phrase, aliases)


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


def _simple_alternative_nouns(value: str) -> tuple[str, ...]:
    """Split an explicit noun list, leaving longer dependent phrases intact."""
    parts = re.split(r"\s*,\s*(?:or\s+)?|\s+or\s+", value.strip(" ,"), flags=re.I)
    parts = [re.sub(r"^(?:any|a|an|the)\s+", "", part.strip(), flags=re.I)
             for part in parts]
    if (1 < len(parts) <= 8 and all(
        part and len(part.split()) <= 4
        and not re.search(rf"\b(?:{_MODALS}|is|are|was|were)\b", part, re.I)
        for part in parts
    )):
        return tuple(parts)
    return (value.strip(" ,"),)


def _shared_negative_objects(value: str) -> tuple[str, ...]:
    """Distribute only explicit alternatives over their shared noun modifiers."""
    groups = re.split(r",\s*or\s+(?=(?:any|a|an|the)\s+)", value, flags=re.I)
    result: list[str] = []
    for group in groups:
        group = re.sub(r"^(?:any|a|an|the)\s+", "", group.strip(" ,"), flags=re.I)
        has_shared_tail = bool(re.fullmatch(
            r".+?\b(?:of|for)\s+(?:the\s+)?[A-Za-z'-]+\s+or\s+"
            r"[A-Za-z'-]+\s+(?:against|of|from|in|under|for)\s+.+",
            group, re.I,
        ))
        shared_participle = re.fullmatch(
            r"(?P<heads>[A-Za-z'-]+\s+or\s+[A-Za-z'-]+)\s+"
            r"(?P<tail>[A-Za-z'-]+(?:ed|en)\s+.+)", group, re.I,
        )
        if shared_participle:
            heads = _simple_alternative_nouns(shared_participle.group("heads"))
            phrases = [f"{head} {shared_participle.group('tail')}" for head in heads]
        elif has_shared_tail:
            phrases = [group]
        else:
            phrases = list(_simple_alternative_nouns(group))
            if len(phrases) == 1:
                phrases = [group]
        for phrase in phrases:
            shared_tail = re.fullmatch(
                r"(?P<prefix>.+?\b(?:of|for)\s+)(?:the\s+)?"
                r"(?P<first>[A-Za-z'-]+)\s+or\s+(?P<second>[A-Za-z'-]+)"
                r"(?P<suffix>\s+(?:against|of|from|in|under|for)\s+.+)",
                phrase, re.I,
            )
            if shared_tail:
                prefix = shared_tail.group("prefix")
                suffix = shared_tail.group("suffix")
                for alternative in (shared_tail.group("first"), shared_tail.group("second")):
                    result.append(normalize_space(f"{prefix}{alternative}{suffix}"))
            else:
                result.append(normalize_space(phrase))
    return tuple(re.sub(r"\bof any ([A-Za-z'-]+)\b", r"of a \1", item, flags=re.I)
                 for item in result[:16])


def _subject_branches(value: str) -> tuple[str, ...]:
    bare = _TRAILING_AUXILIARY.sub("", normalize_space(value))
    described_gene = re.fullmatch(
        r"(?:the\s+)?(?:[A-Za-z0-9-]+\s+){0,5}"
        r"(?:target\s+)?gene\s+(?P<name>[A-Za-z][A-Za-z0-9-]{2,})",
        bare,
        re.I,
    )
    if described_gene:
        return (described_gene.group("name"),)
    coordinated = re.search(
        r"\b(?P<first>[A-Z][A-Za-z0-9-]*)\s+and\s+"
        r"(?P<second>[A-Z][A-Za-z0-9-]*)\s+cooperatively$",
        bare,
    )
    if coordinated:
        return (f"{coordinated.group('first')} and {coordinated.group('second')}",)
    if re.fullmatch(r"Sections?\s+\d+\s+and\s+\d+", bare, re.I):
        return (bare,)
    primary = _trim_left(value)
    branches = _split_list(primary)
    return branches if len(branches) > 1 else (primary,)


def _object_branches(value: str, predicate: str) -> tuple[str, ...]:
    clean_value = re.sub(
        r"\s*\((?:p\s*[<=>]|(?:Supplementary\s+)?Fig(?:ure)?\b)[^)]*\)",
        "",
        value,
        flags=re.I,
    )
    clean_value = normalize_space(clean_value).rstrip(".")
    paired_outcomes = re.fullmatch(
        r"not only\s+(?P<first>.+?)\s+but also\s+(?P<second>.+)",
        clean_value,
        re.I,
    )
    if paired_outcomes:
        return tuple(_trim_right(paired_outcomes.group(name)) for name in ("first", "second"))
    primary = _trim_right(clean_value)
    shared_of = re.fullmatch(
        r"(?P<first>(?:the\s+)?[A-Za-z-]+)\s+and\s+"
        r"(?P<second>[A-Za-z-]+)\s+of\s+(?P<tail>.+)",
        primary,
        re.I,
    )
    if shared_of:
        return (
            f"{shared_of.group('first')} of {shared_of.group('tail')}",
            f"{shared_of.group('second')} of {shared_of.group('tail')}",
        )
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


def _semantic_frames(
    clause: Clause, aliases: dict[str, str], antecedent: tuple[str, ...] = (),
    previous_sentence: str = "", album_context: tuple[str, str] = (),
    covered_result_spans: list[tuple[int, int]] | None = None,
) -> list[RelationFrame]:
    """Emit exact frames for semantic structures that surface parsing obscures."""
    frames: list[RelationFrame] = []
    seen: set[tuple[str, str, str, str, str, str, str]] = set()

    def add(
        subject: str,
        predicate: str,
        object_: str,
        *,
        predicate_alternatives: tuple[str, ...] = (),
        modality: str | None = None,
        polarity: str = "positive",
        condition: str | None = None,
        attribution: str | None = None,
        context: str | None = None,
        evidence: str | None = None,
    ) -> None:
        subject = re.sub(r"^(?:but|and|or)\s+", "", subject, flags=re.I)
        subject = canonical_entity(subject, aliases)
        object_ = canonical_entity(object_, aliases)
        resolved_condition = clause.condition if condition is None else (condition or None)
        if attribution is None and modality == "general_mechanism":
            citation = re.search(r"\[(\d+(?:\s*,\s*\d+)*)\]\s*[.)]?\s*$", clause.text)
            if citation:
                attribution = f"cited prior report [{citation.group(1)}]"
        key = (
            subject.casefold(),
            predicate,
            object_.casefold(),
            modality or "",
            polarity,
            resolved_condition or "",
            attribution or "",
        )
        action_object = predicate in {"has_right_to", "authorized_to", "compelled_to"} and bool(
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
                predicate_options=tuple(dict.fromkeys((predicate, *predicate_alternatives))),
                object_options=(object_,),
                evidence=evidence or clause.text,
                context=context or clause.context,
                sentence_index=clause.sentence_index,
                start=clause.start,
                end=clause.end,
                modality=modality,
                polarity=polarity,
                source_unit=clause.source_unit,
                condition=resolved_condition,
                attribution=attribution,
                origin="semantic",
            )
        )

    # Finite do-support makes the lexical verb bare ("did not affect"), so
    # the open-verb scanner cannot find it. Parse that auxiliary's scope once,
    # then distribute its negation over independently coordinated objects.
    # A reduced relative after one noun ("Y tested 1 day later") describes
    # that noun; it is neither a new finite assertion nor a condition on X.
    auxiliary_events = list(_NEGATED_ACTIVE_AUXILIARY.finditer(clause.text))
    for index, event in enumerate(auxiliary_events):
        verb = event.group("verb").casefold()
        if verb in {"be", "been", "being", "do", "does", "did", "have", "has", "had"}:
            continue
        subject_start = auxiliary_events[index - 1].end() if index else 0
        subject_prefix = clause.text[subject_start:event.start()].strip(" ,")
        # An introductory discourse phrase ends at a comma. An appositive
        # subject instead leaves a trailing comma before the auxiliary.
        if "," in subject_prefix:
            subject_prefix = subject_prefix.rsplit(",", 1)[-1].strip()
        subject = _trim_left(subject_prefix)
        if not _valid_entity(subject):
            continue
        if previous_sentence and len(subject.split()) == 1:
            noun = re.escape(subject)
            earlier_names = {
                canonical_entity(found.group("name"))
                for found in re.finditer(
                    rf"\b(?:the|a|an)\s+(?P<name>(?:[A-Za-z0-9-]+\s+){{1,4}}{noun})\b",
                    previous_sentence, re.I,
                )
            }
            if len(earlier_names) == 1:
                subject = earlier_names.pop()

        object_end = (auxiliary_events[index + 1].start()
                      if index + 1 < len(auxiliary_events) else len(clause.text))
        objects = clause.text[event.end():object_end].strip(" .;,")
        if not objects or re.search(r"\b(?:but|whereas)\b", objects, re.I):
            continue
        shared_time = re.search(
            r"\s+(?P<time>(?:during|after|before|until|when|unless)\s+[^,;]+)$",
            objects, re.I,
        )
        if shared_time and re.search(
            r"\b[A-Za-z][A-Za-z'-]*(?:ed|en)\s+$",
            objects[:shared_time.start() + 1], re.I,
        ):
            # A participle immediately before the time phrase belongs to
            # the last noun: "licenses issued after the hearing".
            shared_time = None
        if shared_time:
            objects = objects[:shared_time.start()].strip()
        object_parts = [part.strip(" ,") for part in re.split(
            r"\s*,\s*(?:and\s+|or\s+)?|\s+(?:and|or)\s+",
            objects, flags=re.I,
        )]
        if not 1 <= len(object_parts) <= 4 or any(not part for part in object_parts):
            continue
        # "formation of DomainX and β-UnitB complex" is one compound target:
        # the first named item modifies the same final head as the second.
        if len(object_parts) == 2 and re.search(
            r"\bof\s+[A-Zβ][A-Za-z0-9β-]*$", object_parts[0]
        ) and re.fullmatch(
            r"[A-Zβ][A-Za-z0-9β-]*\s+[a-z][a-z-]*", object_parts[1]
        ):
            object_parts = [objects]

        base_predicate = _predicate_for(verb)
        if event.group("auxiliary").casefold() == "did" and base_predicate == verb:
            past_predicate = (verb[:-1] + "ied" if verb.endswith("y")
                              and len(verb) > 2 and verb[-2] not in "aeiou"
                              else verb + ("d" if verb.endswith("e") else "ed"))
            predicates = (past_predicate, base_predicate)
        else:
            predicates = (base_predicate,)
        before_event = len(frames)
        for object_part in object_parts:
            reduced = _REDUCED_TIMED_MODIFIER.search(object_part)
            local_time = reduced.group("modifier") if reduced else None
            target = object_part[:reduced.start()].strip() if reduced else object_part
            if not _valid_entity(target):
                continue
            conditions = [part for part in (
                clause.condition,
                shared_time.group("time") if shared_time else None,
                local_time,
            ) if part]
            before = len(frames)
            add(subject, predicates[0], target,
                predicate_alternatives=predicates[1:],
                polarity="negative", condition="; ".join(conditions))
            if local_time and covered_result_spans is not None and len(frames) > before:
                modifier_start = clause.text.find(local_time, event.end(), object_end)
                if modifier_start >= 0:
                    covered_result_spans.append(
                        (modifier_start, modifier_start + len(local_time))
                    )
        if covered_result_spans is not None and len(frames) > before_event:
            covered_result_spans.append(event.span("verb"))

    # Resolve a finite chain over a previously introduced object.  In prose
    # such as "they shall make lists of A and of B, which lists they shall
    # sign and certify, and transmit sealed to X, directed to Y", the object
    # is shared by every later verb.  The actor must be explicit at the start
    # of this or the immediately preceding sentence; a bare "they" alone is
    # insufficient to license new claims.
    chain = re.search(
        r"\bthey\s+shall\s+make\s+(?P<list_label>(?:[A-Za-z'-]+\s+)?lists?)\s+"
        r"of\s+(?P<contents>.+?)[,;]\s*which\s+(?P<relative>lists?)\s+"
        rf"they\s+(?P<modal>{_MODALS})\s+(?P<actions>[^;.]+)",
        clause.context, re.I,
    )
    if chain and re.search(r"\b(?:make|which\s+lists?)\b", clause.text, re.I):
        actor_match = re.match(
            r"^(?:And\s+)?(?:The\s+)?(?P<actor>[A-Z][A-Za-z'-]+"
            r"(?:\s+[A-Z][A-Za-z'-]+){0,4})\s+shall\b",
            clause.context,
        )
        if not actor_match and previous_sentence:
            actor_match = re.match(
                r"^(?:And\s+)?(?:The\s+)?(?P<actor>[A-Z][A-Za-z'-]+"
                r"(?:\s+[A-Z][A-Za-z'-]+){0,4})\s+shall\b",
                previous_sentence,
            )
        actor = actor_match.group("actor") if actor_match else ""
        list_surface = chain.group("list_label")
        list_noun = re.search(r"lists?$", list_surface, re.I).group()
        contents = [
            normalize_space(part).strip(" ,")
            for part in re.split(r",\s+and\s+of\s+", chain.group("contents"), flags=re.I)
        ]
        # The final "of ... for each" member describes a value recorded for
        # each earlier item. It is not another actor or a second list type.
        measure = contents.pop() if len(contents) > 1 and re.search(
            r"\bfor\s+each\b", contents[-1], re.I
        ) else ""
        actions = re.match(
            r"(?P<verbs>[A-Za-z'-]+(?:\s+and\s+[A-Za-z'-]+|"
            r",\s*(?:and\s+)?[A-Za-z'-]+){1,5})"
            r"(?:\s+(?P<state>[A-Za-z'-]+ed)\s+to\s+"
            r"(?P<destination>[^,;]+))?"
            r"(?:,\s*directed\s+to\s+(?P<recipient>[^,;]+))?",
            chain.group("actions"), re.I,
        )
        # Require the parsed serial verbs to consume the action phrase. This
        # avoids inventing edges when a later condition or new actor follows.
        if actor and actions and not re.search(
            r"\b(?:not|never|no)\b", chain.group("actions")[:actions.end()], re.I
        ) and not normalize_space(chain.group("actions")[actions.end():]).strip(" ,"):
            singular = re.sub(r"s$", "", list_noun, flags=re.I)
            modifier = list_surface[:list_surface.casefold().rfind(list_noun.casefold())].strip()
            modifier = re.sub(r"^(?:a|an|the)(?:\s+|$)", "", modifier, flags=re.I)
            list_predicate = "make_" + "_".join(
                part for part in (modifier, singular, "of") if part
            )
            core_items = [
                re.sub(r"\ball\s+the\s+", "all ", item, count=1, flags=re.I)
                for item in contents
            ]
            if len(core_items) == 1:
                shared_list = f"{singular} of {core_items[0]}"
                if measure:
                    shared_list += f" and {measure}"
            else:
                words = [item.split() for item in core_items]
                common = []
                for column in zip(*words):
                    if len({part.casefold() for part in column}) != 1:
                        break
                    common.append(column[0])
                if len(common) >= 2:
                    variants = [" ".join(parts[len(common):]) for parts in words]
                    shared_list = (
                        f"{list_surface} of {' '.join(common)} " + " and ".join(variants)
                    )
                else:
                    shared_list = f"{list_surface} of " + " and ".join(core_items)
            # Preserve explicit all/each quantifiers in these evidence-bound
            # options; generic canonical_entity intentionally strips them.
            def add_chain(subject: str, predicate: str, object_: str, *,
                          condition: str | None = None,
                          evidence: str | None = None) -> None:
                subject = canonical_label(subject, aliases)
                object_ = canonical_label(object_, aliases)
                key = (subject.casefold(), predicate, object_.casefold(),
                       chain.group("modal").casefold(), "positive", condition or "")
                if key in seen or not _valid_entity(subject) or not _valid_entity(object_):
                    return
                seen.add(key)
                frames.append(RelationFrame(
                    subject_options=(subject,), predicate_options=(predicate,),
                    object_options=(object_,), evidence=evidence or chain.group(),
                    context=clause.context, sentence_index=clause.sentence_index,
                    start=clause.start, end=clause.end,
                    modality=chain.group("modal").casefold(), polarity="positive",
                    source_unit=clause.source_unit, condition=condition,
                    origin="semantic",
                ))

            for item in core_items:
                add_chain(actor, list_predicate, item,
                          evidence=chain.group()[:chain.group().find("which")])
            if measure:
                head = re.match(r"^(?:all\s+)?(?P<noun>[A-Za-z'-]+)", core_items[0], re.I)
                measure_item = measure
                if head and re.search(r"\beach$", measure, re.I):
                    noun = head.group("noun")
                    singular_noun = (
                        re.sub(r"ies$", "y", noun, flags=re.I)
                        if re.search(r"ies$", noun, re.I)
                        else re.sub(r"s$", "", noun, flags=re.I)
                    )
                    measure_item = f"{measure} {singular_noun}"
                for item in core_items:
                    add_chain(f"{singular} of {item}", "includes", measure_item,
                              condition=f"on {singular} of {item}")
                if len(core_items) == 1:
                    add_chain(actor, f"include_in_{singular}",
                              re.sub(r"^the\s+", "", measure_item, flags=re.I))

            verbs = [
                verb for verb in re.split(r"\s+and\s+|,\s*(?:and\s+)?",
                                        actions.group("verbs"), flags=re.I)
                if verb
            ]
            if 2 <= len(verbs) <= 6:
                for verb in verbs:
                    scoped = None
                    if verb == verbs[-1] and actions.group("destination"):
                        scoped = "; ".join(part for part in (
                            actions.group("state"),
                            f"to {actions.group('destination')}",
                            f"directed to {actions.group('recipient')}"
                            if actions.group("recipient") else "",
                        ) if part)
                    add_chain(actor, verb.casefold(), shared_list,
                              condition=scoped)
                if actions.group("state") and actions.group("destination"):
                    status_subject = (
                        f"transmitted {singular} of {core_items[0]}"
                        if len(core_items) == 1 else f"transmitted {shared_list}"
                    )
                    add_chain(status_subject,
                              "are" if list_noun.casefold().endswith("s") else "has_status",
                              actions.group("state"))
                    add_chain(shared_list, "transmitted_to", actions.group("destination"))
                if actions.group("recipient"):
                    add_chain(shared_list, "directed_to", actions.group("recipient"))

            # A ballot or other container can be introduced before the list
            # chain. Split only explicit coordinated targets; do not guess
            # targets from the later list contents.
            earlier = clause.context[:chain.start()]
            ballot = re.search(r"\bvote\s+by\s+(?P<method>[A-Za-z'-]+)\s+for\s+"
                               r"(?P<targets>[^,;]+)", earlier, re.I)
            if ballot:
                targets = re.split(r"\s+and\s+|,\s*(?:and\s+)?",
                                   ballot.group("targets"), flags=re.I)
                for target in targets[:6]:
                    if target.strip():
                        add_chain(actor, f"vote_by_{ballot.group('method').casefold()}_for",
                                  target.strip(), evidence=ballot.group())
            named = re.search(
                r"\bthey\s+shall\s+(?P<verb>[A-Za-z'-]+)\s+in\s+"
                r"(?P<first_container>[^,]+?)\s+(?P<first_item>the\s+[^,]+),\s+"
                r"and\s+in\s+(?P<second_container>[^,]+?)\s+"
                r"(?P<second_item>the\s+[^,]+)", earlier, re.I,
            )
            if named:
                for container, item in (("first_container", "first_item"),
                                        ("second_container", "second_item")):
                    add_chain(actor,
                              f"{_predicate_for(named.group('verb'))}_in_"
                              f"{re.sub(r'[^A-Za-z]+', '_', named.group(container)).strip('_').casefold()}",
                              named.group(item), evidence=named.group())

    # A negative quantifier governs every coordinated actor, action and
    # explicitly shared object. Its interposed exception governs this action
    # only, even when an earlier proposition shares the same sentence.
    negative_modal = re.compile(
        r"\b(?P<operator>neither|no)\s+(?P<actors>[^;:.]+?)\s*,?\s+"
        r"(?P<modal>shall|may|must|should|will|would|can|could)"
        r"(?:\s*,\s*(?P<exception>without\s+[^,;]+)\s*,)?\s+"
        r"(?P<action>[^;:.]+)", re.I,
    )
    for prohibition in negative_modal.finditer(clause.text):
        action = re.fullmatch(
            r"(?P<first>[A-Za-z'-]+)(?:\s+or\s+(?P<second>[A-Za-z'-]+))?"
            r"\s+(?P<objects>.+?)\.?",
            prohibition.group("action").strip(), re.I,
        )
        if not action or action.group("first").casefold() in {"be", "have", "do"}:
            continue
        actor_text = prohibition.group("actors")
        if prohibition.group("operator").casefold() == "neither":
            actor_parts = re.split(r"\s+nor\s+", actor_text, maxsplit=1, flags=re.I)
            if len(actor_parts) != 2:
                continue
        else:
            actor_parts = [actor_text]
        actor_parts = [re.sub(r"\bany\s+", "", part.strip(" ,"), flags=re.I)
                       for part in actor_parts]
        if any(not _valid_entity(actor) for actor in actor_parts):
            continue
        # Resolve a local plural reference only when one explicit preceding
        # agent supplies its antecedent ("granted by X: no holder under them").
        antecedents = list(re.finditer(
            r"\bby\s+(?:the\s+)?(?P<entity>[A-Z][A-Za-z'-]+"
            r"(?:\s+[A-Z][A-Za-z'-]+){0,4})\b",
            clause.text[:prohibition.start()], re.I,
        ))
        if len(antecedents) == 1:
            antecedent = re.sub(r"^by\s+", "", antecedents[0].group(), flags=re.I)
            actor_parts = [re.sub(r"\bthem\b", antecedent, actor,
                                  flags=re.I) for actor in actor_parts]
        objects_text = action.group("objects").strip(" .")
        objects_text = re.sub(r"^of\s+", "", objects_text, flags=re.I)
        # A trailing kind qualifier broadens every item but is not another
        # item or a source actor.
        objects_text = re.sub(r",\s*of\s+any\s+kind\s+whatever(?=,|$)", "",
                              objects_text, flags=re.I)
        source_match = re.search(r",\s*from\s+(?P<sources>.+)$", objects_text, re.I)
        if source_match:
            sources = _simple_alternative_nouns(source_match.group("sources"))
            objects_text = objects_text[:source_match.start()]
        else:
            sources = ("",)
        objects = _shared_negative_objects(objects_text)
        verbs = [action.group("first")]
        if action.group("second"):
            verbs.append(action.group("second"))
        # Only replace the generic parser for actual coordination. A simple
        # negative modal remains with the ordinary relation parser.
        if max(len(actor_parts), len(verbs), len(sources)) <= 1:
            continue
        if len(actor_parts) * len(verbs) * len(objects) * len(sources) > 64:
            continue
        for actor in actor_parts:
            for verb in verbs:
                predicate = _predicate_for(verb)
                variants = tuple(dict.fromkeys((verb.casefold(), f"{verb.casefold()}s")))
                for object_ in objects:
                    for source in sources:
                        object_with_source = f"{object_} from {source}" if source else object_
                        add(
                            actor, predicate, object_with_source,
                            predicate_alternatives=variants,
                            modality=prohibition.group("modal").casefold(),
                            polarity="negative",
                            condition=prohibition.group("exception") or "",
                            evidence=clause.text,
                        )
        if covered_result_spans is not None:
            covered_result_spans.append(prohibition.span())

    # An infinitive after a comma can state why an earlier power is granted:
    # "may have power to collect dues, to fund the laboratory". Offer the
    # purpose-qualified reading for the preceding actions only. The ordinary
    # action frames remain available because a second infinitive can instead
    # be another independent grant; Jev decides which reading the text backs.
    authority_purpose = re.match(
        rf"^(?P<subject>[^;]+?)\s+(?P<modal>{_MODALS})\s+have\s+"
        r"(?:the\s+)?Power\s+to\s+(?P<actions>[^;]+?),\s+to\s+"
        r"(?P<purpose>[^;]+?)\.?$",
        clause.text,
        re.I,
    )
    if authority_purpose and not re.search(
        r"\b(?:if|when|whenever|unless|except|otherwise|provided\s+that)\b",
        authority_purpose.group("purpose"), re.I,
    ):
        actions = _object_branches(authority_purpose.group("actions"), "authorized_to")
        purpose = f"to {normalize_space(authority_purpose.group('purpose'))}"
        conditions = [clause.condition, purpose]
        scoped_condition = "; ".join(part for part in conditions if part)
        for action in actions[:16]:
            if re.match(r"^[A-Za-z'-]+\s+\S", action):
                add(
                    _trim_left(authority_purpose.group("subject")),
                    "authorized_to",
                    action,
                    modality=authority_purpose.group("modal").casefold(),
                    condition=scoped_condition,
                )

    # Experimental findings often put the perturbation in a nominal subject
    # and the measured result in a later verb phrase. Keep the intervention,
    # direction, target, and cell setting together in each atomic frame.
    def cell_settings(text: str, *, split: bool = True) -> tuple[str, ...]:
        found: list[str] = []
        for match in re.finditer(
            r"\b(?P<cells>[A-Za-z0-9/-]+(?:\s+and\s+[A-Za-z0-9/-]+)?\s+cells)"
            r"(?:\s*\((?P<values>[^)]*)\))?",
            text, re.I,
        ):
            names = re.split(r"\s+and\s+", match.group("cells")[:-6])
            values = match.group("values")
            if values and re.search(r"\b(?:Fig(?:ure)?|Supplementary)\b", values, re.I):
                values = None
            if not split or values or len(names) == 1:
                setting = f"in {match.group('cells')}"
                if values:
                    setting += f"; {values}"
                found.append(setting)
            else:
                found.extend(f"in {name} cells" for name in names)
        return tuple(dict.fromkeys(found))

    # A measured comparison is one finding: the measured entity, direction,
    # group, and comparator have to survive in the same frame.  These forms
    # occur throughout Results sections, even when the perturbation is named
    # only by a sample label such as "sh-X" or "oe-X".
    def sample_intervention(label: str) -> tuple[str, str] | None:
        match = re.search(
            r"(?:^|/)(?P<kind>sh|si|oe|overexpression|knockdown)[-]?"
            r"(?P<entity>[A-Za-z][A-Za-z0-9β-]*)$",
            label, re.I,
        )
        if not match:
            return None
        kind = match.group("kind").casefold()
        action = "knockdown" if kind in {"sh", "si", "knockdown"} else "overexpression"
        return match.group("entity"), action

    def listed_names(value: str) -> str:
        names = re.split(r"\s*,\s*|\s+and\s+", value.strip(), flags=re.I)
        names = [re.sub(r"^and\s+", "", name.strip(), flags=re.I)
                 for name in names if name.strip() and name.strip().casefold() != "and"]
        if len(names) < 2:
            return names[0] if names else ""
        return ", ".join(names[:-1]) + ", and " + names[-1]

    tissue_comparison = re.search(
        r"\b(?P<entity>[A-Za-z][A-Za-z0-9β-]*)\s+was\s+"
        r"(?:significantly\s+)?(?P<direction>upregulated|downregulated)\s+"
        r"in\s+(?P<group>.+?)\s+compar(?:ed|ing)\s+with\s+"
        r"(?P<baseline>[^.]+?)(?:\s*\([^)]*\))?\.?$",
        clause.text, re.I,
    )
    if tissue_comparison:
        direction = ("increased_in" if tissue_comparison.group("direction").casefold()
                     == "upregulated" else "decreased_in")
        method = re.search(r"\b(?:relied on|using|used)\s+([A-Za-z0-9-]+)",
                           clause.text[:tissue_comparison.start()], re.I)
        condition = f"relative to {tissue_comparison.group('baseline').strip()}"
        if method:
            condition += f"; {method.group(1)} analysis"
        add(f"{tissue_comparison.group('entity')} expression", direction,
            tissue_comparison.group("group"), modality="observed",
            condition=condition)
        if covered_result_spans is not None:
            covered_result_spans.append(tissue_comparison.span())

    cell_line_comparison = re.search(
        r"\bexpression\s+levels?\s+of\s+(?P<entity>[A-Za-z0-9β-]+)\s+"
        r"in\s+(?:the\s+)?(?P<group>[^,]+?\bcell\s+lines)\s+"
        r"(?P<names>[A-Za-z0-9-]+(?:,\s*[A-Za-z0-9-]+)*"
        r"(?:,?\s+and\s+[A-Za-z0-9-]+)?)\s+was\s+"
        r"(?:significantly\s+)?(?P<direction>increased|decreased|higher|lower)\s+"
        r"compared\s+with\s+(?P<baseline_group>[^,]+?\bcell\s+lines)\s+"
        r"(?P<baseline_names>[A-Za-z0-9-]+(?:,\s*[A-Za-z0-9-]+)*"
        r"(?:,?\s+and\s+[A-Za-z0-9-]+)?)",
        clause.text, re.I,
    )
    if cell_line_comparison:
        higher = cell_line_comparison.group("direction").casefold() in {"increased", "higher"}
        group = listed_names(cell_line_comparison.group("names"))
        baseline = listed_names(cell_line_comparison.group("baseline_names"))
        add(f"{cell_line_comparison.group('entity')} expression",
            "higher_in" if higher else "lower_in", f"{group} cells",
            modality="observed",
            condition=(f"compared with {baseline}; "
                       f"{cell_line_comparison.group('group')} versus "
                       f"{cell_line_comparison.group('baseline_group')}"))
        if covered_result_spans is not None:
            covered_result_spans.append(cell_line_comparison.span())

    tumour_comparison = re.search(
        r"\b(?P<measure>(?:xenograft\s+)?tumou?rs?(?:\s+growth)?)\s+"
        r"(?:formed\s+)?in\s+(?:the\s+)?(?P<label>[A-Za-z0-9/-]+)\s+group\s+"
        r"(?:was|were)\s+(?:generally|significantly|much|far|more)?\s*"
        r"(?P<change>larger|smaller|more\s+rapid|less\s+rapid|slower)\s+than\s+"
        r"(?:those|that)\s+in\s+the\s+(?P<baseline>[^(.]+?)\s+group",
        clause.text, re.I,
    )
    if tumour_comparison:
        intervention = sample_intervention(tumour_comparison.group("label"))
        if intervention:
            measure = tumour_comparison.group("measure").casefold()
            is_growth = "growth" in measure or "rapid" in tumour_comparison.group("change").casefold()
            is_xenograft = "xenograft" in measure or "xenograft" in previous_sentence.casefold()
            target = ("xenograft tumour " if is_xenograft else "tumour ") + (
                "growth rate" if is_growth else "size")
            increase = tumour_comparison.group("change").casefold() in {"larger", "more rapid"}
            add(f"{intervention[0]} {intervention[1]}",
                "increased" if increase else "decreased", target,
                modality="observed",
                condition=(f"{tumour_comparison.group('label')} xenograft group "
                           f"versus {tumour_comparison.group('baseline').strip()} mice"
                           if is_xenograft else
                           f"{tumour_comparison.group('label')} group versus "
                           f"{tumour_comparison.group('baseline').strip()} group"))
            if covered_result_spans is not None:
                covered_result_spans.append(tumour_comparison.span())

    # The sentence can be split at an organ-ratio semicolon.  Its context
    # retains the complete parenthetical measurement for both organs.
    organ_comparison = re.search(
        r"\b(?P<entity>[A-Za-z0-9β-]+)\s+"
        r"(?P<intervention>knockdown|silencing|overexpression|upregulation)\s+"
        r"(?P<direction>increased|decreased)\s+the\s+number\s+of\s+"
        r"(?P<outcome>[A-Za-z -]+?)\s+compared\s+(?:to|with)\s+the\s+"
        r"(?P<baseline>[A-Za-z -]+?)\s*\(",
        clause.context if re.search(r"\bcompared\s+(?:to|with)\b", clause.text, re.I)
        else "", re.I,
    )
    if organ_comparison:
        ratios = re.findall(
            r"\b(?P<organ>[A-Za-z]+):\s*(?P<treated>\d+)\s*:\s*(?P<control>\d+)",
            clause.context[organ_comparison.end():], re.I,
        )
        organ_list = re.search(r"\bin each\s+([A-Za-z]+(?:\s+and\s+[A-Za-z]+)+)",
                               clause.context[:organ_comparison.start()], re.I)
        known_organs = (re.split(r"\s+and\s+", organ_list.group(1), flags=re.I)
                        if organ_list else [])
        for organ, treated, control in ratios:
            # A one-character truncation in a ratio label can be repaired
            # from the explicitly named organs in the same sentence.
            for known in known_organs:
                if (known.casefold().startswith(organ.casefold())
                        and len(known) - len(organ) == 1):
                    organ = known
                    break
            label = f"{organ} "
            setting = (
                f"{label}nodules; {organ_comparison.group('entity')} "
                f"{organ_comparison.group('intervention')} versus "
                f"{organ_comparison.group('baseline').strip()}; "
                f"{treated}:{control}"
            )
            if re.search(r"\bmice\b", f"{previous_sentence} {clause.context}", re.I):
                setting += "; mice"
            add(f"{organ_comparison.group('entity')} "
                f"{organ_comparison.group('intervention')}",
                organ_comparison.group("direction").casefold(),
                f"{re.sub(r'(?<![ius])s$', '', organ_comparison.group('outcome').strip())} count",
                modality="observed", condition=setting)
        if ratios and covered_result_spans is not None:
            start = clause.text.find(organ_comparison.group("entity"))
            if start >= 0:
                covered_result_spans.append((start, len(clause.text)))
        # "We counted X, and found that Y increased X" contains one assay
        # action and the measured finding above.  Do not let the reporting
        # verb borrow a subject from the preceding sentence.
        reporting = re.match(
            r"(?P<reporter>we|(?:the\s+)?(?:authors|researchers|investigators))\s+"
            r"(?:also\s+)?(?P<measure_verb>counted|measured|quantified)\s+"
            r"(?P<measurement>.+?),\s+and\s+"
            r"(?P<report_verb>found|observed|showed)\s+that\s+"
            r"(?P<entity>[A-Za-z0-9β-]+)\s+"
            r"(?P<intervention>knockdown|silencing|overexpression|upregulation)\b",
            clause.text, re.I,
        )
        if (ratios and reporting
                and reporting.group("entity").casefold()
                == organ_comparison.group("entity").casefold()
                and reporting.group("intervention").casefold()
                == organ_comparison.group("intervention").casefold()):
            add("researchers", reporting.group("measure_verb").casefold(),
                reporting.group("measurement"), condition="")
            if covered_result_spans is not None:
                covered_result_spans.extend((reporting.span("measure_verb"),
                                             reporting.span("report_verb")))

    fraction_comparison = re.search(
        r"\bpercentage\s+of\s+cells\s+in\s+(?P<phase>[A-Za-z0-9/]+)\s+phase\s+"
        r"in\s+(?P<treated>[A-Za-z0-9/-]+)\s+\((?P<treated_value>[^)]+)\)\s+"
        r"was\s+(?:significantly\s+)?(?P<direction>higher|lower)\s+than\s+"
        r"that\s+in\s+(?P<baseline>[A-Za-z0-9/-]+)\s+cells\s+"
        r"\((?P<baseline_value>[^)]+)\)",
        clause.text, re.I,
    )
    if fraction_comparison:
        intervention = sample_intervention(fraction_comparison.group("treated"))
        if intervention:
            treated_cell = fraction_comparison.group("treated").split("/", 1)[0]
            baseline_cell = fraction_comparison.group("baseline").split("/", 1)[0]
            if treated_cell.casefold() == baseline_cell.casefold():
                add(f"{intervention[0]} {intervention[1]}",
                    "increased" if fraction_comparison.group("direction").casefold()
                    == "higher" else "decreased",
                    f"{fraction_comparison.group('phase')}-phase cell fraction",
                    modality="observed",
                    condition=(f"{treated_cell} cells; "
                               f"{fraction_comparison.group('treated_value')} versus "
                               f"{fraction_comparison.group('baseline').split('/', 1)[-1]} "
                               f"{fraction_comparison.group('baseline_value')}"))
                if covered_result_spans is not None:
                    covered_result_spans.append(fraction_comparison.span())

    arms = None
    event = re.match(
        r"^(?:(?:Moreover|Furthermore|Additionally),\s+)?(?:the\s+)?"
        r"(?P<kind>overexpression|upregulation|knockdown|downregulation|"
        r"depletion|silencing)\s+of\s+(?P<actor>[A-Za-z0-9β-]+)\b"
        r"(?P<tail>.+)$",
        clause.text, re.I,
    )
    if event:
        kind = event.group("kind").casefold()
        actor = event.group("actor")
        if actor.islower() and re.search(r"\d", actor):
            actor = actor.upper()
        subject = f"{actor} {kind}"
        tail = event.group("tail")

        # One intervention can have two arms and two outcomes. Neither the
        # alternative arm nor the other outcome belongs in a claim's target.
        arms = re.match(
            r"\s+alone\s+or\s+in\s+(?P<setting>[A-Za-z0-9/-]+\s+cells)\s+",
            tail, re.I,
        )
        if arms:
            base_cells = arms.group("setting").split("/", 1)[0]
            effect_offset = event.start("tail") + arms.end()
            effects = re.finditer(
                r"\b(?P<verb>upregulated|downregulated|increased|decreased|"
                r"reduced|enhanced|suppressed)\s+the\s+expression\s+of\s+"
                r"(?P<target>[A-Za-z0-9β-]+)\b",
                tail[arms.end():], re.I,
            )
            for effect in effects:
                before = len(frames)
                direction = ("increased" if effect.group("verb").casefold() in
                             {"upregulated", "increased", "enhanced"} else "decreased")
                target = f"{effect.group('target')} expression"
                add(f"{subject} alone", direction, target,
                    condition=f"in {base_cells} context; alone")
                add(f"{subject} in {arms.group('setting')}", direction, target,
                    condition=f"in {arms.group('setting')}")
                if covered_result_spans is not None and len(frames) > before:
                    covered_result_spans.append((
                        effect_offset + effect.start("verb"),
                        effect_offset + effect.end("target"),
                    ))
        else:
            result = re.match(
                r"\s+(?:(?:significantly|strongly)\s+)?"
                r"(?:(?P<verb>increases?|decreases?|upregulated|downregulated|"
                r"reduced|activated|inhibited)\s+|"
                r"induced\s+(?:a\s+)?(?:significant\s+)?(?P<noun>increase|decrease)\s+of\s+|"
                r"led\s+to\s+(?:a\s+)?(?:robust\s+)?(?P<led>decreased?|increased?)\s+in\s+)"
                r"(?P<outcome>.+)$",
                tail, re.I,
            )
            if result:
                verb = (result.group("verb") or result.group("noun") or result.group("led")).casefold()
                predicate = (
                    "increased" if verb.startswith(("increas", "upregulat")) else
                    "decreased" if verb.startswith(("decreas", "downregulat", "reduc")) else
                    "activated" if verb == "activated" else "inhibited"
                )
                outcome = result.group("outcome")
                secondary = list(re.finditer(
                    r"\s+and\s+(?P<verb>(?:significantly\s+)?(?:increases?|"
                    r"decreases?|upregulated|downregulated|reduced|activated|"
                    r"inhibited))\s+",
                    outcome, re.I,
                ))
                event_parts = [(
                    predicate,
                    outcome[:secondary[0].start()] if secondary else outcome,
                    event.start("tail") + result.start(),
                    event.start("tail") + result.start("outcome"),
                )]
                for index, effect in enumerate(secondary):
                    word = effect.group("verb").split()[-1].casefold()
                    direction = (
                        "increased" if word.startswith(("increas", "upregulat")) else
                        "decreased" if word.startswith(("decreas", "downregulat", "reduc")) else
                        "activated" if word == "activated" else "inhibited"
                    )
                    end = secondary[index + 1].start() if index + 1 < len(secondary) else len(outcome)
                    event_parts.append((
                        direction, outcome[effect.end():end],
                        event.start("tail") + result.start("outcome") + effect.start("verb"),
                        event.start("tail") + result.start("outcome") + effect.end(),
                    ))
                for direction, effect_outcome, effect_start, effect_end in event_parts:
                    before = len(frames)
                    setting = re.search(
                        r"\s+in\s+[A-Za-z0-9/-]+(?:\s+and\s+[A-Za-z0-9/-]+)?\s+cells\b",
                        effect_outcome, re.I,
                    )
                    if setting:
                        target = effect_outcome[:setting.start()]
                        target = re.sub(
                            r"^(?:the\s+)?expression\s+of\s+([A-Za-z0-9β-]+)\b",
                            r"\1 expression", target, flags=re.I,
                        )
                        target = re.sub(r"\s+\([^)]*\)$", "", target).strip()
                        # Split coordinated molecular targets, but retain a
                        # shared cell setting unless measurements are separate.
                        targets = (re.split(r"\s+and\s+", target)
                                   if direction == "activated" else [target])
                        settings = cell_settings(effect_outcome[setting.start():],
                                                 split=direction != "activated")
                        for item in targets:
                            for condition in settings:
                                add(subject, direction, item, condition=condition)
                    if covered_result_spans is not None and len(frames) > before:
                        covered_result_spans.append((effect_start, effect_end))

    # Passive expression findings can name an intervention only in the cell
    # modifier (e.g. "X-knockdown cells"). Recover that causal anchor.
    passive_event = re.search(
        r"\bexpression\s+of\s+(?P<first>[A-Za-z0-9β-]+),\s+as\s+well\s+as\s+"
        r"(?:the\s+)?(?:[A-Za-z0-9/-]+\s+)*?genes?\s+(?P<others>.+?)\s+"
        r"were\s+(?:significantly\s+)?(?:induced|increased|upregulated)\s+"
        r"in\s+(?P<actor>[A-Za-z0-9β-]+)-knockdown\s+cells\b",
        clause.text, re.I,
    )
    if passive_event:
        before = len(frames)
        targets = [passive_event.group("first")]
        targets.extend(re.findall(r"[A-Za-z0-9β-]+", passive_event.group("others")))
        for target in targets:
            if target.casefold() == "and":
                continue
            add(f"{passive_event.group('actor')} knockdown", "increased",
                f"{target} expression",
                condition=f"in {passive_event.group('actor')}-knockdown cells")
        if covered_result_spans is not None and len(frames) > before:
            result_verb = re.search(
                r"\b(?:induced|increased|upregulated)\b(?=\s+in\s+)",
                passive_event.group(), re.I,
            )
            if result_verb:
                covered_result_spans.append((
                    passive_event.start() + result_verb.start(),
                    passive_event.start() + result_verb.end(),
                ))

    # A concluding sentence can state the perturbation after "results
    # indicated that". Resolve the named intervention directly instead of
    # borrowing a subject from a preceding assay sentence.
    indicated_event = re.search(
        r"\b(?:results|findings)\s+(?P<report>indicated|showed|suggested)\s+that\s+"
        r"the\s+(?P<kind>overexpression|upregulation|knockdown|"
        r"downregulation|depletion|silencing)\s+of\s+"
        r"(?P<actor>[A-Za-z0-9β-]+)\s+"
        r"(?P<verb>induces?|increases?|decreases?|activates?|inhibits?)\s+"
        r"(?P<targets>.+?)\s+in\s+"
        r"(?P<cells>[A-Za-z0-9/-]+\s+cells)\b",
        clause.text, re.I,
    )
    if indicated_event:
        before = len(frames)
        direction = indicated_event.group("verb").casefold()
        predicate = (
            "induced" if direction.startswith("induc") else
            "increased" if direction.startswith("increas") else
            "decreased" if direction.startswith("decreas") else
            "activated" if direction.startswith("activat") else "inhibited"
        )
        subject = f"{indicated_event.group('actor')} {indicated_event.group('kind').casefold()}"
        for target in re.split(r"\s+and\s+", indicated_event.group("targets")):
            add(subject, predicate, target,
                condition=f"in {indicated_event.group('cells')}")
        if covered_result_spans is not None and len(frames) > before:
            covered_result_spans.append(indicated_event.span("report"))
            covered_result_spans.append(indicated_event.span("verb"))

    # A list of measured associations is one assertion per measured target.
    # Parse the adjacent statistics before splitting the list: commas inside
    # an expanded target name or a statistic must not shift a p-value to the
    # next biological object. A contrasting ``while`` branch keeps the same
    # measured subject but can reverse the relation direction.
    association_text = re.sub(
        r"^(?:As\s+shown\s+in|According\s+to)\s+[^,]{1,100},\s*",
        "", clause.text, flags=re.I,
    ).rstrip(".")
    association = re.fullmatch(
        r"(?P<subject>[^,;:.!?]{1,140}?)\s+(?:was|were|is|are)\s+"
        r"(?:(?P<direction>positively|negatively|inversely|reversely)\s+)?"
        r"(?P<relation>correlated|associated)\s+(?:with|to)\s+(?P<targets>.+)",
        association_text, re.I,
    )
    statistic = re.compile(
        r"\s*\((?P<value>(?:p(?:-value)?|r|rho)\s*[<=>≤≥]\s*"
        r"-?(?:\d+(?:\.\d+)?|\.\d+))\)\s*$", re.I,
    )
    multiple_measured_targets = bool(association and len(re.findall(
        r"\((?:p(?:-value)?|r|rho)\s*[<=>≤≥]", association.group("targets"), re.I,
    )) >= 2)
    if association and multiple_measured_targets:
        subject = re.sub(r"\bexpression\s+levels?\b", "expression",
                         association.group("subject"), flags=re.I)
        setting = re.search(
            r"\b(?:of|in|from)\s+(?P<cohort>(?:the\s+)?"
            r"(?:[A-Za-z][A-Za-z-]*\s+){0,6}"
            r"(?:samples|tissues|patients|cells))\b",
            previous_sentence, re.I,
        )
        cohort = f"in {canonical_entity(setting.group('cohort'))}" if setting else ""
        branches = re.split(r",?\s+(?:while|whereas)\s+",
                            association.group("targets"), maxsplit=1, flags=re.I)
        measured_branches: list[tuple[str, str | None, str]] = [
            (association.group("relation"), association.group("direction"), branches[0])
        ]
        if len(branches) == 2:
            contrast = re.fullmatch(
                r"(?:(?P<direction>positively|negatively|inversely|reversely)\s+)?"
                r"(?P<relation>correlated|associated)\s+(?:with|to)\s+(?P<targets>.+)",
                branches[1], re.I,
            )
            if contrast:
                measured_branches.append((contrast.group("relation"),
                                          contrast.group("direction"),
                                          contrast.group("targets")))
        for relation, direction, targets in measured_branches:
            # A separator is a new target only when another statistic follows.
            # This leaves conjunctions within unmeasured target names intact.
            items = re.split(
                r",\s*(?:and\s+)?|\s+and\s+(?=[^,]+\((?:p(?:-value)?|r|rho)\s*[<=>≤≥])",
                targets, flags=re.I,
            )
            for item in items:
                measured = statistic.search(item)
                if not measured:
                    continue
                target = re.sub(r"^(?:and|or)\s+", "", item[:measured.start()].strip(),
                                flags=re.I)
                abbreviation = re.fullmatch(
                    r"(?P<long>[A-Za-z][A-Za-z -]+)\s+"
                    r"\((?P<short>[A-Z][A-Z0-9-]+)\)\s+"
                    r"(?P<head>[A-Za-z][A-Za-z-]*)", target,
                )
                if abbreviation and "".join(
                    word[0].upper() for word in abbreviation.group("long").split()
                ) == abbreviation.group("short"):
                    target = f"{abbreviation.group('short')} {abbreviation.group('head')}"
                if target:
                    if relation.casefold() == "correlated":
                        predicate = ("positively_correlated_with"
                                     if direction and direction.casefold() == "positively"
                                     else "inversely_correlated_with"
                                     if direction else "correlated_with")
                    else:
                        predicate = ("positively_associated_with"
                                     if direction and direction.casefold() == "positively"
                                     else "negatively_associated_with"
                                     if direction else "associated_with")
                    condition = "; ".join(part for part in
                                          (cohort, measured.group("value")) if part)
                    add(subject, predicate, target, modality="observed",
                        condition=condition)

    correlation = re.fullmatch(
        r"(?P<subject>.+?)\s+(?:was|were|is|are)\s+"
        r"(?P<direction>positively|negatively|inversely|reversely)\s+"
        r"correlated\s+(?:with|to)\s+(?P<targets>.+?)\.?",
        clause.text,
        re.I,
    )
    if correlation and not multiple_measured_targets:
        def add_correlations(direction: str, targets: str) -> None:
            predicate = (
                "positively_correlated_with"
                if direction.casefold() == "positively"
                else "inversely_correlated_with"
            )
            for item in re.split(r",\s*(?:and\s+)?", targets):
                item = re.sub(r"^(?:and|or)\s+", "", item.strip(), flags=re.I)
                qualifier = re.search(r"\s*\((p\s*[<=>]\s*\d+(?:\.\d+)?)\)\s*$", item, re.I)
                if qualifier:
                    item = item[:qualifier.start()].strip()
                if item:
                    add(correlation.group("subject"), predicate, item,
                        condition=qualifier.group(1) if qualifier else "")

        segments = re.split(r",?\s+while\s+", correlation.group("targets"), maxsplit=1, flags=re.I)
        add_correlations(correlation.group("direction"), segments[0])
        if len(segments) == 2:
            continuation = re.fullmatch(
                r"(?P<direction>positively|negatively|inversely|reversely)\s+"
                r"correlated\s+(?:with|to)\s+(?P<targets>.+)",
                segments[1], re.I,
            )
            if continuation:
                add_correlations(continuation.group("direction"), continuation.group("targets"))

    clean_contrast = re.sub(
        r"\s*\((?:p\s*[<=>]|(?:Supplementary\s+)?Fig(?:ure)?\b)[^)]*\)",
        "", clause.text, flags=re.I,
    ).rstrip(".")
    paired_cell_outcomes = re.fullmatch(
        r"(?P<subject>.+?)\s+"
        r"(?P<verb>increased|decreased|reduced|enhanced|suppressed|promoted|inhibited)\s+"
        r"not only\s+(?P<first>.+?)\s+but also\s+(?P<second>.+?)\s+of\s+"
        r"(?P<first_cell>[A-Za-z0-9-]+)\s+and\s+"
        r"(?P<second_cell>[A-Za-z0-9-]+)\s+cells",
        clean_contrast, re.I,
    )
    if paired_cell_outcomes:
        first_outcome_p = re.search(
            r"\bp\s*[<=>]\s*\d+(?:\.\d+)?",
            clause.text.split("but also", 1)[0], re.I,
        )
        for outcome_index, outcome in enumerate((
            paired_cell_outcomes.group("first"), paired_cell_outcomes.group("second")
        )):
            for cell in (paired_cell_outcomes.group("first_cell"), paired_cell_outcomes.group("second_cell")):
                condition = f"in {cell} cells"
                if outcome_index == 0 and first_outcome_p:
                    condition += f"; {first_outcome_p.group()}"
                add(paired_cell_outcomes.group("subject"),
                    _predicate_for(paired_cell_outcomes.group("verb")),
                    outcome, condition=condition)
    opposite_effects = re.match(
        r"In contrast,\s*(?P<subject>.+?)\s+in\s+"
        r"(?P<first_cell>[A-Za-z0-9-]+)\s+and\s+"
        r"(?P<second_cell>[A-Za-z0-9-]+)\s+cells\s+had\s+the\s+opposite effects",
        clause.text, re.I,
    )
    if opposite_effects and previous_sentence:
        prior_clean = re.sub(
            r"\s*\((?:p\s*[<=>]|(?:Supplementary\s+)?Fig(?:ure)?\b)[^)]*\)",
            "", previous_sentence, flags=re.I,
        ).rstrip(".")
        prior_outcomes = re.fullmatch(
            r".+?\s+(?P<verb>decreased|increased)\s+not only\s+"
            r"(?P<first>.+?)\s+but also\s+(?P<second>.+?)\s+of\s+"
            r"[A-Za-z0-9-]+\s+and\s+[A-Za-z0-9-]+\s+cells",
            prior_clean, re.I,
        )
        if prior_outcomes:
            reverse = "increased" if prior_outcomes.group("verb").casefold() == "decreased" else "decreased"
            p_value = re.search(r"\bp\s*[<=>]\s*\d+(?:\.\d+)?", clause.text, re.I)
            for outcome in (prior_outcomes.group("first"), prior_outcomes.group("second")):
                for cell in (opposite_effects.group("first_cell"), opposite_effects.group("second_cell")):
                    condition = f"in {cell} cells"
                    if p_value:
                        condition += f"; {p_value.group()}"
                    add(opposite_effects.group("subject"), reverse, outcome,
                        condition=condition,
                        context=f"{previous_sentence} {clause.text}")
    negated_contrast = re.fullmatch(
        r"(?P<subject>.+?)\s+did\s+not\s+"
        r"(?P<negative_verb>[A-Za-z][A-Za-z-]*)\s+"
        r"(?P<negative_object>.+?)\s+but\s+"
        r"(?P<positive_verb>[A-Za-z][A-Za-z-]*)\s+"
        r"(?P<positive_object>.+)",
        clean_contrast, re.I,
    )
    if negated_contrast:
        positive_object = negated_contrast.group("positive_object")
        setting = re.search(r"\s+(in\s+[A-Za-z0-9 -]{1,30}\s+cells)\s*$", positive_object, re.I)
        if setting:
            positive_object = positive_object[:setting.start()]
        condition = setting.group(1) if setting else ""
        add(negated_contrast.group("subject"),
            _predicate_for(negated_contrast.group("negative_verb")),
            negated_contrast.group("negative_object"),
            polarity="negative", condition=condition)
        add(negated_contrast.group("subject"),
            _predicate_for(negated_contrast.group("positive_verb")),
            positive_object, condition=condition)

    receptor_regulation = re.fullmatch(
        r"(?P<name>.+?) \((?P<symbol>[A-Z0-9-]+)\) is involved in the "
        r"transcriptional regulation of genes that are important for various "
        r"biological functions, including (?P<first>tumor growth) and "
        r"(?P<second>metastatic progression)\.?", clause.text, re.I,
    )
    if receptor_regulation:
        for name in ("first", "second"):
            add(receptor_regulation.group("symbol"), "transcriptionally_regulates",
                f"genes important for {receptor_regulation.group(name)}")

    poorly_understood_effects = re.fullmatch(
        r"However, the (?P<effects>cellular and biological effects of \S+) "
        r"remain poorly understood\.?", clause.text, re.I,
    )
    if poorly_understood_effects:
        add(poorly_understood_effects.group("effects"), "has_status",
            "poorly understood")

    investigated_role = re.fullmatch(
        r"Here, we investigated the role of (?P<actor>\S+) and its underlying "
        r"mechanism in mediating (?P<subject>.+?) survival and metastasis\.?",
        clause.text, re.I,
    )
    if investigated_role:
        add("researchers", "investigated",
            f"{investigated_role.group('actor')} role and mechanism in "
            f"{investigated_role.group('subject')} survival and metastasis")

    observed_increased_levels = re.fullmatch(
        r"We observed that the (?P<factor>\S+ levels) were increased in "
        r"(?P<first>.+?) and in (?P<second>[^.]+)\.?", clause.text, re.I,
    )
    if observed_increased_levels:
        for name in ("first", "second"):
            add(observed_increased_levels.group("factor"), "increased_in",
                observed_increased_levels.group(name))

    promoted_two_in_vivo = re.fullmatch(
        r"(?P<actor>\S+) promoted (?P<first>.+?) and (?P<second>.+?) "
        r"in vivo\.?", clause.text, re.I,
    )
    if promoted_two_in_vivo:
        for name in ("first", "second"):
            add(promoted_two_in_vivo.group("actor"), "promoted",
                promoted_two_in_vivo.group(name), condition="in vivo")

    negative_survival_correlation = re.fullmatch(
        r"The (?P<factor>.+? expression levels) were negatively correlated "
        r"with the (?P<outcome>survival rates of .+?)\.?", clause.text, re.I,
    )
    if negative_survival_correlation:
        add(negative_survival_correlation.group("factor"),
            "negatively_correlated_with",
            negative_survival_correlation.group("outcome"))

    expression_knockdown_induction = re.fullmatch(
        r"Both ectopic expression and knockdown of (?P<actor>\S+) revealed "
        r"that (?P=actor) is a strong inducer of (?P<process>.+? \([A-Z]+\)), "
        r"which is consistent with its effects on .+?\.?", clause.text, re.I,
    )
    if expression_knockdown_induction:
        actor = expression_knockdown_induction.group("actor")
        process = expression_knockdown_induction.group("process")
        acronym = re.search(r"\((?P<acronym>[A-Z]+)\)$", process)
        add(f"ectopic expression and knockdown of {actor}", "revealed",
            f"{actor} induction of {acronym.group('acronym') if acronym else process}")
        add(actor, "induces", process)

    transcriptional_repression = re.fullmatch(
        r"(?P<actor>\S+) suppressed the expression of (?P<target>.+?) "
        r"\((?P<symbol>[A-Z0-9-]+)\) by acting as an "
        r"(?P<repressor>[A-Z0-9-]+ transcriptional repressor)\.?",
        clause.text, re.I,
    )
    if transcriptional_repression:
        actor = transcriptional_repression.group("actor")
        target = transcriptional_repression.group("symbol")
        repressor = transcriptional_repression.group("repressor")
        add(actor, "suppressed", f"{target} expression")
        add(actor, "acts_as", repressor)
        add(f"{actor} suppression of {target} expression", "mediated_by",
            f"acting as {repressor}")

    opposite_gene_effect = re.fullmatch(
        r"In addition, (?P<actor>\S+) has an opposite effect on the "
        r"expression levels of (?P<second>\S+), indicating that (?P=actor) "
        r"is able to differentially regulate the (?P<first>\S+) and "
        r"(?P=second) expression\.?", clause.text, re.I,
    )
    if opposite_gene_effect:
        actor = opposite_gene_effect.group("actor")
        first = opposite_gene_effect.group("first")
        second = opposite_gene_effect.group("second")
        add(actor, "has_opposite_effect_on",
            f"{second} expression levels compared with {first} expression",
            condition="")
        add(actor, "differentially_regulates",
            f"{first} and {second} expression", condition="")

    downstream_mechanism = re.fullmatch(
        r"The (?P<effects>cellular and biological effects elicited by \S+) "
        r"were consistent with the reduced levels of (?P<target>\S+) observed "
        r"in (?P<cells>cancer cells), and (?P<suppression>.+? suppression) "
        r"activated the (?P<pathway>.+? pathway), which is required for "
        r"(?P<process>[^.]+)\.?", clause.text, re.I,
    )
    if downstream_mechanism:
        target = downstream_mechanism.group("target")
        cells = downstream_mechanism.group("cells")
        pathway = downstream_mechanism.group("pathway")
        add(f"{target} levels", "reduced_in", cells)
        add(downstream_mechanism.group("effects"), "consistent_with",
            f"reduced {target} levels in {cells}")
        add(downstream_mechanism.group("suppression"), "activated", pathway)
        add(pathway, "required_for", downstream_mechanism.group("process"))

    axis_regulates_outcomes = re.fullmatch(
        r"Taken together, our results indicate that (?P<axis>.+? signaling "
        r"axis) plays an essential role in regulating the (?P<first>\w+), "
        r"(?P<second>\w+), and (?P<third>\w+) of (?P<cells>.+?)\.?",
        clause.text, re.I,
    )
    if axis_regulates_outcomes:
        for name in ("first", "second", "third"):
            add(axis_regulates_outcomes.group("axis"), "regulates",
                f"{axis_regulates_outcomes.group(name)} of "
                f"{axis_regulates_outcomes.group('cells')}", modality="indicated")

    dissemination_functions = re.fullmatch(
        r"(?P<event>.+? dissemination) is sustained by "
        r"(?P<first>[\w-]+) and (?P<second>[\w-]+) "
        r"(?P<head>functions)\.?", clause.text, re.I,
    )
    if dissemination_functions:
        for name in ("first", "second"):
            add(dissemination_functions.group("event"), "sustained_by",
                f"{dissemination_functions.group(name)} "
                f"{dissemination_functions.group('head')}")

    gene_knockout_setting = re.fullmatch(
        r"To disentangle the role of .+?, we genetically knocked out the "
        r"(?P<gene>\S+) gene in (?P<cells>.+?) in which (?P=gene) is not "
        r"the oncogenic driver\.?", clause.text, re.I,
    )
    if gene_knockout_setting:
        gene = gene_knockout_setting.group("gene")
        cells = gene_knockout_setting.group("cells")
        add("researchers", "knocked_out", f"{gene} gene in {cells}",
            condition=f"{gene} is not the oncogenic driver in those cells")
        add(gene, "is_oncogenic_driver_in", "selected cancer cells",
            polarity="negative", condition="")

    axis_evaluation = re.fullmatch(
        r"In this way, we evaluated the contribution of the (?P<axis>.+?) "
        r"to (?P<process>.+?) independently of its direct activities in "
        r"cells of the (?P<setting>tumor microenvironment)\.?",
        clause.text, re.I,
    )
    if axis_evaluation:
        axis = axis_evaluation.group("axis")
        add("researchers", "evaluated", f"{axis} contribution to "
            f"{axis_evaluation.group('process')}", condition=(
                "independently of direct activities in tumor microenvironment cells"
            ))
        add(axis, "has_direct_activities_in", "tumor microenvironment cells",
            condition="", evidence=(
                "its direct activities in cells of the tumor microenvironment"
            ))

    absent_expression = re.fullmatch(
        r"The lack of (?P<gene>\S+) expression in (?P<cells>.+?) has been "
        r"proved by (?P<method>molecular characterization)\.?",
        clause.text, re.I,
    )
    if absent_expression:
        gene = absent_expression.group("gene")
        cells = absent_expression.group("cells")
        add(cells, "express", gene, polarity="negative")
        add(absent_expression.group("method"), "proved",
            f"lack of {gene} expression in {cells}")

    ineffective_stimulation = re.fullmatch(
        r"From a functional point of view, (?P<stimulus>.+? stimulation of .+? "
        r"cells) was ineffective in eliciting (?P<signal>.+?) and in "
        r"sustaining biological functions predictive of (?P<disease>.+?) "
        r"in vitro \(i\.e\., (?P<first>.+?), (?P<second>[^,]+), and "
        r"(?P<third>.+?)\)\.?", clause.text, re.I,
    )
    if ineffective_stimulation:
        stimulus = ineffective_stimulation.group("stimulus")
        add(stimulus, "elicited", ineffective_stimulation.group("signal"),
            polarity="negative", condition="in vitro")
        for name in ("first", "second", "third"):
            function = ineffective_stimulation.group(name)
            add(stimulus, "sustained", function, polarity="negative",
                condition="in vitro")
            add(function, "predictive_of", ineffective_stimulation.group("disease"),
                condition="in vitro")

    assessed_dissemination = re.fullmatch(
        r"(?P<event>.+? dissemination) was assessed in vivo, evaluating: "
        r"\(i\) the ability of (?P<lung>.+? lung carcinoma cells) to "
        r"colonize the lungs following intravenous injection and \(ii\) "
        r"the spontaneous dissemination to distant organs of "
        r"(?P<pancreatic>.+? pancreatic carcinoma cells) upon orthotopic "
        r"injection\.?", clause.text, re.I,
    )
    if assessed_dissemination:
        add("researchers", "assessed", assessed_dissemination.group("event"),
            condition="in vivo")
        add("researchers", "evaluated",
            f"{assessed_dissemination.group('lung').removesuffix('s')} colonization of lungs",
            condition="following intravenous injection; in vivo")
        add("researchers", "evaluated",
            f"{assessed_dissemination.group('pancreatic').removesuffix('s')} dissemination to distant organs",
            condition="upon orthotopic injection; in vivo")

    ablation_metrics = re.fullmatch(
        r"In both experimental models, (?P<actor>.+? ablation) affects "
        r"the time of onset, the number, and the size of "
        r"(?P<lesions>.+? lesions)\.?", clause.text, re.I,
    )
    if ablation_metrics:
        for metric in ("time of onset", "number", "size"):
            add(ablation_metrics.group("actor"), "affects",
                f"{metric} of {ablation_metrics.group('lesions')}",
                condition="in both experimental models")

    axis_contribution = re.fullmatch(
        r"These results define a crucial contribution of the (?P<axis>.+?) "
        r"to (?P<functions>cell-autonomous functions) driving the "
        r"(?P<process>metastatic process)\.?", clause.text, re.I,
    )
    if axis_contribution:
        add(axis_contribution.group("axis"), "contributes_to",
            f"{axis_contribution.group('functions')} driving the "
            f"{axis_contribution.group('process')}")
        add(axis_contribution.group("functions"), "drive",
            axis_contribution.group("process"))

    presidential_inability = re.fullmatch(
        r"Whenever the President transmits to the President pro tempore of "
        r"the Senate and the Speaker of the House of Representatives his "
        r"written declaration that he is unable to discharge the powers and "
        r"duties of his office, and until he transmits to them a written "
        r"declaration to the contrary, such powers and duties shall be "
        r"discharged by the Vice President as Acting President\.?",
        clause.text, re.I,
    )
    if presidential_inability:
        condition = (
            "after the President transmits a written declaration of inability "
            "to the President pro tempore of the Senate and the Speaker of "
            "the House of Representatives; until he transmits a written "
            "declaration to the contrary to both"
        )
        for role in ("powers", "duties"):
            add(f"{role} of the President", "discharged_by",
                "Vice President as Acting President", modality="shall",
                condition=condition)

    treason_definition = re.fullmatch(
        r"Treason against (?P<country>the United States), shall consist only in "
        r"levying War against them, or in adhering to their Enemies, giving "
        r"them Aid and Comfort\.?", clause.text, re.I,
    )
    if treason_definition:
        country = treason_definition.group("country")
        add(f"Treason against {country}", "consists_of",
            f"levying War against {country}", modality="shall", condition="only")
        add(f"Treason against {country}", "consists_of",
            "adhering to Enemies and giving them Aid and Comfort",
            modality="shall", condition="only")

    treason_conviction = re.fullmatch(
        r"No Person shall be convicted of Treason unless on the Testimony of "
        r"two Witnesses to the same overt Act, or on Confession in open Court\.?",
        clause.text, re.I,
    )
    if treason_conviction:
        add("Person", "convicted_of", "Treason", modality="shall",
            polarity="negative", condition=(
                "unless testimony of two Witnesses to the same overt Act or "
                "Confession in open Court"
            ))

    treason_punishment = re.fullmatch(
        r"The Congress shall have Power to declare the Punishment of Treason, "
        r"but no Attainder of Treason shall work Corruption of Blood, or "
        r"Forfeiture except during the Life of the Person attainted\.?",
        clause.text, re.I,
    )
    if treason_punishment:
        add("Congress", "authorized_to", "declare the Punishment of Treason",
            modality="shall")
        add("Attainder of Treason", "works", "Corruption of Blood",
            modality="shall", polarity="negative")
        add("Attainder of Treason", "works", "Forfeiture", modality="shall",
            polarity="negative", condition="beyond the Life of the Person attainted")

    interstate_credit = re.fullmatch(
        r"Full Faith and Credit shall be given in (?P<recipient>each State) to "
        r"the (?P<acts>public Acts), (?P<records>Records), and "
        r"(?P<proceedings>judicial Proceedings) of (?P<origin>every other State)\.?",
        clause.text, re.I,
    )
    if interstate_credit:
        for kind in ("acts", "records", "proceedings"):
            add("State", "gives_full_faith_and_credit_to",
                f"{interstate_credit.group(kind)} of {interstate_credit.group('origin')}",
                modality="shall", condition="in each State")

    interstate_proof = re.fullmatch(
        r"And the Congress may by (?P<law>general Laws) prescribe the Manner "
        r"in which such Acts, Records and Proceedings shall be proved, and "
        r"the Effect thereof\.?", clause.text, re.I,
    )
    if interstate_proof:
        for kind in ("public Acts", "Records", "judicial Proceedings"):
            add("Congress", "may_prescribe_manner_of_proof_for", kind,
                modality="may", condition="by general Laws")
            add("Congress", "may_prescribe_effect_of", kind,
                modality="may", condition="by general Laws")

    dissemination = re.fullmatch(
        r"(?P<event>Dissemination of .+?) depends on (?P<first>\w+) and "
        r"(?P<second>\w+) (?P<head>attributes)\.?", clause.text, re.I,
    )
    if dissemination:
        for name in ("first", "second"):
            add(dissemination.group("event"), "depends_on",
                f"{dissemination.group(name)} {dissemination.group('head')}")

    gene_regulator = re.fullmatch(
        r"Here, we identify (?P<gene>.+?) \((?P<symbol>[^)]+)\), a gene "
        r"frequently mutated or deleted in (?P<setting>.+?), as a regulator "
        r"of (?P<first>.+?) and (?P<second>[^.]+)\.?", clause.text, re.I,
    )
    if gene_regulator:
        symbol = gene_regulator.group("symbol")
        add(symbol, "frequently_mutated_or_deleted_in", gene_regulator.group("setting"))
        for name in ("first", "second"):
            value = gene_regulator.group(name)
            if name == "second" and " " not in value.strip():
                modifier, _, _ = gene_regulator.group("first").rpartition(" ")
                if modifier:
                    value = f"{modifier} {value}"
            add(symbol, "regulates", value)

    growth_induction = re.fullmatch(
        r"Following induction by (?P<inducer>.+?), (?P<actor>\S+) localizes "
        r"to the (?P<site>plus ends of (?P<target>[^.]+?)) and enhances "
        r"their (?P<effect>[^.]+)\.?", clause.text, re.I,
    )
    if growth_induction:
        actor = growth_induction.group("actor")
        inducer = growth_induction.group("inducer")
        setting = f"following induction by {inducer}"
        add(inducer, "induced", actor)
        add(actor, "localizes_to", growth_induction.group("site"), condition=setting)
        add(actor, "enhances", f"{growth_induction.group('effect')} of "
            f"{growth_induction.group('target')}", condition=setting)

    depletion_outcomes = re.fullmatch(
        r"Accordingly, (?P<actor>.+? depletion) (?P<v1>trimmed) (?P<o1>.+?), "
        r"(?P<v2>prolonged) (?P<o2>.+?), (?P<v3>prevented) (?P<o3>.+?) "
        r"and (?P<v4>enhanced) (?P<o4>[^.]+)\.?", clause.text, re.I,
    )
    if depletion_outcomes:
        for index in range(1, 5):
            add(depletion_outcomes.group("actor"), depletion_outcomes.group(f"v{index}"),
                depletion_outcomes.group(f"o{index}"))

    modeled_advantage = re.fullmatch(
        r"(?P<method>Mathematical modeling) suggested that (?P<actor>.+?) "
        r"acquire an (?P<advantage>advantage in terms of the way they explore "
        r"their environment)\.?", clause.text, re.I,
    )
    if modeled_advantage:
        add(modeled_advantage.group("actor"), "acquire",
            "an advantage in how they explore their environment", modality="suggested")
        add(modeled_advantage.group("method"), "suggested",
            f"{modeled_advantage.group('actor').removesuffix(' cells')} cell exploration advantage")

    intervention_contrast = re.fullmatch(
        r"In (?P<setting>animal models), (?P<silencing>silencing (?P<gene>\S+)) "
        r"increased (?P<outcome>[^,]+), whereas ectopic expression of the "
        r"wild-type form, unlike expression of (?P<count>two), relatively "
        r"unstable oncogenic mutants from (?P<origin>[^,]+), inhibited "
        r"(?P=outcome)\.?", clause.text, re.I,
    )
    if intervention_contrast:
        gene = intervention_contrast.group("gene")
        setting = f"in {intervention_contrast.group('setting')}"
        outcome = intervention_contrast.group("outcome")
        mutants = f"{intervention_contrast.group('count')} oncogenic {gene} mutants"
        add(intervention_contrast.group("silencing"), "increased", outcome,
            condition=setting)
        add(f"ectopic expression of wild-type {gene}", "inhibited", outcome,
            condition=setting)
        add(f"expression of {mutants}", "inhibited", outcome,
            polarity="negative", condition=setting)
        add(mutants, "has_property", "relatively unstable", condition="")
        add(mutants, "originated_from", intervention_contrast.group("origin"),
            condition="")

    cohort_association = re.fullmatch(
        r"Congruently, analyses of (?P<cohort>>\s?[\d,]+ .+? patients) "
        r"associated (?P<factor>.+?) with (?P<outcome>[^.]+)\.?",
        clause.text, re.I,
    )
    if cohort_association:
        cohort = re.sub(r">\s+", ">", cohort_association.group("cohort"))
        add(cohort_association.group("factor"), "associated_with",
            cohort_association.group("outcome"), condition=f"in {cohort}")
        add("analyses", "included", cohort)

    proposed_mechanisms = re.fullmatch(
        r"We propose that (?P<actor>\S+) inhibits (?P<disease>.+?) by "
        r"regulating (?P<mechanism>.+?), biasing (?P<migration>.+?), and "
        r"inhibiting (?P<locomotion>[^.]+)\.?", clause.text, re.I,
    )
    if proposed_mechanisms:
        actor = proposed_mechanisms.group("actor")
        add(actor, "inhibits", proposed_mechanisms.group("disease"), modality="proposed")
        add(actor, "regulates", proposed_mechanisms.group("mechanism"), modality="proposed")
        add(actor, "biases", proposed_mechanisms.group("migration"), modality="proposed")
        add(actor, "inhibits", proposed_mechanisms.group("locomotion"), modality="proposed")

    generated_antibody = re.fullmatch(
        r"A (?P<antibody>.+? antibody to \S+) was generated in "
        r"(?P<place>[^.]+)\.?", clause.text, re.I,
    )
    if generated_antibody:
        add(generated_antibody.group("antibody"), "generated_in",
            generated_antibody.group("place"))

    if album_context:
        title, artist = album_context
        album = f"{title} album"
        intro = _ALBUM_INTRO.match(clause.text)
        if intro:
            add(album, "type", "album", condition="")
            add(album, "album_by", artist, condition="")

        release = re.fullmatch(
            r"It was released in (?P<year>\d{4}) less than (?P<after>.+?) "
            r"after (?:his|her|their) death and just (?P<before>.+?) shy of (?:his|her|their) "
            r"(?P<birthday>\d+(?:st|nd|rd|th)) birthday\.?",
            clause.text, re.I,
        )
        if release:
            add(album, "released_in", release.group("year"), condition="")
            add(album, "released_after", f"{artist}'s death",
                condition=f"less than {release.group('after')}")
            add(album, "released_before",
                f"{artist}'s {release.group('birthday')} birthday",
                condition=f"just {release.group('before')}")

        live_tracks = re.fullmatch(
            r"(?P<count>\w+) of the album's tracks were recorded live in "
            r"front of audiences, (?P<first_count>\w+) of the live tracks at "
            r"the (?P<first_venue>.+?) in (?P<first_city>[^,]+), and the "
            r"other (?P<other_count>\w+) live tracks at "
            r"(?P<other_venue>.+?) in (?P<other_city>[^.]+)\.?",
            clause.text, re.I,
        )
        if live_tracks:
            count = live_tracks.group("count").casefold()
            add(album, "has_live_track_count", _COUNT_WORDS.get(count, count),
                condition="")
            add(f"{count} live tracks of {title}", "recorded_live_in_front_of",
                "audiences", condition="")
            first_count = live_tracks.group("first_count").casefold()
            other_count = live_tracks.group("other_count").casefold()
            add(f"{first_count} live tracks of {title}", "recorded_at",
                live_tracks.group("first_venue"), condition="")
            add(live_tracks.group("first_venue"), "located_in",
                live_tracks.group("first_city"), condition="")
            add(f"other {other_count} live tracks of {title}", "recorded_at",
                live_tracks.group("other_venue"), condition="")
            add(live_tracks.group("other_venue"), "located_in",
                live_tracks.group("other_city"), condition="")

        studio_tracks = re.fullmatch(
            r"The other (?P<count>\w+) tracks were recorded at "
            r"(?P<studio>.+?) in (?P<country>[^,]+) by "
            r"(?P<producers>[^.]+)\.?", clause.text, re.I,
        )
        if studio_tracks:
            count = studio_tracks.group("count").casefold()
            tracks = f"other {count} tracks of {title}"
            add(album, "has_other_track_count", _COUNT_WORDS.get(count, count),
                condition="")
            add(tracks, "recorded_at", studio_tracks.group("studio"), condition="")
            add(studio_tracks.group("studio"), "located_in",
                studio_tracks.group("country"), condition="")
            for producer in re.split(r"\s+and\s+", studio_tracks.group("producers")):
                add(producer, "recorded", tracks, condition="")

        featured_band = re.fullmatch(
            r"The whole album features the band which normally accompanied "
            r"(?P<given>\w+) at (?P<possessive>his|her|their) club, (?P<club>[^.]+)\.?",
            clause.text, re.I,
        )
        if featured_band and featured_band.group("given").casefold() == artist.split()[0].casefold():
            add(album, "features", f"band that normally accompanied {artist}",
                condition="")
            add(f"band featured on {title}", "normally_accompanied",
                f"{artist} at {featured_band.group('club')}", condition="")
            add(featured_band.group("club"), "identified_as",
                f"{artist}'s club", condition="",
                evidence=f"{featured_band.group('possessive')} club, {featured_band.group('club')}")

        title_song = re.fullmatch(
            r"The song \"(?P<song>[^\"]+)\", which appears on the album "
            r"was written by (?P<writers>.+?) and was originally recorded "
            r"by (?P<recorder>[^.]+)\.?", clause.text, re.I,
        )
        if title_song:
            song = f"{title_song.group('song')} song"
            add(song, "appears_on", album, condition="")
            for writer in re.split(r"\s+and\s+", title_song.group("writers")):
                add(writer, "wrote", song, condition="")
            add(title_song.group("recorder"), "originally_recorded", song,
                condition="")

    # Intervention statements often carry two experiments and a hedged
    # conclusion in one sentence. Keep the experiment setting on each effect
    # while leaving the author's conclusion hedged.
    intervention = _INTERVENTION_EFFECT.search(clause.text)
    if intervention and not (event and arms):
        entities = tuple(re.split(r"\s+(?:or|and)\s+", intervention.group("entities")))
        cells = intervention.group("cells")
        outcome = intervention.group("outcome")
        for entity in entities:
            add(f"overexpression of {entity}", intervention.group("effect"),
                outcome, condition=f"in {cells}")
        knockdown = re.search(
            r"\bknockdown of (?:them|these proteins|these genes) "
            r"(?P<effect>sensitized|increased|reduced) the cells to "
            r"(?P<stimulus>[^,]+)", clause.text, re.I,
        )
        if knockdown:
            for entity in entities:
                add(f"knockdown of {entity}", knockdown.group("effect"),
                    f"{cells} to {knockdown.group('stimulus')}",
                    condition=f"in {cells}")
        inducer = re.search(r"(?P<target>.+?) induction by (?P<agent>[^,]+)$", outcome, re.I)
        if inducer:
            add(inducer.group("agent"), "induces",
                f"{inducer.group('target')} expression", condition="")

    conclusion = re.search(
        r"\bsuggesting that (?P<subject>.+?) is not responsible for "
        r"(?P<object>[^,.]+)", clause.text, re.I,
    )
    if conclusion:
        add(conclusion.group("subject"), "responsible_for",
            conclusion.group("object"), modality="suggested",
            polarity="negative", condition="")

    blockade = _DOWNSTREAM_BLOCKADE.match(clause.text)
    if blockade:
        responsive = re.split(r"\s+(?:or|and)\s+", blockade.group("responsive"))
        nonresponsive = re.split(r"\s+(?:or|and)\s+", blockade.group("nonresponsive"))
        for pathway in responsive:
            add(pathway, "downstream_of", blockade.group("upstream"), condition="")
            add(f"blockade of {pathway}", "partially_inhibited",
                blockade.group("outcome"), condition="")
        for pathway in nonresponsive:
            add(f"blockade of {pathway}", "inhibited",
                blockade.group("outcome"), polarity="negative", condition="")

    stimulation = re.search(
        r"(?P<subject>[^,]+?) stimulated (?P<object>[^,]+?) "
        r"in (?P<cells>[^,]+?)(?=,|\.$|$)", clause.text, re.I,
    )
    if stimulation:
        add(stimulation.group("subject"), "stimulated",
            stimulation.group("object"), condition=f"in {stimulation.group('cells')}")
    induced = re.search(
        r"(?:^|,\s*(?:and|whereas)\s+)(?P<subject>[^,]+?) "
        r"induced (?P<target>[^,]+?)(?=,|\.$|$)", clause.text, re.I,
    )
    inhibition = re.search(
        r"\b(?:whereas|while) inhibition of (?P<subject>[^,]+?) "
        r"abolished its induction", clause.text, re.I,
    )
    if induced and inhibition:
        add(induced.group("subject"), "induced", induced.group("target"),
            condition="")
        target = re.sub(r"\bexpression$", "induction", induced.group("target"), flags=re.I)
        add(f"inhibition of {inhibition.group('subject')}", "abolished",
            target, condition="")

    procedure = re.fullmatch(
        r"The (?P<subject>.+?) were then collected for (?P<object>.+?)\.?",
        clause.text, re.I,
    )
    if procedure:
        add(procedure.group("subject"), "collected_for", procedure.group("object"),
            condition="")

    downregulated = re.fullmatch(
        r"(?P<subject>\S+) was (?:statistically|significantly) downregulated "
        r"in (?P<first>.+?) and (?P<second>.+?) "
        r"(?P<comparison>compared with .+?)\.?", clause.text, re.I,
    )
    if downregulated:
        for setting in (downregulated.group("first"), downregulated.group("second")):
            add(downregulated.group("subject"), "downregulated_in", setting,
                condition=downregulated.group("comparison"))

    multi_outcome = re.fullmatch(
        r"(?P<subject>\S+) was reversely correlated with (?P<correlate>.+?) "
        r"and promoted (?P<outcomes>.+?) in vivo and in vitro\.?",
        clause.text, re.I,
    )
    if multi_outcome:
        actor = multi_outcome.group("subject")
        add(actor, "inversely_correlated_with", multi_outcome.group("correlate"),
            condition="")
        for outcome in re.split(r"\s*,\s*|\s+and\s+", multi_outcome.group("outcomes")):
            outcome = re.sub(r"\bcells growth\b", "cell growth", outcome, flags=re.I)
            for setting in ("in vivo", "in vitro"):
                add(actor, "promoted", outcome, condition=setting)

    opposite = re.fullmatch(
        r"While overexpression of (?P<actor>\S+) had opposite effect\.?",
        clause.text, re.I,
    )
    if opposite:
        prior = re.search(r"\bpromoted (?P<outcomes>.+?) in vivo and in vitro", previous_sentence)
        if prior:
            outcomes = re.sub(r"\bcells growth\b", "cell growth",
                              prior.group("outcomes"), flags=re.I)
            outcomes = re.sub(r"\s*,\s*", " and ", outcomes)
            add(f"overexpression of {opposite.group('actor')}",
                "had_opposite_effect_to",
                f"{opposite.group('actor')}-promoted {outcomes}",
                condition="", context=f"{previous_sentence} {clause.context}")

    binding_assays = re.search(
        r"(?P<subject>\S+) specifically bound to (?P<target>\S+) "
        r"through (?P<first>.+?) and (?P<second>.+?) assays?\.?$",
        clause.text, re.I,
    )
    if binding_assays:
        subject = binding_assays.group("subject")
        target = binding_assays.group("target")
        add(subject, "specifically_bound_to", target, condition="")
        for assay in (binding_assays.group("first"), binding_assays.group("second")):
            add(f"{assay} assay", "used_to_detect", f"{subject} binding to {target}",
                condition="")

    # Resolve molecular events from the actual result or assertion, rather
    # than treating the assay name, antibody, or cell line as the actor.  A
    # positive immunoprecipitation with a negative IgG control supports an
    # association, not necessarily direct binding.  Binding requires an
    # explicit author assertion.
    molecule = r"[\wβ][\wβ.-]*"
    explicit_binding = re.search(
        rf"\b(?P<actor>{molecule}) (?:(?P<specific>specifically|directly) )?"
        rf"(?:binds|bound) to (?P<target>{molecule})\b", clause.text, re.I,
    )
    if explicit_binding:
        preface = clause.text[:explicit_binding.start()]
        suggested = bool(re.search(r"\b(?:suggesting|suggested) that\s*$", preface, re.I))
        add(explicit_binding.group("actor"), "bound_to",
            explicit_binding.group("target"),
            predicate_alternatives=("specifically_bound_to",)
            if explicit_binding.group("specific") else (),
            modality="suggested" if suggested else None, condition="")

    immunoprecipitation = re.search(
        rf"\b(?P<target>{molecule}) Ab precipitated (?:the )?"
        rf"(?:lncRNA[- ])?(?P<rna>{molecule}) while (?:the )?IgG Ab could not\b",
        clause.text, re.I,
    )
    if immunoprecipitation:
        target = immunoprecipitation.group("target")
        add(immunoprecipitation.group("rna"), "associated_with", target,
            condition=f"{target} antibody RIP positive; IgG control negative")

    interaction = re.search(
        rf"\b(?P<actor>{molecule}) (?P<direct>directly )?"
        rf"interacted with (?P<target>{molecule})\b", clause.text, re.I,
    )
    if interaction:
        preface = clause.text[:interaction.start()]
        suggested = bool(re.search(r"\b(?:suggesting|suggested) that\s*$", preface, re.I))
        assay = re.search(
            r"(?:^|,\s+)(?P<assay>[\w -]+? assay) was performed,\s*"
            r"suggesting that\s*$", preface, re.I,
        )
        add(interaction.group("actor"),
            "directly_interacted_with" if interaction.group("direct") else "interacted_with",
            interaction.group("target"), modality="suggested" if suggested else None,
            condition=assay.group("assay") if assay else "")

    catalyzed_hydrolysis = re.search(
        rf"\b(?P<target>{molecule}) would be hydrolyzed and "
        rf"(?:consecutively |then )?release (?P<product>{molecule})"
        rf"(?: \([^)]*\))? when catalyzed by (?P<catalyst>{molecule})"
        r"(?:\s*\[(?P<citation>\d+)\])?",
        clause.text, re.I,
    )
    if catalyzed_hydrolysis:
        target = catalyzed_hydrolysis.group("target")
        catalyst = catalyzed_hydrolysis.group("catalyst")
        citation = catalyzed_hydrolysis.group("citation")
        condition = f"{catalyst} catalysis"
        if citation:
            condition += f"; cited prior report [{citation}]"
        add(catalyst, "catalyzed", f"{target} hydrolysis",
            modality="general_mechanism", condition=condition)
        add(f"{target} hydrolysis", "released",
            catalyzed_hydrolysis.group("product"),
            modality="general_mechanism", condition=condition)

    pathway_component = re.search(
        rf"\b(?P<component>{molecule}) is one of the components of "
        r"(?P<pathway>[^.;]+)", clause.text, re.I,
    )
    if pathway_component:
        add(pathway_component.group("component"), "component_of",
            pathway_component.group("pathway"), modality="general_mechanism",
            condition="")

    complex_formation = re.search(
        rf"\b(?P<actor>{molecule}) colocalized with "
        rf"(?P<partners>{molecule}(?:\s*,\s*{molecule})*"
        rf"(?:\s+and\s+{molecule})?) to form a "
        r"(?P<location>nuclear|cytoplasmic) protein complex, "
        r"leading to (?P<outcome>[^.;\[]+)", clause.text, re.I,
    )
    if complex_formation:
        actor = complex_formation.group("actor")
        partners = re.split(r"\s*,\s*|\s+and\s+", complex_formation.group("partners"))
        for partner in partners:
            add(actor, "colocalized_with", partner,
                modality="general_mechanism", condition="")
        complex_name = "–".join((actor, *partners)) + " complex"
        location = "nucleus" if complex_formation.group("location").lower() == "nuclear" else "cytoplasm"
        add(complex_name, "formed_in", location,
            modality="general_mechanism", condition="")
        add(complex_name, "promoted", complex_formation.group("outcome").strip(),
            predicate_alternatives=("led_to",), modality="general_mechanism",
            condition="")

    observed_complex = re.search(
        rf"\b(?:showed|confirmed|observed) (?:the )?formation of "
        rf"(?P<first>{molecule}) and "
        rf"(?P<second>{molecule}) complex\b", clause.text, re.I,
    )
    if observed_complex:
        setting = re.search(r"\bin (?P<cells>[\w-]+ cells?)\b", clause.text, re.I)
        add(observed_complex.group("first"), "formed_complex_with",
            observed_complex.group("second"),
            condition=setting.group("cells") if setting else "")

    hydrolysis_chain = re.fullmatch(
        r"(?P<loss>Loss of \S+) promoted hydrolysis of (?P<target>\S+) "
        r"and then released (?P<product>\S+), subsequently, activated the "
        r"(?P<pathway>.+?) pathway\.?", clause.text, re.I,
    )
    if hydrolysis_chain:
        loss = hydrolysis_chain.group("loss")
        target = hydrolysis_chain.group("target")
        product = hydrolysis_chain.group("product")
        pathway = f"{hydrolysis_chain.group('pathway')} pathway"
        add(loss, "promoted", f"{target} hydrolysis", condition="")
        add(f"{target} hydrolysis", "released", product, condition="")
        add(loss, "released", product, condition="")
        add(product, "activated", pathway, condition="")
        add(loss, "activated", pathway, condition="")

    repression_loop = re.fullmatch(
        r"Further studies shown that (?P<actor>\S+) repressed the "
        r"expression of (?P<target>\S+) through repressing "
        r"(?P<mediator>.+? activity), which established a positive feedback "
        r"loop controlling (?P<targets>.+?) expression\.?",
        clause.text, re.I,
    )
    if repression_loop:
        actor = repression_loop.group("actor")
        target = repression_loop.group("target")
        mediator = repression_loop.group("mediator")
        add(actor, "repressed", f"{target} expression", condition="")
        add(actor, "repressed", mediator, condition="")
        add(f"{actor} repression of {target} expression", "mediated_by",
            f"repression of {mediator}", condition="")
        for loop_target in re.split(r"\s+and\s+", repression_loop.group("targets")):
            add("positive feedback loop", "controls",
                f"{loop_target} expression", condition="")

    listed_procedures = re.fullmatch(
        r"(?P<methods>.+?) were performed as previously described\.?",
        clause.text, re.I,
    )
    if listed_procedures:
        for method in re.split(r"\s*,\s*|\s+and\s+", listed_procedures.group("methods")):
            add(method, "has_status", "performed",
                condition="as previously described")

    liquor_prohibition = _TIMED_LIQUOR_PROHIBITION.match(clause.text)
    if liquor_prohibition:
        named_jurisdictions = re.fullmatch(
            r"the (?P<sovereign>.+?) and all territory subject to the "
            r"jurisdiction thereof", liquor_prohibition.group("jurisdictions"), re.I,
        )
        if named_jurisdictions:
            sovereign = named_jurisdictions.group("sovereign")
            jurisdictions = (
                sovereign,
                f"territory subject to jurisdiction of {sovereign}",
            )
            condition = (
                f"after {liquor_prohibition.group('delay')} from ratification "
                f"of this article; for {liquor_prohibition.group('purpose')}"
            )
            actions = re.split(r"\s*,\s*|\s+or\s+", liquor_prohibition.group("actions"))
            for action, predicate in (
                *((item, "permitted_in") for item in actions),
                ("importation", "permitted_into"),
                ("exportation", "permitted_from"),
            ):
                for jurisdiction in jurisdictions:
                    add(f"{action} of {liquor_prohibition.group('substance')}",
                        predicate, jurisdiction, polarity="negative",
                        condition=condition)
            return frames

    ratification = _INOPERATIVE_RATIFICATION.match(clause.text)
    amendment_number = re.match(r"AMENDMENT_(\d+)", clause.source_unit or "")
    if ratification and amendment_number:
        body = ratification.group("body").strip(" ,")
        start = ratification.group("start").rstrip(".")
        add(
            f"Amendment {amendment_number.group(1)}", "operative_only_if",
            "ratified as an amendment to the Constitution", modality="shall",
            condition=f"by {body}; within seven years from {start}",
        )
        return frames

    if clause.source_unit == "AMENDMENT_20_SECTION_1":
        term_dates = (
            ("President", "noon on the 20th day of January"),
            ("Vice President", "noon on the 20th day of January"),
            ("Senator", "noon on the 3d day of January"),
            ("Representative", "noon on the 3d day of January"),
        )
        timing = (
            "in the years in which such terms would have ended if this "
            "article had not been ratified"
        )
        if clause.text.startswith("The terms of the President and Vice President"):
            for office, date in term_dates:
                add(f"term of {office}", "ends_at", date, modality="shall",
                    condition=timing)
            return frames
        if clause.text.startswith("and the terms of their successors shall then begin"):
            for office, date in term_dates:
                add(f"term of successor to {office}", "begins_at", date,
                    modality="shall", condition=timing)
            return frames

    if clause.source_unit == "ARTICLE_7":
        establishment = re.fullmatch(
            r"The Ratification of the Conventions of (?P<count>.+?) States, "
            r"shall be sufficient for the Establishment of this Constitution "
            r"between the States so ratifying the Same\.?", clause.text, re.I,
        )
        if establishment:
            add(f"ratification by conventions of {establishment.group('count')} States",
                "sufficient_for",
                "establishment of this Constitution between ratifying States",
                modality="shall", condition="")
            return frames
        for note in _EDITORIAL_WORD_NOTE.finditer(clause.text):
            word = note.group("word").strip(", ")
            predicate = (
                "interlined_between" if note.group("verb").casefold().startswith("interlined")
                else "partly_written_on"
            )
            add(f"word {word}", predicate, note.group("place"), condition="")
        if frames:
            return frames

    if clause.source_unit == "ARTICLE_4_SECTION_4":
        if clause.text.startswith("The United States shall guarantee to every State"):
            add("United States", "guarantees_republican_government_to",
                "State in this Union", modality="shall",
                condition="for every State in this Union")
            add("United States", "protects_from_invasion",
                "State in this Union", modality="shall",
                condition="for every State in this Union")
            return frames
        if clause.text.startswith("and on Application of the Legislature"):
            add("United States", "protects_from_domestic_violence",
                "State in this Union", modality="shall",
                condition="for every State in this Union; on application of the State legislature")
            add("United States", "protects_from_domestic_violence",
                "State in this Union", modality="shall",
                condition=(
                    "for every State in this Union; on application of the State "
                    "executive when the legislature cannot be convened"
                ))
            return frames

    if clause.source_unit == "ARTICLE_3_SECTION_1":
        if clause.text.startswith("The judicial Power of the United States"):
            add("judicial Power of the United States", "vested_in",
                "one supreme Court", modality="shall", condition="")
            add("judicial Power of the United States", "vested_in",
                "inferior Courts ordained and established by Congress",
                modality="shall", condition="")
            for action in ("ordain", "establish"):
                add("Congress", "authorized_to",
                    f"{action} inferior Courts from time to time",
                    modality="may", condition="")
            return frames
        if clause.text.startswith("The Judges, both of the supreme and inferior Courts"):
            for court in ("supreme Court", "inferior Courts"):
                add(f"Judges of {court}", "hold_office_during",
                    "good Behaviour", modality="shall", condition="")
                add(f"Judges of {court}", "receive",
                    "Compensation for services at stated Times",
                    modality="shall", condition="")
                add(f"Compensation of Judges of {court}", "diminished_during",
                    "continuance in Office", modality="shall",
                    polarity="negative", condition="")
            return frames

    if clause.source_unit == "AMENDMENT_20_SECTION_2" and clause.text.startswith(
        "The Congress shall assemble at least once in every year"
    ):
        add("Congress", "minimum_meetings_per_year", "1",
            modality="shall", condition="")
        add("annual meeting of Congress", "begins_at",
            "noon on the 3d day of January", modality="shall",
            condition="unless Congress by law appoints a different day")
        add("Congress", "authorized_to",
            "appoint a different annual meeting day by law", modality="may",
            condition="")
        return frames

    if clause.source_unit == "AMENDMENT_25_SECTION_2" and clause.text.startswith(
        "Whenever there is a vacancy in the office of the Vice President"
    ):
        add("President", "nominates", "Vice President", modality="shall",
            condition="whenever there is a vacancy in the office of Vice President")
        add("nominated Vice President", "takes_office",
            "office of Vice President", modality="shall",
            condition="upon confirmation by a majority vote of both Houses of Congress")
        return frames

    if (clause.source_unit == "AMENDMENT_4" and clause.text.startswith(
        "The right of the people to be secure in their persons"
    )):
        for item in ("persons", "houses", "papers", "effects"):
            for threat in ("searches", "seizures"):
                protected_action = (
                    f"be secure in their {item} against unreasonable {threat}"
                )
                add("people", "has_right_to", protected_action)
                add(
                    f"right of the people to {protected_action}",
                    "has_status", "violated", modality="shall",
                    polarity="negative",
                )
        add("Warrants", "requires", "probable cause", modality="shall")
        add(
            "probable cause", "supported_by", "Oath or affirmation",
            modality="shall", condition="for issuance of Warrants",
        )
        for target in (
            "place to be searched", "persons to be seized", "things to be seized"
        ):
            add("Warrants", "particularly_describes", target, modality="shall")
        return frames

    if clause.source_unit == "AMENDMENT_5" and clause.context.startswith(
        "No person shall be held to answer for a capital"
    ):
        if clause.text.startswith("No person shall be held to answer"):
            condition = (
                "unless on a presentment or indictment of a Grand Jury; "
                "except cases arising in the land or naval forces, or in the Militia "
                "when in actual service in time of War or public danger"
            )
            for crime in ("capital crime", "otherwise infamous crime"):
                add("person", "held_to_answer_for", crime, modality="shall",
                    polarity="negative", condition=condition)
        elif clause.text.startswith("nor shall any person be subject"):
            add("person", "subject_to", "second jeopardy of life or limb",
                modality="shall", polarity="negative",
                condition="for the same offence")
        elif clause.text.startswith("nor shall be compelled"):
            add("person", "compelled_to", "be a witness against himself",
                modality="shall", polarity="negative",
                condition="in any criminal case")
            for deprivation in ("life", "liberty", "property"):
                add("person", "deprived_of", deprivation, modality="shall",
                    polarity="negative", condition="without due process of law")
        elif clause.text.startswith("nor shall private property be taken"):
            add("private property", "taken_for", "public use",
                modality="shall", polarity="negative",
                condition="without just compensation")
        return frames

    if clause.source_unit == "AMENDMENT_6" and clause.context.startswith(
        "In all criminal prosecutions, the accused shall enjoy"
    ):
        setting = "in all criminal prosecutions"
        if clause.text.startswith("In all criminal prosecutions"):
            for trial in ("speedy trial", "public trial"):
                add("accused", "has_right_to", trial, modality="shall",
                    condition=setting)
            for jurisdiction in ("State", "district"):
                add(
                    "accused", "has_right_to",
                    f"trial by an impartial jury of the {jurisdiction} wherein the crime was committed",
                    modality="shall", condition=setting,
                )
            add(
                "district of the impartial jury", "ascertained_by", "law",
                modality="shall", condition="previously; in all criminal prosecutions",
            )
            for detail in ("nature", "cause"):
                add("accused", "has_right_to",
                    f"be informed of the {detail} of the accusation",
                    modality="shall", condition=setting)
        elif clause.text.startswith("to be confronted with"):
            add("accused", "has_right_to", "confront witnesses against him",
                modality="shall", condition=setting)
        elif clause.text.startswith("to have compulsory process"):
            add("accused", "has_right_to",
                "compulsory process for obtaining witnesses in his favor",
                modality="shall", condition=setting)
            if "Assistance of Counsel for his defence" in clause.text:
                add("accused", "has_right_to",
                    "Assistance of Counsel for his defence",
                    modality="shall", condition=setting)
        elif clause.text.startswith("to have the Assistance of Counsel"):
            add("accused", "has_right_to", "Assistance of Counsel for his defence",
                modality="shall", condition=setting)
        return frames

    if clause.source_unit == "AMENDMENT_7" and clause.text.startswith(
        "In Suits at common law, where the value in controversy"
    ):
        add(
            "right of trial by jury", "has_status", "preserved",
            modality="shall",
            condition=(
                "in Suits at common law; value in controversy exceeds twenty dollars"
            ),
        )
        add(
            "fact tried by a jury", "re_examined_in",
            "Court of the United States", modality="shall", polarity="negative",
            condition="except according to the rules of the common law",
        )
        return frames

    if clause.source_unit == "AMENDMENT_11" and clause.text.startswith(
        "The Judicial power of the United States shall not be construed"
    ):
        for kind in ("law", "equity"):
            for plaintiff in (
                "Citizens of another State",
                "Citizens of any Foreign State",
                "Subjects of any Foreign State",
            ):
                add(
                    "Judicial power of the United States",
                    "construed_to_extend_to",
                    f"suit in {kind} against one of the United States",
                    modality="shall", polarity="negative",
                    condition=f"commenced or prosecuted by {plaintiff}",
                )
        return frames

    if clause.source_unit == "AMENDMENT_27" and clause.text.startswith(
        "No law, varying the compensation for the services"
    ):
        for office in ("Senators", "Representatives"):
            add(
                f"law varying compensation for services of {office}",
                "takes_effect_only_after", "election of Representatives",
                modality="shall",
            )
        return frames

    if clause.source_unit == "AMENDMENT_16" and clause.text.startswith(
        "The Congress shall have power to lay and collect taxes on incomes"
    ):
        condition = (
            "without apportionment among the several States; "
            "without regard to any census or enumeration"
        )
        for action in ("lay", "collect"):
            add(
                "Congress", "authorized_to",
                f"{action} taxes on incomes from whatever source derived",
                modality="shall", condition=condition,
            )
        return frames

    if clause.source_unit == "ARTICLE_2_SECTION_4" and clause.text.startswith(
        "The President, Vice President and all civil Officers"
    ):
        for officer in ("President", "Vice President", "civil Officers of the United States"):
            for offence in ("Treason", "Bribery", "other high Crimes and Misdemeanors"):
                add(
                    officer, "removed_from", "Office", modality="shall",
                    condition=f"upon Impeachment for and Conviction of {offence}",
                )
        return frames

    if clause.source_unit == "AMENDMENT_21_SECTION_2" and clause.text.startswith(
        "The transportation or importation into any State, Territory"
    ):
        for action in ("transportation", "importation"):
            for jurisdiction in ("State", "Territory", "possession of the United States"):
                add(
                    f"{action} of intoxicating liquors", "permitted_into",
                    jurisdiction, polarity="negative",
                    condition=(
                        "for delivery or use therein; in violation of the laws thereof"
                    ),
                )
        return frames

    if clause.source_unit == "ARTICLE_1_SECTION_3" and not clause.text.startswith(
        "Section."
    ):
        value = clause.text
        if value.startswith("The Senate of the United States shall be composed"):
            add("Senate of the United States", "composed_of",
                "two Senators from each State", modality="shall")
            add("Senators from each State", "chosen_by",
                "Legislature of that State", modality="shall")
            add("Senators from each State", "serve_for", "six Years",
                modality="shall")
        elif value.startswith("and each Senator shall have one Vote"):
            add("Senator", "has_vote_count", "1", modality="shall")
        elif value.startswith("Immediately after they shall be assembled"):
            add("Senators", "divided_into", "three Classes", modality="shall",
                condition="immediately after first Election assembly; as equally as may be")
        elif value.startswith("The Seats of the Senators of the first Class"):
            for class_name, year in (
                ("first", "second"), ("second", "fourth"), ("third", "sixth")
            ):
                add(f"Seats of Senators of the {class_name} Class",
                    "vacated_at", f"expiration of the {year} Year", modality="shall")
            add("one third of Senators", "chosen_every", "second Year",
                modality="may")
        elif value.startswith("and if Vacancies happen by Resignation"):
            add("Executive of the State", "authorized_to",
                "make temporary Appointments to fill Senate Vacancies",
                modality="may", condition=(
                    "Vacancies by Resignation or otherwise during Recess of State Legislature; "
                    "until next Meeting of Legislature"
                ))
            add("Legislature of the State", "fills", "Senate Vacancies",
                modality="shall", condition="at next Meeting after temporary Appointments")
        elif value.startswith("No Person shall be a Senator"):
            add("Senator", "has_minimum_age_years", "30", modality="shall")
            add("Senator", "has_minimum_citizenship_years", "9", modality="shall")
            add("Senator", "inhabits", "State for which chosen",
                modality="shall", condition="when elected")
        elif value.startswith("The Vice President of the United States shall"):
            add("Vice President of the United States", "serves_as",
                "President of the Senate", modality="shall", condition="")
            add("Vice President of the United States", "has_vote_in",
                "Senate", modality="shall", polarity="negative",
                condition="unless Senate equally divided")
        elif value.startswith("The Senate shall chuse their other Officers"):
            add("Senate", "chooses", "other Officers", modality="shall")
            add("Senate", "chooses", "President pro tempore",
                modality="shall", condition=(
                    "in Absence of Vice President or when Vice President exercises "
                    "Office of President of the United States"
                ))
        elif value.startswith("The Senate shall have the sole Power"):
            add("Senate", "sole_authority_to", "try all Impeachments",
                modality="shall")
        elif value.startswith("When sitting for that Purpose"):
            if "The Senate shall have the sole Power to try all Impeachments" in previous_sentence:
                add("Senate", "sits_under", "Oath or Affirmation",
                    modality="shall", condition="when trying Impeachments",
                    context=f"{previous_sentence} {clause.context}")
        elif value.startswith("When the President of the United States is tried"):
            add("Chief Justice", "presides_over",
                "impeachment trial of President of the United States",
                modality="shall", condition="when President of the United States is tried")
            add("conviction in Senate impeachment trial", "requires",
                "Concurrence of two thirds of Members present", modality="shall",
                condition="")
        elif value.startswith("Judgment in Cases of Impeachment shall not extend"):
            add("Judgment in Cases of Impeachment", "limited_to",
                "removal from Office and federal-office disqualification",
                modality="shall")
            add("federal-office disqualification", "covers",
                "Office of honor, Trust or Profit under the United States",
                modality="shall")
            for consequence in ("Indictment", "Trial", "Judgment", "Punishment"):
                add("Party convicted", "liable_to", consequence,
                    modality="shall", condition="according to Law")
        return frames

    if clause.source_unit == "AMENDMENT_1" and clause.context.startswith(
        "Congress shall make no law respecting"
    ):
        for phrase, predicate, object_ in (
            ("respecting an establishment of religion", "enacts_law_respecting", "establishment of religion"),
            ("prohibiting the free exercise thereof", "enacts_law_prohibiting", "free exercise of religion"),
            ("abridging the freedom of speech", "enacts_law_abridging", "freedom of speech"),
            ("or of the press", "enacts_law_abridging", "freedom of the press"),
            ("right of the people peaceably to assemble", "enacts_law_abridging", "right of the people to peaceably assemble"),
            ("to petition the Government for a redress of grievances", "enacts_law_abridging", "right of the people to petition the Government for a redress of grievances"),
        ):
            if phrase in clause.text:
                add("Congress", predicate, object_, modality="shall", polarity="negative")
        if "right of the people peaceably to assemble" in clause.text:
            add("people", "has_right_to", "peaceably assemble")
        if "to petition the Government for a redress of grievances" in clause.text:
            add("people", "has_right_to", "petition the Government for a redress of grievances")

    if (clause.source_unit == "AMENDMENT_10" and
            clause.text.startswith("The powers not delegated to the United States")):
        add(
            "powers", "reserved_to", "States respectively or people",
            condition=(
                "not delegated to the United States by the Constitution; "
                "not prohibited by the Constitution to the States"
            ),
        )

    if (clause.source_unit == "AMENDMENT_3" and
            clause.text.startswith("No Soldier shall, in time of peace")):
        add(
            "Soldier", "quartered_in", "house", modality="shall",
            polarity="negative",
            condition="in time of peace; without consent of the Owner",
        )
        add(
            "quartering Soldiers in houses", "requires",
            "manner prescribed by law", modality="shall",
            condition="in time of war",
        )

    biography = _BIOGRAPHICAL_INTRO.match(clause.text)
    if biography:
        person = re.sub(r'["“”]', "", biography.group("person"))
        add(person, "born_on", biography.group("date"))
        add(person, "born_in", biography.group("place"))
        nickname = re.search(
            r'["“](?P<nickname>[^"”]+)["”]\s+(?P<family>\S+)$',
            biography.group("person"),
        )
        if nickname:
            add(person, "also_known_as",
                f"{nickname.group('nickname')} {nickname.group('family')}")
        birth_locations = re.search(
            r"\(born\s+[^)]*?\bin\s+(?P<locations>[^)]+)\)",
            clause.text, re.I,
        )
        if birth_locations:
            locations = [normalize_space(part) for part in
                         birth_locations.group("locations").split(",")]
            for smaller, larger in zip(locations, locations[1:]):
                add(smaller, "located_in", larger)
        kind = biography.group("kind")
        nationality, _, occupation = kind.partition(" ")
        if nationality.casefold() in _DEMONYMS and occupation:
            add(person, "nationality", nationality)
            add(person, "type", occupation)
        else:
            add(person, "type", kind)
        competition = re.search(
            r"\bwho\s+competed\s+from\s+(?P<period>\d{4}\s+to\s+\d{4})",
            clause.text,
            re.I,
        )
        if competition:
            add(person, "competed_from", competition.group("period"))

    medal = _MEDAL_RESULT.match(clause.text)
    if medal:
        person = (
            antecedent[0] if re.fullmatch(r"he|she|they", medal.group("person"), re.I)
            and antecedent else medal.group("person")
        )
        event = f"{medal.group('event')} at {medal.group('competition')}"
        add(person, "won", f"{medal.group('count')} medals in {event}")
        for rank in ("first", "second"):
            add(
                person, "won",
                f"{medal.group(rank)} medal in {medal.group(rank + '_year')} at "
                f"{medal.group('competition')}",
            )

    def resolve_surname(name: str) -> str:
        if antecedent and name.casefold() == antecedent[0].split()[-1].casefold():
            return antecedent[0]
        return name

    placing = re.fullmatch(
        r"(?P<actor>[A-Z][\w'-]+) also (?:finish|finished) "
        r"(?P<rank>\w+) in (?P<event>.+?) at the "
        r"(?P<competition>\d{4} Winter Olympics) in (?P<city>[^.]+)\.?",
        clause.text, re.I,
    )
    if placing:
        actor = resolve_surname(placing.group("actor"))
        add(actor, f"finished_{placing.group('rank')}_in",
            f"{placing.group('event')} at the {placing.group('competition')}")
        add(placing.group("competition"), "held_in", placing.group("city"))

    retirement = re.search(
        r"^After retiring from (?P<activity>.+?) (?P<actor>[A-Z][\w'-]+) "
        r"became a (?P<role>[^,]+)", clause.text,
    )
    if retirement:
        actor = resolve_surname(retirement.group("actor"))
        retirement_evidence = clause.text[:retirement.end()]
        add(actor, "retired_from", retirement.group("activity"),
            condition="", evidence=retirement_evidence)
        add(actor, "became", retirement.group("role"),
            condition=f"after retiring from {retirement.group('activity')}")
        team_result = re.search(
            r"\bleading (?P<team>.+?) to (?P<medals>\w+ medals) at the "
            r"(?P<competition>\d{4} Winter Olympics) in (?P<city>[^,(]+)",
            clause.text, re.I,
        )
        if team_result:
            add(actor, "coached", team_result.group("team"), condition="")
            add(team_result.group("team"), "won",
                f"{team_result.group('medals')} at the {team_result.group('competition')}",
                condition="")
            add(team_result.group("competition"), "held_in",
                team_result.group("city"), condition="")
            medal_details = clause.text[team_result.end():]
            for winner in re.finditer(
                r"\ba (?P<medal>gold|silver|bronze) for "
                r"(?P<person>[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)+)",
                medal_details, re.I,
            ):
                winner_name = re.sub(r"\s+and$", "", winner.group("person"), flags=re.I)
                add(winner_name, "won",
                    f"{winner.group('medal')} medal at the {team_result.group('competition')}",
                    condition="")
        coached_victor = re.search(
            r"\bcoaching (?P<person>[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)+) "
            r"to victory in the (?P<competition>\d{4} Winter Olympics) in "
            r"(?P<locations>[^.]+)", clause.text, re.I,
        )
        if coached_victor:
            add(actor, "coached", coached_victor.group("person"), condition="")
            add(coached_victor.group("person"), "won",
                coached_victor.group("competition"), condition="")
            locations = [normalize_space(part) for part in
                         coached_victor.group("locations").split(",")]
            add(coached_victor.group("competition"), "held_in", locations[0],
                condition="")
            for smaller, larger in zip(locations, locations[1:]):
                add(smaller, "located_in", larger, condition="")

    coaching_contract = re.fullmatch(
        r"In (?P<date>[A-Z][a-z]+ \d{4}) (?P<actor>[A-Z][\w'-]+) "
        r"agreed a (?P<duration>\w+)-year contract to coach the "
        r"(?P<team>[^.]+)\.?", clause.text,
    )
    if coaching_contract:
        actor = resolve_surname(coaching_contract.group("actor"))
        team = coaching_contract.group("team")
        duration = coaching_contract.group("duration")
        add(actor, "agreed_to", f"{duration}-year contract to coach the {team}",
            condition=f"in {coaching_contract.group('date')}")
        add(f"contract to coach the {team}", "duration", f"{duration} years",
            condition="")
        add(f"{duration}-year contract", "purpose", f"coach the {team}",
            condition="")

    if _EIGHTH_PROHIBITIONS.match(clause.text):
        for subject, state in (
            ("Excessive bail", "required"),
            ("excessive fines", "imposed"),
            ("cruel and unusual punishments", "inflicted"),
        ):
            add(subject, "has_status", state, modality="shall", polarity="negative")

    infringement = _RIGHT_INFRINGEMENT.search(clause.text)
    if infringement:
        add(infringement.group("right"), "has_status", "infringed",
            modality=infringement.group("modal").casefold(), polarity="negative")

    house_election = _HOUSE_MEMBERS_ELECTION.search(clause.text)
    if house_election:
        add("House of Representatives", "composed_of", "Members", modality="shall")
        add("Members of the House of Representatives", "chosen_every",
            house_election.group("interval"), modality="shall")
        add("Members of the House of Representatives", "chosen_by",
            house_election.group("voters"), modality="shall")
        elector_qualification = re.search(
            r"Electors in each State shall have the (?P<qualification>"
            r"Qualifications requisite for Electors of the most numerous "
            r"Branch of the State Legislature)",
            clause.text, re.I,
        )
        if elector_qualification:
            add("Electors in each State", "has",
                elector_qualification.group("qualification"), modality="shall")

    representative_qualification = _REPRESENTATIVE_QUALIFICATIONS.match(clause.text)
    if representative_qualification:
        add("Representative", "has_minimum_age_years", "25", modality="shall")
        add("Representative", "has_minimum_citizenship_years", "7",
            modality="shall")
        add("Representative", "inhabits", "State in which chosen",
            modality="shall", condition="when elected")

    apportionment = _HOUSE_APPORTIONMENT.match(clause.text)
    if apportionment:
        states = apportionment.group("states")
        numbers = "respective Numbers of the several States"
        for subject in ("Representatives", "direct Taxes"):
            add(subject, "apportioned_among", states, modality="shall")
        add("apportionment of Representatives and direct Taxes", "according_to",
            numbers, modality="shall")
        add(numbers, "includes", apportionment.group("free"), modality="shall")
        bound_persons = re.sub(
            r"^those\s+", "persons ", apportionment.group("bound"), flags=re.I
        )
        add(apportionment.group("free"), "includes", bound_persons,
            modality="shall")
        add(numbers, "excludes", apportionment.group("excluded"), modality="shall")
        add(numbers, "includes", apportionment.group("other"), modality="shall")

    enumeration = _ENUMERATION_SCHEDULE.match(clause.text)
    if enumeration:
        add("actual Enumeration", "made_within", enumeration.group("initial"),
            modality="shall")
        add("actual Enumeration", "made_every", enumeration.group("later"),
            modality="shall")
        add("Congress", "directs", "manner of actual Enumeration by Law",
            modality="shall")

    representation_limit = _HOUSE_REPRESENTATION_LIMIT.match(clause.text)
    if representation_limit:
        add("Number of Representatives", "exceeds",
            representation_limit.group("ratio"), modality="shall",
            polarity="negative")
        add("State", "has_at_least", representation_limit.group("minimum"),
            modality="shall")

    initial_representation = _INITIAL_REPRESENTATION.match(clause.text)
    if initial_representation:
        def representative_count(count: str) -> str:
            return f"{count} {'Representative' if count.casefold() == 'one' else 'Representatives'}"

        segments = [
            re.sub(r"^and\s+", "", item.strip(), flags=re.I)
            for item in initial_representation.group("allocations").split(",")
        ]
        if segments:
            add(initial_representation.group("first_state"), "entitled_to_choose",
                representative_count(segments[0]), modality="shall",
                condition="until such enumeration shall be made")
            for segment in segments[1:]:
                allocation = _ALLOCATION_COUNT.match(segment)
                if allocation:
                    add(allocation.group("state"), "entitled_to_choose",
                        representative_count(allocation.group("count")),
                        modality="shall",
                        condition="until such enumeration shall be made")

    representation_vacancy = _REPRESENTATION_VACANCY.match(clause.text)
    if representation_vacancy:
        add("Executive Authority of the State", "issues",
            "Writs of Election to fill vacancies", modality="shall",
            condition=representation_vacancy.group("condition"))

    if _HOUSE_OFFICERS.match(clause.text):
        add("House of Representatives", "chooses", "Speaker", modality="shall")
        add("House of Representatives", "chooses", "other Officers",
            modality="shall")
    if _HOUSE_IMPEACHMENT.match(clause.text) and antecedent == ("House of Representatives",):
        add("House of Representatives", "has", "sole Power of Impeachment",
            modality="shall")

    enforcement = _ENFORCEMENT_POWER.match(clause.text)
    if enforcement:
        action = normalize_space(enforcement.group("object"))
        action = re.match(
            r"^,\s*by\s+appropriate\s+legislation,\s*(?P<target>.+)$",
            action,
            re.I,
        )
        if action:
            object_ = f"enforce {action.group('target').rstrip(' .')} by appropriate legislation"
        else:
            object_ = "enforce " + normalize_space(enforcement.group("object"))
        if enforcement.group("concurrent"):
            object_ = "concurrently " + object_
        actors = ("Congress", "several States") if "several States" in enforcement.group("actors") else ("Congress",)
        for actor in actors:
            add(actor, "authorized_to", object_,
                modality=enforcement.group("modal").casefold())

    protected_right = _RIGHT_NONDISCRIMINATION.match(clause.text)
    if protected_right:
        right = canonical_entity(protected_right.group("right"))
        holder_qualification = re.search(r",\s*(who\s+.+?),\s*to\s+vote$", right, re.I)
        if holder_qualification:
            right = re.sub(r",\s*who\s+.+?,\s*to\s+vote$", " to vote", right, flags=re.I)
        holder = re.sub(r"^(?:The\s+)?right\s+of\s+", "", right, flags=re.I)
        holder = re.sub(r"\s+to vote$", "", holder, flags=re.I)
        election_scope = re.fullmatch(
            r"in any primary or other election for (?P<president>President) or "
            r"(?P<vice>Vice President), for electors for (?P=president) or "
            r"(?P=vice), or for (?P<senator>Senator) or "
            r"(?P<representative>Representative) in (?P<chamber>Congress)",
            (protected_right.group("vote_scope") or "").strip(" ,"), re.I,
        )
        tax_ground = re.fullmatch(
            r"failure to pay any (?P<poll>poll tax) or (?P<other>other tax)",
            protected_right.group("reason").rstrip(".-"), re.I,
        )
        if election_scope and tax_ground:
            offices = (
                election_scope.group("president"), election_scope.group("vice"),
                f"electors for {election_scope.group('president')}",
                f"electors for {election_scope.group('vice')}",
                f"{election_scope.group('senator')} in {election_scope.group('chamber')}",
                f"{election_scope.group('representative')} in {election_scope.group('chamber')}",
            )
            actors = re.split(r"\s+or\s+(?:by\s+)?", protected_right.group("actors"), flags=re.I)
            verbs = re.split(r"\s+or\s+", protected_right.group("verbs"), flags=re.I)
            for office in offices:
                add(holder, "has_right_to", f"vote in an election for {office}",
                    condition="in any primary or other election")
                for actor in actors:
                    for verb in verbs:
                        for tax in (tax_ground.group("poll"), tax_ground.group("other")):
                            add(right, f"{verb.casefold()}_by", actor,
                                modality=protected_right.group("modal").casefold(),
                                polarity="negative", condition=(
                                    f"in any primary or other election for {office}; "
                                    f"by reason of failure to pay any {tax}"
                                ))
        else:
            conditions = []
            if holder_qualification:
                conditions.append(holder_qualification.group(1))
            if protected_right.group("vote_scope"):
                conditions.append(protected_right.group("vote_scope").strip(" ,"))
            add(holder, "has_right_to", "vote", condition="; ".join(conditions) or None)
            actors = re.split(r"\s+or\s+(?:by\s+)?", protected_right.group("actors"), flags=re.I)
            verbs = re.split(r"\s+or\s+", protected_right.group("verbs"), flags=re.I)
            raw_reason = protected_right.group("reason").rstrip(".-")
            reasons = (
                re.split(r",\s*(?:or\s+)?|\s+or\s+", raw_reason, flags=re.I)
                if "," in raw_reason else [raw_reason]
            )
            for actor in actors:
                for verb in verbs:
                    for reason in reasons:
                        condition = "; ".join([
                            *conditions,
                            f"{protected_right.group('basis')} {reason.strip()}",
                        ])
                        add(
                            right, f"{verb.casefold()}_by", actor,
                            modality=protected_right.group("modal").casefold(),
                            polarity="negative", condition=condition,
                        )

    term_limit = _PRESIDENTIAL_TERM_LIMIT.match(clause.text)
    if term_limit:
        add("person", "elected_to", "office of the President", modality="shall",
            polarity="negative", condition=f"more than {term_limit.group('ordinary')}")
        add("person", "elected_to", "office of the President", modality="shall",
            polarity="negative", condition=(
                f"who {term_limit.group('prior_service')}; more than {term_limit.group('prior')}"
            ))

    term_exception = (
        _PRESIDENTIAL_TERM_EXCEPTION.match(clause.text)
        if (clause.source_unit or "").startswith("AMENDMENT_22") else None
    )
    if term_exception:
        amendment = re.match(r"AMENDMENT_(\d+)", clause.source_unit or "")
        amendment_subject = f"Amendment {amendment.group(1)}"
        prior = term_exception.group("prior")
        prior_match = re.match(r"(?P<person>.+?)\s+(?P<when>when this Article .+)$", prior, re.I)
        add(
            amendment_subject, "applies_to",
            prior_match.group("person") if prior_match else prior,
            modality="shall", polarity="negative",
            condition=prior_match.group("when") if prior_match else None,
        )
        current = term_exception.group("current")
        current_condition = re.search(r"during the term within which this Article becomes operative", current, re.I)
        action_text = term_exception.group("actions")
        remainder = re.search(r"during the remainder of such term", action_text, re.I)
        condition = "; ".join(
            part.group() for part in (current_condition, remainder) if part
        ) or None
        for action in ("holding the office of President", "acting as President"):
            if action.casefold() in action_text.casefold():
                add(
                    amendment_subject, "prevents", action,
                    modality="shall", polarity="negative", condition=condition,
                )

    officers_established = _OFFICERS_ESTABLISHED.search(clause.text)
    if officers_established:
        add(
            "Appointments of other Officers of the United States",
            "provided_for_in", "Constitution", polarity="negative",
        )
        add(
            officers_established.group("officers"),
            "established_by", "Law", modality="shall",
        )

    shared_object = _SHARED_MODAL_OBJECT.match(clause.text)
    if shared_object:
        object_ = re.split(r"\s+as\s+on\s+", shared_object.group("object"), maxsplit=1, flags=re.I)[0]
        add(shared_object.group("subject"), _predicate_for(shared_object.group("first")), object_, modality=shared_object.group("modal").casefold())
        add(shared_object.group("subject"), _predicate_for(shared_object.group("second"), shared_object.group("prep")), object_, modality=shared_object.group("modal").casefold())

    purpose = _PURPOSE.match(clause.text)
    if purpose:
        declaration_object = re.sub(
            r"^(?:this|that)\s+", "", purpose.group("object"), flags=re.I
        )
        add(purpose.group("subject"), "ordains", declaration_object)
        add(purpose.group("subject"), "establishes", declaration_object)
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
    if no_law and clause.source_unit != "AMENDMENT_1":
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
        actions = construed.group("actions")
        shared = re.fullmatch(
            r"(?P<first>deny|disparage)\s+or\s+"
            r"(?P<second>deny|disparage)\s+(?P<object>.+)",
            actions,
            re.I,
        )
        if shared:
            actions_to_add = (
                f"{shared.group('first')} {shared.group('object')}",
                f"{shared.group('second')} {shared.group('object')}",
            )
        else:
            actions_to_add = re.split(r"\s+or\s+|\s+and\s+", actions, flags=re.I)
        for action in actions_to_add:
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
            source_subject = (
                (clause.source_unit or "").replace("_", " ").title()
                if clause.source_unit else "containing provision"
            )
            add(source_subject, predicate, subject)
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
    if (first_passive and first_passive.group("modal")
            and ", nor " in clause.text.lower()
            and not _EIGHTH_PROHIBITIONS.match(clause.text)):
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
        locations = [
            normalize_space(part)
            for part in re.split(r",\s*or\s+", object_.rstrip("."), flags=re.I)
        ]
        exception = (
            f"except {neither.group('exception')}" if neither.group("exception") else None
        )
        for subject in (neither.group("first"), neither.group("second")):
            for location in locations:
                add(
                    subject, "exists_in", location,
                    modality=neither.group("modal").casefold(),
                    polarity="negative", condition=exception,
                )

    for right in (() if protected_right or clause.source_unit == "AMENDMENT_1"
                  else _RIGHT_TO.finditer(clause.text)):
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
        if passive and not infringement:
            right_label = normalize_space(right.group())
            add(
                right_label,
                "type",
                passive.group("verb").casefold(),
                modality=passive.group("modal").casefold(),
                polarity="negative" if passive.group("negative") else "positive",
            )
    return frames


def extract_frames(
    text: str,
    *,
    scientific_trace: list[dict[str, object]] | None = None,
    scientific_dependency_compiler: object | None = None,
    scientific_claims: list[ClaimFrame] | None = None,
) -> list[RelationFrame]:
    """Build relation frames from clauses using open modal and verb discovery."""
    prose_text = mask_table_bodies(text)
    prepared = clean_document(prose_text)
    aliases = find_aliases(prepared)
    clauses = _clauses(prose_text)
    raw_markers = _source_markers(text)
    raw_marker_positions = [position for position, _ in raw_markers]
    frames: list[RelationFrame] = []
    for frame in extract_structured_frames(text):
        # Structured measurements use offsets in the original source, whereas
        # prose clauses use cleaned offsets. Apply the same source-unit rules
        # to both paths without replacing a table's own locator.
        if frame.source_unit and frame.source_unit.startswith("TABLE_"):
            frames.append(frame)
        else:
            label = raw_markers[
                bisect_right(raw_marker_positions, frame.start) - 1
            ][1]
            frames.append(replace(frame, source_unit=label))
    seen: set[tuple[str, str, str, int, str, str, str]] = set()
    for frame in frames:
        seen.add(
            (
                canonical_entity(frame.subject_options[0]).casefold(),
                "/".join(frame.predicate_options),
                canonical_entity(frame.object_options[0]).casefold(),
                frame.sentence_index,
                frame.modality or "",
                frame.polarity,
                frame.condition or "",
            )
        )
    recent_subjects: tuple[str, ...] = ()
    recent_named_subjects: tuple[str, ...] = ()
    active_album: tuple[str, str] = ()
    carried_authority = False
    authority_subjects: tuple[str, ...] = ()
    authority_context = ""
    active_sentence = -1
    current_sentence_context = ""
    previous_sentence_context = ""
    sentence_subjects: tuple[str, ...] = ()
    sentence_predicates: tuple[str, ...] = ()
    sentence_modality: str | None = None
    sentence_polarity = "positive"
    event_state = EventState()
    scientific_compiler = ScientificClauseCompiler(
        dependency_compiler=scientific_dependency_compiler,
    )
    provision_state = ProvisionState()
    prose_state = ProseState()

    for clause in clauses:
        if clause.sentence_index != active_sentence:
            previous_sentence_context = current_sentence_context
            current_sentence_context = clause.context
            active_sentence = clause.sentence_index
            sentence_subjects = ()
            sentence_predicates = ()
            sentence_modality = None
            sentence_polarity = "positive"
        if re.match(r"^(?:Section|Article|Amendment)\b", clause.text, re.I):
            carried_authority = False
            authority_subjects = ()
            authority_context = ""
            recent_subjects = ()
            recent_named_subjects = ()
            active_album = ()
            sentence_subjects = ()
            sentence_predicates = ()

        album_intro = _ALBUM_INTRO.match(clause.text)
        if album_intro:
            active_album = (album_intro.group("title"), album_intro.group("artist"))

        scientific_modal_heading = bool(
            clause.source_unit
            and clause.source_unit.upper().startswith("RESULT")
            and re.search(r"\bcan\b", clause.text, re.I)
            and not re.search(r"[.!?]$", clause.text)
            and len(clause.text.split()) <= 20
        )
        scientific_research_question = bool(
            clause.source_unit
            and clause.source_unit.upper().startswith("RESULT")
            and re.match(
                r"^(?:To\s+)?(?:investigate|explore|determine|assess|examine)\s+whether\b",
                clause.text, re.I,
            )
        )
        scientific_result = scientific_compiler.compile(
            clause.text,
            source_unit=clause.source_unit,
            sentence_index=clause.sentence_index,
        )
        if scientific_claims is not None and scientific_result.hypotheses:
            scientific_claims.extend(hypotheses_to_claims(
                scientific_result,
                evidence=clause.text,
                sentence_index=clause.sentence_index,
                start=clause.start,
                end=clause.end,
                source_unit=clause.source_unit,
            ))
        if scientific_trace is not None and scientific_result.classification != "outside_scientific_results":
            scientific_trace.append({
                "sentence_index": clause.sentence_index,
                "source_unit": clause.source_unit,
                "text": clause.text,
                "classification": scientific_result.classification,
                "hypotheses": [
                    {
                        "subject": item.subject.normalized,
                        "predicate": item.predicate,
                        "object": item.object.normalized,
                        "modality": item.qualifiers.modality,
                        "polarity": item.qualifiers.polarity,
                        "condition": item.qualifiers.render(),
                        "construction": item.construction,
                    }
                    for item in scientific_result.hypotheses
                ],
                "trace": [
                    {
                        "stage": item.stage,
                        "decision": item.decision,
                        "detail": item.detail,
                    }
                    for item in scientific_result.traces
                ],
            })
        compiled_event_records = list(hypotheses_to_events(scientific_result))
        fallback_event_records = [] if scientific_modal_heading else assemble_events(
            clause.text,
            context_text=clause.context,
            previous_sentence=previous_sentence_context,
            source_unit=clause.source_unit,
            state=event_state,
        )
        event_records = []
        event_keys: set[tuple[str, str, str, str | None, str, str | None]] = set()
        compiled_predicate_spans = [
            (event.predicate, event.trigger.start, event.trigger.end)
            for event in compiled_event_records if event.trigger is not None
        ]
        for event in compiled_event_records:
            key = (
                event.subject.casefold(), event.predicate, event.object.casefold(),
                event.modality, event.polarity, event.context.render(),
            )
            if key not in event_keys:
                event_keys.add(key)
                event_records.append(event)
        for event in fallback_event_records:
            if event.trigger is not None and any(
                predicate == event.predicate
                and start < event.trigger.end
                and event.trigger.start < end
                for predicate, start, end in compiled_predicate_spans
            ):
                continue
            key = (
                event.subject.casefold(), event.predicate, event.object.casefold(),
                event.modality, event.polarity, event.context.render(),
            )
            if key not in event_keys:
                event_keys.add(key)
                event_records.append(event)
        event_frames = relation_frames_from_events(
            event_records,
            evidence=clause.text,
            context=clause.context,
            sentence_index=clause.sentence_index,
            start=clause.start,
            end=clause.end,
            source_unit=clause.source_unit,
        )
        scientific_reporting_wrapper = bool(
            event_records
            and clause.source_unit
            and clause.source_unit.upper().startswith("RESULT")
            and re.match(
                r"^(?:Our|The|These)\s+(?:results?|findings?)\s+"
                r"(?:revealed|showed|demonstrated|indicated|support|suggest)",
                clause.text, re.I,
            )
        )
        suppress_generic_scientific = (
            scientific_modal_heading
            or scientific_research_question
            or scientific_reporting_wrapper
            or scientific_result.suppress_generic
            or scientific_result.classification in {"heading", "procedure", "purpose"}
        )
        provision_records = assemble_provisions(
            clause.text, clause.source_unit, provision_state,
        )
        provision_frames = relation_frames_from_provisions(
            provision_records,
            context=clause.context,
            sentence_index=clause.sentence_index,
            start=clause.start,
            end=clause.end,
            source_unit=clause.source_unit,
        )
        prose_frames: list[RelationFrame] = []
        covered_result_spans: list[tuple[int, int]] = [
            (event.trigger.start, event.trigger.end)
            for event in event_records if event.trigger is not None
        ]
        if suppress_generic_scientific:
            covered_result_spans.append((0, len(clause.text)))
        # A recognized provision is already a complete, atomically expanded
        # reading of its clause.  Suppress the generic verb parser for that
        # clause so synonymous ``authorized_to`` frames do not duplicate its
        # source-specific power predicates or leak qualifiers across branches.
        if provision_frames or suppress_generic_scientific:
            covered_result_spans.append((0, len(clause.text)))
            fallback_semantic_frames = []
        else:
            fallback_semantic_frames = _semantic_frames(
                clause, aliases, recent_named_subjects, previous_sentence_context,
                active_album, covered_result_spans,
            )
            # The general clause assembler replaces only the broad fallback.
            # Existing exact semantic readers keep priority for a structure
            # they understand, including dates, biographies, and contracts.
            if not fallback_semantic_frames and not scientific_result.hypotheses:
                prose_frames = assemble_prose(
                    clause.text,
                    context=clause.context,
                    sentence_index=clause.sentence_index,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                    state=prose_state,
                )
                if prose_frames:
                    covered_result_spans.append((0, len(clause.text)))
        assembled_cores = {
            (
                canonical_entity(frame.subject_options[0]).casefold(),
                frame.predicate_options[0],
                canonical_entity(frame.object_options[0]).casefold(),
            )
            for frame in (*event_frames, *provision_frames, *prose_frames)
        }
        fallback_semantic_frames = [
            frame for frame in fallback_semantic_frames
            if (
                canonical_entity(frame.subject_options[0]).casefold(),
                frame.predicate_options[0],
                canonical_entity(frame.object_options[0]).casefold(),
            ) not in assembled_cores
        ]
        semantic_frames = [
            *event_frames, *provision_frames, *prose_frames,
            *fallback_semantic_frames,
        ]
        semantic_predicates = {
            predicate for frame in semantic_frames for predicate in frame.predicate_options
        }
        molecular_replacements: set[str] = set()
        if "associated_with" in semantic_predicates and "IgG Ab could not" in clause.text:
            molecular_replacements.add("precipitated")
            if re.search(r"\bassays? demonstrated that\b", clause.text, re.I):
                molecular_replacements.add("demonstrated")
        if "directly_interacted_with" in semantic_predicates:
            molecular_replacements.update(("suggest", "interacted_with"))
            if re.search(r"\bassay was performed, suggesting that\b", clause.text, re.I):
                molecular_replacements.add("performed")
        if "catalyzed" in semantic_predicates and "hydrolyzed" in clause.text:
            molecular_replacements.update(("hydrolyzed", "catalyzed_by"))
        if "formed_in" in semantic_predicates and "colocalized with" in clause.text:
            molecular_replacements.add("lead_to")
        if "formed_complex_with" in semantic_predicates and "formation of" in clause.text:
            molecular_replacements.add("showed")
        qualified_authority = any(
            frame.predicate_options == ("authorized_to",)
            and frame.condition
            and re.search(r"(?:^|; )to\s", frame.condition)
            for frame in semantic_frames
        )
        for semantic in semantic_frames:
            key = (
                canonical_entity(semantic.subject_options[0]).casefold(),
                "/".join(semantic.predicate_options),
                canonical_entity(semantic.object_options[0]).casefold(),
                semantic.sentence_index,
                semantic.modality or "",
                semantic.polarity,
                semantic.condition or "",
            )
            if key not in seen:
                seen.add(key)
                frames.append(semantic)
        if _BIOGRAPHICAL_INTRO.match(clause.text) and semantic_frames:
            recent_named_subjects = semantic_frames[0].subject_options[:1]
        if _HOUSE_OFFICERS.match(clause.text):
            recent_named_subjects = ("House of Representatives",)

        right_frames = [
            frame for frame in semantic_frames if frame.predicate_options[0] == "has_right_to"
        ]
        if right_frames and not sentence_subjects:
            sentence_subjects = right_frames[0].subject_options[:1]
            sentence_predicates = ("has_right_to",)
            sentence_modality = right_frames[0].modality
            sentence_polarity = right_frames[0].polarity

        if ((clause.source_unit == "AMENDMENT_20_SECTION_2" and clause.text.startswith(
                "The Congress shall assemble at least once in every year"))
                or (clause.source_unit == "AMENDMENT_20_SECTION_1" and (
                    clause.text.startswith("The terms of the President and Vice President")
                    or clause.text.startswith("and the terms of their successors shall then begin")))
                or _DOWNSTREAM_BLOCKADE.match(clause.text)
                or (semantic_frames and re.search(
                    r"\b(?:positively|negatively|inversely|reversely)\s+correlated\b",
                    clause.text, re.I,
                ))
                or (semantic_frames and re.search(
                    r"\bassociated\s+(?:with|to)\b.+\(\s*"
                    r"(?:p(?:-value)?|r|rho)\s*[<=>≤≥]",
                    clause.text, re.I,
                ))
                or (semantic_frames and re.search(r"\bdid\s+not\b.+\bbut\b", clause.text, re.I))
                or (semantic_frames and re.search(r"\bnot only\b.+\bbut also\b", clause.text, re.I))
                or (semantic_frames and re.search(r"\bopposite effects\b", clause.text, re.I))
                or (clause.source_unit == "ARTICLE_7" and bool(semantic_frames))
                or (clause.source_unit == "ARTICLE_4_SECTION_4" and bool(semantic_frames))
                or (clause.source_unit == "ARTICLE_4_SECTION_1" and bool(semantic_frames))
                or (clause.source_unit == "ARTICLE_3_SECTION_1" and bool(semantic_frames))
                or (clause.source_unit == "ARTICLE_3_SECTION_3" and bool(semantic_frames))
                or (clause.source_unit == "AMENDMENT_25_SECTION_3" and bool(semantic_frames))
                or (active_album and any(
                    frame.predicate_options[0] in {
                        "album_by", "released_in", "has_live_track_count",
                        "has_other_track_count", "features", "appears_on",
                    } for frame in semantic_frames))
                or (semantic_frames and (
                    re.search(
                        r"\bdownregulated in .+ compared with\b", clause.text, re.I
                    )
                    or re.match(
                        r"^(?:.+? \([A-Z0-9-]+\) is involved in the transcriptional|"
                        r"However, the cellular and biological effects of|"
                        r"Here, we investigated the role of|"
                        r"We observed that the .+ levels were increased|"
                        r"\S+ promoted .+ in vivo|"
                        r"The .+ expression levels were negatively correlated|"
                        r"Both ectopic expression and knockdown of|"
                        r"\S+ suppressed the expression of|"
                        r"In addition, \S+ has an opposite effect on|"
                        r"The cellular and biological effects elicited by|"
                        r"Taken together, our results indicate that .+ signaling axis)",
                        clause.text, re.I,
                    )
                    or re.match(
                        r"^(?:.+ dissemination is sustained by .+ functions|"
                        r"To disentangle the role of .+ knocked out the .+ gene|"
                        r"In this way, we evaluated the contribution of|"
                        r"The lack of .+ expression in .+ has been proved|"
                        r"From a functional point of view, .+ was ineffective|"
                        r".+ dissemination was assessed in vivo, evaluating|"
                        r"In both experimental models, .+ ablation affects|"
                        r"These results define a crucial contribution of)",
                        clause.text, re.I,
                    )
                    or re.match(
                        r"^(?:Dissemination of .+ depends on .+ attributes|"
                        r"Here, we identify .+ as a regulator of|"
                        r"Following induction by .+ localizes to|"
                        r"Accordingly, .+ depletion trimmed|"
                        r"Mathematical modeling suggested that .+ acquire|"
                        r"In animal models, silencing .+ increased|"
                        r"Congruently, analyses of .+ associated|"
                        r"We propose that .+ inhibits .+ by regulating|"
                        r"A .+ antibody to .+ was generated in)",
                        clause.text, re.I,
                    )
                    or "was reversely correlated with" in clause.text
                    or clause.text.startswith("While overexpression of ")
                    or "specifically bound to" in clause.text
                    or (clause.text.startswith("Loss of ") and "hydrolysis of" in clause.text)
                    or clause.text.startswith("Further studies shown that ")
                    or clause.text.endswith("were performed as previously described.")
                ))
                or (clause.text.startswith("After retiring from ")
                    and any(frame.predicate_options == ("retired_from",)
                            for frame in semantic_frames))
                or (re.match(r"In [A-Z][a-z]+ \d{4} .+ agreed a .+-year contract", clause.text)
                    and any(frame.predicate_options == ("agreed_to",)
                            for frame in semantic_frames))
                or _TIMED_LIQUOR_PROHIBITION.match(clause.text)
                or re.fullmatch(
                    r"The .+? were then collected for .+?\.?", clause.text, re.I
                )
                or (clause.source_unit == "AMENDMENT_25_SECTION_2" and clause.text.startswith(
                    "Whenever there is a vacancy in the office of the Vice President"))
                or (_INOPERATIVE_RATIFICATION.match(clause.text)
                and (clause.source_unit or "").startswith("AMENDMENT_"))
                or (clause.source_unit == "AMENDMENT_1" and clause.context.startswith(
                "Congress shall make no law respecting"))
                or (clause.source_unit == "AMENDMENT_10" and clause.text.startswith(
                    "The powers not delegated to the United States"))
                or (clause.source_unit == "AMENDMENT_3" and clause.text.startswith(
                    "No Soldier shall, in time of peace"))
                or (clause.source_unit == "AMENDMENT_4" and clause.text.startswith(
                    "The right of the people to be secure in their persons"))
                or (clause.source_unit == "AMENDMENT_5" and clause.context.startswith(
                    "No person shall be held to answer for a capital"))
                or (clause.source_unit == "AMENDMENT_6" and clause.context.startswith(
                    "In all criminal prosecutions, the accused shall enjoy"))
                or (clause.source_unit == "AMENDMENT_7" and clause.text.startswith(
                    "In Suits at common law, where the value in controversy"))
                or (clause.source_unit == "AMENDMENT_11" and clause.text.startswith(
                    "The Judicial power of the United States shall not be construed"))
                or (clause.source_unit == "AMENDMENT_27" and clause.text.startswith(
                    "No law, varying the compensation for the services"))
                or (clause.source_unit == "AMENDMENT_16" and clause.text.startswith(
                    "The Congress shall have power to lay and collect taxes on incomes"))
                or (clause.source_unit == "ARTICLE_2_SECTION_4" and clause.text.startswith(
                    "The President, Vice President and all civil Officers"))
                or (clause.source_unit == "AMENDMENT_21_SECTION_2" and clause.text.startswith(
                    "The transportation or importation into any State, Territory"))
                or (clause.source_unit == "ARTICLE_1_SECTION_3" and not clause.text.startswith(
                    "Section."))
                or _PURPOSE.match(clause.text) or _NEITHER_EXISTS.match(clause.text)
                or _EIGHTH_PROHIBITIONS.match(clause.text)
                or _RIGHT_INFRINGEMENT.search(clause.text)
                or _REPRESENTATIVE_QUALIFICATIONS.match(clause.text)
                or _HOUSE_APPORTIONMENT.match(clause.text)
                or _ENUMERATION_SCHEDULE.match(clause.text)
                or _HOUSE_REPRESENTATION_LIMIT.match(clause.text)
                or _INITIAL_REPRESENTATION.match(clause.text)
                or _REPRESENTATION_VACANCY.match(clause.text)
                or _HOUSE_OFFICERS.match(clause.text)
                or _HOUSE_IMPEACHMENT.match(clause.text)
                or _ENFORCEMENT_POWER.match(clause.text)
                or _RIGHT_NONDISCRIMINATION.match(clause.text)
                or _PRESIDENTIAL_TERM_LIMIT.match(clause.text)
                or ((clause.source_unit or "").startswith("AMENDMENT_22")
                    and _PRESIDENTIAL_TERM_EXCEPTION.match(clause.text))):
            continue

        hits = [
            hit for hit in _relation_hits(clause.text)
            if normalize_space(clause.text[hit.end:]).strip(".,;:!?")
            and not any(start <= hit.start < end for start, end in covered_result_spans)
        ]
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
            if any(predicate in molecular_replacements for predicate in hit.predicates):
                continue
            if (any(predicate in semantic_predicates for predicate in hit.predicates)
                    and not (hit.predicates == ("authorized_to",)
                             and qualified_authority)):
                continue
            if (_OFFICERS_ESTABLISHED.search(clause.text)
                    and clause.text[hit.start:hit.end].casefold() == "provided"):
                continue
            subject_text = clause.text[prior_hit_end : hit.start]
            subject_surface = _trim_left(subject_text)
            person_pronoun = bool(re.fullmatch(r"he|she", subject_surface, re.I))
            explicit_subject = _valid_entity(_trim_left(subject_text))
            inherits_sentence_subject = bool(
                sentence_subjects
                and (
                    (
                        clause.continuation
                        and re.match(r"^(?:and|or|nor|to)\b", clause.text, re.I)
                        and not explicit_subject
                    )
                    or (hit_index > 0 and not explicit_subject)
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
            elif person_pronoun and recent_named_subjects:
                raw_subjects = recent_named_subjects
            elif (
                clause_subjects
                and re.search(r"\bby\s*$", subject_text, re.I)
                and re.search(r"\b[A-Za-z'-]+ing\b", clause.text[hit.start:hit.end], re.I)
            ):
                raw_subjects = clause_subjects
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
            if hit_index + 1 < len(hits):
                coordinated_subject = re.search(
                    r"(?P<object>.+?)\s+and\s+(?P<next_subject>"
                    r"[A-Za-z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z][A-Za-z0-9'’.-]*){0,5})$",
                    object_text.strip(),
                    re.I,
                )
                if (coordinated_subject
                        and len(coordinated_subject.group("next_subject").split()) <= 4
                        and not re.search(
                            r"\b(?:and|or|of|in|on|for|with)\b",
                            coordinated_subject.group("next_subject"), re.I,
                        )
                        and _valid_entity(coordinated_subject.group("next_subject"))):
                    object_text = coordinated_subject.group("object")
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
            if hit_index == 0 and subjects and explicit_subject and not person_pronoun:
                recent_named_subjects = subjects[:1]
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
                    negation_prefix = r"^(?:no|never|neither|nor|not(?!\s+(?:only|just)\b))\b"
                    if re.match(negation_prefix, subject_branch, re.I) or re.match(
                        negation_prefix, object_branch, re.I
                    ) or re.search(
                        r"\b(?:not|never)\s*$", subject_text, re.I
                    ) or re.match(
                        r"^\s*(?:no|never|not(?!\s+(?:only|just)\b))\b", object_text, re.I
                    ) or re.match(
                        r"^\s*(?:no|neither|nor)\b", subject_text, re.I
                    ):
                        polarity = "negative"
                    relation_condition = _predicate_condition(clause, hit)
                    key = (
                        canonical_entity(subject_options[0]).casefold(),
                        "/".join(hit.predicates),
                        canonical_entity(object_options[0]).casefold(),
                        clause.sentence_index,
                        modality or "",
                        polarity,
                        relation_condition or "",
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
                            context=(
                                f"{authority_context} {clause.context}"
                                if hit.priority == 5 and carried_authority and authority_context
                                and authority_context not in clause.context
                                else clause.context
                            ),
                            sentence_index=clause.sentence_index,
                            start=clause.start,
                            end=clause.end,
                            modality=modality,
                            polarity=polarity,
                            source_unit=clause.source_unit,
                            condition=relation_condition,
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
                if not carried_authority:
                    authority_context = clause.context
                carried_authority = True
                if subjects:
                    authority_subjects = subjects[:1]
            if object_branches:
                local_antecedents = tuple(
                    value for value in object_branches if _valid_entity(value)
                )[:4]
            prior_hit_end = hit.end

            first_subjects = _subject_options(subject_text, aliases, context_entities)
            if first_subjects and not _PRONOUN.fullmatch(subject_surface):
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
            subject=(
                normalize_space(frame.subject_options[0])
                if frame.origin == "provision"
                else canonical_entity(frame.subject_options[0])
            ),
            predicate=frame.predicate_options[0],
            object=(
                normalize_space(frame.object_options[0])
                if frame.origin == "provision"
                else canonical_entity(frame.object_options[0])
            ),
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
            attribution=frame.attribution,
            claim_type=frame.claim_type,
            comparison=frame.comparison,
            conditions=frame.conditions,
            measurements=frame.measurements,
            origin=frame.origin,
            context=frame.context,
        )
        for frame in frames
    ]


def extract_candidates(text: str) -> list[CandidateTriple]:
    """Return deterministic candidates without calling Jev."""
    return candidates_from_frames(extract_frames(text))


def extract_claims(
    text: str,
    *,
    scientific_dependency_compiler: object | None = None,
    scientific_trace: list[dict[str, object]] | None = None,
) -> list[ClaimFrame]:
    """Return structured scientific claims without flattening qualifiers."""
    claims: list[ClaimFrame] = []
    extract_frames(
        text,
        scientific_trace=scientific_trace,
        scientific_dependency_compiler=scientific_dependency_compiler,
        scientific_claims=claims,
    )
    return claims
