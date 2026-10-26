"""Command line for the experience index and the agent.

python -m app.cli ingest                 # index data/resume/ (skips unchanged files)
python -m app.cli ingest path/to/file.md --force
python -m app.cli search "Kubernetes in production" -k 5 --mode hybrid
python -m app.cli tailor posting.md      # run the agent, print the tailored section
python -m app.cli tailor posting.md --out result.md --json state.json
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from pydantic_core import to_jsonable_python

from app.config import get_settings
from app.db import LOOP_FACTORY, AsyncSessionLocal, engine, init_db
from app.graph.builder import build_graph
from app.services.ingest import find_files, ingest_file, remove_missing
from app.services.retrieval import MODES, search_experience


async def _ingest(paths: list[str], force: bool) -> None:
    default = not paths
    files = find_files([Path(p) for p in paths] if paths else [Path(get_settings().resume_dir)])
    if not files:
        print("No .md, .txt, or .pdf files found. Put your resume in data/resume/.")
        return
    await init_db()
    async with AsyncSessionLocal() as db:
        for f in files:
            result = await ingest_file(db, f, force=force)
            status = "unchanged" if result.skipped else "indexed"
            print(f"{status:>9}  {result.chunks:>3} chunks  {result.filename}")
        if default:  # only prune when indexing the whole folder
            for name in await remove_missing(db, files):
                print(f"  removed         {name}")


async def _search(query: str, k: int, mode: str | None) -> None:
    async with AsyncSessionLocal() as db:
        results = await search_experience(db, query, k=k, mode=mode)
    for i, e in enumerate(results, start=1):
        scores = " ".join(f"{name}={value:.3f}" for name, value in e.scores.items())
        print(f"{i}. [{e.section}] {e.context}\n   {e.content}\n   {scores}\n")


async def _tailor(posting_path: str, out: str | None, state_out: str | None) -> None:
    posting = Path(posting_path).read_text(encoding="utf-8")
    state, started = {}, time.perf_counter()
    async for mode, chunk in build_graph().astream({"posting": posting}, stream_mode=["updates", "values"]):
        if mode == "values":
            state = chunk
        else:
            for node in chunk:
                print(f"{time.perf_counter() - started:6.1f}s  {node}", file=sys.stderr)
    result = state["result"]
    if out:
        Path(out).write_text(result.markdown, encoding="utf-8")
    if state_out:
        dump = json.dumps(state, default=to_jsonable_python, indent=2, ensure_ascii=False)
        Path(state_out).write_text(dump, encoding="utf-8")
    print(result.markdown)


async def _main(args: argparse.Namespace) -> None:
    try:
        if args.command == "ingest":
            await _ingest(args.paths, args.force)
        elif args.command == "search":
            await _search(args.query, args.k, args.mode)
        else:
            await _tailor(args.posting, args.out, args.json)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="index resume files (default: data/resume/)")
    ingest.add_argument("paths", nargs="*")
    ingest.add_argument("--force", action="store_true", help="re-embed files even if unchanged")
    search = sub.add_parser("search", help="search the experience index")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=5)
    search.add_argument("--mode", choices=MODES)
    tailor = sub.add_parser("tailor", help="tailor the indexed resume to a job posting")
    tailor.add_argument("posting", help="a text or Markdown file with the job posting")
    tailor.add_argument("--out", help="also write the tailored section to this Markdown file")
    tailor.add_argument("--json", help="write the full graph state to this JSON file")
    asyncio.run(_main(parser.parse_args()), loop_factory=LOOP_FACTORY)


if __name__ == "__main__":
    main()
