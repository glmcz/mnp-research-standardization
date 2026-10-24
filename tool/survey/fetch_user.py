"""Bring Martin's downloaded datasets (2026-10-24) into data/raw; complete what was missed.

Martin fetched the datasets on his reference list into ~/Downloads/datasets. This copies the data
files the survey reads into data/raw/datasets_user/ (gitignored; copied, never symlinked), and
fetches the RIVM repository's Git LFS files, which a plain clone leaves as 130-byte pointers.

    uv run python tool/survey/fetch_user.py [--src ~/Downloads/datasets]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tool" / "discover"))
import catalog  # noqa: E402

DEST = ROOT / "data/raw/datasets_user"
COPY = {
    "durum.xlsx": "02_freshwater/DURUM_Urban_Stormwater/data/"
    "Urban_Runoff_MP_Database (2018-2024).xlsx",
    "valine_oregon.xlsx": "02_freshwater/Zenodo_Oregon_Rivers/Valine_et_al_Data_Final27.xlsx",
    "moore_dw_samples.xlsx": "03_drinking_water/CA_Moore_Institute_Microplastic_Portal/data/"
    "drinking_water_data/clean_drinking_water_data/Samples_Merged.xlsx",
    "moore_dw_manuscripts.xlsx": "03_drinking_water/CA_Moore_Institute_Microplastic_Portal/data/"
    "drinking_water_data/clean_drinking_water_data/Manuscripts.xlsx",
}
# Python's client is refused by this host; a curl download (2026-10-24) is copied in by hand:
# data.cnra.ca.gov/dataset/78ac95ac-9665-4e53-aea6-ad0762055cce -> sfbay_microparticledata.xlsx
RIVM = "https://media.githubusercontent.com/media/rivm-syso/MicroplasticsERA_water/main/"
RIVM_LFS = (
    "Output/Data/2026-07-07Particle_concentrations_total.rds",
    "Output/Data/Rescaled_concentrations_2026-05-13.Rds",
    "rawdata/QAQC_Scores_Monitoring_Studies.xlsx",
    "rawdata/Mintenig_2025/Concentrations.xlsx",
    "rawdata/Mintenig_2025/readme.xlsx",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=Path.home() / "Downloads/datasets")
    a = ap.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    for name, rel in COPY.items():
        shutil.copyfile(a.src / rel, DEST / name)
        print("copied", name)
    for rel in RIVM_LFS:
        raw = catalog.get(RIVM + rel.replace(" ", "%20"))
        if raw.startswith(b"version https://git-lfs"):
            raise SystemExit(f"{rel}: still an LFS pointer")
        out = DEST / "rivm" / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        print("fetched", rel, len(raw))


if __name__ == "__main__":
    main()
