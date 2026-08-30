# Bot Approval Handoff

## Status

**BLOCKED — NOT READY FOR EXTERNAL APPROVAL**

Phase 9 smoke validation is implemented, but the required full evidence is not
present. The smoke report correctly fails closed for the 1,000 paired-game
strength gate and the one-hour soak gate. This repository must not submit an
approval request while either gate is incomplete.

## Local configuration

- Ruleset: `tetrio-public-2026-08-30`
- Preset: `bot_standard`
- Board: 10×20 visible rows with four buffer rows
- Rotation: SRS+
- Piece sequence: 7-bag
- Hold: enabled
- Target execution speed: minimum 0.6 PPS
- Runtime: CPU and CLI first

## AI and authority boundaries

```text
Ruleset + seed → Simulator/GameState → Move Generator → Evaluator/Search → Move
                                                     ↓
                                             Execution Scheduler
```

The Simulator owns every state transition. Agents receive a snapshot and
return a validated `Move`; they do not edit boards or simulator state. The
viewer/replay layer is read-only and the scheduler changes timing, never the
selected Move.

## Evidence required before handoff

- [ ] Ruleset fixtures and transition suite remain 100% green.
- [ ] 1,000 paired seeded games: Greedy > Random at least 55%.
- [ ] 1,000 paired seeded games: Search > Greedy at least 55%.
- [ ] Invalid Candidate and Move counts are zero.
- [ ] Decision latency P95 ≤ 100 ms and P99 ≤ 250 ms.
- [ ] PPS target is measured at or above 0.6 with error within ±5%.
- [ ] One-hour headless soak has zero crashes, invalid moves, and state corruption.
- [ ] CPU and memory evidence is attached to the final validation report.

Run the local validator in full mode after collecting those measurements:

```bash
python3 -m benchmark.final_validation --mode full --json
```

## Abuse prevention and scope

- No Bot Account authentication, cookies, tokens, credentials, or online
  submission code belongs in this repository.
- No TETR.IO network adapter is part of this runtime.
- CLI inputs are validated; search depth/width and scheduler PPS are bounded.
- Malformed Moves are rejected before simulator transition.
- Missing or mismatched evidence fails validation instead of being inferred.
- Neural evaluation remains deferred unless the documented paired benchmark
  proves a real improvement over Search within the CPU parameter/latency gate.

## Manual handoff steps

1. Run Phase 9 full validation and retain its machine-readable report.
2. Review every criterion and attach the seeded event-log/report hashes.
3. Confirm the external adapter and approval process in a separate controlled
   project.
4. Perform any approval submission manually outside this repository.
