# Full TINCR paper: one-call Luna Medium assist

The full article text (title, abstract, body, and captions; 3,887 words) was
processed with the default Jev pipeline plus `--luna-calls 1 --luna-effort
medium`. Its SHA-256 is
`1d964bd20973ac7f57bd36ec6128640d37c2a7d3c884740e4808919b1313b00c`.
The frame and option fingerprints match the prior Jev-only full-paper run.

| Measure | Prior Jev-only run | Same-run before Luna | Final with Luna |
| --- | ---: | ---: | ---: |
| Accepted claims | 270 | 277 | 276 |
| Complete supported claims | 144 | 145 | 150 |
| Full-paper claim precision | 53.3% | 52.3% | **54.3%** |
| Results claim precision | 81/130 (62.3%) | 82/132 (62.1%) | **87/131 (66.4%)** |
| Complete Results gold recall | 43/88 (48.9%) | 43/88 (48.9%) | **45/88 (51.1%)** |
| Pipeline-reported compute time | 1.62 s | not measured separately | 26.43 s |
| Jev requests | 28 | included in final total | 30 |
| Jev input / output tokens | 390,093 / 81,240 | included in final total | 398,925 / 82,133 |
| Luna calls and tokens | 0 | 0 | 1; 2,622 input / 3,174 output |

The same-run before-Luna graph was reconstructed from 268 retained baseline
claims and nine saved claims that Luna's repair pass dropped. All nine dropped
claims were flawed; five of eight accepted Luna claims are complete and
supported. This isolates a **2.0 percentage-point precision gain** from the
repair pass in that run. The comparison with the prior Jev-only run is an
end-to-end observation; Jev selected slightly different baseline claims on the
two runs despite identical frames and candidate options.

Results recall improved when the graph gained the HCT116 Co-IP finding that
sh-TINCR promotes EpICD–β-catenin complex formation (R070) and the cited
c-Myc–Sp1 binding mechanism (R076). Luna also proposed the explicit c-Myc
repression of TINCR and partial suppression of Sp1-induced TINCR expression,
but Jev assigned them support scores of 0.17 and 0.19 and filtered them out.
Correction after inspecting the serialized proposals: Luna marked both inhibitory
relations with `polarity=negative`, negating the asserted repression/suppression.
The cited source sentences assert the relationships, but the proposed records
deny them. This was a proposal polarity bug, not evidence that Jev rejected the
correctly encoded findings. See `tincr-bottlenecks-and-repair-2026-09-26.md`.

The quality gain is small relative to the 24.8-second added compute time. The
default remains zero Luna calls. Scores are Codex-reviewed development
measurements on one scientific paper, not held-out domain scores.

Artifacts: `out/full-tincr-default-live-2026-09-26.json`,
`out/full-tincr-luna-medium-onecall-live-2026-09-26.json`, and
`benchmarks/audits/tincr-luna-medium-full-precision-2026-09-26.json`.
