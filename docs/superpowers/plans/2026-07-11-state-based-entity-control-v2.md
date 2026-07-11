# State Based Entity Control v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy state-based entity-control blueprint with a Home Assistant 2026.7+ v2 that preserves all existing behavior, adds UI-native configuration and manual-off lockout, and is traceable and testable.

**Architecture:** Keep the deliverable as one Home Assistant blueprint because inputs, triggers, variables, and actions must be imported as one YAML document. Add a small standard-library test suite that parses the blueprint, inspects its UI/schema contract, and renders decision templates with mocked Home Assistant state helpers; add a Docker-based validation script for authoritative Home Assistant configuration expansion.

**Tech Stack:** Home Assistant 2026.7 automation blueprints, YAML, Jinja templates, Python 3 `unittest`, PyYAML, Jinja2, Docker with `ghcr.io/home-assistant/home-assistant:2026.7.2`.

---

## File map

- Create `blueprints/v2/state_based_entity_control.yaml`: the complete v2 blueprint, including UI inputs, normalized variables, triggers, gates, lockout logic, timeout resolution, actions, and trace aliases. Preserve the v1 blueprint at its existing path.
- Create `tests/test_state_based_entity_control.py`: fast blueprint contract and template behavior tests that run without installing Home Assistant.
- Create `tests/validate_state_based_entity_control.sh`: build a temporary Home Assistant configuration, instantiate the blueprint through `use_blueprint`, and run Home Assistant's configuration checker in the pinned container.
- Reference `docs/superpowers/specs/2026-07-11-state-based-entity-control-v2-design.md`: approved behavior contract; do not modify unless implementation exposes a genuine contradiction.

### Task 1: Establish the v2 blueprint UI contract

**Files:**
- Create: `tests/test_state_based_entity_control.py`
- Create: `blueprints/v2/state_based_entity_control.yaml`

- [ ] **Step 1: Write the failing metadata and UI contract tests**

Create `tests/test_state_based_entity_control.py` with this initial content:

```python
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "blueprints" / "state_based_entity_control.yaml"


class BlueprintLoader(yaml.SafeLoader):
    pass


def _input(loader, node):
    return {"!input": loader.construct_scalar(node)}


BlueprintLoader.add_constructor("!input", _input)


def load_blueprint():
    return yaml.load(BLUEPRINT.read_text(), Loader=BlueprintLoader)


def flatten_inputs(document):
    flattened = {}
    for key, value in document["blueprint"]["input"].items():
        if "input" in value:
            flattened.update(value["input"])
        else:
            flattened[key] = value
    return flattened


class BlueprintUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_blueprint()
        cls.inputs = flatten_inputs(cls.document)

    def test_requires_home_assistant_2026_7(self):
        self.assertEqual(
            self.document["blueprint"]["homeassistant"]["min_version"],
            "2026.7.0",
        )

    def test_groups_inputs_into_ui_sections(self):
        sections = self.document["blueprint"]["input"]
        self.assertEqual(
            list(sections),
            [
                "core",
                "state_matching",
                "actions_config",
                "light_conditions",
                "blocking",
                "manual_off",
                "execution_windows",
                "alternate_timeouts",
                "advanced",
                "diagnostics",
            ],
        )
        for section in sections.values():
            self.assertIn("input", section)
            if section.get("collapsed"):
                for item in section["input"].values():
                    self.assertIn("default", item)

    def test_common_settings_use_native_selectors(self):
        expected = {
            "trigger_entities": "entity",
            "target_entities": "entity",
            "off_target_entities": "entity",
            "main_timeout": "duration",
            "activation_actions": "action",
            "deactivation_actions": "action",
            "illuminance_enabled": "boolean",
            "illuminance_threshold": "number",
            "sun_enabled": "boolean",
            "sun_elevation_threshold": "number",
            "light_gate_mode": "select",
            "target_state_tracking": "boolean",
            "manual_off_enabled": "boolean",
            "manual_off_duration": "duration",
            "execution_schedule": "entity",
            "logbook_enabled": "boolean",
        }
        for name, selector in expected.items():
            self.assertIn(selector, self.inputs[name]["selector"], name)

    def test_regex_and_unlimited_ranges_remain_ui_editable(self):
        for name in (
            "activation_state_pattern",
            "deactivation_state_pattern",
            "target_state_pattern",
            "activation_blocker_state_pattern",
            "deactivation_blocker_state_pattern",
            "manual_off_state_pattern",
            "advanced_execution_ranges",
            "advanced_alternate_timeouts",
        ):
            self.assertIn("text", self.inputs[name]["selector"], name)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the UI contract tests and verify they fail against v1**

Run:

```bash
python3 -m unittest tests.test_state_based_entity_control.BlueprintUiTests -v
```

Expected: failures for the missing `homeassistant` metadata, sections, and v2 input names.

- [ ] **Step 3: Replace the blueprint metadata and input block**

In `blueprints/v2/state_based_entity_control.yaml`, use the name with a `v2`
suffix, rewrite the description, declare `min_version: 2026.7.0`, and define
the ten tested sections in the tested order. Use these exact selector shapes and
defaults throughout the section definitions:

```yaml
blueprint:
  name: State Based Entity Control v2
  description: >-
    Controls entities or custom actions from arbitrary entity states, with
    optional light gates, blockers, schedules, alternate timeouts, and a
    manual-off lockout. All options are configurable from the blueprint UI.
  domain: automation
  homeassistant:
    min_version: 2026.7.0
  input:
    core:
      name: Core control
      icon: mdi:toggle-switch
      input:
        trigger_entities:
          name: Trigger entities
          selector:
            entity:
              multiple: true
        target_entities:
          name: Target entities
          selector:
            entity:
              multiple: true
        off_target_entities:
          name: Separate deactivation targets
          default: []
          selector:
            entity:
              multiple: true
        main_timeout:
          name: Deactivation delay
          default: {hours: 0, minutes: 0, seconds: 30}
          selector:
            duration:
    state_matching:
      name: State matching
      icon: mdi:regex
      collapsed: true
      input:
        activation_state_pattern:
          name: Activation state pattern
          default: "on"
          selector: {text: {}}
        deactivation_state_pattern:
          name: Explicit deactivation state pattern
          default: ""
          selector: {text: {}}
        target_state_tracking:
          name: Track target state
          default: true
          selector: {boolean: {}}
        target_state_pattern:
          name: Active target state pattern
          default: "on"
          selector: {text: {}}
    actions_config:
      name: Custom actions
      icon: mdi:play-box-multiple
      collapsed: true
      input:
        activation_actions:
          name: Activation actions
          default: []
          selector: {action: {}}
        deactivation_actions:
          name: Deactivation actions
          default: []
          selector: {action: {}}
```

Continue the same block with these complete section definitions:

```yaml
    light_conditions:
      name: Light conditions
      icon: mdi:brightness-6
      collapsed: true
      input:
        illuminance_enabled:
          name: Enable illuminance gate
          default: false
          selector: {boolean: {}}
        illuminance_sensor:
          name: Illuminance sensor
          default: ""
          selector:
            entity:
              filter:
                domain: sensor
                device_class: illuminance
        illuminance_threshold:
          name: Illuminance at or below
          default: 100
          selector:
            number:
              min: 0
              max: 100000
              unit_of_measurement: lx
              mode: box
        sun_enabled:
          name: Enable solar-elevation gate
          default: false
          selector: {boolean: {}}
        sun_elevation_threshold:
          name: Solar elevation at or below
          default: 0
          selector:
            number:
              min: -90
              max: 90
              unit_of_measurement: "°"
              mode: slider
        light_gate_mode:
          name: When both light gates are enabled
          default: any
          selector:
            select:
              mode: dropdown
              options:
                - label: Either gate passes
                  value: any
                - label: Both gates pass
                  value: all
    blocking:
      name: Blocking
      icon: mdi:cancel
      collapsed: true
      input:
        activation_blocker_entity:
          name: Activation blocker
          default: ""
          selector: {entity: {}}
        activation_blocker_state_pattern:
          name: Activation blocker state pattern
          default: "on"
          selector: {text: {}}
        deactivation_blocker_entity:
          name: Deactivation blocker
          default: ""
          selector: {entity: {}}
        deactivation_blocker_state_pattern:
          name: Deactivation blocker state pattern
          default: "on"
          selector: {text: {}}
    manual_off:
      name: Manual-off lockout
      icon: mdi:hand-back-right-off
      collapsed: true
      input:
        manual_off_enabled:
          name: Enable manual-off lockout
          default: false
          selector: {boolean: {}}
        manual_off_duration:
          name: Manual-off lockout duration
          default: {hours: 0, minutes: 30, seconds: 0}
          selector: {duration: {}}
        manual_off_state_pattern:
          name: Manual-off state pattern
          default: "off"
          selector: {text: {}}
    execution_windows:
      name: Execution windows
      icon: mdi:calendar-clock
      collapsed: true
      input:
        execution_schedule:
          name: Execution schedule helper
          default: ""
          selector:
            entity:
              filter:
                domain: schedule
        execution_window_1_enabled:
          name: Enable daily window 1
          default: false
          selector: {boolean: {}}
        execution_window_1_start:
          name: Daily window 1 start
          default: "00:00:00"
          selector: {time: {}}
        execution_window_1_end:
          name: Daily window 1 end
          default: "00:00:00"
          selector: {time: {}}
        execution_window_2_enabled:
          name: Enable daily window 2
          default: false
          selector: {boolean: {}}
        execution_window_2_start:
          name: Daily window 2 start
          default: "00:00:00"
          selector: {time: {}}
        execution_window_2_end:
          name: Daily window 2 end
          default: "00:00:00"
          selector: {time: {}}
        execution_window_3_enabled:
          name: Enable daily window 3
          default: false
          selector: {boolean: {}}
        execution_window_3_start:
          name: Daily window 3 start
          default: "00:00:00"
          selector: {time: {}}
        execution_window_3_end:
          name: Daily window 3 end
          default: "00:00:00"
          selector: {time: {}}
    alternate_timeouts:
      name: Alternate timeouts
      icon: mdi:timer-cog
      collapsed: true
      input:
        alternate_timeout_1_enabled:
          name: Enable alternate timeout 1
          default: false
          selector: {boolean: {}}
        alternate_timeout_1_start:
          name: Alternate timeout 1 start
          default: "00:00:00"
          selector: {time: {}}
        alternate_timeout_1_end:
          name: Alternate timeout 1 end
          default: "00:00:00"
          selector: {time: {}}
        alternate_timeout_1_duration:
          name: Alternate timeout 1 duration
          default: {hours: 0, minutes: 0, seconds: 30}
          selector: {duration: {}}
        alternate_timeout_2_enabled:
          name: Enable alternate timeout 2
          default: false
          selector: {boolean: {}}
        alternate_timeout_2_start:
          name: Alternate timeout 2 start
          default: "00:00:00"
          selector: {time: {}}
        alternate_timeout_2_end:
          name: Alternate timeout 2 end
          default: "00:00:00"
          selector: {time: {}}
        alternate_timeout_2_duration:
          name: Alternate timeout 2 duration
          default: {hours: 0, minutes: 0, seconds: 30}
          selector: {duration: {}}
        alternate_timeout_3_enabled:
          name: Enable alternate timeout 3
          default: false
          selector: {boolean: {}}
        alternate_timeout_3_start:
          name: Alternate timeout 3 start
          default: "00:00:00"
          selector: {time: {}}
        alternate_timeout_3_end:
          name: Alternate timeout 3 end
          default: "00:00:00"
          selector: {time: {}}
        alternate_timeout_3_duration:
          name: Alternate timeout 3 duration
          default: {hours: 0, minutes: 0, seconds: 30}
          selector: {duration: {}}
    advanced:
      name: Advanced unlimited ranges
      icon: mdi:code-braces
      collapsed: true
      input:
        advanced_execution_ranges:
          name: Additional execution ranges
          default: ""
          selector: {text: {multiline: true}}
        advanced_alternate_timeouts:
          name: Additional alternate timeouts
          default: ""
          selector: {text: {multiline: true}}
    diagnostics:
      name: Diagnostics
      icon: mdi:text-box-search
      collapsed: true
      input:
        logbook_enabled:
          name: Write logbook entries
          default: true
          selector: {boolean: {}}
```

Keep the names in the code block as the UI labels. Add the approved design's
format explanation to the two advanced section descriptions, not as untested
changes to individual selector definitions.

- [ ] **Step 4: Run the UI contract tests and verify they pass**

Run:

```bash
python3 -m unittest tests.test_state_based_entity_control.BlueprintUiTests -v
```

Expected: four tests pass.

- [ ] **Step 5: Commit the v2 UI contract**

```bash
git add blueprints/v2/state_based_entity_control.yaml tests/test_state_based_entity_control.py
git commit -m "feat: add state control v2 blueprint inputs"
```

### Task 2: Normalize entities and preserve state-matching semantics

**Files:**
- Modify: `tests/test_state_based_entity_control.py`
- Modify: `blueprints/v2/state_based_entity_control.yaml`

- [ ] **Step 1: Add failing structure tests for triggers and core variables**

Append this class to the test file:

```python
class RuntimeStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_blueprint()
        cls.yaml_text = BLUEPRINT.read_text()

    def test_uses_modern_automation_keys_and_restart_mode(self):
        self.assertIn("triggers", self.document)
        self.assertIn("conditions", self.document)
        self.assertIn("actions", self.document)
        self.assertNotIn("trigger", self.document)
        self.assertNotIn("condition", self.document)
        self.assertEqual(self.document["mode"], "restart")
        self.assertEqual(self.document["max_exceeded"], "silent")

    def test_has_all_required_trigger_ids(self):
        ids = {item.get("id") for item in self.document["triggers"]}
        self.assertEqual(
            ids,
            {
                "automation_reloaded",
                "home_assistant_started",
                "trigger_entity_changed",
                "target_state_stable",
                "manual_lockout_expired",
            },
        )

    def test_defines_core_matching_decisions(self):
        variables = self.document["variables"]
        for name in (
            "available_trigger_entities",
            "activation_entities",
            "deactivation_entities",
            "active_target_entities",
            "effective_target_state_tracking",
            "trigger_source_allows_activation",
        ):
            self.assertIn(name, variables)
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
python3 -m unittest tests.test_state_based_entity_control.RuntimeStructureTests -v
```

Expected: failures because the v1 runtime still uses singular legacy keys and
does not define the v2 decisions.

- [ ] **Step 3: Replace legacy runtime variables with normalized v2 variables**

Expose every input used by a template, normalize list inputs, and calculate
duration seconds explicitly. Use list-valued selectors directly rather than
comma splitting. The core of the new `variables` block must follow this shape:

```yaml
variables:
  trigger_entities: !input trigger_entities
  target_entities: !input target_entities
  configured_off_target_entities: !input off_target_entities
  off_target_entities: >-
    {{ configured_off_target_entities
       if configured_off_target_entities | count > 0 else target_entities }}
  activation_state_pattern: !input activation_state_pattern
  deactivation_state_pattern: !input deactivation_state_pattern
  target_state_tracking: !input target_state_tracking
  target_state_pattern: !input target_state_pattern
  available_trigger_entities: >-
    {{ trigger_entities | reject('is_state', 'unknown')
       | reject('is_state', 'unavailable') | list }}
  activation_entities: >-
    {% set ns = namespace(value=[]) %}
    {% for entity_id in available_trigger_entities %}
      {% if states(entity_id) | regex_match(
          '^(' ~ activation_state_pattern ~ ')$', ignorecase=true) %}
        {% set ns.value = ns.value + [entity_id] %}
      {% endif %}
    {% endfor %}
    {{ ns.value }}
  deactivation_entities: >-
    {% set ns = namespace(value=[]) %}
    {% if deactivation_state_pattern | trim %}
      {% for entity_id in available_trigger_entities %}
        {% if states(entity_id) | regex_match(
            '^(' ~ deactivation_state_pattern ~ ')$', ignorecase=true) %}
          {% set ns.value = ns.value + [entity_id] %}
        {% endif %}
      {% endfor %}
    {% elif activation_entities | count == 0 %}
      {% set ns.value = available_trigger_entities %}
    {% endif %}
    {{ ns.value }}
  active_target_entities: >-
    {% set ns = namespace(value=[]) %}
    {% for entity_id in target_entities %}
      {% if states(entity_id) | regex_match(
          '^(' ~ target_state_pattern ~ ')$', ignorecase=true) %}
        {% set ns.value = ns.value + [entity_id] %}
      {% endif %}
    {% endfor %}
    {{ ns.value }}
  effective_target_state_tracking: >-
    {% set ns = namespace(transient=false) %}
    {% for entity_id in target_entities %}
      {% if entity_id.split('.')[0] in ['scene', 'script'] %}
        {% set ns.transient = true %}
      {% endif %}
    {% endfor %}
    {{ target_state_tracking and not ns.transient }}
  trigger_source_allows_activation: >-
    {{ trigger is not defined or trigger.id != 'target_state_stable' }}
```

- [ ] **Step 4: Replace triggers and the availability condition with modern syntax**

Use these trigger IDs and input references:

```yaml
triggers:
  - trigger: event
    event_type: automation_reloaded
    id: automation_reloaded
  - trigger: homeassistant
    event: start
    id: home_assistant_started
  - trigger: state
    entity_id: !input trigger_entities
    id: trigger_entity_changed
  - trigger: state
    entity_id: !input target_entities
    for: {seconds: 3}
    id: target_state_stable
  - trigger: state
    entity_id: !input target_entities
    for: !input manual_off_duration
    id: manual_lockout_expired

conditions:
  - alias: At least one trigger entity is available
    condition: template
    value_template: "{{ available_trigger_entities | count > 0 }}"
```

Set `mode: restart` and `max_exceeded: silent` at the document root.

- [ ] **Step 5: Run all tests and commit**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: seven tests pass.

```bash
git add blueprints/v2/state_based_entity_control.yaml tests/test_state_based_entity_control.py
git commit -m "feat: normalize state control runtime"
```

### Task 3: Add light gates, blockers, and manual-off lockout

**Files:**
- Modify: `tests/test_state_based_entity_control.py`
- Modify: `blueprints/v2/state_based_entity_control.yaml`

- [ ] **Step 1: Add failing tests for gate variables and lockout wiring**

Add these methods to `RuntimeStructureTests`:

```python
    def test_defines_environment_and_blocker_decisions(self):
        variables = self.document["variables"]
        for name in (
            "illuminance_gate_passed",
            "sun_gate_passed",
            "light_gates_passed",
            "activation_blocked",
            "deactivation_blocked",
        ):
            self.assertIn(name, variables)

    def test_manual_lockout_is_a_timestamp_based_gate(self):
        template = self.document["variables"]["manual_off_lockout_active"]
        self.assertIn("last_changed", template)
        self.assertIn("manual_off_duration_seconds", template)
        self.assertIn("manual_off_state_pattern", template)
```

- [ ] **Step 2: Run the gate tests and verify they fail**

Run:

```bash
python3 -m unittest \
  tests.test_state_based_entity_control.RuntimeStructureTests.test_defines_environment_and_blocker_decisions \
  tests.test_state_based_entity_control.RuntimeStructureTests.test_manual_lockout_is_a_timestamp_based_gate -v
```

Expected: errors for missing variables.

- [ ] **Step 3: Add light-gate variables with explicit unavailable handling**

Expose the light inputs and implement these decisions. Use float conversions
with impossible defaults so a configured but invalid sensor fails closed:

```yaml
  illuminance_enabled: !input illuminance_enabled
  illuminance_sensor: !input illuminance_sensor
  illuminance_threshold: !input illuminance_threshold
  sun_enabled: !input sun_enabled
  sun_elevation_threshold: !input sun_elevation_threshold
  light_gate_mode: !input light_gate_mode
  illuminance_gate_passed: >-
    {{ not illuminance_enabled or
       (illuminance_sensor != '' and
        states(illuminance_sensor) not in ['unknown', 'unavailable'] and
        states(illuminance_sensor) | float(100001) <=
          illuminance_threshold | float) }}
  sun_gate_passed: >-
    {{ not sun_enabled or
       (state_attr('sun.sun', 'elevation') is not none and
        state_attr('sun.sun', 'elevation') | float(91) <=
          sun_elevation_threshold | float) }}
  light_gates_passed: >-
    {% if illuminance_enabled and sun_enabled %}
      {{ (illuminance_gate_passed or sun_gate_passed)
         if light_gate_mode == 'any'
         else (illuminance_gate_passed and sun_gate_passed) }}
    {% elif illuminance_enabled %}
      {{ illuminance_gate_passed }}
    {% elif sun_enabled %}
      {{ sun_gate_passed }}
    {% else %}
      {{ true }}
    {% endif %}
```

- [ ] **Step 4: Add blocker and lockout variables**

Expose both blocker inputs. A missing entity or empty pattern disables its
blocker. Calculate the manual duration from the selector mapping and detect a
recent matching target using `last_changed`:

```yaml
  activation_blocked: >-
    {{ activation_blocker_entity != '' and
       activation_blocker_state_pattern | trim != '' and
       states(activation_blocker_entity) | regex_match(
         '^(' ~ activation_blocker_state_pattern ~ ')$', ignorecase=true) }}
  deactivation_blocked: >-
    {{ deactivation_blocker_entity != '' and
       deactivation_blocker_state_pattern | trim != '' and
       states(deactivation_blocker_entity) | regex_match(
         '^(' ~ deactivation_blocker_state_pattern ~ ')$', ignorecase=true) }}
  manual_off_duration_seconds: >-
    {{ (manual_off_duration.days | default(0) | int * 86400) +
       (manual_off_duration.hours | default(0) | int * 3600) +
       (manual_off_duration.minutes | default(0) | int * 60) +
       (manual_off_duration.seconds | default(0) | int) }}
  manual_off_lockout_active: >-
    {% set ns = namespace(active=false) %}
    {% if manual_off_enabled and manual_off_duration_seconds | int > 0 %}
      {% for entity_id in target_entities %}
        {% if states(entity_id) | regex_match(
            '^(' ~ manual_off_state_pattern ~ ')$', ignorecase=true)
            and as_timestamp(now()) - as_timestamp(states[entity_id].last_changed)
              < manual_off_duration_seconds | int %}
          {% set ns.active = true %}
        {% endif %}
      {% endfor %}
    {% endif %}
    {{ ns.active }}
```

- [ ] **Step 5: Run all tests and commit**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: nine tests pass.

```bash
git add blueprints/v2/state_based_entity_control.yaml tests/test_state_based_entity_control.py
git commit -m "feat: add activation gates and manual lockout"
```

### Task 4: Implement UI time windows and unlimited advanced ranges

**Files:**
- Modify: `tests/test_state_based_entity_control.py`
- Modify: `blueprints/v2/state_based_entity_control.yaml`

- [ ] **Step 1: Add failing schedule and timeout contract tests**

Add these methods to `RuntimeStructureTests`:

```python
    def test_builds_three_native_window_records(self):
        variables = self.document["variables"]
        self.assertEqual(len(variables["native_execution_windows"]), 3)
        self.assertEqual(len(variables["native_timeout_windows"]), 3)
        for window in variables["native_timeout_windows"]:
            self.assertEqual(set(window), {"enabled", "start", "end", "duration"})

    def test_defines_validated_schedule_and_timeout_decisions(self):
        variables = self.document["variables"]
        for name in (
            "advanced_ranges_valid",
            "execution_window_configured",
            "execution_allowed",
            "resolved_timeout_seconds",
        ):
            self.assertIn(name, variables)
        self.assertIn("first", variables["resolved_timeout_seconds"])
```

- [ ] **Step 2: Run the schedule tests and verify they fail**

Run:

```bash
python3 -m unittest \
  tests.test_state_based_entity_control.RuntimeStructureTests.test_builds_three_native_window_records \
  tests.test_state_based_entity_control.RuntimeStructureTests.test_defines_validated_schedule_and_timeout_decisions -v
```

Expected: errors for missing variables.

- [ ] **Step 3: Build native execution and timeout records**

Expose the schedule, advanced strings, and all slot inputs. Build exactly three
records of each kind so later templates use one generic loop:

```yaml
  native_execution_windows:
    - enabled: !input execution_window_1_enabled
      start: !input execution_window_1_start
      end: !input execution_window_1_end
    - enabled: !input execution_window_2_enabled
      start: !input execution_window_2_start
      end: !input execution_window_2_end
    - enabled: !input execution_window_3_enabled
      start: !input execution_window_3_start
      end: !input execution_window_3_end
  native_timeout_windows:
    - enabled: !input alternate_timeout_1_enabled
      start: !input alternate_timeout_1_start
      end: !input alternate_timeout_1_end
      duration: !input alternate_timeout_1_duration
    - enabled: !input alternate_timeout_2_enabled
      start: !input alternate_timeout_2_start
      end: !input alternate_timeout_2_end
      duration: !input alternate_timeout_2_duration
    - enabled: !input alternate_timeout_3_enabled
      start: !input alternate_timeout_3_start
      end: !input alternate_timeout_3_end
      duration: !input alternate_timeout_3_duration
```

- [ ] **Step 4: Add range validation and execution-window evaluation**

Validate advanced execution entries as `start-end` and alternate entries as
`start-end,duration`. Accept one- or two-digit hours to preserve v1 input and
accept either integer seconds or `H:MM:SS` durations. Use anchored patterns:

```yaml
  time_pattern: '(?:[01]?\\d|2[0-3]):[0-5]\\d:[0-5]\\d'
  duration_pattern: '(?:\\d+|(?:\\d+):[0-5]\\d:[0-5]\\d)'
  advanced_ranges_valid: >-
    {% set ns = namespace(valid=true) %}
    {% for value in (advanced_execution_ranges | replace(' ', '')).split(';')
       if value %}
      {% if not value | regex_match(
          '^' ~ time_pattern ~ '-' ~ time_pattern ~ '$') %}
        {% set ns.valid = false %}
      {% endif %}
    {% endfor %}
    {% for value in (advanced_alternate_timeouts | replace(' ', '')).split(';')
       if value %}
      {% if not value | regex_match(
          '^' ~ time_pattern ~ '-' ~ time_pattern ~ ',' ~ duration_pattern ~ '$') %}
        {% set ns.valid = false %}
      {% endif %}
    {% endfor %}
    {{ ns.valid }}
```

Add the execution decision using `today_at()` so one-digit advanced hours are
normalized before comparison:

```yaml
  execution_schedule: !input execution_schedule
  advanced_execution_ranges: !input advanced_execution_ranges
  advanced_alternate_timeouts: !input advanced_alternate_timeouts
  execution_window_configured: >-
    {% set ns = namespace(configured=execution_schedule != '') %}
    {% for window in native_execution_windows %}
      {% if window.enabled %}
        {% set ns.configured = true %}
      {% endif %}
    {% endfor %}
    {{ ns.configured or advanced_execution_ranges | trim != '' }}
  execution_allowed: >-
    {% set ns = namespace(matched=false) %}
    {% set current = now() %}
    {% if execution_schedule != '' and is_state(execution_schedule, 'on') %}
      {% set ns.matched = true %}
    {% endif %}
    {% for window in native_execution_windows if window.enabled %}
      {% set start = today_at(window.start) %}
      {% set end = today_at(window.end) %}
      {% if start == end or
            (start < end and start <= current <= end) or
            (start > end and (current >= start or current <= end)) %}
        {% set ns.matched = true %}
      {% endif %}
    {% endfor %}
    {% for value in (advanced_execution_ranges | replace(' ', '')).split(';')
       if value %}
      {% set times = value.split('-') %}
      {% set start = today_at(times[0]) %}
      {% set end = today_at(times[1]) %}
      {% if start == end or
            (start < end and start <= current <= end) or
            (start > end and (current >= start or current <= end)) %}
        {% set ns.matched = true %}
      {% endif %}
    {% endfor %}
    {{ not execution_window_configured or ns.matched }}
```

- [ ] **Step 5: Resolve the first matching timeout as seconds**

Expose `main_timeout` and resolve the first matching duration with this exact
priority algorithm:

```yaml
  main_timeout: !input main_timeout
  resolved_timeout_seconds: >-
    {% set ns = namespace(first=none) %}
    {% set current = now() %}
    {% for window in native_timeout_windows
       if window.enabled and ns.first is none %}
      {% set start = today_at(window.start) %}
      {% set end = today_at(window.end) %}
      {% if start == end or
            (start < end and start <= current <= end) or
            (start > end and (current >= start or current <= end)) %}
        {% set duration = window.duration %}
        {% set ns.first =
          duration.days | default(0) | int * 86400 +
          duration.hours | default(0) | int * 3600 +
          duration.minutes | default(0) | int * 60 +
          duration.seconds | default(0) | int %}
      {% endif %}
    {% endfor %}
    {% for value in
       (advanced_alternate_timeouts | replace(' ', '')).split(';')
       if value and ns.first is none %}
      {% set pair = value.split(',') %}
      {% set times = pair[0].split('-') %}
      {% set start = today_at(times[0]) %}
      {% set end = today_at(times[1]) %}
      {% if start == end or
            (start < end and start <= current <= end) or
            (start > end and (current >= start or current <= end)) %}
        {% if pair[1] | regex_match('^\\d+$') %}
          {% set ns.first = pair[1] | int %}
        {% else %}
          {% set parts = pair[1].split(':') | map('int') | list %}
          {% set ns.first = parts[0] * 3600 + parts[1] * 60 + parts[2] %}
        {% endif %}
      {% endif %}
    {% endfor %}
    {% if ns.first is not none %}
      {{ ns.first }}
    {% else %}
      {{ main_timeout.days | default(0) | int * 86400 +
         main_timeout.hours | default(0) | int * 3600 +
         main_timeout.minutes | default(0) | int * 60 +
         main_timeout.seconds | default(0) | int }}
    {% endif %}
```

- [ ] **Step 6: Stop malformed runs before choosing an action**

Start the root action list with:

```yaml
actions:
  - alias: Validate advanced time ranges
    if:
      - condition: template
        value_template: "{{ not advanced_ranges_valid }}"
    then:
      - stop: >-
          Advanced execution ranges or alternate timeouts contain an invalid
          value. Use H:MM:SS-H:MM:SS and H:MM:SS-H:MM:SS,duration entries.
        error: true
```

- [ ] **Step 7: Run all tests and commit**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: eleven tests pass.

```bash
git add blueprints/v2/state_based_entity_control.yaml tests/test_state_based_entity_control.py
git commit -m "feat: add UI schedules and alternate timeouts"
```

### Task 5: Implement traced activation and revalidated deactivation actions

**Files:**
- Modify: `tests/test_state_based_entity_control.py`
- Modify: `blueprints/v2/state_based_entity_control.yaml`

- [ ] **Step 1: Add failing action-flow contract tests**

Add these methods to `RuntimeStructureTests`:

```python
    def test_action_flow_has_traceable_branches(self):
        aliases = self.yaml_text
        for alias in (
            "Execution window allows this run",
            "Manual-off lockout is inactive",
            "Activation conditions match",
            "Wait before deactivation",
            "Revalidate after deactivation delay",
            "Run activation actions",
            "Run deactivation actions",
        ):
            self.assertIn(f"alias: {alias}", aliases)

    def test_custom_actions_and_default_fallbacks_are_wired(self):
        self.assertIn("sequence: !input activation_actions", self.yaml_text)
        self.assertIn("sequence: !input deactivation_actions", self.yaml_text)
        self.assertIn("action: homeassistant.turn_on", self.yaml_text)
        self.assertIn("action: homeassistant.turn_off", self.yaml_text)

    def test_off_branch_rechecks_volatile_conditions_after_delay(self):
        marker = "alias: Revalidate after deactivation delay"
        tail = self.yaml_text.split(marker, 1)[1]
        for decision in (
            "execution_allowed",
            "available_trigger_entities",
            "deactivation_entities",
            "manual_off_lockout_active",
            "deactivation_blocked",
            "active_target_entities",
        ):
            self.assertIn(decision, tail)
```

- [ ] **Step 2: Run the action-flow tests and verify they fail**

Run:

```bash
python3 -m unittest \
  tests.test_state_based_entity_control.RuntimeStructureTests.test_action_flow_has_traceable_branches \
  tests.test_state_based_entity_control.RuntimeStructureTests.test_custom_actions_and_default_fallbacks_are_wired \
  tests.test_state_based_entity_control.RuntimeStructureTests.test_off_branch_rechecks_volatile_conditions_after_delay -v
```

Expected: failures because the v2 branches are not complete.

- [ ] **Step 3: Add common gates and the activation branch**

After advanced validation, stop outside an execution window with a trace-visible
alias, then stop while manual lockout is active. Add a `choose` activation branch
whose aliased template conditions require activation entities, passing light
gates, no activation blocker, target inactive unless tracking is disabled, and
an allowed trigger source. Treat `manual_lockout_expired` as an allowed source
even if another target in a multi-target selection is already active.

The activation sequence logs conditionally, then selects custom or fallback
actions:

```yaml
  - alias: Run activation actions
    choose:
      - conditions:
          - condition: template
            value_template: "{{ activation_actions | count > 0 }}"
        sequence: !input activation_actions
    default:
      - action: homeassistant.turn_on
        target:
          entity_id: !input target_entities
```

Expose `activation_actions`, `deactivation_actions`, and `logbook_enabled` as
variables. When logging is enabled, call `logbook.log` using modern `action`,
`data`, and a friendly-name list resolved from the target entities.

- [ ] **Step 4: Add the delayed deactivation branch and post-delay checks**

The second `choose` branch requires deactivation entities, no deactivation
blocker, and either disabled target tracking or at least one active target. Log
the selected timeout when enabled, delay with:

```yaml
      - alias: Wait before deactivation
        delay:
          seconds: "{{ resolved_timeout_seconds | int(0) }}"
```

After the delay, add individual aliased template conditions for
`execution_allowed`, nonempty `available_trigger_entities`, nonempty
`deactivation_entities`, inactive `manual_off_lockout_active`, false
`deactivation_blocked`, and the target-state tracking rule. Then run:

```yaml
      - alias: Run deactivation actions
        choose:
          - conditions:
              - condition: template
                value_template: "{{ deactivation_actions | count > 0 }}"
            sequence: !input deactivation_actions
        default:
          - action: homeassistant.turn_off
            target:
              entity_id: "{{ off_target_entities }}"
```

- [ ] **Step 5: Run all tests and commit**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: fourteen tests pass.

```bash
git add blueprints/v2/state_based_entity_control.yaml tests/test_state_based_entity_control.py
git commit -m "feat: add traced state control actions"
```

### Task 6: Validate blueprint expansion in Home Assistant 2026.7

**Files:**
- Create: `tests/validate_state_based_entity_control.sh`
- Modify: `tests/test_state_based_entity_control.py`

- [ ] **Step 1: Add a failing test for the validation script contract**

Add this class:

```python
class ValidationScriptTests(unittest.TestCase):
    def test_validation_script_pins_supported_home_assistant(self):
        script = (ROOT / "tests" / "validate_state_based_entity_control.sh").read_text()
        self.assertIn("home-assistant:2026.7.2", script)
        self.assertIn("--script check_config", script)
        self.assertIn("use_blueprint", script)
```

- [ ] **Step 2: Run the test and verify it fails because the script is absent**

Run:

```bash
python3 -m unittest \
  tests.test_state_based_entity_control.ValidationScriptTests -v
```

Expected: `FileNotFoundError` for the validation script.

- [ ] **Step 3: Create the isolated Home Assistant validation script**

Create executable `tests/validate_state_based_entity_control.sh` with this
content:

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
default_config:
automation: !include automations.yaml
input_boolean:
  validation_trigger:
  validation_target:
YAML

cat >"${config_dir}/automations.yaml" <<'YAML'
- alias: State control blueprint validation
  use_blueprint:
    path: local/state_based_entity_control.yaml
    input:
      trigger_entities:
        - input_boolean.validation_trigger
      target_entities:
        - input_boolean.validation_target
YAML

docker run --rm \
  -v "${config_dir}:/config" \
  ghcr.io/home-assistant/home-assistant:2026.7.2 \
  python -m homeassistant --script check_config --config /config
```

Mark it executable with `chmod +x tests/validate_state_based_entity_control.sh`.

- [ ] **Step 4: Run fast tests, then authoritative validation**

Run:

```bash
python3 -m unittest discover -s tests -v
tests/validate_state_based_entity_control.sh
```

Expected: fifteen unit tests pass, and Home Assistant ends with
`Configuration valid!` without blueprint selector, schema, or template errors.
If the container reports a schema error, correct the blueprint syntax and add a
unit assertion that would catch that exact regression before rerunning both
commands.

- [ ] **Step 5: Commit integration validation**

```bash
git add blueprints/v2/state_based_entity_control.yaml tests/test_state_based_entity_control.py tests/validate_state_based_entity_control.sh
git commit -m "test: validate blueprint with Home Assistant 2026.7"
```

### Task 7: Complete regression review and handoff

**Files:**
- Modify: `blueprints/v2/state_based_entity_control.yaml` only if verification exposes an issue
- Modify: `tests/test_state_based_entity_control.py` only when adding a regression assertion

- [ ] **Step 1: Compare implemented inputs against every approved capability**

Run:

```bash
rg -n '^## |^- Preserve|^- Add|^- Home Assistant|^- No version' \
  docs/superpowers/specs/2026-07-11-state-based-entity-control-v2-design.md
rg -n 'name:|alias:' blueprints/v2/state_based_entity_control.yaml
```

Expected: each preserved feature and acceptance criterion maps to an input,
decision variable, trigger, condition alias, action branch, or test. Add a
specific assertion before fixing any uncovered gap.

- [ ] **Step 2: Run formatting and placeholder checks**

Run:

```bash
git diff --check
rg -n 'TBD|FIXME|PLACEHOLDER|turnning|triggerring|illuminace|mintues' \
  blueprints tests
```

Expected: both commands produce no findings.

- [ ] **Step 3: Run the complete verification suite from a clean process**

Run:

```bash
python3 -m unittest discover -s tests -v
tests/validate_state_based_entity_control.sh
git status --short
```

Expected: all unit tests pass, Home Assistant reports `Configuration valid!`,
and status shows only intentional implementation changes if a final regression
fix has not yet been committed.

- [ ] **Step 4: Commit any final regression correction**

If Step 3 required a correction, commit only the blueprint and its regression
test:

```bash
git add blueprints/v2/state_based_entity_control.yaml tests/test_state_based_entity_control.py
git commit -m "fix: complete state control v2 regression coverage"
```

If no correction was needed, do not create an empty commit.

- [ ] **Step 5: Record final evidence for handoff**

Capture the unit-test count, Home Assistant image version, configuration-check
result, and final `git status --short` in the implementation handoff. Do not
claim completion unless both verification commands were run successfully in
this task.
