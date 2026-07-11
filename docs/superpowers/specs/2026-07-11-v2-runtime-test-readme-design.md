# V2 Runtime Test and README Design

## Summary

Add an automated runtime smoke test for
`blueprints/v2/state_based_entity_control.yaml` and an end-user README beside
the blueprint. The test runs Home Assistant 2026.7.2 in Docker, loads the real
automation and `input_boolean` integrations, drives entity state changes, and
asserts target behavior. The README explains UI-first configuration, advanced
features, troubleshooting, and every verification command.

## Goals

- Verify the blueprint through Home Assistant's real automation engine rather
  than only parsing templates and checking configuration.
- Cover activation, delayed deactivation, manual-off lockout, lockout expiry,
  and trigger changes during lockout.
- Keep the runtime test isolated, deterministic, and runnable without a local
  Home Assistant installation.
- Document every v2 UI section, default, advanced format, and important runtime
  behavior for end users.
- Preserve the v1 blueprint unchanged.

## Non-goals

- Testing every combination already covered by the fast unit/template suite.
- Starting Home Assistant's HTTP server or testing REST/WebSocket
  authentication.
- Testing external integrations, physical devices, or frontend rendering.
- Supporting Home Assistant versions older than 2026.7.0.

## Runtime Test Architecture

Create `tests/run_state_based_entity_control_runtime.py`. It runs inside the
pinned Home Assistant container and starts Home Assistant core in-process. The
runner loads a temporary configuration containing real `input_boolean` helpers
and an automation instantiated from the v2 blueprint. It calls Home Assistant
services to change helper states and observes resulting states through the
state machine.

Create `tests/validate_state_based_entity_control_runtime.sh`. The shell wrapper
creates and cleans a temporary configuration directory, copies the v2 blueprint
into Home Assistant's expected blueprint path, writes the test configuration,
and launches the Python runner in
`ghcr.io/home-assistant/home-assistant:2026.7.2`. The repository is mounted
read-only for access to the runner. The script uses `set -euo pipefail` and
returns the container's exit status.

The existing Python unit suite gains a contract test that verifies the runtime
runner and wrapper exist, the container version is pinned, and the wrapper
invokes the runner.

## Runtime Scenarios

The runner uses real `input_boolean` entities for the trigger and target. It
instantiates the blueprint with short test durations and executes these
scenarios in a fresh Home Assistant instance or after a complete state reset:

1. **Activation:** turn the trigger on and require the target to become `on`.
2. **Delayed deactivation:** turn the trigger off, require the target to remain
   `on` before the delay expires, then require it to become `off` afterward.
3. **Manual-off lockout:** with the trigger active and target on, turn the
   target off manually and require it to remain off during the lockout.
4. **Lockout expiry:** require the active trigger to restore the target after
   the manual-off duration expires.
5. **Trigger changes during lockout:** toggle the trigger while the target is
   manually locked out and require no target action before lockout expiry; the
   target is reevaluated using the final trigger state after expiry.

The exact test durations must be long enough to avoid scheduler races but short
enough for a routine developer check. State assertions use monotonic deadlines
and short polling intervals. Fixed sleeps may only establish a deliberate
"still unchanged before deadline" assertion. Every timeout reports the
scenario, entity, expected state, actual state, and elapsed time.

## Lifecycle and Failure Handling

- The runner initializes and starts Home Assistant before configuring state
  transitions.
- Setup failures and unavailable services fail the test immediately.
- Each scenario prints a start and success line with elapsed time.
- Assertions raise descriptive failures and produce a nonzero process exit.
- Home Assistant is stopped in a `finally` block on both success and failure.
- Temporary configuration is removed by the wrapper's exit trap.
- Test execution must not modify the repository or leave generated files.

## README Structure

Create `blueprints/v2/README.md` for end users. It contains:

1. Overview and Home Assistant 2026.7+ requirement.
2. Installation/import instructions and a UI-first quick start.
3. A motion-sensor/light example.
4. Every UI section and its defaults:
   - Core entities and timeout.
   - State matching.
   - Custom actions.
   - Light conditions.
   - Blocking.
   - Manual-off handling.
   - Execution windows.
   - Alternate timeouts.
   - Advanced ranges.
   - Diagnostics.
5. Activation, explicit deactivation, and inverse-state matching semantics.
6. Default actions versus custom action-editor sequences.
7. Illuminance and solar-elevation `any`/`all` behavior.
8. Activation and deactivation blocker behavior.
9. Manual-off lockout illustrated as a short event timeline.
10. UI time pickers, schedule helpers, and unlimited advanced range syntax.
11. Alternate-timeout priority: native slots, advanced ranges, main timeout.
12. Examples for same-day, overnight, all-day, decimal duration, and regex
    entries.
13. Scene/script targets and separate deactivation targets.
14. Target-state tracking, manual control, diagnostics, traces, and
    troubleshooting.
15. Commands for fast unit tests, configuration validation, and the runtime
    integration test.
16. Known constraints.

The README leads with UI instructions. YAML is used only where it is the
clearest representation of an advanced expression or generated automation
input. Every command and path must match committed files.

## Known Constraints to Document

- Home Assistant 2026.7.0 or newer is required.
- State patterns are case-insensitive regular expressions and invalid patterns
  are reported by Home Assistant template execution.
- Illuminance, sun elevation, blockers, and schedules are gates; they do not
  independently trigger activation.
- Three daily execution windows and three alternate-timeout windows are
  directly available in the blueprint UI.
- Unlimited extra ranges use semicolon-separated advanced text fields.
- Advanced whitespace is ignored, equal endpoints mean all day, and a start
  later than its end crosses midnight.
- A custom action sequence is responsible for its own targets. Empty custom
  sequences use the selected target entities and Home Assistant's default
  `turn_on` or `turn_off` action.

## Verification

Run all of the following after implementation:

```bash
python3 -m unittest discover -v
tests/validate_state_based_entity_control.sh
tests/validate_state_based_entity_control_runtime.sh
git diff --check
git status --short
```

Acceptance requires:

- The existing fast suite and new contract tests pass.
- Home Assistant 2026.7.2 accepts the configuration.
- All five real runtime scenarios pass.
- The README documents every input section and uses accurate commands.
- The v1 blueprint has no diff from the pre-v2 baseline.
- Test commands leave the worktree clean.
