# examples/astrobee — the real-world showcase

A vendored slice of [NASA's astrobee](https://github.com/nasa/astrobee)
flight-software repository, retrofitted with Entiendo. The full retrofit
(akashdatageek/astrobee PRs #3–#4) mapped **43 units over 195 recognized
source files**; this slice carries six of them, chosen so that every honest
state the gate can report shows up on real code:

| Unit | State | What it shows |
|---|---|---|
| `astrobee.bmr` | GREEN | pure enum-migration parser, single-arg fixtures |
| `astrobee.sweep` | GREEN | 2-arg function judged through a harness |
| `astrobee.mapping` | GREEN | **a latent bug found by authoring fixtures** — `parse_localization_log_str` crashes on a value with no trailing unit (`float('')`); pinned as an `expectError` row, so an upstream fix flags the row |
| `astrobee.common` | GREEN | a catkin-style package deep in the tree (`common/localization_common/`) |
| `astrobee.merge` | GREEN | its `import localization_common.utilities` is resolved by the **repo-wide package map** → the `astrobee.merge → astrobee.common` edge; the eval loader mirrors the same map (judge/extractor parity) |
| `astrobee.stats` | ENV-BLOCKED | `contract.requires: [rosbag, numpy]` — outside a ROS install the verdict is "wrong environment", never "broken code"; exit 0, counted, grey |

```bash
cd examples/astrobee
ent validate            # 6 manifests valid
ent extract             # graph: 6 units, 1 verified edge, no drift
ent eval --all          # 5 GREEN, 1 ENV-BLOCKED
ent ci                  # → exit 0
ent dev                 # the Universe on http://127.0.0.1:7373
```

Every expectation in `evals/*/smoke.jsonl` states its provenance in its row
name where it matters — the `astrobee.mapping` crash row is
implementation-derived (it pins today's behaviour, found by execution, not
blessed truth). Harnesses live beside the fixtures, outside all claims, so
editing them never moves a composite fingerprint.

## Provenance & license

The `.py` files are unmodified copies from
[nasa/astrobee](https://github.com/nasa/astrobee) (via the
akashdatageek/astrobee fork), © United States Government / NASA, licensed
under the **Apache License 2.0** — each file retains its original license
header. The Entiendo manifests, fixtures, and harnesses in this directory are
part of Entiendo and carry its license.
