# State Based Entity Control v2 Design

## Summary

Create `blueprints/v2/state_based_entity_control.yaml` as a version 2 Home
Assistant automation blueprint. Version 2 may change its input schema and will
require Home Assistant 2026.7.0 or newer, but it must retain every capability of
the current blueprint. Configuration must be available from Home Assistant's
blueprint UI. Native selectors should replace encoded values wherever the
blueprint schema supports them; advanced text inputs remain available where
Home Assistant cannot represent repeatable regex or paired range data.

## Goals

- Preserve arbitrary entity-state matching, including case-insensitive regular
  expressions.
- Preserve separate activation and deactivation targets and behavior.
- Preserve activation and timeout blockers, illuminance and solar-elevation
  gates, delayed deactivation, alternate timeouts, execution ranges, manual
  target control, and startup/reload evaluation.
- Add an optional manual-off lockout during which trigger state changes do not
  cause actions.
- Replace legacy automation syntax and service-only inputs with current Home
  Assistant syntax and UI-native selectors.
- Make behavior deterministic, traceable, and safe when entities or sensor
  values are unavailable.

## Non-goals

- Migrating existing automations instantiated from version 1.
- Eliminating advanced text fields at the cost of regex support or an unlimited
  number of time ranges.
- Turning illuminance, sun elevation, blockers, or schedule changes into
  independent activation triggers. They remain gates evaluated when the
  automation otherwise runs.
- Creating helper entities automatically.

## Compatibility

The blueprint declares `homeassistant.min_version: 2026.7.0`. It uses current
`triggers`, `conditions`, `actions`, and `action` syntax. Version 2 is a breaking
input-schema revision; users recreate or manually migrate automations created
from version 1.

## Blueprint UI

Inputs are grouped into sections. Optional and advanced sections are collapsed
by default, and every collapsed input has a default.

### Core control

- Trigger entity selection, supporting one or more entities.
- Target entity selection, supporting one or more entities.
- Optional separate deactivation target selection. When empty, it resolves to
  the activation targets.
- Main deactivation delay using a duration selector, defaulting to 30 seconds.

### State matching

- Activation state pattern, default `on`.
- Optional explicit deactivation state pattern. When empty, deactivation means
  that no available trigger matches the activation pattern.
- Desired target state pattern, default `on`.
- A target-state tracking toggle. Disabling it replaces version 1's magic
  `none` value and prevents the automation from turning off a target merely
  because it was activated manually.

Patterns are case-insensitive regular expressions and are implicitly anchored
to the entire entity state. They stay as UI text inputs because Home Assistant
cannot dynamically populate a state selector from another blueprint input and
a fixed state list would remove arbitrary-state support.

### Actions

- Optional activation sequence using the action selector.
- Optional deactivation sequence using the action selector.

An empty activation sequence runs `homeassistant.turn_on` against the selected
activation entities. An empty deactivation sequence runs
`homeassistant.turn_off` against the resolved deactivation entities. A custom
sequence runs exactly as authored and may target entities, devices, areas,
scenes, scripts, or arbitrary actions. The selected entities continue to drive
state tracking and log names even when a custom sequence is used.

### Light conditions

- Enable illuminance gate toggle, illuminance sensor selector, and threshold
  number selector measured in lux (`lx`).
- Enable solar-elevation gate toggle and threshold number selector measured in
  degrees.
- Combination selector with `any` and `all` choices when both gates are
  enabled. Its default is `any`, preserving version 1 behavior.

An enabled gate with an unavailable or non-numeric value does not permit
activation. With no enabled gate, activation is unrestricted by light level.

### Blocking

- Optional activation blocker and case-insensitive state pattern.
- Optional deactivation blocker and case-insensitive state pattern.

An entity blocks only when both the entity and a non-empty pattern are
configured and its current state fully matches that pattern. Deactivation
blockers are rechecked after the delay.

### Manual-off lockout

- Enable toggle, disabled by default.
- Duration selector.
- Manual-off state pattern, default `off`.

When a target enters a matching manual-off state while activation conditions
are present, its `last_changed` timestamp establishes a lockout. During the
lockout, trigger-driven activation and deactivation decisions are suppressed.
Trigger changes still start automation traces but produce no target action.
A stable-target-state trigger using the configured duration reevaluates the
automation at lockout expiry. If activation conditions still match, activation
may resume; otherwise the target remains off. This uses entity state timestamps
and does not require a timer helper.

An automation-driven deactivation does not cause unwanted reactivation: its
trigger entities are inactive, so the lockout-expiry evaluation cannot satisfy
activation conditions.

### Schedules and alternate timeouts

The common UI exposes three optional daily execution windows. Each has an
enable toggle and native start/end time selectors. Equal endpoints mean all
day, and a start later than its end means the range crosses midnight.

Users may alternatively select a Home Assistant `schedule` helper for weekly
or more complex execution windows. When both a helper and daily windows are
configured, being inside either source permits execution. Execution gating
applies to the complete automation, preserving version 1 behavior.

The common UI also exposes three optional alternate-timeout windows. Each has
an enable toggle, start selector, end selector, and duration selector. The first
matching enabled slot wins.

Advanced UI text inputs retain the version 1 formats for an unlimited number of
daily execution ranges and alternate timeout ranges. Whitespace is ignored.
Native UI alternate-timeout slots take priority, followed by advanced ranges in
input order, followed by the main timeout. Overlaps are allowed because
priority is deterministic. Advanced malformed entries stop that automation run
with a descriptive trace message rather than being ignored.

### Diagnostics

- Logbook toggle, enabled by default for version 1 parity.
- Entries identify the resolved target and whether an activation,
  deactivation wait, or deactivation action is occurring.
- Automation trace step aliases identify schedule, availability, light,
  blocker, target-state, manual-lockout, and timeout decisions.

## Runtime Model

Blueprint inputs are exposed as variables and normalized once. Entity inputs
become lists even when only one entity is selected. Optional inputs resolve to
empty lists, empty strings, or explicit booleans rather than relying on YAML
null coercion.

The automation remains in `restart` mode with silent maximum-exceeded handling.
It runs for:

- Home Assistant startup.
- `automation_reloaded` events.
- Any trigger-entity state change.
- Any target-entity state change that remains stable for three seconds.
- A target state remaining stable for the configured manual-off duration. This
  trigger is harmless when manual-off lockout is disabled or does not apply.

Illuminance, sun elevation, blockers, and schedule helpers do not independently
trigger a run. This prevents frequently changing values from perpetually
restarting a pending deactivation.

### Matching semantics

- An available trigger is one whose state is neither `unknown` nor
  `unavailable`.
- At least one trigger must be available or the run stops without target
  actions.
- Activation is present when any available trigger fully matches the activation
  pattern.
- If an explicit deactivation pattern exists, deactivation is present when any
  available trigger fully matches it.
- Without an explicit deactivation pattern, deactivation is present when no
  available trigger matches the activation pattern.
- A target is considered active when any tracked target fully matches the
  desired target pattern. This retains version 1's any-match behavior.
- Scene and script targets default to target-state tracking disabled because
  their transient states cannot reliably represent activation. Users can still
  provide custom actions and separate deactivation targets.

### Activation flow

1. Confirm the run is inside an execution window, if configured.
2. Confirm at least one trigger is available.
3. Suppress target actions when a manual-off lockout is active.
4. Require activation to be present.
5. Require the enabled light gates to pass using the selected `any`/`all` mode.
6. Require the activation blocker not to match.
7. Require target-state tracking to be disabled or no target to be active.
8. Preserve manual-off protection: a stable target-change trigger does not
   reactivate a target while the trigger remains active. Trigger-entity,
   startup, reload, and lockout-expiry evaluations may activate it.
9. Log when enabled, then run the custom or fallback activation action.

### Deactivation flow

1. Apply the common execution-window, availability, and manual-lockout gates.
2. Require deactivation to be present.
3. Require target-state tracking to be disabled or a target to be active.
4. Require the deactivation blocker not to match.
5. Resolve the timeout using native alternate slots, advanced alternate ranges,
   and then the main timeout.
6. Log the pending action when enabled and delay for the resolved timeout.
7. Re-evaluate execution window, trigger availability and state, manual-off
   lockout, deactivation blocker, and tracked target state.
8. If the conditions still pass, log and run the custom or fallback
   deactivation action.

A trigger-entity or target-entity change restarts the automation and therefore
cancels a stale delay. The explicit post-delay checks also protect against gate
changes that do not independently trigger the automation.

## Error Handling

- Unknown and unavailable trigger entities are excluded from matching.
- If all trigger entities are unavailable, the run stops without changing a
  target so manual control remains possible.
- Enabled light gates fail closed when their sensor values are missing or
  non-numeric.
- Optional blocker inputs with no state pattern are treated as disabled.
- Advanced range entries are validated for their field count, time format, and
  duration format before action selection. Invalid input stops the run with a
  trace-visible reason.
- Custom action failures use Home Assistant's normal action error behavior and
  appear in the automation trace.

## Verification

Verification must include YAML parsing with support for `!input`, current Home
Assistant blueprint/schema validation where available, and behavior-focused
tests or reproducible template evaluations for:

- Activation with default and regex state patterns.
- Explicit and inverse deactivation matching.
- Mixed available, unknown, and unavailable trigger entities.
- Target-state tracking enabled and disabled.
- Stable target changes and manual-off protection.
- Manual-off lockout activation, ignored trigger changes, expiry, and an
  inactive trigger at expiry.
- Activation and deactivation blockers, including a blocker change during the
  off delay.
- Illuminance-only, sun-only, `any`, `all`, and unavailable sensor cases.
- Same-day, overnight, equal-endpoint, schedule-helper, combined, overlapping,
  malformed, and unlimited advanced execution ranges.
- Alternate timeout priority and fallback to the main timeout.
- Restart cancellation and post-delay revalidation.
- Default actions, custom action sequences, scenes/scripts, and separate
  deactivation targets.
- Startup and automation-reload evaluation.
- Logbook enabled and disabled behavior.

## Acceptance Criteria

- Home Assistant 2026.7+ imports the blueprint and renders every input in the
  blueprint UI.
- No version 1 capability identified in this document is removed.
- Common configuration requires no encoded range syntax or direct YAML edits.
- Arbitrary regex states and unlimited ranges remain configurable through
  advanced fields in the UI.
- Manual-off lockout ignores trigger-driven actions for its configured duration
  and reevaluates when the duration expires.
- Automation traces make every skipped action and selected timeout explainable.
