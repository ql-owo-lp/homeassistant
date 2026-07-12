# State Based Entity Control v2

State Based Entity Control v2 coordinates one or more entities from the states
of one or more trigger entities. It can turn targets on immediately, turn them
off after a delay, limit execution by light level or time, honor blockers, and
avoid undoing a manual off command for a configurable interval. Configuration
is designed for Home Assistant's automation UI; the advanced text fields are
optional.

The original v1 blueprint remains at
`blueprints/state_based_entity_control.yaml`. Importing or using v2 does not
replace existing v1 automations.

## Requirements

- Home Assistant 2026.7.0 or newer (Home Assistant 2026.7).
- At least one trigger entity and one target entity.
- Trigger and target entities whose states express the behavior you want to
  match. State patterns are case-insensitive regular expressions matched
  against the entire state.

To install from this repository, open **Settings > Automations & scenes >
Blueprints**, select **Import blueprint**, and enter
`https://raw.githubusercontent.com/ql-owo-lp/homeassistant/main/blueprints/v2/state_based_entity_control.yaml`.
Alternatively, copy `blueprints/v2/state_based_entity_control.yaml` to
`<config>/blueprints/automation/<namespace>/`, then reload automations.
Create an automation with **Settings > Automations & scenes > Create
automation > Use blueprint** and select **State Based Entity Control v2**.

## Quick start

For a motion-controlled light:

1. Create an automation from **State Based Entity Control v2**.
2. In **Core entities and timeout**, choose the motion binary sensor as
   **Trigger entities** and the light as **Target entities**.
3. Leave **Off target entities** empty and set **Main timeout** to the desired
   no-motion delay. Its default is 30 seconds.
4. Leave **Activation state pattern** at `on` and **Deactivation state
   pattern** empty. Motion `on` activates the light; any available trigger state
   that does not match `on` requests deactivation.
5. Leave both custom action editors empty so the blueprint uses
   `homeassistant.turn_on` and `homeassistant.turn_off` for the selected light.
6. Save the automation, walk in front of the sensor, and inspect the automation
   trace if the light does not respond.

An activation occurs when at least one available trigger matches. A pending
deactivation is cancelled and reevaluated whenever another relevant state
change restarts the automation.

## UI configuration reference

### Core entities and timeout

- **Trigger entities** has no default and accepts multiple entities. Every
  state change reevaluates the automation. Triggers in `unknown` or
  `unavailable` are ignored; the run stops if none remain available.
- **Target entities** has no default and accepts multiple entities. These are
  used by the default activation action and for target-state tracking.
- **Off target entities** defaults to an empty list. When empty, the target
  entities are also the default deactivation targets. Select a different list
  when activation and deactivation must address different entities.
- **Main timeout** defaults to 30 seconds (`0` hours, `0` minutes, `30`
  seconds). It is the deactivation delay when no alternate timeout matches.

### State matching

- **Activation state pattern** defaults to `on`. It is a case-insensitive,
  full-state regular expression; partial matches such as `onward` do not match
  `on`.
- **Deactivation state pattern** defaults to empty. When it is empty,
  deactivation uses inverse semantics: deactivation is requested only when no
  available trigger matches the activation pattern. When it is non-empty, any
  available trigger matching this explicit, case-insensitive full-state regex
  requests deactivation. The activation branch has priority if both branches
  qualify.
- **Track target state** defaults to enabled. The blueprint compares targets
  with **Target state pattern**, avoids redundant activation when any target is
  already desired, and avoids redundant deactivation when no target is desired.
  Target changes also cause reevaluation. Disable tracking for intentionally
  stateless behavior; it is disabled automatically if any target is a scene or
  script.
- **Target state pattern** defaults to `on` and uses the same case-insensitive,
  full-state regex rules.

Useful state-pattern examples:

```text
Activation pattern: on|playing|home
Explicit deactivation pattern: off|idle|not_home
```

Because these are regular expressions, escape punctuation when it should be
literal. Home Assistant reports an invalid regex during template execution;
test complex patterns in **Developer tools > Template** before relying on them.

### Actions

- **Activation actions** defaults to an empty action sequence.
- **Deactivation actions** defaults to an empty action sequence.

When empty, the blueprint calls `homeassistant.turn_on` for **Target entities**
and `homeassistant.turn_off` for the resolved **Off target entities**. When a
custom sequence is present, the sequence completely replaces that fallback.
Custom sequences own their targets: select targets inside every service or
device action in the action editor. The blueprint does not inject the core
target lists into custom actions.

Custom actions can contain normal UI actions, conditions, delays, scenes, or
scripts. The resolved deactivation timeout still happens before a custom
deactivation sequence; timeout resolution follows the priority described under
**Alternate timeouts**.

### Light conditions

These settings gate activation only. They do not prevent deactivation.

- **Enable illuminance gate** defaults to off.
- **Illuminance sensor** defaults to empty and accepts an illuminance sensor.
- **Illuminance threshold** defaults to `100 lx` (allowed range `0` to
  `100000 lx`). Activation passes at or below the threshold. A missing,
  `unknown`, `unavailable`, or nonnumeric enabled sensor fails closed.
- **Enable sun elevation gate** defaults to off.
- **Sun elevation threshold** defaults to `0°` (allowed range `-90°` to
  `90°`). Activation passes when `sun.sun` elevation is at or below it. Missing
  or nonnumeric elevation fails closed.
- **Light gate mode** defaults to `any`. With both gates enabled, `any` allows
  activation when either passes; `all` requires both. With one enabled, that
  gate must pass. With neither enabled, light conditions pass.

Illuminance and sun changes are environmental gates, not triggers. A trigger
entity must change (or another blueprint trigger must occur) before a newly
passing light condition is evaluated.

### Blocking

- **Activation blocker entity** defaults to empty. If selected and its state
  matches **Activation blocker state pattern**, activation is prevented.
- **Activation blocker state pattern** defaults to `on`.
- **Deactivation blocker entity** defaults to empty. If selected and its state
  matches **Deactivation blocker state pattern**, deactivation is prevented,
  including when revalidated after the timeout.
- **Deactivation blocker state pattern** defaults to `on`.

Blocker patterns are case-insensitive full-state regular expressions. A blank
entity or blank pattern disables that blocker. Blocker changes are gates and do
not independently trigger a run.

### Manual-off handling

- **Enable manual off handling** defaults to off.
- **Manual off duration** defaults to 30 minutes.
- **Manual off state pattern** defaults to `off` and is a case-insensitive,
  full-state regular expression.

When enabled, a target currently matching the manual-off pattern is held off
until the configured interval since its `last_changed` time has elapsed.
Changes during the lockout restart the automation's wait, but the remaining
time is recalculated rather than extending the original interval. At expiry,
the latest trigger state and all gates are reevaluated.

```text
T+0.0  Target is manually turned off; lockout begins.
T+0.5  Trigger changes; the target remains off.
T+N    Lockout expires; current trigger state is reevaluated.
```

This setting is the explicit way to preserve manual control while an activating
trigger remains active. Target-state tracking also suppresses unnecessary
service calls, but it is not a substitute for a timed manual-off policy.

### Execution windows

- **Execution schedule** defaults to empty and accepts one `schedule` helper.
- **Enable daily window 1**, **2**, and **3** each default to off.
- Every daily window start and end defaults to `00:00:00`.

Use the three UI time-picker ranges for common daily schedules. A start earlier
than its end is a same-day interval, a start later than its end crosses
midnight, and equal endpoints mean all day. Boundaries are inclusive.

If no schedule, enabled UI window, or advanced execution range is configured,
execution is always allowed. Once any is configured, the sources use OR
semantics: the schedule helper being `on`, any enabled UI window matching, or
any advanced execution range matching allows the run. Execution windows gate
both activation and deactivation and are checked again after a deactivation
delay. Schedule state changes do not independently trigger the automation.

```text
Same-day range: 09:00:00-17:00:00
Overnight range: 22:00:00-02:00:00
All-day range: 00:00:00-00:00:00
```

### Alternate timeouts

- **Enable alternate timeout 1**, **2**, and **3** each default to off.
- Every alternate timeout start and end defaults to `00:00:00`.
- Every alternate timeout duration defaults to 30 seconds.

Each enabled UI slot selects a different deactivation delay during its daily
range. Same-day, overnight, all-day, and inclusive-boundary rules match the
execution windows. If ranges overlap, resolution stops at the first match in
this exact order: `native slots → advanced ranges → main timeout`. Native slots
are checked 1, then 2, then 3; advanced entries are checked from left to right.

### Advanced ranges

Both advanced fields default to empty. They provide unlimited extra daily
ranges beyond the three UI slots. Whitespace is ignored, entries are separated
by semicolons, hours may have one or two digits, and times must include minutes
and seconds. Decimal seconds are supported. Equal endpoints mean all day and a
start later than its end crosses midnight.

**Advanced execution ranges** use unlimited `start-end` entries:

```yaml
09:00:00-17:00:00; 22:00:00-02:00:00; 00:00:00-00:00:00
```

**Advanced alternate timeouts** use unlimited `start-end,duration` entries.
Duration is either numeric seconds or an hours/minutes/seconds value, with
optional decimal seconds:

```yaml
Alternate timeout: 17:00:00-19:30:00,30
Decimal timeout: 19:30:00-20:00:00,0:00:07.5
```

A malformed nonempty entry stops the run with an error; it is not silently
skipped. Advanced timeout entries are considered only after all three native
timeout slots and before the main timeout.

### Diagnostics

- **Enable logbook diagnostics** defaults to on.

When enabled, the blueprint records pending deactivation, activation, and
deactivation decisions in the Home Assistant logbook. Disable it to reduce
logbook noise. For deeper inspection, open the automation and select **Traces**:
branch aliases show time-range validation, lockout waiting, gate decisions,
the deactivation delay, post-delay revalidation, and the action selected.

## Scenes and scripts

Scenes and scripts are stateless or do not reliably express the target state
that their action produced. If any **Target entity** is in the `scene` or
`script` domain, target-state tracking is automatically disabled for the whole
target list, so qualifying runs can invoke the configured action again.

The default activation fallback can turn on a scene or script. Many scenes have
no meaningful off action, so configure **Off target entities** with the lights
or switches that should be turned off, or supply a custom deactivation
sequence. Remember that a custom sequence must select its own targets; **Off
target entities** is applied automatically only by the empty-action fallback.

Separate off targets are also useful when activation calls a scene while
deactivation should address a group, or when a script's cleanup entities differ
from its activation entities.

## Troubleshooting

- **Nothing runs:** confirm at least one trigger is not `unknown` or
  `unavailable`. Unavailable triggers are excluded, and a run stops when all
  configured triggers are unavailable. Confirm the automation is enabled and
  inspect its trace.
- **A state pattern never matches or the trace reports a template error:**
  patterns match the entire state, case-insensitively. Correct an invalid regex
  in Developer tools before saving it to the blueprint.
- **The trace stops at advanced validation:** fix the named malformed range.
  Execution entries require `start-end`; timeout entries require
  `start-end,duration`; entries are semicolon-separated. One malformed entry
  invalidates both advanced fields for that run.
- **Changing lux, sun elevation, a blocker, or a schedule does nothing:** these
  environmental values are gates and do not trigger independently. Cause a
  configured trigger entity to change or run/reload the automation to
  reevaluate them.
- **A target turns off despite a new activating state:** the deactivation delay
  is revalidated, so inspect the trace for which triggers remained available,
  which regex matched, whether the execution window still allowed the run, and
  whether target tracking considered deactivation relevant.
- **A manual off is immediately undone:** enable manual-off handling, verify the
  manual state matches its pattern, and choose a nonzero duration. Check the
  trace's lockout aliases and the target's `last_changed` value.
- **A custom action affects no entity:** custom sequences own their targets.
  Add a target to each relevant action in the UI editor, or clear the sequence
  to restore the blueprint's `homeassistant.turn_on`/`homeassistant.turn_off`
  fallback.

Known constraints: only three execution windows and three alternate-timeout
windows are directly available as UI slots; use advanced fields for additional
ranges. Regex compilation errors are surfaced by Home Assistant at template
execution. Gates are sampled only on a blueprint trigger. With target-state
tracking enabled for multiple stateful targets, any one matching target makes
activation appear satisfied and any one matching target makes deactivation
relevant; use custom actions or disable tracking if every target must be
reasserted on each qualifying run.

For evidence, enable logbook diagnostics temporarily and compare its entries
with the automation trace. Traces are the authoritative view of the branch,
conditions, delay, revalidation, and action sequence used by an individual run.

## Testing

From the repository root, run the fast unit and template suite, configuration
expansion validation, and real Home Assistant runtime scenarios:

```bash
python3 -m unittest discover -v
tests/validate_state_based_entity_control.sh
tests/validate_state_based_entity_control_runtime.sh
```

The validators use the pinned Home Assistant 2026.7.2 container. The runtime
validator exercises activation, delayed deactivation, manual-off lockout,
trigger changes during lockout, and lockout expiry against real Home Assistant
entities.
