"""
Knowledge Brain Evaluation CLI.

Provides commands for evaluating knowledge quality:
  knowledge health   - Run health check on the vault
  knowledge evaluate - Run full evaluation report
  knowledge benchmark - Benchmark retrieval performance

Usage:
  python run_knowledge_eval.py health
  python run_knowledge_eval.py evaluate
  python run_knowledge_eval.py benchmark --notes 1000
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import argparse
import json

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.knowledge.config import KnowledgeConfig
from src.knowledge.knowledge_service import KnowledgeService
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.retriever import KnowledgeRetriever
from src.knowledge.evaluation import KnowledgeEvaluator

console = Console()


def get_evaluator(vault_path: str | None = None) -> KnowledgeEvaluator:
    """Create a KnowledgeEvaluator for the given vault path."""
    config = KnowledgeConfig(vault_path) if vault_path else KnowledgeConfig()
    repo = KnowledgeRepository(config)
    service = KnowledgeService(config, repo)
    retriever = KnowledgeRetriever(repo)
    return KnowledgeEvaluator(service, retriever=retriever)


def cmd_health(args) -> None:
    """Run health check on the knowledge vault."""
    evaluator = get_evaluator(args.vault)
    result = evaluator.health_check()

    console.print(Panel("[bold cyan]Knowledge Brain Health Check[/bold cyan]"))

    table = Table(title="Health Issues")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right", style="yellow")

    table.add_row("Orphan Notes", str(len(result.orphan_notes)))
    table.add_row("Missing Provenance", str(len(result.missing_provenance)))
    table.add_row("Malformed Frontmatter", str(len(result.malformed_frontmatter)))
    table.add_row("Broken Wikilinks", str(len(result.broken_wikilinks)))
    table.add_row("Duplicate Candidates", str(len(result.duplicate_candidates)))
    table.add_row("Low Confidence Notes", str(len(result.low_confidence_notes)))
    table.add_row("Notes Without Relationships", str(len(result.notes_without_relationships)))
    table.add_row("Conflicting Knowledge", str(len(result.conflicting_knowledge)))

    console.print(table)

    status = "[bold green]HEALTHY[/bold green]" if result.is_healthy else "[bold red]ISSUES FOUND[/bold red]"
    console.print(f"\nOverall: {status} ({result.issues_count} issues)")

    if args.json:
        console.print(json.dumps(result.to_dict(), indent=2))


def cmd_evaluate(args) -> None:
    """Run full evaluation report."""
    evaluator = get_evaluator(args.vault)
    report = evaluator.full_evaluation()

    console.print(Panel("[bold cyan]Knowledge Brain Full Evaluation[/bold cyan]"))

    # Growth report
    growth = report["growth"]
    console.print(f"\n[bold]Knowledge Growth:[/bold]")
    console.print(f"  Total Notes: {growth['total_notes']}")
    console.print(f"  Total Relationships: {growth['total_relationships']}")
    console.print(f"  Orphans: {growth['orphans']}")
    console.print(f"  Average Confidence: {growth['average_confidence']}")
    console.print(f"  Sources: {growth['sources_represented']}")
    console.print(f"  Projects: {growth['projects_represented']}")

    # Notes by type
    if growth["notes_by_type"]:
        type_table = Table(title="Notes by Type")
        type_table.add_column("Type", style="cyan")
        type_table.add_column("Count", justify="right", style="yellow")
        for note_type, count in sorted(growth["notes_by_type"].items()):
            type_table.add_row(note_type, str(count))
        console.print(type_table)

    # Retrieval metrics
    retrieval = report["retrieval"]
    console.print(f"\n[bold]Retrieval Quality:[/bold]")
    console.print(f"  Mean Reciprocal Rank: {retrieval['mean_reciprocal_rank']}")
    console.print(f"  Mean Average Precision: {retrieval['mean_average_precision']}")

    ret_table = Table(title="Retrieval Metrics @K")
    ret_table.add_column("K", style="cyan")
    ret_table.add_column("Precision", justify="right")
    ret_table.add_column("Recall", justify="right")
    ret_table.add_column("Hit Rate", justify="right")
    for k in sorted(retrieval["precision_at_k"].keys()):
        ret_table.add_row(
            str(k),
            str(retrieval["precision_at_k"][k]),
            str(retrieval["recall_at_k"][k]),
            str(retrieval["hit_rate_at_k"][k]),
        )
    console.print(ret_table)

    # Health
    health = report["health"]
    status = "[bold green]HEALTHY[/bold green]" if health["is_healthy"] else "[bold red]ISSUES FOUND[/bold red]"
    console.print(f"\n[bold]Health Check:[/bold] {status} ({health['issues_count']} issues)")

    if args.json:
        console.print(json.dumps(report, indent=2))


def cmd_benchmark(args) -> None:
    """Benchmark retrieval performance."""
    evaluator = get_evaluator(args.vault)
    result = evaluator.benchmark_retrieval(num_notes=args.notes)

    console.print(Panel("[bold cyan]Retrieval Performance Benchmark[/bold cyan]"))
    console.print(f"  Notes: {result['num_notes']}")
    console.print(f"  Retrieval Time: {result['retrieval_time_ms']} ms")
    console.print(f"  Results Returned: {result['results_returned']}")
    console.print(f"  Notes/Second: {result['notes_per_second']}")

    if args.json:
        console.print(json.dumps(result, indent=2))


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Knowledge Brain Evaluation CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Health check
    health_parser = subparsers.add_parser("health", help="Run health check on the vault")
    health_parser.add_argument("--vault", type=str, default=None, help="Vault path")
    health_parser.add_argument("--json", action="store_true", help="Output as JSON")
    health_parser.set_defaults(func=cmd_health)

    # Full evaluation
    eval_parser = subparsers.add_parser("evaluate", help="Run full evaluation report")
    eval_parser.add_argument("--vault", type=str, default=None, help="Vault path")
    eval_parser.add_argument("--json", action="store_true", help="Output as JSON")
    eval_parser.set_defaults(func=cmd_evaluate)

    # Benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Benchmark retrieval performance")
    bench_parser.add_argument("--vault", type=str, default=None, help="Vault path")
    bench_parser.add_argument("--notes", type=int, default=100, help="Number of notes to benchmark")
    bench_parser.add_argument("--json", action="store_true", help="Output as JSON")
    bench_parser.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
