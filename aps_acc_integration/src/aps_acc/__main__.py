"""Command-line interface — run `python -m aps_acc <command>`.

Commands:
  login       Run the 3-legged OAuth flow once; persists refresh token.
  diagnose    Run all health probes and print verdicts.
  projects    Pull project list (2-legged) and write JSON/CSV.
  issues      Pull issues for a project (3-legged).
  rfis        Pull RFIs for a project (3-legged).
  submittals  Pull submittals for a project (3-legged).
  pull-all    Pull projects + issues + rfis + submittals for one project.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from aps_acc import APSClient
from aps_acc.config import Settings
from aps_acc.diagnostics import diagnose as run_diagnostics
from aps_acc.exceptions import APSError
from aps_acc.exporters import write_records
from aps_acc.logging_setup import setup_logging

log = logging.getLogger("aps_acc.cli")


@click.group()
@click.option("--log-level", default=None, help="Override LOG_LEVEL from env.")
@click.pass_context
def cli(ctx: click.Context, log_level: str | None) -> None:
    """APS / ACC integration CLI."""
    settings = Settings.from_env()
    setup_logging(level=log_level or settings.log_level)
    ctx.obj = settings


@cli.command()
@click.option("--scopes", default="data:read data:write account:read", show_default=True)
@click.pass_obj
def login(settings: Settings, scopes: str) -> None:
    """Run the 3-legged login flow once.

    Opens your browser, captures the OAuth code on a localhost server, and
    persists the resulting refresh token to APS_TOKEN_STORE_PATH.
    """
    client = APSClient(settings)
    try:
        token = client.auth.interactive_login(scopes.split())
    except APSError as exc:
        click.echo(f"Login failed: {exc}", err=True)
        sys.exit(1)
    click.echo(
        f"Login successful. Refresh token saved to {settings.token_store_path}\n"
        f"Granted scopes: {' '.join(sorted(token.scopes))}"
    )


@cli.command()
@click.option("--project-id", default=None, help="Project UUID for 3LO probes.")
@click.pass_obj
def diagnose(settings: Settings, project_id: str | None) -> None:
    """Run health probes and print a verdict for each."""
    client = APSClient(settings)
    results = run_diagnostics(client, project_id=project_id)
    for r in results:
        click.echo(r.render())
        click.echo("")
    if not all(r.passed for r in results):
        sys.exit(2)


@cli.command()
@click.option("--status", default="active", show_default=True)
@click.option("--platform", default="acc", show_default=True)
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.pass_obj
def projects(settings: Settings, status: str, platform: str, output: Path) -> None:
    """List all ACC projects in the account (2-legged)."""
    client = APSClient(settings)
    try:
        records = list(client.admin.list_projects(status=status, platform=platform))
    except APSError as exc:
        click.echo(f"Failed: {exc}", err=True)
        sys.exit(1)
    n = write_records(records, output)
    click.echo(f"Wrote {n} projects to {output}")


@cli.command()
@click.option("--project-id", required=True)
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.pass_obj
def issues(settings: Settings, project_id: str, output: Path) -> None:
    """Pull all issues for a project (3-legged)."""
    client = APSClient(settings)
    try:
        records = list(client.issues.list_issues(project_id))
    except APSError as exc:
        click.echo(f"Failed: {exc}", err=True)
        sys.exit(1)
    n = write_records(records, output)
    click.echo(f"Wrote {n} issues to {output}")


@cli.command()
@click.option("--project-id", required=True)
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.pass_obj
def rfis(settings: Settings, project_id: str, output: Path) -> None:
    """Pull all RFIs for a project (3-legged)."""
    client = APSClient(settings)
    try:
        records = list(client.rfis.list_rfis(project_id))
    except APSError as exc:
        click.echo(f"Failed: {exc}", err=True)
        sys.exit(1)
    n = write_records(records, output)
    click.echo(f"Wrote {n} RFIs to {output}")


@cli.command()
@click.option("--project-id", required=True)
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.pass_obj
def submittals(settings: Settings, project_id: str, output: Path) -> None:
    """Pull all submittal items for a project (3-legged)."""
    client = APSClient(settings)
    try:
        records = list(client.submittals.list_items(project_id))
    except APSError as exc:
        click.echo(f"Failed: {exc}", err=True)
        sys.exit(1)
    n = write_records(records, output)
    click.echo(f"Wrote {n} submittals to {output}")


@cli.command(name="pull-all")
@click.option("--project-id", required=True)
@click.option("--output-dir", required=True, type=click.Path(path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json")
@click.pass_obj
def pull_all(settings: Settings, project_id: str, output_dir: Path, fmt: str) -> None:
    """Pull issues, RFIs, and submittals for one project in one shot."""
    client = APSClient(settings)
    output_dir.mkdir(parents=True, exist_ok=True)

    pulls = [
        ("issues", client.issues.list_issues, [project_id], {}),
        ("rfis", client.rfis.list_rfis, [project_id], {}),
        ("submittals", client.submittals.list_items, [project_id], {}),
    ]
    for name, func, args, kwargs in pulls:
        try:
            records = list(func(*args, **kwargs))
        except APSError as exc:
            click.echo(f"[{name}] failed: {exc}", err=True)
            continue
        out = output_dir / f"{name}.{fmt}"
        n = write_records(records, out)
        click.echo(f"[{name}] wrote {n} records to {out}")


if __name__ == "__main__":
    cli()
