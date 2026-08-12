"""`ent lock --os` / `ent lock --undo --os` — OS-level golden immutability.

The hooks and CI detect-and-revert; filesystem immutability is the only TRUE
pre-execution block available locally: `chattr +i` (Linux) / `chflags uchg`
(macOS) on every golden file plus `entiendo/goldens.lock`. Requires
privileges (root / sudo); without them each file degrades gracefully to a
note — the layered protections above still hold.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
from pathlib import Path

from .. import integrity


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "lock",
        help="[trust] apply OS-level immutability to golden files (chattr/chflags)",
        description="OS-level immutability for goldens — the only true pre-execution block.",
    )
    p.add_argument("--os", dest="os_level", action="store_true", required=True,
                   help="required flag: this is the OS-immutability variant")
    p.add_argument("--undo", action="store_true", help="remove the immutability flag")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _targets(root: Path) -> list[Path]:
    files = [root / rel for rel in integrity.golden_files(root)]
    lock = integrity.lock_path(root)
    if lock.exists():
        files.append(lock)
    return files


def _cmd_for(undo: bool) -> list[str] | None:
    system = platform.system()
    if system == "Linux":
        return ["chattr", "-i" if undo else "+i"]
    if system == "Darwin":
        return ["chflags", "nouchg" if undo else "uchg"]
    return None


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    cmd = _cmd_for(args.undo)
    if cmd is None:
        print(f"ent lock: no immutability support on {platform.system()} — "
              "the hook + CI layers still protect the goldens.")
        return 0

    targets = _targets(root)
    if not targets:
        print("ent lock: no golden files found — nothing to lock.")
        return 0

    ok, failed = 0, 0
    for f in targets:
        proc = subprocess.run([*cmd, str(f)], capture_output=True, text=True)
        if proc.returncode == 0:
            ok += 1
        else:
            failed += 1
            reason = (proc.stderr or "").strip().splitlines()[-1:] or ["unknown"]
            print(f"  ! {f.relative_to(root)}: {reason[0]}")

    verb = "unlocked" if args.undo else "locked"
    print(f"ent lock: {verb} {ok}/{len(targets)} file(s)"
          + (" — failures above usually mean missing privileges (sudo) or an "
             "unsupported filesystem; detect-and-revert + CI still apply" if failed else ""))
    return 0 if failed == 0 else 1
