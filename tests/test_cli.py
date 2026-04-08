"""Tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from magma.cli import main


class TestCli:
    """Tests for CLI commands via CliRunner."""

    def test_help_shows_subcommands(self) -> None:
        """Test that --help shows parse and scan commands."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "parse" in result.output
        assert "scan" in result.output

    def test_version(self) -> None:
        """Test --version flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_parse_command_help(self) -> None:
        """Test parse --help."""
        runner = CliRunner()
        result = runner.invoke(main, ["parse", "--help"])
        assert result.exit_code == 0
        assert "Parse a C file" in result.output

    def test_scan_command_help(self) -> None:
        """Test scan --help."""
        runner = CliRunner()
        result = runner.invoke(main, ["scan", "--help"])
        assert result.exit_code == 0
        assert "Use-After-Free" in result.output

    def test_scan_nonexistent_file(self) -> None:
        """Test scan with nonexistent file."""
        runner = CliRunner()
        result = runner.invoke(main, ["scan", "/nonexistent/file.c"])
        assert result.exit_code != 0

    def test_parse_nonexistent_file(self) -> None:
        """Test parse with nonexistent file."""
        runner = CliRunner()
        result = runner.invoke(main, ["parse", "/nonexistent/file.c"])
        assert result.exit_code != 0
