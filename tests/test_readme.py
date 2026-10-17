"""The README is what strangers trust first: keep it in step with the code."""

import re
from pathlib import Path

from taxagent.agent.diagram import workflow_order
from taxagent.cli import main

README = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")


def test_the_diagram_shows_every_workflow_step():
    diagram = README.split("```mermaid")[1].split("```")[0]

    for step in workflow_order():
        # \b = a word boundary: "explain" must not be found inside "explained"
        assert re.search(rf"\b{step}\b", diagram), f"{step} is missing from the diagram"


def test_every_taxagent_command_in_the_readme_exists():
    commands = set(re.findall(r"taxagent (\w+)", README))
    assert commands  # the README does name some commands

    for command in commands:
        try:
            main([command, "--help"])  # an unknown command fails before --help
        except SystemExit as stopped:
            assert stopped.code == 0, f"taxagent {command} does not exist"
