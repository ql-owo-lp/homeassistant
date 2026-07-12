# V2 Runtime Test and README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Dockerized Home Assistant 2026.7.2 runtime test that proves real entity transitions and a complete UI-first README for the v2 blueprint.

**Architecture:** A shell wrapper creates an isolated Home Assistant configuration with two blueprint automations and launches an in-process Python runner inside the pinned Home Assistant container. One automation covers activation/deactivation and the other covers manual-off lockout, keeping scenario state independent; the README lives beside the v2 blueprint and documents every UI section and test command.

**Tech Stack:** Home Assistant 2026.7.2, Docker, Python 3 asyncio, Bash, unittest, Markdown.

---

## File map

- Create `tests/run_state_based_entity_control_runtime.py`: bootstrap Home Assistant, drive real helper services, poll states, report five runtime scenarios, and shut down safely.
- Create `tests/validate_state_based_entity_control_runtime.sh`: prepare temporary configuration and run the Python harness in the pinned container.
- Modify `tests/test_state_based_entity_control.py`: add fast contract tests for runtime files and README coverage.
- Create `blueprints/v2/README.md`: end-user UI configuration and troubleshooting guide.
- Do not modify `blueprints/state_based_entity_control.yaml` or `blueprints/v2/state_based_entity_control.yaml` unless the real runtime test exposes a blueprint defect; any defect requires a failing regression test first.

### Task 1: Add the real activation and deactivation runtime harness

**Files:**
- Create: `tests/run_state_based_entity_control_runtime.py`
- Create: `tests/validate_state_based_entity_control_runtime.sh`
- Modify: `tests/test_state_based_entity_control.py`

- [ ] **Step 1: Write the failing runtime-file contract test**

Extend `ValidationScriptTests` with:

```python
    def test_runtime_validator_uses_pinned_home_assistant_and_runner(self):
        tests_dir = Path(__file__).resolve().parent
        wrapper = (tests_dir / "validate_state_based_entity_control_runtime.sh").read_text(
            encoding="utf-8"
        )
        runner = (tests_dir / "run_state_based_entity_control_runtime.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("home-assistant:2026.7.2", wrapper)
        self.assertIn("run_state_based_entity_control_runtime.py", wrapper)
        self.assertIn("RuntimeConfig", runner)
        self.assertIn("async_setup_hass", runner)
        self.assertIn("scenario_activation", runner)
        self.assertIn("scenario_delayed_deactivation", runner)
```

- [ ] **Step 2: Run the contract test and verify the missing-file failure**

Run:

```bash
python3 -m unittest \
  tests.test_state_based_entity_control.ValidationScriptTests.test_runtime_validator_uses_pinned_home_assistant_and_runner -v
```

Expected: `FileNotFoundError` for `validate_state_based_entity_control_runtime.sh`.

- [ ] **Step 3: Create the runtime wrapper and isolated configuration**

Create executable `tests/validate_state_based_entity_control_runtime.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_dir="$(mktemp -d)"
trap 'rm -rf "${config_dir}"' EXIT

mkdir -p "${config_dir}/blueprints/automation/local"
cp "${repo_dir}/blueprints/v2/state_based_entity_control.yaml" \
  "${config_dir}/blueprints/automation/local/state_based_entity_control.yaml"

cat >"${config_dir}/configuration.yaml" <<'YAML'
homeassistant:
  name: Blueprint Runtime Test
  latitude: 0
  longitude: 0
  elevation: 0
  unit_system: metric
  time_zone: Etc/UTC
input_boolean:
  basic_trigger:
  basic_target:
  lockout_trigger:
  lockout_target:
automation: !include automations.yaml
YAML

cat >"${config_dir}/automations.yaml" <<'YAML'
- alias: Basic state control runtime test
  use_blueprint:
    path: local/state_based_entity_control.yaml
    input:
      trigger_entities:
        - input_boolean.basic_trigger
      target_entities:
        - input_boolean.basic_target
      main_timeout:
        seconds: 0.8
      logbook_enabled: false
- alias: Manual lockout runtime test
  use_blueprint:
    path: local/state_based_entity_control.yaml
    input:
      trigger_entities:
        - input_boolean.lockout_trigger
      target_entities:
        - input_boolean.lockout_target
      main_timeout:
        seconds: 0.2
      manual_off_enabled: true
      manual_off_duration:
        seconds: 1.5
      logbook_enabled: false
YAML

docker run --rm \
  -v "${config_dir}:/config" \
  -v "${repo_dir}/tests:/workspace/tests:ro" \
  ghcr.io/home-assistant/home-assistant:2026.7.2 \
  python /workspace/tests/run_state_based_entity_control_runtime.py /config
```

Run `chmod +x tests/validate_state_based_entity_control_runtime.sh`.

- [ ] **Step 4: Create the in-process runner with the first two scenarios**

Create `tests/run_state_based_entity_control_runtime.py`:

```python
#!/usr/bin/env python3
import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import monotonic
import sys

from homeassistant import bootstrap
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.runner import RuntimeConfig


async def call_input_boolean(hass: HomeAssistant, service: str, entity_id: str) -> None:
    await hass.services.async_call(
        "input_boolean",
        service,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )


async def wait_for_state(
    hass: HomeAssistant,
    scenario: str,
    entity_id: str,
    expected: str,
    timeout: float,
) -> None:
    started = monotonic()
    while monotonic() - started < timeout:
        state = hass.states.get(entity_id)
        if state is not None and state.state == expected:
            return
        await asyncio.sleep(0.05)
    state = hass.states.get(entity_id)
    actual = None if state is None else state.state
    raise AssertionError(
        f"{scenario}: expected {entity_id}={expected}, got {actual} "
        f"after {monotonic() - started:.2f}s"
    )


async def assert_state_after(
    hass: HomeAssistant,
    scenario: str,
    entity_id: str,
    expected: str,
    duration: float,
) -> None:
    await asyncio.sleep(duration)
    state = hass.states.get(entity_id)
    actual = None if state is None else state.state
    if actual != expected:
        raise AssertionError(
            f"{scenario}: expected {entity_id} to remain {expected} for "
            f"{duration:.2f}s, got {actual}"
        )


async def run_scenario(name: str, scenario: Callable[[], Awaitable[None]]) -> None:
    started = monotonic()
    print(f"START {name}", flush=True)
    await scenario()
    print(f"PASS  {name} ({monotonic() - started:.2f}s)", flush=True)


async def scenario_activation(hass: HomeAssistant) -> None:
    await call_input_boolean(hass, "turn_on", "input_boolean.basic_trigger")
    await wait_for_state(
        hass, "activation", "input_boolean.basic_target", "on", 2.0
    )


async def scenario_delayed_deactivation(hass: HomeAssistant) -> None:
    await call_input_boolean(hass, "turn_off", "input_boolean.basic_trigger")
    await assert_state_after(
        hass, "delayed deactivation", "input_boolean.basic_target", "on", 0.25
    )
    await wait_for_state(
        hass, "delayed deactivation", "input_boolean.basic_target", "off", 2.0
    )


async def async_main(config_dir: Path) -> None:
    runtime = RuntimeConfig(config_dir=str(config_dir), skip_pip=True)
    hass = await bootstrap.async_setup_hass(runtime)
    if hass is None:
        raise RuntimeError("Home Assistant setup returned no instance")
    if hass.config.recovery_mode:
        raise RuntimeError("Home Assistant entered recovery mode")
    try:
        await hass.async_start()
        await hass.async_block_till_done()
        for entity_id in (
            "input_boolean.basic_trigger",
            "input_boolean.basic_target",
            "input_boolean.lockout_trigger",
            "input_boolean.lockout_target",
        ):
            await wait_for_state(hass, "setup", entity_id, "off", 2.0)
        await run_scenario("activation", lambda: scenario_activation(hass))
        await run_scenario(
            "delayed deactivation", lambda: scenario_delayed_deactivation(hass)
        )
    finally:
        await hass.async_stop(force=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: run_state_based_entity_control_runtime.py CONFIG_DIR")
    asyncio.run(async_main(Path(sys.argv[1])))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the fast contract and real runtime test**

Run:

```bash
python3 -m unittest discover -v
tests/validate_state_based_entity_control_runtime.sh
```

Expected: fast tests pass and the runtime output contains `PASS  activation`
and `PASS  delayed deactivation`. If Home Assistant 2026.7.2 APIs differ from
the inspected signatures, add a failing contract/regression assertion before
making the smallest compatibility correction.

- [ ] **Step 6: Commit the first real runtime scenarios**

```bash
git add tests/test_state_based_entity_control.py \
  tests/run_state_based_entity_control_runtime.py \
  tests/validate_state_based_entity_control_runtime.sh
git commit -m "test: exercise blueprint in Home Assistant runtime"
```

### Task 2: Add manual-off lockout runtime scenarios

**Files:**
- Modify: `tests/run_state_based_entity_control_runtime.py`
- Modify: `tests/test_state_based_entity_control.py`

- [ ] **Step 1: Extend the contract test before adding scenarios**

Add these assertions to the runtime contract test:

```python
        self.assertIn("scenario_manual_off_lockout", runner)
        self.assertIn("scenario_trigger_changes_during_lockout", runner)
        self.assertIn("scenario_lockout_expiry", runner)
```

- [ ] **Step 2: Run the focused contract and verify it fails**

Run the focused unittest from Task 1. Expected: failure because the three
scenario function names are absent.

- [ ] **Step 3: Add the three lockout scenarios**

Add these functions to the runner:

```python
async def scenario_manual_off_lockout(hass: HomeAssistant) -> None:
    await call_input_boolean(hass, "turn_on", "input_boolean.lockout_trigger")
    await wait_for_state(
        hass, "manual-off setup", "input_boolean.lockout_target", "on", 2.0
    )
    await call_input_boolean(hass, "turn_off", "input_boolean.lockout_target")
    await assert_state_after(
        hass, "manual-off lockout", "input_boolean.lockout_target", "off", 0.25
    )


async def scenario_trigger_changes_during_lockout(hass: HomeAssistant) -> None:
    await call_input_boolean(hass, "turn_off", "input_boolean.lockout_trigger")
    await asyncio.sleep(0.10)
    await call_input_boolean(hass, "turn_on", "input_boolean.lockout_trigger")
    await assert_state_after(
        hass,
        "trigger changes during lockout",
        "input_boolean.lockout_target",
        "off",
        0.30,
    )


async def scenario_lockout_expiry(hass: HomeAssistant) -> None:
    await wait_for_state(
        hass, "lockout expiry", "input_boolean.lockout_target", "on", 2.5
    )
```

Invoke them after the basic scenarios, in this order:

```python
        await run_scenario(
            "manual-off lockout", lambda: scenario_manual_off_lockout(hass)
        )
        await run_scenario(
            "trigger changes during lockout",
            lambda: scenario_trigger_changes_during_lockout(hass),
        )
        await run_scenario(
            "lockout expiry", lambda: scenario_lockout_expiry(hass)
        )
```

- [ ] **Step 4: Run all five real scenarios three times**

Run:

```bash
tests/validate_state_based_entity_control_runtime.sh
tests/validate_state_based_entity_control_runtime.sh
tests/validate_state_based_entity_control_runtime.sh
```

Expected on every run: five `PASS` lines and exit code 0. If a timing boundary
is flaky, preserve the behavior durations and increase only assertion timeout
headroom; do not remove the pre-expiry unchanged assertions.

- [ ] **Step 5: Run the fast suite and commit**

```bash
python3 -m unittest discover -v
git diff --check
git add tests/test_state_based_entity_control.py \
  tests/run_state_based_entity_control_runtime.py
git commit -m "test: cover manual lockout in Home Assistant runtime"
```

### Task 3: Add the v2 configuration README

**Files:**
- Create: `blueprints/v2/README.md`
- Modify: `tests/test_state_based_entity_control.py`

- [ ] **Step 1: Write the failing README coverage contract**

Add a `ReadmeTests` class that loads `blueprints/v2/README.md` and asserts these
exact headings or strings are present:

```python
class ReadmeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (
            Path(__file__).resolve().parents[1] / "blueprints" / "v2" / "README.md"
        ).read_text(encoding="utf-8")

    def test_readme_covers_configuration_and_operations(self):
        required = (
            "# State Based Entity Control v2",
            "## Requirements",
            "## Quick start",
            "## UI configuration reference",
            "### Core entities and timeout",
            "### State matching",
            "### Actions",
            "### Light conditions",
            "### Blocking",
            "### Manual-off handling",
            "### Execution windows",
            "### Alternate timeouts",
            "### Advanced ranges",
            "### Diagnostics",
            "## Scenes and scripts",
            "## Troubleshooting",
            "## Testing",
        )
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, self.readme)

    def test_readme_commands_and_formats_match_the_repository(self):
        for text in (
            "Home Assistant 2026.7",
            "python3 -m unittest discover -v",
            "tests/validate_state_based_entity_control.sh",
            "tests/validate_state_based_entity_control_runtime.sh",
            "start-end,duration",
            "native slots → advanced ranges → main timeout",
        ):
            with self.subTest(text=text):
                self.assertIn(text, self.readme)
```

- [ ] **Step 2: Run the README tests and verify the missing-file failure**

Expected: `FileNotFoundError` for `blueprints/v2/README.md`.

- [ ] **Step 3: Write the README**

Create `blueprints/v2/README.md` using all headings asserted above. Its content
must implement the approved README structure and include these exact examples:

```text
Activation pattern: on|playing|home
Explicit deactivation pattern: off|idle|not_home
Same-day range: 09:00:00-17:00:00
Overnight range: 22:00:00-02:00:00
All-day range: 00:00:00-00:00:00
Alternate timeout: 17:00:00-19:30:00,30
Decimal timeout: 19:30:00-20:00:00,0:00:07.5
```

Document the manual-off timeline as:

```text
T+0.0  Target is manually turned off; lockout begins.
T+0.5  Trigger changes; the target remains off.
T+N    Lockout expires; current trigger state is reevaluated.
```

The UI reference must state every default from the blueprint, explain that
empty custom action sequences use `homeassistant.turn_on` and
`homeassistant.turn_off`, state that custom sequences own their targets, and
explain schedule/helper OR semantics. Troubleshooting must cover unavailable
triggers, invalid regexes, malformed advanced ranges, environment gates not
triggering independently, traces, and logbook diagnostics.

- [ ] **Step 4: Run README and full tests**

```bash
python3 -m unittest tests.test_state_based_entity_control.ReadmeTests -v
python3 -m unittest discover -v
git diff --check
```

Expected: all tests pass with no whitespace errors.

- [ ] **Step 5: Commit the README**

```bash
git add blueprints/v2/README.md tests/test_state_based_entity_control.py
git commit -m "docs: explain state control v2 configuration"
```

### Task 4: Run final authoritative verification

**Files:**
- Modify only when a failing verification has a new regression test first.

- [ ] **Step 1: Run the complete fast suite**

```bash
python3 -m unittest discover -v
```

Expected: all tests pass with zero failures or errors.

- [ ] **Step 2: Validate Home Assistant configuration expansion**

```bash
tests/validate_state_based_entity_control.sh
```

Expected: exit code 0 after `Testing configuration at /config`.

- [ ] **Step 3: Run the real Home Assistant scenarios**

```bash
tests/validate_state_based_entity_control_runtime.sh
```

Expected: five named `PASS` lines and exit code 0.

- [ ] **Step 4: Verify scope and cleanliness**

```bash
git diff --check
git diff --exit-code 66d5d0e -- blueprints/state_based_entity_control.yaml
rg -n 'TB[D]|FIXM[E]|PLACEHOLDE[R]' blueprints/v2 tests || true
git status --short
```

Expected: no diff/placeholder findings, no v1 changes, and a clean worktree.

- [ ] **Step 5: Record evidence in the handoff**

Report the fast-test count, Home Assistant image version, all five scenario
names, both validator exit results, final commit, and clean status. Do not claim
completion without fresh output from Steps 1-4.
