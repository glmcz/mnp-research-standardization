"""The protocol is generated from a registry, so it cannot drift from the code.

A methodology document that is maintained by hand describes the pipeline as it was on the day
someone last remembered to edit it. This one is rendered from a registry that the test suite
holds against the actual CLI: a command with no protocol entry, or an entry naming a command
that no longer exists, fails the build.
"""

import ast
from pathlib import Path

import pytest

from mnp import config, protocol

MODULES = ("corpus", "extract", "rescale", "ek", "infer")


def _subcommands_in_source(module: str) -> set[str]:
    """Parsed with ast: `add_parser("x").set_defaults(...)` chains defeat a line-wise grep."""
    source = (config.ROOT / "src" / "mnp" / module / "__main__.py").read_text()
    found = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.add(f"{module} {node.args[0].value}")
    return found


def _report_subcommands() -> set[str]:
    from mnp.report import __main__ as report_cli

    return {f"report {name}" for name in (*report_cli.RUNNERS, *report_cli.COMMANDS)}


def _choice_subcommands(module: str) -> set[str]:
    """Some CLIs take a positional with `choices=[...]` instead of sub-parsers."""
    source = (config.ROOT / "src" / "mnp" / module / "__main__.py").read_text()
    found = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "choices" and isinstance(kw.value, ast.List):
                for element in kw.value.elts:
                    if isinstance(element, ast.Constant) and isinstance(element.value, str):
                        found.add(f"{module} {element.value}")
    return found


def actual_commands() -> set[str]:
    commands: set[str] = set()
    for module in MODULES:
        commands |= _subcommands_in_source(module)
    return commands | _report_subcommands() | _choice_subcommands("eval")


def test_every_command_the_code_offers_has_a_protocol_step():
    documented = {step.command for step in protocol.STEPS}
    missing = sorted(actual_commands() - documented)
    assert not missing, f"commands with no protocol entry: {missing}"


def test_every_protocol_step_names_a_command_that_exists():
    documented = {step.command for step in protocol.STEPS}
    stale = sorted(documented - actual_commands())
    assert not stale, f"protocol steps naming commands that no longer exist: {stale}"


@pytest.mark.parametrize("field", ["purpose", "inputs", "outputs", "invalidated_by"])
def test_no_step_is_documented_with_a_blank(field):
    blank = [s.command for s in protocol.STEPS if not getattr(s, field)]
    assert not blank, f"{field} empty on: {blank}"


def test_every_step_states_what_kind_of_result_it_produces():
    for step in protocol.STEPS:
        assert step.kind in protocol.KINDS, f"{step.command}: {step.kind!r}"


def test_a_step_that_calls_a_model_is_not_claimed_deterministic():
    """The one property no amount of engineering gives us: judgement is not reproducible."""
    for step in protocol.STEPS:
        if step.kind == "judgement":
            assert step.ground_truth, f"{step.command}: judgement with nothing to score it against"


def test_the_document_is_rendered_from_the_registry(tmp_path):
    text = protocol.render()
    for step in protocol.STEPS:
        assert f"`{step.command}`" in text, f"{step.command} missing from the rendered protocol"
    assert text.startswith("# Protocol")


def test_the_committed_document_is_current():
    """`report protocol` regenerates it; this fails when someone edits the prose instead."""
    path = Path(config.ROOT / "docs" / "PROTOCOL.md")
    assert path.is_file(), "docs/PROTOCOL.md has not been generated"
    assert path.read_text() == protocol.render(), (
        "docs/PROTOCOL.md is out of date — run `python -m mnp.report protocol`"
    )
