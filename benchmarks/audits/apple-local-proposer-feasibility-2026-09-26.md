# Apple on-device FoundationModels complete-claim probe — 2026-09-26

## Scope and method

This is a **bounded development diagnostic**, not a held-out or independently human-audited score. The two frozen source passages were [scientific](../fixtures/span-fresh-scientific-2026-09-26.json) (four gold claims) and [legal](../fixtures/span-fresh-legal-2026-09-26.json) (three gold claims). The model saw only each fixture's `text`, not its instruction, gold, IDs, or review notes. The same generic extraction prompt requested separate complete atomic records with actor, relation, target, polarity, modality, material condition, and one exact contiguous evidence substring. No OpenAI or Jev calls were made.

Host: macOS 26.4, arm64, Swift 6.3.2, Apple model availability `available`. The intended `@Generable`/`@Guide` struct is preserved at `/tmp/jevy-apple-model-probe/probe.swift`, but compilation failed because the installed Command Line Tools do not contain the `FoundationModelsMacros` compiler plugin; no full Xcode was installed. One implementation adjustment used Apple's documented `DynamicGenerationSchema` with the **same seven required string fields**. Its source and executable are `/tmp/jevy-apple-model-probe/dynamic.swift` and `/tmp/jevy-apple-model-probe/dynamic`. This tests on-device guided generation, but it is not literally an `@Generable` run. Apple describes both [macro-generated structured types](https://developer.apple.com/documentation/foundationmodels/generable) and [runtime dynamic schemas](https://developer.apple.com/documentation/foundationmodels/generating-swift-data-structures-with-guided-generation); `GeneratedContent.jsonString` is the captured [generated content representation](https://developer.apple.com/documentation/foundationmodels/generatedcontent).

The calls were sequential, once per passage, with a fresh session each time. Wall time is measured inside the process from just before availability checking through response or error. It excludes Swift compilation. No sampling distribution or repeatability claim follows from one call each. The exact response wrapper files are `/tmp/jevy-apple-model-probe/scientific-output.json` and `/tmp/jevy-apple-model-probe/legal-output.json`; the generated JSON string below is copied verbatim from the former.

## Raw output and evidence validation

Scientific call: **5.03 s**, two records, no API error. Exact `rawGeneratedJSON`:

```json
{"claims": [{"polarity": "positive", "evidence": "We found that plants generally benefited from soil microbes, and this benefit was greater whenever their current watering conditions matched the microbes' historical watering conditions.", "actor": "plants", "target": "soil microbes", "modality": "generally", "materialCondition": "whenever their current watering conditions matched the microbes' historical watering conditions", "relation": "benefited from"}, {"modality": "principally", "relation": "were not necessary", "actor": "plants", "polarity": "negative", "materialCondition": "for this environmental matching benefit to emerge", "target": "historical treatments", "evidence": "Moreover, we found microbes from droughted soils could better tolerate drought stress."}]}
```

| Record | Exact evidence substring? | Actual source offsets (Python, end exclusive) | Complete-claim review |
| --- | --- | --- | --- |
| 1 | Yes | 0–186 | Fails both possible matches: it attaches the moisture-match condition to the **general** microbial benefit and omits that the matched-condition benefit was **greater**. It also uses `generally` as modality. |
| 2 | Yes | 319–405 | Fails: the cited span is the **drought** sentence, while the record claims plants “were not necessary” with historical treatments as target. The proper claim concerns **plant presence in historical treatments** being unnecessary for the environmental matching benefit. Exact substring checking alone missed this wrong-support error. |

Legal call: **71.89 s**, no generated claims. The exact `error` string:

```text
FoundationModels.LanguageModelSession.GenerationError.exceededContextWindowSize(FoundationModels.LanguageModelSession.GenerationError.Context(debugDescription: "Content contains 4089 tokens, which exceeds the maximum allowed context size of 4096.", underlyingErrors: [Provided 4,089 tokens, but the maximum allowed is 4,096.], errorDescriptionOverride: nil))
```

The legal model invocation exhausted its context during generation. There was no retry, truncation, sentence splitting, or prompt retuning. The failure is part of this probe's feasibility result, not a legal extraction score on completed output. Apple's documentation notes that a session can throw when it [exceeds available context](https://developer.apple.com/documentation/foundationmodels/generable).

## Codex review against frozen gold

Using the fixtures' strict complete-claim rubric, the scientific output matches **0/4** gold claims and **0/2** emitted records are complete and correctly supported: **0% recall, 0% precision** on that tiny development passage. The legal call emitted no records because it failed, so legal recall was **0/3 for this attempted run**; precision is undefined because there is no denominator. These are not release metrics. The second scientific record has a material wrong-evidence and role error, so the zero-unsupported-critical-claims gate is not met in this probe.

Failure types: conflated distinct findings; condition attached to the wrong event; omitted comparative direction; modifier assigned to modality; unresolved/incorrect actor and target; evidence copied from an unrelated sentence; legal context-window exhaustion. The observed outputs do **not** justify implementing or promoting an Apple local proposer. A future run would first need an environment with the `@Generable` plugin, bounded output/context strategy, and fresh blind evaluation; this probe makes no claim that those changes would recover performance.
