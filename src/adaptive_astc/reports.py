"""Compatibility entry point for historical report scripts."""

from pathlib import Path

from adaptive_astc.reporting import ReportGenerator


def render_report(run_dir: Path, report_dir: Path) -> None:
    ReportGenerator(run_dir, report_dir).render()
