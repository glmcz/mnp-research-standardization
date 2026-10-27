# Reisser 2013 and Eriksen 2014: the same tows, two values in NCEI

A case study for idea C (`docs/2026-10-10-review-call.md`), done 2026-10-12. Inputs are in
`data/raw/ncei/reisser_eriksen/` (gitignored; `SHA256SUMS` lists every file), and the outputs
of that run are in `out_2026-10-12/`.

- **Same tows.** All 171 Reisser 2013 rows in NCEI (doi 10.1371/journal.pone.0080466) are the
  same net tows as 171 of the Eriksen 2014 rows (doi 10.1371/journal.pone.0111913).
  - Reisser is the last author of Eriksen 2014, which cites Reisser 2013 as reference [10].
  - Eriksen's figshare data (doi 10.6084/m9.figshare.1015289) names "J. Reisser" as the
    source of 198 tows.
- **Same published numbers.** In pieces/km², Reisser Table S1 and the figshare sum CD1–CD4
  agree within 0.1 % for 168 of the 171 tows.
- **Different NCEI values.** NCEI converted each paper differently, and this accounts for
  every tow (largest relative error 2e-4):
  - **Depth:**
    - Reisser rows use Cs / 1e6 / d, with d = 0.085 m for Manta and 0.300 m for Neuston.
    - Reisser's Methods state 0.17 m for Manta (full immersion) and 0.3 m for Neuston.
    - Eriksen rows use d = 0.08 m for all 680 tows; Eriksen 2014 prints no net dimensions.
    - No NCEI field holds 0.085 m (checked 2026-10-27). The public table's `Water Sample Depth (m)`
      is 0 for all 851 rows of both papers, and it has no net-dimension field. The submission sheet
      NCEI staff keyed from the paper (`R_MP_data_S2N.xlsx`) holds only the pieces/m³ result, its
      data dictionary calls it a "density", and the ISO record lists it as "MICROPLASTIC
      CONCENTRATION (measured)". So 0.085 m has no semantic definition anywhere: it is a divisor
      implied by NCEI's arithmetic.
    - Pattern, not proof: NCEI's divisor is half the mouth height for both nets (Neuston 0.6 m →
      0.3, Manta 0.17 m → 0.085). Reisser states half immersion for the Neuston net and full
      immersion for the Manta net, so the two agree for Neuston and disagree for Manta.
    - The survey table uses Reisser's 0.17 m for these tows, in NCEI and in AOMI, which holds
      NCEI's values (`tool/survey/table.py`, `NET_DEPTH`). Not a tolerance: a sampling parameter a
      factor of two apart is a metadata question for NCEI.
    - The same tows under Eriksen's DOI are all labelled "Neuston net", 0.33 mm mesh, and imply
      0.08 m; 129 of them are Reisser's Manta tows.
  - **Size range:** Eriksen rows keep CD1 + CD2 (0.33–4.75 mm). Reisser rows keep Cs, which
    covers all sizes up to 82.6 mm. So 17 tows are zero under Eriksen and positive under
    Reisser.
- **The ×1.9 was a pairing artefact.** The same-day, under-2-km rule also paired replicate
  tows from the same station.
  - For true same-tow pairs, the median ratio is 1.035 (IQR 0.94–1.41): Manta 1.13,
    Neuston 0.356.
  - Reisser's own wind-mixing median of 1.9 is a coincidence. NCEI uses the uncorrected Cs.

## Re-run

Run the scripts in this order; each one's arguments are in its docstring.

1. `extract.py`
2. `pair.py`
3. `xml2txt.py`
4. `fig_profile.py`
5. `reconcile.py`
6. `tow_identity.py`
7. `eriksen_global_depth.py`

Use `unset VIRTUAL_ENV; uv run --no-project --with pandas --with openpyxl python -I <script> ...`.
