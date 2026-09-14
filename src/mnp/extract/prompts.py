"""The extraction prompt. Its field list is generated from the schema models so
the model is asked for exactly what `SurfaceMeasurement` can hold.

Numbers are requested as printed strings ("-50 ± 9.7", "10 mM NaCl",
"room temperature"): the model copies, `extract.coerce` parses. Asking the
model to convert is asking it to hallucinate.
"""

from __future__ import annotations

import hashlib
import json

from mnp.schema import models

OUTPUT_TEMPLATE = {
    "measurements": [
        {
            "particle_name": "string as the paper names it, e.g. 'PS-COOH 100 nm' | null",
            "material": "polymer, e.g. 'polystyrene' | null",
            "functionalisation": "e.g. 'carboxylate', 'amine', 'plain' | null",
            "supplier": "string | null",
            "size_nominal_nm": "as printed, e.g. '100 nm' | null",
            "size_measured_nm": "as printed, e.g. '112 ± 3 nm' | null",
            "quantity": "'zeta potential' | 'electrophoretic mobility'",
            "value": "as printed, e.g. '-50 ± 9.7' (keep the sign, keep ±)",
            "unit": "as printed, e.g. 'mV' or 'µm cm/Vs' or '10^-8 m2/Vs'",
            "n": "number of replicates as printed | null",
            "conditions": {
                "medium_text": "the dispersion medium as written, e.g. '10 mM NaCl' | null",
                "medium_class": "one of: " + ", ".join(c.value for c in models.MediumClass),
                "ionic_strength": "as written, e.g. '10 mM NaCl', '0.15 M' | null",
                "pH": "as written, e.g. '7.4' or 'between 6.8 and 7.2' | null",
                "temperature": "as written, e.g. '25 °C' or 'room temperature' | null",
                "instrument": "make and model, e.g. 'Malvern Zetasizer Nano ZS' | null",
            },
            "medium_matches_exposure": "true | false | null",
            "evidence_quote": "verbatim copy of the sentence or table row the value comes from",
            "evidence_location": "e.g. 'Methods, para 2' or 'Table 1'",
        }
    ]
}


def _field_notes() -> str:
    lines = []
    for name, info in models.MeasurementConditions.model_fields.items():
        extra = info.json_schema_extra or {}
        if extra.get("required_for_reporting"):
            lines.append(f"- {name}: {extra['checklist_why']}")
    return "\n".join(lines)


def system_prompt() -> str:
    template = json.dumps(OUTPUT_TEMPLATE, indent=2, ensure_ascii=False)
    return f"""You extract surface-charge measurements of micro- and nanoplastic particles from
scientific articles. You will receive the article's methods, tables and relevant
sections. Return one JSON object and nothing else.

Rules — each one matters:
1. Report only what the text states. Never compute, convert, average or infer a
   number. If the paper does not state a condition, use null. Do not assume
   25 °C, pH 7 or water when the paper is silent.
2. Copy numbers exactly as printed, as strings, with sign and ± ("-50 ± 9.7").
   Copy units as printed. Copy conditions as written ("10 mM NaCl", not "10").
3. evidence_quote must be a verbatim, character-for-character copy of the
   sentence or table row that contains the value. It will be checked against the
   article text; a paraphrase counts as a fabrication.
4. One object per (particle × medium × condition). A table with 8 particles
   measured in 2 media yields up to 16 objects. Skip cells marked n.d. or empty.
5. Zeta potential and electrophoretic mobility are different quantities. Say
   which one the paper reports; do not convert between them.
6. A condition applies only within the experiment that states it. Repeat it in
   another object only when the paper says it covers that measurement too ("all
   zeta potentials were measured at 25 °C in 1 mM KCl") — never across a separate
   preparation that restates nothing. Whenever you carry a condition, quote the
   sentence that establishes it in evidence_quote alongside the value's row (join
   with " || "), or it will be flagged as read across experiments.
7. Only a temperature tied to the measurement counts. Incubation, exposure,
   culture, digestion and storage temperatures are a different step: leave
   temperature null, even if the paper states no other temperature.
8. A printed composition is an ionic strength ("0.0027 M potassium chloride,
   0.137 M sodium chloride"): copy the composition verbatim into ionic_strength
   and let the pipeline do the arithmetic. Never look up what a buffer's name
   nominally means.
9. If the article reports no zeta potential or mobility of a plastic particle,
   return {{"measurements": []}}.

Why the conditions matter (a value without them is not comparable):
{_field_notes()}

Output format (values describe what to put there):
{template}"""


def user_prompt(pmcid: str | None, extraction_text: str) -> str:
    return (
        f"Article {pmcid or 'unknown'}.\n\n<article>\n{extraction_text}\n</article>\n\n"
        "Return the JSON object now."
    )


def prompt_sha256() -> str:
    return hashlib.sha256(system_prompt().encode()).hexdigest()
