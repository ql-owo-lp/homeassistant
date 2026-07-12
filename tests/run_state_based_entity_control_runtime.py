#!/usr/bin/env python3
import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import monotonic
import sys

from homeassistant import bootstrap
from homeassistant.const import (
    ATTR_DOMAIN,
    ATTR_ENTITY_ID,
    ATTR_SERVICE,
    ATTR_SERVICE_DATA,
    EVENT_CALL_SERVICE,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.runner import RuntimeConfig


class TargetActionRecorder:
    def __init__(self, hass: HomeAssistant, target_entity_id: str) -> None:
        self.target_entity_id = target_entity_id
        self.actions: list[tuple[float, str]] = []
        hass.bus.async_listen(EVENT_CALL_SERVICE, self._record_action)

    @callback
    def _record_action(self, event: Event) -> None:
        domain = event.data.get(ATTR_DOMAIN)
        service = event.data.get(ATTR_SERVICE)
        if domain != "homeassistant" or service not in {"turn_on", "turn_off"}:
            return
        service_data = event.data.get(ATTR_SERVICE_DATA, {})
        entity_ids = service_data.get(ATTR_ENTITY_ID, [])
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        if self.target_entity_id in entity_ids:
            self.actions.append((monotonic(), service))

    def clear(self) -> None:
        self.actions.clear()

    async def assert_no_actions_for(self, duration: float) -> None:
        started = monotonic()
        await asyncio.sleep(duration)
        if self.actions:
            action_time, service = self.actions[0]
            raise AssertionError(
                f"expected no homeassistant actions for {self.target_entity_id} "
                f"during {duration:.2f}s, got {service} after "
                f"{action_time - started:.2f}s"
            )

    async def wait_for_action(
        self, expected_service: str, timeout: float
    ) -> None:
        started = monotonic()
        while monotonic() - started < timeout:
            if any(service == expected_service for _, service in self.actions):
                return
            await asyncio.sleep(0.02)
        recorded = [
            f"{service}@{action_time - started:.2f}s"
            for action_time, service in self.actions
        ]
        raise AssertionError(
            f"expected homeassistant.{expected_service} for "
            f"{self.target_entity_id} within {timeout:.2f}s; "
            f"recorded {recorded}"
        )


async def call_input_boolean(
    hass: HomeAssistant, service: str, entity_id: str
) -> None:
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


async def run_scenario(
    name: str, scenario: Callable[[], Awaitable[None]]
) -> None:
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


async def scenario_manual_off_lockout(hass: HomeAssistant) -> None:
    target = "input_boolean.manual_target"
    recorder = TargetActionRecorder(hass, target)
    await call_input_boolean(hass, "turn_on", "input_boolean.manual_trigger")
    await wait_for_state(
        hass, "manual-off lockout", target, "on", 2.0
    )
    recorder.clear()
    await call_input_boolean(hass, "turn_off", target)
    await recorder.assert_no_actions_for(0.25)
    await wait_for_state(hass, "manual-off lockout", target, "off", 0.2)


async def scenario_trigger_changes_during_lockout(hass: HomeAssistant) -> None:
    scenario = "trigger changes during lockout"
    target = "input_boolean.changes_target"
    recorder = TargetActionRecorder(hass, target)
    await call_input_boolean(hass, "turn_on", "input_boolean.changes_trigger")
    await wait_for_state(hass, scenario, target, "on", 2.0)
    recorder.clear()
    await call_input_boolean(hass, "turn_off", target)
    await call_input_boolean(hass, "turn_off", "input_boolean.changes_trigger")
    await recorder.assert_no_actions_for(0.30)
    await recorder.wait_for_action("turn_off", 2.5)
    await wait_for_state(hass, scenario, target, "off", 0.2)


async def scenario_lockout_expiry(hass: HomeAssistant) -> None:
    scenario = "lockout expiry"
    target = "input_boolean.expiry_target"
    recorder = TargetActionRecorder(hass, target)
    await call_input_boolean(hass, "turn_on", "input_boolean.expiry_trigger")
    await wait_for_state(hass, scenario, target, "on", 2.0)
    recorder.clear()
    await call_input_boolean(hass, "turn_off", target)
    await recorder.assert_no_actions_for(0.25)
    await recorder.wait_for_action("turn_on", 2.5)
    await wait_for_state(hass, scenario, target, "on", 0.2)


async def async_main(config_dir: Path) -> None:
    runtime = RuntimeConfig(config_dir=str(config_dir), skip_pip=True)
    hass = await bootstrap.async_setup_hass(runtime)
    if hass is None:
        raise RuntimeError("Home Assistant setup returned no instance")
    try:
        if hass.config.recovery_mode:
            raise RuntimeError("Home Assistant entered recovery mode")
        await hass.async_start()
        await hass.async_block_till_done()
        for entity_id in (
            "input_boolean.basic_trigger",
            "input_boolean.basic_target",
            "input_boolean.manual_trigger",
            "input_boolean.manual_target",
            "input_boolean.changes_trigger",
            "input_boolean.changes_target",
            "input_boolean.expiry_trigger",
            "input_boolean.expiry_target",
        ):
            await wait_for_state(hass, "runtime setup", entity_id, "off", 2.0)
        await run_scenario("activation", lambda: scenario_activation(hass))
        await run_scenario(
            "delayed deactivation", lambda: scenario_delayed_deactivation(hass)
        )
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
    finally:
        await hass.async_stop(force=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: run_state_based_entity_control_runtime.py CONFIG_DIR"
        )
    asyncio.run(async_main(Path(sys.argv[1])))


if __name__ == "__main__":
    main()
