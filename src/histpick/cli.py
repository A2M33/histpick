"""histpick: pick commands from your shell history and save them as a script."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from . import __version__, history, writer
from .picker import pick


def parse_numbers(text: str, count: int) -> list[int]:
    """'1 5-3,8' -> [0, 4, 3, 2, 7]. Numbers are 1-based, as shown by --list.

    The result keeps the order you wrote, ranges included, because that is the
    order the commands go into the script.
    """
    out: list[int] = []
    for part in text.replace(",", " ").split():
        if "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
            out.extend(range(a, b + 1) if a <= b else range(a, b - 1, -1))
        else:
            out.append(int(part))
    bad = [n for n in out if not 1 <= n <= count]
    if bad:
        raise ValueError(f"no command number {bad[0]} (there are {count})")
    return [n - 1 for n in dict.fromkeys(out)]


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    finally:
        _pause_if_double_clicked()


def _double_clicked() -> bool:
    # A double-clicked histpick.exe gets its own console, with no shell attached to it.
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    import ctypes

    procs = (ctypes.c_uint32 * 2)()
    return ctypes.windll.kernel32.GetConsoleProcessList(procs, 2) == 1


def _pause_if_double_clicked() -> None:
    # That console vanishes when we exit; keep it open so the message stays readable.
    if _double_clicked():
        input("Press Enter to close.")


def run_hint(path: Path, shell: str, platform: str = sys.platform) -> str:
    """The command that runs a saved script."""
    if shell == "powershell":
        if platform == "win32":  # Windows blocks unsigned scripts by default
            return f'powershell -ExecutionPolicy Bypass -File "{path}"'
        return f'pwsh -File "{path}"'
    return f"{shell} {shlex.quote(str(path))}"


def _main(argv: list[str] | None) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(errors="replace")

    p = argparse.ArgumentParser(
        prog="histpick",
        description="Pick commands from your shell history and save them as a script.",
    )
    p.add_argument("-o", "--output", help="file to write (default: histpick-<date>.<ext> in this folder)")
    p.add_argument("--shell", choices=["powershell", "bash", "zsh", "fish"],
                   help="whose history to read (default: detected)")
    p.add_argument("--limit", type=int, default=300, help="how many recent commands to offer (default 300)")
    p.add_argument("--grep", default="", help="only offer commands containing this text")
    p.add_argument("--list", action="store_true", help="print recent commands with numbers and exit")
    p.add_argument("--pick", metavar="NUMBERS", help='choose by number without the picker, e.g. "1 3-5"')
    p.add_argument("--last", type=int, metavar="N", help="take the last N commands without the picker")
    p.add_argument("--print", action="store_true", help="print the script instead of saving it")
    p.add_argument("--force", action="store_true", help="overwrite the output file")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    if args.shell:
        shell = next(s for s in history.known_shells() if s.name == args.shell)
    else:
        shell = history.detect()
    if shell is None or not shell.path.is_file():
        where = shell.path if shell else "any known location"
        print(f"No shell history found in {where}. Try --shell.", file=sys.stderr)
        return 1

    commands = [c for c in history.read(shell) if not writer.is_own_command(c)]
    items = history.recent_unique(commands)
    if args.grep:  # search the whole history, then keep the newest matches
        items = [c for c in items if args.grep.lower() in c.lower()]
    items = items[: args.limit]
    if not items:
        print("No matching commands.", file=sys.stderr)
        return 1

    if args.list:
        width = len(str(len(items)))
        for n, c in enumerate(items, 1):
            first, *rest = c.splitlines() or [""]
            more = f"  (+{len(rest)} lines)" if rest else ""
            print(f"{n:>{width}}  {first}{more}")
        return 0

    if args.last:
        chosen = list(reversed(items[: args.last]))
    elif args.pick:
        try:
            idx = parse_numbers(args.pick, len(items))
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        chosen = [items[i] for i in idx]
    else:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print("Not a terminal. Use --list with --pick, or --last.", file=sys.stderr)
            return 2
        chosen = pick(items, title=f"histpick: {shell.name} history")
        if chosen is None:
            print("Cancelled.")
            return 1

    if not chosen:
        print("Nothing chosen.")
        return 1

    text = writer.render(chosen, shell.name)
    if args.print:
        sys.stdout.write(text)
        return 0
    path = Path(args.output) if args.output else Path(writer.default_name(shell.ext))
    if not path.suffix:
        path = path.with_suffix(shell.ext)
    try:
        writer.save(text, path, shell.name, args.force)
    except FileExistsError as e:
        print(e, file=sys.stderr)
        return 2
    path = path.resolve()
    print(f"Saved {len(chosen)} command{'s' if len(chosen) != 1 else ''} to {path}")
    if _double_clicked():
        print(f"Open this folder to find it: {path.parent}")
    print(f"Run it with: {run_hint(path, shell.name)}")
    return 0
