# Validation system, Q2: runs and results, 2026-10-19

The design is in `docs/DESIGN_2026-10-18_hypotheses-method-evaluation.md` §3 and the code in
`src/mnp/validate/`. Q2 asks why a zeta value has the opposite sign to the one its surface group
gives in clean water. The numbers are in `out/tables/validate_sign_metrics.json`, and the judge
numbers, once the run ends, in `out/tables/validate_judge_metrics.json`.

## The runs

- **Reader A:** claude-sonnet-5, run `sign-a-20261019`.
- **Reader B:** claude-opus-4-6, run `sign-b-20261019`.
  - The first B run failed on every paper: claude-opus-5-5 needs Claude Code 2.1.280 or later,
    and the reader CLI here is 2.1.92 (`data/interim/validate/sign/errors.jsonl`).
  - B was rerun with the newest Opus this CLI runs.
- **Pilot:** run `sign-a-pilot`, two papers, read by hand before the sweep.

## The guard that was wrong

The first scoring rejected 15 reader answers at V1: 6 of reader A's and 9 of reader B's.
13 of them were "corona" answers citing a line where an anionic surfactant coated the amine beads
(PMC11117817).

The rule's own text counts "another coating adsorbed" as corona, but the evidence pattern lacked
the coating words. So the code was wrong, not the readers. It was fixed test-first: the test case
was added, seen to fail, then the pattern was changed.

After the fix, V1 rejects 2 answers, both reader A's. Both inferred a labelling error from the
absence of an amine mention, and absence is not evidence.

This is the guard-push-toward-absence failure the project has met before (memory
`guards-push-toward-absence`). A false rejection deletes a correct, cited answer, and only reading
the rejections finds it.

## The judges

The OpenRouter account had no credit, and three larger models were refused with HTTP 402
(gemini-3.8-flash, mistral-medium-3-5, gpt-6-luna). The jury is therefore:

- GPT-OSS-120B on Groq (OpenAI family);
- gemini-2.5-flash-lite (Google);
- mistral-small-3.2-24b-instruct (Mistral).

Tier 1 was not run:

- Nimble needs Ollama 0.35 or later, and 0.21.0 is installed.
- Microsoft-Decision-1 is not on OpenRouter.

### Coverage

- gemini-2.5-flash-lite and mistral-small judged all 69 of reader A's rows. Each lost the
  clumped-beads trap to a 402 when the OpenRouter credit ran out.
- Claude judged all 69, and both traps.
- GPT-OSS-120B stopped at Groq's daily cap of 200 000 tokens for the model, after 12 of the 19
  papers (34 of reader A's 69 rows), both traps included. The remaining calls resume with
  `judge run --judge groq --jobs 1` once the cap frees. Run one worker: two workers starve each
  other under the 8 000 tokens-a-minute limit.
- Two runs split by judge can record the same call twice, so scoring keeps the last record of
  each call (`judge.latest`, tested).

### Results (`out/tables/validate_judge_metrics.json`, reader A)

| Judge | Rows | Calls supported | Accepts the decoy | Pick flips with order | Traps caught |
|---|---|---|---|---|---|
| gpt-oss-120b | 34 | 79 % | 0 % | 2 % | 0 of 2 |
| gemini-2.5-flash-lite | 69 | 100 % | 87 % | 0 % | 0 of 1 |
| mistral-small-3.2 | 69 | 81 % | 41 % | 0 % | 1 of 1 |
| claude-sonnet-5 (own family) | 69 | 64 % | not asked | 26 % | 1 of 2 |

What it says:

- **A judge that says yes to everything also says yes to a fluent wrong cause.**
  gemini-2.5-flash-lite called every reader answer supported, and 87 % of the decoys too.
- **No self-preference showed.** Claude was the strictest judge of its own family's reader,
  but the least stable: its pick of cause changed in 26 % of rows when only the order of the
  cause list was reversed. The jury's picks hardly moved.
- **Neither trap is safe with a judge.** No judge caught both. gpt-oss-120b fell for both.

So a judge is one more vote, and the checks that can be code stay code. The deck's slide 19
shows this table from the metrics file.

