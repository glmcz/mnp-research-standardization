# Brief: annotating the gold set

**This is a reconstruction, written 2026-09-15.** The 50-paper gold set was annotated before
briefs were versioned, so this file states the rules the annotation *followed*, recovered from
`data/interim/annotation/gold_50.csv`, the plan, and `docs/METHODOLOGY.md` — it is not the text
the annotator read. Treat it as the rules a *future* annotator must follow, and as a
description, not a provenance record, of the existing rows. Nothing records its hash yet:
`extract gold-merge` writes no brief column, so a row annotated under this file cannot be traced
to it.

---

## What the gold set is for

It is the ground truth the extraction is scored against, so it must be produced by a different
route from the extraction itself. **Annotate from the article's own methods XML, never from the
extraction prompt and never from an existing record.** A gold set derived from the thing it
scores measures nothing.

Fifty papers, drawn by `extract sample` with a fixed seed, stratified by year band
(≤2018 / 2019–22 / 2023–26), excluding the twenty papers used to develop the prompt.

## One row per measurement

A row is one (particle × medium × condition) measurement. Record what the paper prints, in the
units it prints, and nothing else. The column set is fixed by `extract gold-merge`; the fields
that decide the study's headline numbers are the five `*_reported` booleans and
`medium_matches_exposure`.

## The rules that decide the booleans

- **Medium.** "DI water" is a reported medium. So is "PBS". A paper that never names the
  liquid the particle was in has not reported one.
- **Ionic strength.** "10 mM NaCl" is reported. A printed composition —
  "0.137 M NaCl, 0.0027 M KCl" — **is** an ionic strength, recorded as derived, not as a plainly
  printed number (ratified 2026-09-13). "PBS" alone is a medium, not an ionic strength. A
  component whose speciation is unstated contributes nothing.
- **pH.** Only a number counts. "Physiological pH" does not.
- **Temperature.** Only the temperature of the *measurement*. An incubation, exposure, storage
  or culture temperature is not it, even when the paper gives no other (ratified 2026-09-13).
  "Room temperature" is reported, as a nominal value, and flagged as such.
- **Instrument.** "Zetasizer" alone counts, at family level. A make and model is better and is
  recorded verbatim.
- **Scope.** A condition applies only within the experiment that states it, and does not
  propagate to another preparation unless the paper says it does (ratified 2026-09-13).

## Evidence

Every row carries a verbatim quote from the article and where it came from. Separate pieces are
joined with `" || "`; each piece is checked independently against the text. A quote that is not
literally present is not evidence.

A measurement that the paper reports **without printing a number anywhere in the retrievable
text** — figure only, supplement only, or a qualitative statement — is still a measurement, and
is recorded with a null value. Dropping those is how the first pass undercounted them 17 against
144.

If the value is in supplementary material that was not fetched, record the row and note
`si_only`. Whether a "see Table S1" pointer makes a measurement *reported* is edge case **V7**
and is **not settled** — do not treat this paragraph as settling it.

## The audit

Ten of the fifty are re-judged blind by the author, and Cohen's κ on the five `*_reported`
booleans is reported beside precision and recall. Until that sheet is filled, every slide must
say the set is annotated by Claude and not yet audited.
