You extract micro/nanoplastic zeta-potential measurements from scientific papers, for a study
of how often such a measurement is reported WITHOUT its measurement conditions.

Work in `/Users/martindurak/Desktop/web_rust/nanoplastics/services/mnp-research` (a `uv`
project). Do the work YOURSELF — do not launch sub-agents or delegate any part of it.

THESE PAPERS ARE DIFFERENT from the earlier waves: a value scanner found no printed
zeta/mobility number in them, yet they mention zeta or electrophoretic mobility. They are the
most important papers in the whole study, because "the measurement exists but the number is
not printed in the text" is exactly what the study is about. Your job is to decide, for each,
whether the paper reports a zeta/mobility measurement of a SYNTHETIC POLYMER particle at all —
and if it does, to record it even though there is no number.

For each PMCID in your list, in order:
1. `uv run python -m mnp.extract show --pmcid <PMCID> --no-system` and read it fully.
2. Decide: does this paper report a zeta potential or electrophoretic mobility of a synthetic
   polymer particle (PS, PE, PP, PET, PVC, PMMA, PLA, PLGA, PCL, nylon, PTFE, latex/polymer
   beads, micro/nanoplastics of any polymer)? NOT natural polymers (chitosan, cellulose,
   lignin, alginate, starch, protein), NOT inorganic (metal oxides, silica, carbon, clay,
   MXene, quantum dots), NOT cells, membranes or sediments.
3. If NO → write `{"measurements": []}`. That is a perfectly good answer; most of these papers
   will be this.
4. If YES → one object per (particle × medium × condition) that the paper describes, with:
   - `value`: the printed number if one exists anywhere (text, table or caption). If the number
     exists only in a figure, only in the supplementary material, or only as a qualitative
     statement ("highly negative", "became less negative"), set `value` to null. A null value
     is expected and wanted here — do not invent or estimate one.
   - `unit`: copy exactly as printed; "mV" if the paper says mV. If no unit is stated anywhere,
     use "mV" for zeta.
   - `quantity`: "zeta potential" or "electrophoretic mobility".
   - `conditions`: {medium_text, medium_class, ionic_strength, pH, temperature, instrument} —
     copy each exactly as written, null when not stated. Do NOT assume 25 °C, pH 7 or water.
     These conditions are the whole point: record them carefully even when the value is null.
   - `particle_name`, `material`, `functionalisation`, `supplier`, `size_nominal_nm`,
     `size_measured_nm`, `medium_matches_exposure`, `evidence_quote`, `evidence_location`.
   - `evidence_quote` must be a verbatim sentence from the shown text — the sentence that says
     the measurement was made. Copy it character for character, including any odd spacing.
   - `medium_class` one of: DI_water, buffer, salt_solution, culture_medium, biofluid,
     environmental_water, other, unreported.
5. Write the JSON to `/tmp/nn_<PMCID>.json` and ingest:
   `uv run python -m mnp.extract ingest --pmcid <PMCID> --json /tmp/nn_<PMCID>.json --model claude-code:sonnet`
6. Rows flagged `value_not_printed` are CORRECT here, not errors. A row dropped as
   `value_unparseable` means the evidence quote lacked a zeta keyword — fix the quote and
   re-ingest. Stop after 3 ingests per paper.

Report back as a compact table: PMCID | rows | note, where note is one short phrase:
"reports zeta, no number printed", "reports zeta with a number", "no plastic zeta in paper",
or the problem you could not resolve. Nothing else.
