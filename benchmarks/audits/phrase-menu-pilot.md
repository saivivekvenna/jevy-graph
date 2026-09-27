# Phrase-menu concept pilot

**Result: 15/15 expected claims recovered, 15/15 emitted claims supported and
complete under this pilot's sentence-level rubric.** Codex reviewed the output
against frozen expected meanings. Six examples are synthetic; six are verbatim
sentences from existing scientific source fixtures. This is selected development
data, with two refinements after inspecting failures, not held-out accuracy.

## Implementation

`src/jevy_graph/phrase_pilot.py` is an isolated experiment. Production extraction
and its defaults are unchanged. It uses no Luna or other generation model.

1. Deterministic lexical/morphological rules offer candidate predicate phrases.
2. Jev identifies the phrases asserting relations, including negated relations.
3. Code creates whole-phrase menus at grammatical boundaries in the source.
4. Jev selects the subject for each predicate, then the object with both earlier
   slots fixed. Both menus allow abstention.
5. Jev identifies applicable source qualifiers. Code preserves nominal `of`
   attachments and moves selected setting/time suffixes into claim conditions.
6. Jev judges whether proposed AND expansions hold individually. Joint actors
   remain collective; distinct outcomes can become separate triples.
7. The regular Jev verifier checks every resulting claim before admission.

The pilot is capped at 16 passages of 80 tokens each. Choices are source spans;
there is no free-form rewriting and no hand-authored per-sentence candidate menu.

## Reviewed examples

| Case | Result |
| --- | --- |
| Increased proliferation and migration | Two edges, both with CRC-cell context |
| Did not increase proliferation | Negative polarity retained |
| May increase proliferation | `may` retained |
| Passive c-Myc repression | Direction preserved through passive predicate |
| Alice and Bob jointly founded Acme | Collective actor preserved |
| Effect only in treated mice | `only` condition retained |
| TINCR transcribed by Sp1 and repressed by c-Myc | Both relations recovered |
| Partial suppression of Sp1-induced expression | `partly` and induced expression preserved |
| Sp1 overexpression in HCT116 and SW480 | Expression target and both cell settings preserved |
| TOP-Flash activity increment | 200%–300% measurement retained |
| Unchanged mRNA but reduced protein | Separate negative and positive findings |
| Dopaminergic tone during conditioning | Event and time context retained |

## Cost and refinements

- Final run: **6 Jev requests**, **15,999 input / 3,331 output tokens**, **0.963 s**
  measured wall time in this local run; **0 Luna calls**.
- Three development runs combined: 17 Jev requests, 47,299 input / 9,945 output
  tokens; 0 Luna calls. Provider token totals are reported, not inferred dollars.
- The first run merged two outcomes. The second separated them but incorrectly
  detached `of TINCR` from the expression node. A generic rule keeping `of`
  attachments with their noun fixed that boundary error on the final run.

## Limits

This shows that a small phrase-menu approach can work. It does not establish
full-paper recall, cross-sentence context/antecedent resolution, general verb
coverage, nominal relationships, source conversion coverage, or novel-domain
performance. This pilot allows both named cell settings in one condition record;
the full-paper audit sometimes counts cell-specific findings separately. Its
100% result must not replace or be directly compared with the prior whole-paper
51.1% recall / 54.3% complete-claim precision.

The next useful evaluation is an untouched sample of more varied sentences using
these frozen rules, then source-context handling if that sample passes.

## Reproduce

```sh
PYTHONPATH=src python3 scripts/probe_phrase_menus.py --output out/phrase-menu-dry.json
PYTHONPATH=src python3 scripts/probe_phrase_menus.py --live
```

Fixture: `benchmarks/fixtures/phrase-menu-pilot.json`.
Final output: `out/phrase-menu-pilot.json`.
Prior outputs: `out/phrase-menu-pilot-v1.json`, `out/phrase-menu-pilot-v2.json`.
Per-claim review: `benchmarks/audits/phrase-menu-pilot-review.json`.
