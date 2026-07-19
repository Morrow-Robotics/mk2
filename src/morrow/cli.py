"""`morrow analyze demo.mp4 --description "..."` — the one command MK2 ships today.

Writes the WorkflowSpec as JSON (the primary artifact) and prints a short evidence
timeline plus any validation issues, so a human can sanity-check the run at a glance.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyze import Analysis, analyze


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="morrow")
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="infer a WorkflowSpec from a demo video")
    a.add_argument("video", help="path to the demonstration video")
    a.add_argument("--description", required=True, help="what you want the robot to do")
    a.add_argument("--transcript", help="path to a text file of in-video narration (optional)")
    a.add_argument("--frames", type=int, default=8, help="frames to sample from the video")
    a.add_argument("--out", help="write the WorkflowSpec JSON here (default: stdout)")

    args = parser.parse_args(argv)

    transcript = Path(args.transcript).read_text() if args.transcript else None
    result = analyze(args.video, args.description, transcript=transcript, frames=args.frames)

    spec_json = result.spec.model_dump_json(indent=2)
    if args.out:
        Path(args.out).write_text(spec_json)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(spec_json)

    _print_summary(result)
    # Non-zero exit if the spec failed a hard invariant — makes the CLI scriptable.
    return 1 if any(i.severity == "error" for i in result.issues) else 0


def _print_summary(result: Analysis) -> None:
    out = sys.stderr
    print(f"\nstatus: {result.spec.status}  (confidence {result.spec.confidence:.2f})", file=out)

    print("\nevidence timeline:", file=out)
    for step in sorted(result.spec.steps, key=lambda s: (s.start_s is None, s.start_s or 0.0)):
        span = f"{step.start_s:.1f}-{step.end_s:.1f}s" if step.start_s is not None and step.end_s is not None else "  ?  "
        print(f"  {span:>12}  {step.action:<8} {step.description}", file=out)

    if result.spec.unknowns:
        print("\nunknowns:", file=out)
        for u in result.spec.unknowns:
            print(f"  ? {u.question}", file=out)

    if result.issues:
        print("\nvalidation issues:", file=out)
        for issue in result.issues:
            print(f"  [{issue.severity}] {issue.message}", file=out)


if __name__ == "__main__":
    raise SystemExit(main())
