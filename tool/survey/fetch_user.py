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
    "aomi.csv": "01_marine_ocean/AOMI_Atlas_Ocean_Microplastics/AOMI_Atlas_Ocean_Microplastics.csv",
}
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
