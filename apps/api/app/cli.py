"""Command line for the experience index and the agent.

python -m app.cli ingest                 # index data/resume/ or PROFILE_MCP (skips unchanged)
python -m app.cli ingest path/to/file.md --force
python -m app.cli search "Kubernetes in production" -k 5 --mode hybrid
python -m app.cli tailor posting.md      # run the agent, review the draft, print the result
python -m app.cli tailor posting.md --out result.md --json state.json --yes
python -m app.cli resume <run id>        # continue a run you quit, or one that stopped on an error
"""

import argparse
import asyncio
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from langgraph.types import Command
from pydantic_core import to_jsonable_python

from app.db import LOOP_FACTORY, AsyncSessionLocal, engine, init_db
from app.graph.builder import build_graph
from app.graph.checkpointer import postgres_checkpointer
from app.review_text import edit_text, format_request, parse_edit
from app.services import tracing
from app.services.ingest import find_files, ingest_configured, ingest_file
from app.services.retrieval import MODES, search_experience

APPROVE = {"action": "approve"}


async def _ingest(paths: list[str], force: bool) -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        if paths:  # just these files, nothing pruned
            files = find_files([Path(p) for p in paths])
            if not files:
                print("No .md, .txt, or .pdf files found.")
                return
            results, removed = [await ingest_file(db, f, force=force) for f in files], []
        else:
            results, removed = await ingest_configured(db, force=force)
            if not results:
                print("No .md, .txt, or .pdf files found. Put your resume in data/resume/.")
        for result in results:
            status = "unchanged" if result.skipped else "indexed"
            print(f"{status:>9}  {result.chunks:>3} chunks  {result.filename}")
        for name in removed:
            print(f"  removed         {name}")


async def _search(query: str, k: int, mode: str | None) -> None:
    async with AsyncSessionLocal() as db:
        results = await search_experience(db, query, k=k, mode=mode)
    for i, e in enumerate(results, start=1):
        scores = " ".join(f"{name}={value:.3f}" for name, value in e.scores.items())
        print(f"{i}. [{e.section}] {e.context}\n   {e.content}\n   {scores}\n")


def _edit_in_editor(request: dict) -> dict:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "vi")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(edit_text(request))
    try:
        subprocess.run([*shlex.split(editor, posix=os.name != "nt"), f.name], check=True)
        return parse_edit(Path(f.name).read_text(encoding="utf-8"), request)
    finally:
        os.unlink(f.name)


def _ask_review(request: dict) -> dict | None:
    """Show the draft and return a decision, or None to stop here and resume later."""
    print(f"\n{format_request(request)}\n")
    try:
        while True:
            choice = input("[a]pprove  [r]evise  [e]dit  [q]uit and resume later: ").strip().lower()[:1]
            if choice == "a":
                return APPROVE
            if choice == "r" and (feedback := input("What should change? ").strip()):
                return {"action": "revise", "feedback": feedback}
            if choice == "e":
                try:
                    return _edit_in_editor(request)
                except (ValueError, OSError, subprocess.CalledProcessError) as e:
                    print(f"Edit not applied: {e}")
            if choice == "q":
                return None
    except (KeyboardInterrupt, EOFError):
        return None


async def _drive(graph, config: dict, payload, auto_approve: bool, run: bool = True) -> dict | None:
    """Run the graph, reviewing each draft, until it finishes (state) or the reviewer quits (None)."""
    run_id = config["configurable"]["thread_id"]
    calls = tokens = 0
    while True:
        if run:
            # One trace per segment, like the API: start, each review, a resume after an error
            segment = "start" if isinstance(payload, dict) else "retry" if payload is None else "review"
            started = time.perf_counter()
            with tracing.traced(run_id, segment) as trace:
                segment_config = {**config, "callbacks": trace.callbacks}
                async for chunk in graph.astream(payload, segment_config, stream_mode="updates"):
                    for node in chunk:
                        if node != "__interrupt__":
                            print(f"{time.perf_counter() - started:6.1f}s  {node}", file=sys.stderr)
            calls += trace.usage.calls
            tokens += trace.usage.input_tokens + trace.usage.output_tokens
            print(f"        {calls} model calls, {tokens:,} tokens so far", file=sys.stderr)
        snapshot = await graph.aget_state(config)
        if not snapshot.interrupts:
            return snapshot.values
        decision = APPROVE if auto_approve else _ask_review(snapshot.interrupts[0].value)
        if decision is None:
            return None
        payload, run = Command(resume=decision), True


async def _run(thread_id: str, posting: str | None, out, state_out, auto_approve: bool) -> None:
    """Start a run (posting given) or pick one up by id. Every step is saved in Postgres."""
    config = {"configurable": {"thread_id": thread_id}}
    print(f"Run {thread_id}", file=sys.stderr)
    async with postgres_checkpointer() as saver:
        graph = build_graph(checkpointer=saver)
        try:
            if posting is not None:
                state = await _drive(graph, config, {"posting": posting}, auto_approve)
            else:
                snapshot = await graph.aget_state(config)
                if not snapshot.values:
                    sys.exit(f"No run with id {thread_id}.")
                # Paused for review: ask first. Stopped on an error: astream(None) continues it.
                run = bool(snapshot.next) and not snapshot.interrupts
                state = await _drive(graph, config, None, auto_approve, run=run)
        except Exception:
            print(
                f"\nThe run stopped. Continue it with: python -m app.cli resume {thread_id}", file=sys.stderr
            )
            raise
    if state is None:
        print(f"\nSaved. Continue with: python -m app.cli resume {thread_id}", file=sys.stderr)
        return
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
        elif args.command == "tailor":
            posting = Path(args.posting).read_text(encoding="utf-8")
            await _run(str(uuid.uuid4()), posting, args.out, args.json, args.yes)
        else:
            await _run(args.run_id, None, args.out, args.json, args.yes)
    finally:
        await engine.dispose()
        tracing.flush()


def _output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", help="also write the tailored section to this Markdown file")
    parser.add_argument("--json", help="write the full graph state to this JSON file")
    parser.add_argument("--yes", action="store_true", help="approve the draft without reviewing it")


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
    _output_args(tailor)
    resume = sub.add_parser("resume", help="continue a saved run by its id")
    resume.add_argument("run_id")
    _output_args(resume)
    asyncio.run(_main(parser.parse_args()), loop_factory=LOOP_FACTORY)


if __name__ == "__main__":
    main()
