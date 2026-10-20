# Reader brief: does the supplement state the ionic strength of this zeta measurement?

You read supplementary text (SI) for papers whose zeta-potential rows have **no ionic strength in
the main text**. For each row, decide whether the SI states the ionic strength of the liquid in
which **that row's zeta potential was measured**. You propose; `verify.py` decides. It rejects
any quote that is not verbatim in the SI file, and any value the quote does not print.

## Inputs

- A packet per paper: `data/interim/si_scan/packets/<PMCID>.md`. It lists the rows without an
  ionic strength (row id, particle, the main text's medium and quote) and what a scan found in
  the SI: strict statements (salt + molar concentration, or "ionic strength" + concentration)
  and broad windows (salt or electrolyte words near a zeta mention). The broad windows are
  mostly noise.
- The SI text itself: `data/interim/si_text/<PMCID>/*.txt`. Open it whenever the packet's
  context is not enough, for example when a table caption names the medium only in its header,
  or when the main text says "see Table S1". Search it for zeta, ζ, mobility, NaCl, KCl,
  electrolyte, ionic, buffer, medium, dispersed, diluted.

## Rules (the extraction's own; do not relax them)

1. **The measurement, not the experiment.** The liquid must be the one the zeta potential was
   measured in. Aggregation, sorption, exposure, culture, transport and modelling conditions
   count only if the text says zeta was measured in that liquid.
2. **The particle.** A membrane's, sand's or cell's zeta potential is not a nanoplastic row's.
3. **is_stated.** The SI calls a number an ionic strength ("ionic strength of 1 mM", "IS = 10 mM",
   "I ≈ 90 mM"). `mM` is that number in mM.
4. **salt_composition.** The SI names one or more salts at **molar** concentrations (mM, M,
   mmol/L, mol/L), which the measurement liquid contains: "diluted in 10 mM KCl". `mM` is the
   ionic strength from them: 1:1 salts (NaCl, KCl, KNO3, NaNO3) × 1; CaCl2, MgCl2, Na2SO4,
   Ca(NO3)2 × 3; MgSO4, CaSO4 × 4; sum over salts. "10 mM KCl" → 10; "1 mM CaCl2" → 3.
5. **Not ionic strengths (record them, never as a claim):**
   - `buffer_only`: a buffer and its concentration ("10 mM phosphate buffer", "PBS", "HEPES
     25 mM"). Never look up a buffer's nominal composition.
   - `di_water_only`: DI, Milli-Q, ultrapure or distilled water, with no salt added at a stated
     final concentration. "A drop of 150 mM NaCl added" states the stock, not the final
     concentration: `di_water_only` with a note.
   - `mass_units_composition`: salts given only in mass units (mg/L, g/L, mg per 10 mL). Do not
     convert.
   - `other_step`: an ionic strength or salt concentration that belongs to another step,
     liquid or particle (rules 1 and 2).
   - A conductivity is never an ionic strength.
   - An ionic strength of 0 mM is unreported.
6. **Series.** If the SI gives zeta at several salt concentrations, assign a value to a row only
   when the row's own particle and condition map to one of them without guessing. If the main
   table's row does not say which level it is, say so in a note and give no claim.

## Output

Append one JSON object per line to your output file. One line per row that gets a verdict
other than `nothing`. Then **one line per paper** with `"row_id": "*"` and `"verdict":
"nothing"` if no row gets anything, or `"verdict": "done"` otherwise. That way every packet is
accounted for.

```json
{"pmcid": "PMC123", "row_id": "PMC123-r2", "verdict": "salt_composition", "mM": 10, "file": "<exact .txt filename in data/interim/si_text/PMC123/>", "quote": "<verbatim, contiguous, <= 300 chars, must contain the number and the salt or 'ionic strength'>", "note": "<one sentence: why this liquid is the zeta measurement's>"}
{"pmcid": "PMC123", "row_id": "*", "verdict": "done", "mM": null, "file": "", "quote": "", "note": ""}
```

- `verdict` ∈ is_stated, salt_composition, buffer_only, di_water_only, mass_units_composition,
  other_step, nothing, done.
- `quote`: copy it character for character from the .txt (line breaks may become spaces). For
  a claim, the quote must contain the concentration and the salt name or the words "ionic
  strength" in one span. If the SI's table layout splits them, quote the caption or sentence
  that joins them; if nothing joins them, give the claim anyway and say so in the note.
- Uncertain? Prefer no claim, with a note. A false "stated" is the worst error here: the study
  measures how often this condition goes unreported.

Do not edit any file other than your output file.
