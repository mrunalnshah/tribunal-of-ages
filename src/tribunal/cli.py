"""Command line: `uv run tribunal <command>`.

Imports happen inside each command, so a command loads only what it needs: downloading
pages shouldn't wait for machine-learning models to load.
"""

import argparse
import json
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="tribunal")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("download", help="fetch parsed books' pages into data/raw/")
    fetch.add_argument("--refresh", action="store_true", help="fetch the pages again")
    commands.add_parser("curate", help="parse, label and check laws into data/processed/")
    commands.add_parser("check", help="check the library against laws.jsonl (no LLM calls)")
    commands.add_parser("index", help="rebuild the search index from laws.jsonl")
    search = commands.add_parser("search", help="show what retrieval returns for a query")
    search.add_argument("query")
    search.add_argument("--themes", default="ancient", help="comma-separated: ancient,fiction")
    judge = commands.add_parser("judge", help="run the whole pipeline on one grievance")
    judge.add_argument("crime")
    judge.add_argument("--outrage", type=int, default=3)
    judge.add_argument("--themes", default="ancient", help="comma-separated: ancient,fiction")
    judge.add_argument("--jurisdiction", default="any")
    evaluate = commands.add_parser("eval", help="score retrieval, or verdicts, on data/eval/")
    evaluate.add_argument("--memory", action="store_true", help="use a throwaway in-memory index")
    evaluate.add_argument("--min-hit", type=float, default=0.0, help="fail below this Hit@5")
    evaluate.add_argument("--verdicts", action="store_true", help="judge real cases (uses LLMs)")
    bench = commands.add_parser("bench", help="time searches, and verdicts with --verdicts")
    bench.add_argument("--memory", action="store_true", help="time an in-memory index")
    bench.add_argument("--repeat", type=int, default=3, help="times to run each search query")
    bench.add_argument("--verdicts", type=int, default=0, help="also time this many verdicts")
    commands.add_parser("shelve", help="write frontend/laws.json for the website's library")
    review = commands.add_parser("records", help="list reported public cases, or act on one")
    review.add_argument("--hide", metavar="ID", help="hide a case from the public record")
    review.add_argument("--restore", metavar="ID", help="show a hidden case again")
    review.add_argument("--delete", metavar="ID", help="delete a case for good")
    kept = commands.add_parser("history", help="export or prune the private history of grievances")
    kept.add_argument("--export", metavar="FILE", help="write it to a JSON Lines file")
    kept.add_argument("--days", type=int, help="with --export: only the last DAYS days")
    kept.add_argument("--prune", type=int, metavar="DAYS", help="delete entries older than DAYS")
    fame = commands.add_parser("hall-of-fame", help="judge the website's archive cases (uses LLMs)")
    fame.add_argument("--check", action="store_true", help="check the archive (no LLM calls)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.command == "download":
        from tribunal.ingest.sources import download

        download(refresh=args.refresh)
        return
    if args.command == "check":
        from tribunal.ingest.curate import check_library

        problems = check_library()
        print("\n".join(problems) or "The library and the corpus agree.")
        sys.exit(1 if problems else 0)
    if args.command == "shelve":
        from tribunal import shelf
        from tribunal.ingest.curate import load_laws

        print(f"shelved {shelf.shelve(load_laws())} laws in {shelf.SHELF}")
        return
    if args.command == "hall-of-fame" and args.check:
        from tribunal import archive
        from tribunal.ingest.curate import load_laws

        problems = archive.problems({law.law_id: law for law in load_laws()})
        print("\n".join(problems) or "The archive quotes the corpus as it is now.")
        sys.exit(1 if problems else 0)

    from tribunal.config import Settings

    settings = Settings()
    if args.command == "curate":
        from tribunal.ingest.curate import curate
        from tribunal.llm import LLMClient

        curate(LLMClient(settings.providers(), timeout=settings.llm_timeout))
    elif args.command == "index":
        from tribunal.ingest.curate import load_laws
        from tribunal.wiring import build_index

        print("now serving", build_index(settings).rebuild(load_laws()))
    elif args.command == "search":
        from tribunal.wiring import build_index

        for hit in build_index(settings).search(args.query, args.themes.split(",")):
            law = hit.law
            print(f"{hit.score:6.2f} {law.law_id:20} {law.jurisdiction:10} {law.tier}", law.summary)
    elif args.command == "judge":
        from tribunal.models import Case
        from tribunal.wiring import build_tribunal

        case = Case(
            crime=args.crime,
            outrage=args.outrage,
            themes=args.themes.split(","),
            jurisdiction=args.jurisdiction,
        )
        print(build_tribunal(settings).judge(case).model_dump_json(indent=2))
    elif args.command == "eval":
        _evaluate(args, settings)
    elif args.command == "bench":
        _bench(args, settings)
    elif args.command == "records":
        _review(args, settings)
    elif args.command == "history":
        _history(args, settings)
    elif args.command == "hall-of-fame":
        from tribunal import archive
        from tribunal.wiring import build_tribunal

        saved = archive.save(archive.build(build_tribunal(settings), archive.read_cases()))
        print(f"saved {saved} verdicts to {archive.ARCHIVE}")


def _evaluate(args: argparse.Namespace, settings) -> None:
    from tribunal import evals

    if args.verdicts:
        from tribunal.wiring import build_tribunal

        print(json.dumps(evals.verdict_eval(build_tribunal(settings)), indent=2))
        return
    report = evals.retrieval_eval(_index(args, settings))
    print(json.dumps(report, indent=2))
    if report["hit@5"] < args.min_hit:
        sys.exit(f"Hit@5 {report['hit@5']:.2f} is below the gate {args.min_hit:.2f}")


def _bench(args: argparse.Namespace, settings) -> None:
    from tribunal import bench, evals
    from tribunal.models import Case

    index = _index(args, settings)
    queries = [case["query"] for case in evals.load_cases(evals.RETRIEVAL_CASES)]
    index.search(queries[0])  # load the models first, so the timings are searches only
    print(bench.summary("search", bench.timed(index.search, queries, args.repeat)))
    if args.verdicts:
        from tribunal.wiring import build_tribunal

        fields = ("crime", "outrage", "themes")
        rows = evals.load_cases(evals.VERDICT_CASES)[: args.verdicts]
        cases = [Case.model_validate({k: row[k] for k in fields if k in row}) for row in rows]
        print(bench.summary("verdicts", bench.timed(build_tribunal(settings).judge, cases)))


def _index(args: argparse.Namespace, settings):
    """The index to measure: the real one, or with --memory a throwaway, in-process copy."""
    if args.memory:  # CI: index laws.jsonl into a throwaway, in-process Qdrant
        from qdrant_client import QdrantClient

        from tribunal.ingest.curate import load_laws
        from tribunal.search import LawIndex, Models

        index = LawIndex(QdrantClient(":memory:"), Models(settings.model_cache))
        index.rebuild(load_laws())
        return index
    from tribunal.wiring import build_index

    return build_index(settings)


def _review(args: argparse.Namespace, settings) -> None:
    """Moderate the public record: list reported cases, or hide, restore or delete one."""
    from tribunal.wiring import build_records

    records = build_records(settings)
    if records is None:
        sys.exit("Set DATABASE_URL first: this court keeps no public record yet.")
    if args.delete:
        print("deleted" if records.delete(args.delete) else "no such case")
    elif args.hide or args.restore:
        done = records.set_hidden(args.hide or args.restore, hidden=bool(args.hide))
        print(("hidden" if args.hide else "restored") if done else "no such case")
    else:
        for record_id, count, hidden, crime in records.reported():
            state = "hidden " if hidden else "visible"
            print(f"{record_id}  {count} reports  {state}  {crime[:70]}")


def _history(args: argparse.Namespace, settings) -> None:
    """Export the private history for study, or prune old entries from it."""
    from pathlib import Path

    from tribunal.wiring import build_history

    history = build_history(settings)
    if history is None:
        sys.exit("Set DATABASE_URL first: this court keeps no history yet.")
    if args.prune is not None:
        print(f"deleted {history.prune(args.prune)} entries older than {args.prune} days")
    if args.export:
        print(f"wrote {history.export(Path(args.export), args.days)} entries to {args.export}")
    if args.prune is None and not args.export:
        sys.exit("Say what to do: --export FILE, --prune DAYS, or both.")
