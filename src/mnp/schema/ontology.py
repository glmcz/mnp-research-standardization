"""CURIEs looked up in OLS4 (2026-09). One place, so the JSON Schema and the
checklist cannot drift apart.

Ionic strength has no term in ENM, NPO, CHMO or ENVO. It is left unmapped on
purpose — inventing a CURIE would be worse than admitting the gap, and the gap
is itself part of the talk's argument.
"""

from __future__ import annotations

PREFIXES = {
    "ENM": "http://purl.enanomapper.org/onto/",
    "NPO": "http://purl.bioontology.org/ontology/npo#NPO_",
    "ENVO": "http://purl.obolibrary.org/obo/ENVO_",
}

ZETA_POTENTIAL = "ENM:0000092"
ELECTROPHORETIC_MOBILITY = "NPO:1315"
HYDRODYNAMIC_SIZE = "NPO:1914"
DRINKING_WATER = "ENVO:00003064"
FRESH_WATER = "ENVO:00002011"

QUANTITY_TERMS = {
    "zeta_potential": ZETA_POTENTIAL,
    "electrophoretic_mobility": ELECTROPHORETIC_MOBILITY,
}

MATRIX_TERMS = {
    "drinking_water": DRINKING_WATER,
    "fresh_water": FRESH_WATER,
}

ALL_TERMS = {
    "zeta_potential": ZETA_POTENTIAL,
    "electrophoretic_mobility": ELECTROPHORETIC_MOBILITY,
    "hydrodynamic_size": HYDRODYNAMIC_SIZE,
    "drinking_water": DRINKING_WATER,
    "fresh_water": FRESH_WATER,
}

UNMAPPED = {
    "ionic_strength_mM": "no ontology term exists for ionic strength in ENM/NPO/CHMO/ENVO",
}


def iri(curie: str) -> str:
    prefix, _, local = curie.partition(":")
    return PREFIXES[prefix] + local
