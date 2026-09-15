# Extraction brief

**Reconstructed 2026-09-13; three rules ratified by Martin the same day** (the ionic
strength of a printed composition, the incubation temperature, and the scope of a condition
— `docs/DECISIONS_NEEDED.md`, `tests/edge/key.yaml` C1/C2/C5). The brief that governed the first corpus run was never stored
in the repository and has been lost with the session scratchpad. This file restates the rules
as they stood at the end of that run, assembled from the personas, the coercion rules in
`src/mnp/extract/coerce.py` and the decisions recorded in worker reports. Records produced
before this date carry `brief_sha256: null` and cannot be traced to their instructions — see
`docs/METHODOLOGY.md` §3.

From here on, every ingest records the hash of this file. Edit it and the hash changes, so a
mid-run rule change is visible in the data instead of silent.

---

## What you are measuring

How often a published zeta potential or electrophoretic mobility of a micro/nanoplastic
particle is reported **without the conditions needed to interpret it**: the dispersion
medium, the ionic strength, the pH, the temperature, and the instrument.

A measurement with no printed number is still a measurement, and is the most important case
in the study. Never discard it.

## What counts as a plastic particle

Synthetic polymers: PS, PE, PP, PET, PVC, PMMA, PLA, PLGA, PCL, nylon, PTFE, PBAT, latex and
polymer beads, micro/nanoplastics of any polymer, weathered or surface-modified.

Excluded: natural polymers (chitosan, cellulose, lignin, alginate, starch, protein, gums),
inorganic particles (metal and metal-oxide, silica, carbon, graphene, clay, MXene, quantum
dots), cells, bacteria, flat membranes and fabrics, sediments and soils. A polymer *coating*
on an inorganic core is not a plastic particle.

## What counts as this study's measurement

Only measurements the paper made. Not:
- a value cited from another study;
- a general stability threshold ("particles above ±30 mV are stable");
- an applied voltage or an accelerating voltage;
- a polymer standard used only to calibrate an instrument.

### The plastic particle must be what was measured

Ratified 2026-09-15 (edge case S8). The measurand has to be the plastic particle itself. A
zeta potential or mobility measured on something else — a protein, a cell, a medium, a
supernatant — does **not** become a plastic measurement because plastic was present earlier in
the experiment. In particular:

- **The particles were removed before the measurement.** Filtered, centrifuged or settled out,
  and the supernatant measured. That is a measurement of the supernatant. Record nothing.
- **The measurand is a different material that was exposed to plastic.** "Zeta potential of Aβ
  when exposed to MNP", "zeta of cells after microplastic exposure". Record nothing, however
  clearly the paper attributes the shift to the plastic.
- **A paper reporting only a change in someone else's zeta.** A shift of a few mV in a peptide
  or a cell is not the plastic's surface charge.

The test is simple: *if the plastic had never been added, would there still be something in the
cuvette with a zeta potential?* If yes, the measurement is of that thing. In the case this rule
was written from, the paper's own no-plastic control returned the same value as the exposed
samples, which settles it.

If the paper measures the plastic **and** something else, record only the plastic's rows.

**Where this rule stops** (edge case S21, ratified 2026-09-15). It removes a measurement when
the plastic is *gone* from the cuvette or was never the analyte. It does **not** remove a
measurement of plastic particles because the liquid around them was treated, aged, filtered of
*other* things, or otherwise messy. Residual particles suspended in a treated water are still
particles: if the paper reports "the ζ potential of PS, PE and PET" in a supernatant that still
holds them, record it, with the treated water as the medium.

The distinction is what is in the cuvette carrying the charge:

| In the cuvette | Record? |
|---|---|
| The plastic particles, in any medium however complex | **yes** |
| A supernatant the particles were removed from | no |
| A protein, cell or floc that would exist without the plastic | no |
| Two mixed particle populations, plastic and something else | see below |

**Two particle populations** (edge case S23, ratified 2026-09-15). When the plastic is mixed
with another colloid — a microgel, a mineral, serum protein — the question "would there still
be something in the cuvette with a zeta potential?" answers yes either way, so it decides
nothing. Use instead: **is the other material adsorbed onto the plastic?**

- Adsorbed onto it → the measured object is a coated plastic particle. **Record it.** A protein
  corona is the textbook case: the particle is the analyte, the serum is its medium.
- Free in suspension alongside it → the reading is a mixture of two populations. Record nothing.

## The value

Copy exactly as printed, with its sign. Never compute, convert, average, estimate or infer.

`value: null` is correct and expected when the number exists only in a figure, only in the
supplement, or only as a qualitative statement ("more negative after ageing"). Record the row
anyway, with its conditions and the sentence that reports the measurement.

A printed range ("−5 to −14 mV") is the value as printed.

## The unit

Verbatim as printed. `cm²/Vs`, `10⁻⁸ m²V⁻¹s⁻¹`, `µm cm/Vs` and `(µm/s)/(V/cm)` are different
strings that convert differently; the conversion is the pipeline's job. A unit retyped into
what you think it "should" be has corrupted this dataset before — 25 rows stored 100× too
large because `cm²/Vs` was rewritten as `m²/Vs`.

Zeta potential and electrophoretic mobility are different quantities. Never convert between
them.

## The conditions

Each one exactly as written, `null` when not stated. Never assume 25 °C, pH 7, or water.

- Medium: verbatim. "DI water" is a reported medium but not a reported ionic strength.
- Ionic strength: a named salt at a stated concentration counts ("10 mM NaCl"). A printed
  *composition* also counts when the strength follows directly from named species at stated
  concentrations — "0.0027 M potassium chloride, 0.137 M sodium chloride" is 139.7 mM — and
  such a value is recorded as **derived**, not as printed. A component whose speciation the
  paper does not state (phosphate at an unstated pH) contributes nothing. "PBS" or "HEPES"
  with no composition does not count — never look up a nominal value.
- pH: numeric only. A range is a range, not a midpoint.
- Temperature: only a temperature explicitly associated with the zeta/mobility
  **measurement** counts. A temperature stated for a different step — incubation, exposure,
  culture, digestion, storage — is not the measurement temperature, and stays not the
  measurement temperature even when the paper gives no other temperature and even when
  temperature is the paper's own variable. This distinction is the single largest source of
  extraction error measured so far.
- Instrument: any named instrument counts. "Zetasizer" with no model is the family level.

### The scope of a condition

A condition holds **only within the experiment that states it**. Do not carry a medium, a
pH, an ionic strength or a temperature across distinct preparations or measurements unless
the paper explicitly says it applies to them ("all samples were measured in ...").

What this means in practice: the row's own `evidence_quote` must carry the sentence that
establishes each condition you record. Join separate sentences with `" || "`. A condition
that appears elsewhere in the article but not in your quote is flagged
`*_not_in_evidence` — it was read across experiments, which is an inference, not a reading.

## The evidence

`evidence_quote` must be a verbatim sentence or table row from the text you were shown,
copied character for character including odd spacing and glued-together tokens. The pipeline
checks it against the article; a quote you cleaned up will fail verification.

## Ambiguity

Report it, do not resolve it. How often the literature is ambiguous is part of the finding.
