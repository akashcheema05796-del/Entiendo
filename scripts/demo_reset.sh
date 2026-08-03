#!/usr/bin/env bash
# One-command H5 demo reset (PLAN_v6 2.4). Restores the scratch fixture so the
# steer → diff → approve demo is repeatable take after take.
#
#   scripts/demo_reset.sh [scratch-dir]     default: /tmp/refundly-demo
#
# Rebuilds the scratch copy from examples/refundly and regenerates the graph.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="${1:-/tmp/refundly-demo}"

rm -rf "$SCRATCH"
cp -r "$REPO_ROOT/examples/refundly" "$SCRATCH"
cd "$SCRATCH"
ent extract >/dev/null
echo "✓ demo reset — fresh scratch at $SCRATCH (graph extracted, no steers, no proposals)"
echo "  next: cd $SCRATCH && ent serve --operator"
