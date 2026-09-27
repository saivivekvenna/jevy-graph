# Bounded Luna candidate repair on the TINCR paper

The unfocused Jev-only baseline for the full paper accepted 270 claims. The
Codex-reviewed baseline had 144/270 fully supported accepted claims and 43/88
complete Results claims. See `tincr-default-live-quality-2026-09-26.md`.

The optional repair path ranks small source windows by rejected/weak Jev claims,
section, and causal or qualified language. One Luna Low or Medium request per
selected window proposes atomic alternatives and missing claims. For each
flagged baseline claim, Jev chooses among the baseline, relevant Luna options,
and none. New selections then pass ordinary Jev verification and filtering.
The configured request cap is 0–2; the default is 0. No full-document model
discovery is involved.

The development probes reused the stored baseline instead of paying for a
second full Jev run:

| Probe | Luna input / output tokens | Luna seconds | Added Jev requests | Observation |
| --- | ---: | ---: | ---: | --- |
| Low, early prompt | 2,186 / 1,587 | 10.3 | 1 | Found c-Myc claims, but model-led deletion over-pruned correct claims; this design was replaced. |
| Medium, revised prompt | 2,215 / 4,176 | 31.5 | 1 | Split the tentative c-Myc mechanism into atomic claims; exposed source-offset drift. |
| Low, option-choice path | 2,860 / 1,088 | 8.1 | 2 | Jev replaced the reversed EpCAM actor claim and other malformed claims, but quality gains were mixed. |

After locating baseline claims by exact evidence text, a cached Medium response
for the c-Myc Results window was replayed with **no additional Luna call**.
Jev chose four Luna alternatives over flawed baseline claims and recovered
missing c-Myc repression and tentative mechanism statements. This was a
targeted development probe, not a new whole-paper precision or recall score.

The observed bottleneck remains Jev's willingness to keep some malformed
baseline choices and to accept some incomplete new claims. Keep Luna rescue
optional until its final outputs have a full claim audit on more documents.

Probe outputs are in `out/tincr-luna-low-one-call-probe.json`,
`out/tincr-luna-medium-one-call-probe.json`,
`out/tincr-luna-low-jev-options-final-probe.json`, and
`out/tincr-luna-medium-corrected-offset-probe.json`.
