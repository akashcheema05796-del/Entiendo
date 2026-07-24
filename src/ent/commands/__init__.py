"""CLI command modules. One file per `ent` subcommand.

Each module exposes `register(subparsers)` which wires its arguments and sets a
`handler(args) -> int` default. Keeping commands one-per-file keeps the phase
boundaries (L0 → L5) legible in the file tree.
"""
