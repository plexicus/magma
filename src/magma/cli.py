"""CLI entry points for the Magma query engine."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import click

from magma.graph import CPGGraph
from magma.ingest import JoernError, load_cpg, run_joern
from magma.query import detect_uaf, format_findings


@click.group()
@click.version_option(package_name="magma-engine")
def main() -> None:
    """Magma — Code Property Graph query engine for vulnerability detection."""


@main.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o", "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path for the CPG DOT file. Defaults to <file>.cpg.dot",
)
def parse(file: Path, output: Path | None) -> None:
    """Parse a C file and export its Code Property Graph as DOT."""
    if output is None:
        output = file.with_suffix(".cpg.dot")

    try:
        click.echo(f"Parsing {file} with Joern...")
        dot_path = run_joern(file, output.parent / ".joern_output")
        click.echo(f"CPG exported to {dot_path}")

        # Validate the export
        nodes, edges = load_cpg(dot_path)
        click.echo(f"Parsed {len(nodes)} nodes, {len(edges)} edges")

    except JoernError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)


@main.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--max-hops",
    type=int,
    default=5,
    help="Maximum data dependency hops to traverse (default: 5).",
)
@click.option(
    "--json-output",
    is_flag=True,
    help="Output findings as JSON instead of human-readable format.",
)
def scan(file: Path, max_hops: int, json_output: bool) -> None:
    """Scan a C file for Use-After-Free vulnerabilities."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Step 1: Parse with Joern
            click.echo(f"[1/4] Parsing {file}...", err=True)
            dot_path = run_joern(file, tmpdir_path)

            # Step 2: Load CPG
            click.echo("[2/4] Loading CPG...", err=True)
            nodes, edges = load_cpg(dot_path)
            click.echo(f"      {len(nodes)} nodes, {len(edges)} edges", err=True)

            # Step 3: Build graph
            click.echo("[3/4] Building sparse matrices...", err=True)
            graph = CPGGraph(nodes, edges)

            # Step 4: Run UAF detection
            click.echo("[4/4] Running UAF detection...", err=True)
            findings = detect_uaf(graph, max_hops=max_hops)

        # Output results
        if json_output:
            click.echo(json.dumps([f.to_dict() for f in findings], indent=2))
        else:
            click.echo(format_findings(findings))

        # Exit code
        sys.exit(1 if findings else 0)

    except JoernError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
