"""D2: the schema, an example instance and the checklist — all from mnp.schema."""

from __future__ import annotations

from pathlib import Path

from mnp.schema import export


def build(out_schema: Path, out_root: Path) -> list[Path]:
    """Schema + example into out_schema/, checklist.md beside them in out_root/."""
    written = export.write_artefacts(Path(out_schema))
    checklist = next(p for p in written if p.name == "checklist.md")
    target = Path(out_root) / "checklist.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(checklist.read_text())
    checklist.unlink()
    return [p for p in written if p.name != "checklist.md"] + [target]
