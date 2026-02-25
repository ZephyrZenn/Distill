from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from distill_workflow_lib.api import run_workflow_from_opml

app = typer.Typer(help="Run Distill workflow in DB-free library mode")


@app.command()
def run_opml(
    opml_file: Path = typer.Argument(..., exists=True, readable=True),
    focus: str = typer.Option("", help="Optional focus topic"),
    hour_gap: int = typer.Option(24, help="Input lookback window in hours"),
    output_json: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Run workflow from an OPML file and print summary output."""
    opml_text = opml_file.read_text(encoding="utf-8")
    result = asyncio.run(
        run_workflow_from_opml(opml_text=opml_text, focus=focus, hour_gap=hour_gap)
    )

    if output_json:
        typer.echo(
            json.dumps(
                {
                    "article_count": result.article_count,
                    "summary": result.summary,
                    "ext_info_count": len(result.ext_info),
                    "logs": result.logs,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    typer.echo(f"article_count: {result.article_count}")
    typer.echo(f"ext_info_count: {len(result.ext_info)}")
    typer.echo("\n=== SUMMARY ===\n")
    typer.echo(result.summary)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
