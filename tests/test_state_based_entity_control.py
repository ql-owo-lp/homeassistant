import math
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment
import yaml


BLUEPRINT = (
    Path(__file__).resolve().parents[1]
    / "blueprints"
    / "v2"
    / "state_based_entity_control.yaml"
)


class BlueprintLoader(yaml.SafeLoader):
    pass


def _input(loader, node):
    return {"!input": loader.construct_scalar(node)}


BlueprintLoader.add_constructor("!input", _input)


class BlueprintUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with BLUEPRINT.open(encoding="utf-8") as blueprint_file:
            cls.document = yaml.load(blueprint_file, Loader=BlueprintLoader)
        cls.blueprint = cls.document["blueprint"]
        cls.sections = cls.blueprint["input"]
        cls.inputs = {
            input_id: input_config
            for section in cls.sections.values()
            for input_id, input_config in section["input"].items()
        }

    def test_blueprint_metadata_and_runtime_root(self):
        self.assertEqual(
            {
                "blueprint",
                "mode",
                "max_exceeded",
                "variables",
                "triggers",
                "conditions",
                "actions",
            },
            set(self.document),
        )
        self.assertEqual("State Based Entity Control v2", self.blueprint["name"])
        self.assertEqual("automation", self.blueprint["domain"])
        self.assertEqual("2026.7.0", self.blueprint["homeassistant"]["min_version"])
        self.assertTrue(self.blueprint["description"].strip())

    def test_sections_are_ordered_and_presented_for_the_ui(self):
        expected_sections = [
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
        ]
        self.assertEqual(expected_sections, list(self.sections))
        for section_id, section in self.sections.items():
            with self.subTest(section=section_id):
                if section_id == "core":
                    self.assertNotIn("collapsed", section)
                else:
                    self.assertIs(True, section.get("collapsed"))
                self.assertTrue(section["name"])
                self.assertTrue(section["icon"])
                self.assertTrue(section["input"])
                for input_config in section["input"].values():
                    self.assertTrue(input_config["name"])

    def test_every_input_in_a_collapsed_section_has_a_default(self):
        for section_id, section in self.sections.items():
            if section.get("collapsed"):
                for input_id, input_config in section["input"].items():
                    with self.subTest(section=section_id, input=input_id):
                        self.assertIn("default", input_config)

    def test_native_selectors_are_used_for_structured_inputs(self):
        expected_selectors = {
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
            "activation_blocker_entity": "entity",
            "deactivation_blocker_entity": "entity",
            "manual_off_enabled": "boolean",
            "manual_off_duration": "duration",
            "execution_schedule": "entity",
            "logbook_enabled": "boolean",
        }
        for input_id, selector_type in expected_selectors.items():
            with self.subTest(input=input_id):
                self.assertIn(selector_type, self.inputs[input_id]["selector"])

    def test_entity_selectors_have_required_cardinality_and_filters(self):
        for input_id in (
            "trigger_entities",
            "target_entities",
            "off_target_entities",
        ):
            with self.subTest(input=input_id):
                self.assertIs(
                    True,
                    self.inputs[input_id]["selector"]["entity"]["multiple"],
                )
        self.assertEqual(
            [{"domain": "sensor", "device_class": "illuminance"}],
            self.inputs["illuminance_sensor"]["selector"]["entity"]["filter"],
        )
        self.assertEqual(
            [{"domain": "schedule"}],
            self.inputs["execution_schedule"]["selector"]["entity"]["filter"],
        )

    def test_state_and_advanced_patterns_use_text_selectors(self):
        text_inputs = [
            "activation_state_pattern",
            "deactivation_state_pattern",
            "target_state_pattern",
            "activation_blocker_state_pattern",
            "deactivation_blocker_state_pattern",
            "manual_off_state_pattern",
            "advanced_execution_ranges",
            "advanced_alternate_timeouts",
        ]
        for input_id in text_inputs:
            with self.subTest(input=input_id):
                self.assertIn("text", self.inputs[input_id]["selector"])
        self.assertTrue(
            self.inputs["advanced_execution_ranges"]["selector"]["text"][
                "multiline"
            ]
        )
        self.assertTrue(
            self.inputs["advanced_alternate_timeouts"]["selector"]["text"][
                "multiline"
            ]
        )

    def test_core_and_state_matching_defaults(self):
        self.assertNotIn("default", self.inputs["trigger_entities"])
        self.assertNotIn("default", self.inputs["target_entities"])
        self.assertEqual([], self.inputs["off_target_entities"]["default"])
        self.assertEqual(
            {"hours": 0, "minutes": 0, "seconds": 30},
            self.inputs["main_timeout"]["default"],
        )
        self.assertEqual("on", self.inputs["activation_state_pattern"]["default"])
        self.assertEqual("", self.inputs["deactivation_state_pattern"]["default"])
        self.assertIs(True, self.inputs["target_state_tracking"]["default"])
        self.assertEqual("on", self.inputs["target_state_pattern"]["default"])

    def test_light_condition_defaults_and_selector_options(self):
        self.assertIs(False, self.inputs["illuminance_enabled"]["default"])
        self.assertEqual("", self.inputs["illuminance_sensor"]["default"])
        illuminance = self.inputs["illuminance_threshold"]["selector"]["number"]
        self.assertEqual(
            {"min": 0, "max": 100000, "unit_of_measurement": "lx", "mode": "box"},
            illuminance,
        )
        self.assertEqual(100, self.inputs["illuminance_threshold"]["default"])
        self.assertIs(False, self.inputs["sun_enabled"]["default"])
        sun = self.inputs["sun_elevation_threshold"]["selector"]["number"]
        self.assertEqual(-90, sun["min"])
        self.assertEqual(90, sun["max"])
        self.assertEqual("°", sun["unit_of_measurement"])
        self.assertEqual(0, self.inputs["sun_elevation_threshold"]["default"])
        self.assertEqual("any", self.inputs["light_gate_mode"]["default"])
        light_mode = self.inputs["light_gate_mode"]["selector"]["select"]
        self.assertEqual(["any", "all"], light_mode["options"])
        self.assertEqual("dropdown", light_mode["mode"])

    def test_optional_feature_defaults_and_advanced_format_documentation(self):
        self.assertEqual([], self.inputs["activation_actions"]["default"])
        self.assertEqual([], self.inputs["deactivation_actions"]["default"])
        self.assertEqual("", self.inputs["activation_blocker_entity"]["default"])
        self.assertEqual(
            "on", self.inputs["activation_blocker_state_pattern"]["default"]
        )
        self.assertEqual("", self.inputs["deactivation_blocker_entity"]["default"])
        self.assertEqual(
            "on", self.inputs["deactivation_blocker_state_pattern"]["default"]
        )
        self.assertIs(False, self.inputs["manual_off_enabled"]["default"])
        self.assertEqual(
            {"hours": 0, "minutes": 30, "seconds": 0},
            self.inputs["manual_off_duration"]["default"],
        )
        self.assertEqual("off", self.inputs["manual_off_state_pattern"]["default"])
        self.assertEqual("", self.inputs["execution_schedule"]["default"])
        self.assertEqual("", self.inputs["advanced_execution_ranges"]["default"])
        self.assertEqual("", self.inputs["advanced_alternate_timeouts"]["default"])
        advanced_description = self.sections["advanced"]["description"]
        self.assertIn("start-end range", advanced_description)
        self.assertIn("start-end,duration", advanced_description)
        self.assertIn("HH:MM:SS", advanced_description)
        self.assertIs(True, self.inputs["logbook_enabled"]["default"])

    def test_repeating_daily_slots_have_exact_shape_and_defaults(self):
        execution_inputs = self.sections["execution_windows"]["input"]
        alternate_inputs = self.sections["alternate_timeouts"]["input"]
        self.assertEqual(10, len(execution_inputs))
        self.assertEqual(12, len(alternate_inputs))
        for slot in range(1, 4):
            with self.subTest(execution_slot=slot):
                enabled = execution_inputs[f"execution_window_{slot}_enabled"]
                self.assertIs(False, enabled["default"])
                self.assertIn("boolean", enabled["selector"])
                for boundary in ("start", "end"):
                    config = execution_inputs[f"execution_window_{slot}_{boundary}"]
                    self.assertEqual("00:00:00", config["default"])
                    self.assertIn("time", config["selector"])
            with self.subTest(alternate_timeout_slot=slot):
                enabled = alternate_inputs[f"alternate_timeout_{slot}_enabled"]
                self.assertIs(False, enabled["default"])
                self.assertIn("boolean", enabled["selector"])
                for boundary in ("start", "end"):
                    config = alternate_inputs[f"alternate_timeout_{slot}_{boundary}"]
                    self.assertEqual("00:00:00", config["default"])
                    self.assertIn("time", config["selector"])
                duration = alternate_inputs[f"alternate_timeout_{slot}_duration"]
                self.assertEqual(
                    {"hours": 0, "minutes": 0, "seconds": 30},
                    duration["default"],
                )
                self.assertIn("duration", duration["selector"])


class RuntimeStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with BLUEPRINT.open(encoding="utf-8") as blueprint_file:
            cls.document = yaml.load(blueprint_file, Loader=BlueprintLoader)

    def test_uses_modern_plural_runtime_keys(self):
        self.assertTrue({"triggers", "conditions", "actions"} <= set(self.document))
        self.assertTrue({"trigger", "condition", "action"}.isdisjoint(self.document))
        self.assertEqual("restart", self.document["mode"])
        self.assertEqual("silent", self.document["max_exceeded"])

    def test_trigger_ids_and_sources_are_exact(self):
        triggers = self.document["triggers"]
        self.assertEqual(
            [
                "automation_reloaded",
                "home_assistant_started",
                "trigger_entity_changed",
                "target_state_changed",
                "target_state_stable",
                "manual_lockout_expired",
            ],
            [trigger["id"] for trigger in triggers],
        )
        self.assertEqual(
            ["event", "homeassistant", "state", "state", "state", "state"],
            [trigger["trigger"] for trigger in triggers],
        )
        self.assertEqual("automation_reloaded", triggers[0]["event_type"])
        self.assertEqual("start", triggers[1]["event"])
        self.assertEqual({"!input": "trigger_entities"}, triggers[2]["entity_id"])
        self.assertEqual({"!input": "target_entities"}, triggers[3]["entity_id"])
        self.assertNotIn("for", triggers[3])
        self.assertEqual({"!input": "target_entities"}, triggers[4]["entity_id"])
        self.assertEqual({"seconds": 3}, triggers[4]["for"])
        self.assertEqual({"!input": "target_entities"}, triggers[5]["entity_id"])
        self.assertEqual({"!input": "manual_off_duration"}, triggers[5]["for"])

    def test_immediate_target_change_restarts_the_shared_lockout_wait(self):
        immediate = next(
            trigger
            for trigger in self.document["triggers"]
            if trigger["id"] == "target_state_changed"
        )
        self.assertEqual("restart", self.document["mode"])
        self.assertEqual({"!input": "target_entities"}, immediate["entity_id"])
        self.assertNotIn("for", immediate)
        self.assertEqual(
            "{{ manual_off_lockout_remaining_seconds }}",
            self.document["actions"][0]["then"][0]["delay"]["seconds"],
        )

    def test_required_normalized_variables_are_present(self):
        required = {
            "available_trigger_entities",
            "activation_entities",
            "deactivation_entities",
            "active_target_entities",
            "effective_target_state_tracking",
            "trigger_source_allows_activation",
        }
        self.assertTrue(required <= set(self.document["variables"]))

    def test_activation_gate_and_manual_lockout_variables_are_present(self):
        required = {
            "illuminance_gate_passed",
            "sun_gate_passed",
            "light_gates_passed",
            "activation_blocked",
            "deactivation_blocked",
            "manual_off_duration_seconds",
            "manual_off_lockout_remaining_seconds",
            "manual_off_lockout_active",
        }
        self.assertTrue(required <= set(self.document["variables"]))

    def test_inputs_are_exposed_without_comma_splitting(self):
        variables = self.document["variables"]
        expected_inputs = {
            "trigger_entities": "trigger_entities",
            "target_entities": "target_entities",
            "configured_off_target_entities": "off_target_entities",
            "activation_state_pattern": "activation_state_pattern",
            "deactivation_state_pattern": "deactivation_state_pattern",
            "target_state_pattern": "target_state_pattern",
            "target_state_tracking": "target_state_tracking",
        }
        for variable, input_name in expected_inputs.items():
            with self.subTest(variable=variable):
                self.assertEqual({"!input": input_name}, variables[variable])
        self.assertNotIn("split(',')", str(variables))

    def test_gate_blocker_and_manual_inputs_are_exposed_as_variables(self):
        variables = self.document["variables"]
        expected_inputs = {
            "illuminance_enabled": "illuminance_enabled",
            "illuminance_sensor": "illuminance_sensor",
            "illuminance_threshold": "illuminance_threshold",
            "sun_enabled": "sun_enabled",
            "sun_elevation_threshold": "sun_elevation_threshold",
            "light_gate_mode": "light_gate_mode",
            "activation_blocker_entity": "activation_blocker_entity",
            "activation_blocker_state_pattern": "activation_blocker_state_pattern",
            "deactivation_blocker_entity": "deactivation_blocker_entity",
            "deactivation_blocker_state_pattern": "deactivation_blocker_state_pattern",
            "manual_off_enabled": "manual_off_enabled",
            "manual_off_duration": "manual_off_duration",
            "manual_off_state_pattern": "manual_off_state_pattern",
        }
        for variable, input_name in expected_inputs.items():
            with self.subTest(variable=variable):
                self.assertEqual({"!input": input_name}, variables[variable])

    def test_root_condition_requires_an_available_trigger(self):
        self.assertEqual(1, len(self.document["conditions"]))
        condition = self.document["conditions"][0]
        self.assertEqual("Require at least one available trigger entity", condition["alias"])
        self.assertEqual("template", condition["condition"])
        self.assertIn("available_trigger_entities | count > 0", condition["value_template"])

    def test_first_action_waits_for_the_active_manual_off_lockout(self):
        self.assertEqual(1, len(self.document["actions"]))
        action = self.document["actions"][0]
        self.assertEqual("Wait for active manual-off lockout", action["alias"])
        self.assertEqual(
            [
                {
                    "condition": "template",
                    "value_template": "{{ manual_off_lockout_active }}",
                }
            ],
            action["if"],
        )
        self.assertEqual(
            [
                {
                    "delay": {
                        "seconds": "{{ manual_off_lockout_remaining_seconds }}"
                    }
                }
            ],
            action["then"],
        )

    def test_startup_and_reload_sources_run_the_same_lockout_wait(self):
        self.assertEqual(
            ["automation_reloaded", "home_assistant_started"],
            [trigger["id"] for trigger in self.document["triggers"][:2]],
        )
        self.assertNotIn("trigger", str(self.document["actions"][0]))


class RuntimeTemplateBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with BLUEPRINT.open(encoding="utf-8") as blueprint_file:
            cls.document = yaml.load(blueprint_file, Loader=BlueprintLoader)
        cls.variables = cls.document["variables"]
        cls.environment = NativeEnvironment(undefined=StrictUndefined)
        cls.environment.tests["match"] = cls._regex_match

    @staticmethod
    def _regex_match(value, pattern, ignorecase=False):
        flags = re.IGNORECASE if ignorecase else 0
        return re.match(pattern, str(value), flags) is not None

    def render(self, variable, **context):
        return self.environment.from_string(self.variables[variable]).render(**context)

    @staticmethod
    def states_for(entity_states):
        return lambda entity_id: entity_states.get(entity_id, "unknown")

    @staticmethod
    def is_number(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        return math.isfinite(number)

    @staticmethod
    def as_timestamp(value, default=None):
        try:
            return value.timestamp()
        except (AttributeError, TypeError, ValueError):
            return default

    class States:
        def __init__(self, entity_states):
            self.entity_states = entity_states

        def __call__(self, entity_id):
            state = self.entity_states.get(entity_id)
            return state.state if state is not None else "unknown"

        def __getitem__(self, entity_id):
            return self.entity_states.get(entity_id)

    def test_off_targets_default_to_targets_only_when_unconfigured(self):
        self.assertEqual(
            ["light.main"],
            self.render(
                "off_target_entities",
                configured_off_target_entities=[],
                target_entities=["light.main"],
            ),
        )
        self.assertEqual(
            ["switch.alt"],
            self.render(
                "off_target_entities",
                configured_off_target_entities=["switch.alt"],
                target_entities=["light.main"],
            ),
        )

    def test_unknown_and_unavailable_triggers_are_excluded(self):
        entity_states = {
            "binary_sensor.ready": "on",
            "binary_sensor.unknown": "unknown",
            "binary_sensor.missing": "unavailable",
        }
        self.assertEqual(
            ["binary_sensor.ready"],
            self.render(
                "available_trigger_entities",
                trigger_entities=list(entity_states),
                states=self.states_for(entity_states),
            ),
        )

    def test_activation_regex_is_fully_anchored_and_case_insensitive(self):
        entity_states = {
            "sensor.upper": "ON",
            "sensor.alternative": "active",
            "sensor.prefix": "onward",
            "sensor.suffix": "inactive",
        }
        self.assertEqual(
            ["sensor.upper", "sensor.alternative"],
            self.render(
                "activation_entities",
                available_trigger_entities=list(entity_states),
                activation_state_pattern="on|active",
                states=self.states_for(entity_states),
            ),
        )

    def test_core_state_regex_preserves_backreferences_and_rejects_newlines(self):
        entity_states = {
            "sensor.backreference": "onon",
            "sensor.prefix": "ononward",
            "sensor.suffix": "preonon",
            "sensor.newline": "onon\n",
        }
        self.assertEqual(
            ["sensor.backreference"],
            self.render(
                "activation_entities",
                available_trigger_entities=list(entity_states),
                activation_state_pattern=r"(on)\1",
                states=self.states_for(entity_states),
            ),
        )

    def test_deactivation_uses_explicit_regex_when_configured(self):
        entity_states = {"sensor.off": "OFF", "sensor.idle": "idle"}
        self.assertEqual(
            ["sensor.off"],
            self.render(
                "deactivation_entities",
                available_trigger_entities=list(entity_states),
                activation_entities=["sensor.idle"],
                deactivation_state_pattern="off",
                states=self.states_for(entity_states),
            ),
        )

    def test_deactivation_inverts_activation_when_no_explicit_regex(self):
        available = ["sensor.one", "sensor.two"]
        context = {
            "available_trigger_entities": available,
            "deactivation_state_pattern": "",
            "states": self.states_for({}),
        }
        self.assertEqual(
            available,
            self.render("deactivation_entities", activation_entities=[], **context),
        )
        self.assertEqual(
            [],
            self.render(
                "deactivation_entities",
                activation_entities=["sensor.one"],
                **context,
            ),
        )

    def test_active_target_entities_use_any_match_semantics(self):
        entity_states = {"light.one": "off", "light.two": "ON"}
        self.assertEqual(
            ["light.two"],
            self.render(
                "active_target_entities",
                target_entities=list(entity_states),
                target_state_pattern="on",
                states=self.states_for(entity_states),
            ),
        )

    def test_scene_or_script_target_disables_effective_tracking(self):
        self.assertFalse(
            self.render(
                "effective_target_state_tracking",
                target_state_tracking=False,
                target_entities=["light.one"],
            )
        )
        self.assertTrue(
            self.render(
                "effective_target_state_tracking",
                target_state_tracking=True,
                target_entities=["light.one", "switch.two"],
            )
        )
        for entity_id in ("scene.relax", "script.movie_time"):
            with self.subTest(entity=entity_id):
                self.assertFalse(
                    self.render(
                        "effective_target_state_tracking",
                        target_state_tracking=True,
                        target_entities=["light.one", entity_id],
                    )
                )

    def test_non_target_sources_allow_activation(self):
        self.assertTrue(self.render("trigger_source_allows_activation"))
        for trigger_id in (
            "automation_reloaded",
            "home_assistant_started",
            "trigger_entity_changed",
            "manual_lockout_expired",
        ):
            with self.subTest(trigger_id=trigger_id):
                trigger = type("Trigger", (), {"id": trigger_id})()
                self.assertTrue(
                    self.render(
                        "trigger_source_allows_activation",
                        trigger=trigger,
                        manual_off_lockout_active=False,
                    )
                )

    def test_target_change_sources_allow_activation_only_after_lockout_wait(self):
        for trigger_id in ("target_state_changed", "target_state_stable"):
            trigger = type("Trigger", (), {"id": trigger_id})()
            with self.subTest(trigger_id=trigger_id, lockout=False):
                self.assertFalse(
                    self.render(
                        "trigger_source_allows_activation",
                        trigger=trigger,
                        manual_off_lockout_active=False,
                    )
                )
            with self.subTest(trigger_id=trigger_id, lockout=True):
                self.assertTrue(
                    self.render(
                        "trigger_source_allows_activation",
                        trigger=trigger,
                        manual_off_lockout_active=True,
                    )
                )

    def test_illuminance_gate_passes_when_disabled(self):
        self.assertTrue(
            self.render(
                "illuminance_gate_passed",
                illuminance_enabled=False,
                illuminance_sensor="",
                illuminance_threshold=100,
                states=self.states_for({}),
                is_number=self.is_number,
            )
        )

    def test_illuminance_gate_requires_a_numeric_state_at_or_below_threshold(self):
        for value, expected in (("99.5", True), ("100", True), ("100.1", False)):
            with self.subTest(value=value):
                self.assertIs(
                    expected,
                    self.render(
                        "illuminance_gate_passed",
                        illuminance_enabled=True,
                        illuminance_sensor="sensor.lux",
                        illuminance_threshold=100,
                        states=self.states_for({"sensor.lux": value}),
                        is_number=self.is_number,
                    ),
                )

    def test_illuminance_gate_fails_closed_for_invalid_or_missing_state(self):
        for sensor, value in (
            ("sensor.lux", "unknown"),
            ("sensor.lux", "unavailable"),
            ("sensor.lux", "not numeric"),
            ("sensor.lux", "nan"),
            ("sensor.lux", "inf"),
            ("sensor.lux", "-inf"),
            ("", "42"),
        ):
            with self.subTest(sensor=sensor, value=value):
                self.assertFalse(
                    self.render(
                        "illuminance_gate_passed",
                        illuminance_enabled=True,
                        illuminance_sensor=sensor,
                        illuminance_threshold=100000,
                        states=self.states_for({"sensor.lux": value}),
                        is_number=self.is_number,
                    )
                )

    def test_sun_gate_passes_when_disabled(self):
        self.assertTrue(
            self.render(
                "sun_gate_passed",
                sun_enabled=False,
                sun_elevation_threshold=0,
                state_attr=lambda entity_id, attribute: None,
                is_number=self.is_number,
            )
        )

    def test_sun_gate_requires_numeric_elevation_at_or_below_threshold(self):
        for elevation, expected in ((-1, True), (0, True), (0.1, False)):
            with self.subTest(elevation=elevation):
                self.assertIs(
                    expected,
                    self.render(
                        "sun_gate_passed",
                        sun_enabled=True,
                        sun_elevation_threshold=0,
                        state_attr=lambda entity_id, attribute, value=elevation: value,
                        is_number=self.is_number,
                    ),
                )
        for elevation in (None, "not numeric", "nan", "inf", "-inf"):
            with self.subTest(elevation=elevation):
                self.assertFalse(
                    self.render(
                        "sun_gate_passed",
                        sun_enabled=True,
                        sun_elevation_threshold=90,
                        state_attr=lambda entity_id, attribute, value=elevation: value,
                        is_number=self.is_number,
                    )
                )

    def test_light_gate_combination_uses_enabled_gates_and_selected_mode(self):
        cases = (
            (False, False, False, False, "all", True),
            (True, False, True, False, "all", True),
            (True, False, False, True, "any", False),
            (False, True, False, True, "all", True),
            (False, True, True, False, "any", False),
            (True, True, True, False, "any", True),
            (True, True, True, False, "all", False),
            (True, True, False, False, "any", False),
        )
        for lux_enabled, sun_enabled, lux_passed, sun_passed, mode, expected in cases:
            with self.subTest(
                lux_enabled=lux_enabled,
                sun_enabled=sun_enabled,
                lux_passed=lux_passed,
                sun_passed=sun_passed,
                mode=mode,
            ):
                self.assertIs(
                    expected,
                    self.render(
                        "light_gates_passed",
                        illuminance_enabled=lux_enabled,
                        sun_enabled=sun_enabled,
                        illuminance_gate_passed=lux_passed,
                        sun_gate_passed=sun_passed,
                        light_gate_mode=mode,
                    ),
                )

    def test_blockers_require_entity_and_nonempty_pattern(self):
        for variable, prefix in (
            ("activation_blocked", "activation"),
            ("deactivation_blocked", "deactivation"),
        ):
            for entity, pattern in (("", "on"), ("input_boolean.guard", ""), ("input_boolean.guard", "  ")):
                with self.subTest(variable=variable, entity=entity, pattern=pattern):
                    self.assertFalse(
                        self.render(
                            variable,
                            **{
                                f"{prefix}_blocker_entity": entity,
                                f"{prefix}_blocker_state_pattern": pattern,
                                "states": self.states_for({"input_boolean.guard": "on"}),
                            },
                        )
                    )

    def test_blockers_match_full_state_case_insensitively(self):
        for variable, prefix in (
            ("activation_blocked", "activation"),
            ("deactivation_blocked", "deactivation"),
        ):
            for state, expected in (("ON", True), ("active", True), ("onward", False), ("inactive", False)):
                with self.subTest(variable=variable, state=state):
                    self.assertIs(
                        expected,
                        self.render(
                            variable,
                            **{
                                f"{prefix}_blocker_entity": "input_boolean.guard",
                                f"{prefix}_blocker_state_pattern": "on|active",
                                "states": self.states_for({"input_boolean.guard": state}),
                            },
                        ),
                    )

    def test_blocker_regex_preserves_backreferences_and_rejects_newlines(self):
        for state, expected in (
            ("onon", True),
            ("ononward", False),
            ("preonon", False),
            ("onon\n", False),
        ):
            with self.subTest(state=state):
                self.assertIs(
                    expected,
                    self.render(
                        "activation_blocked",
                        activation_blocker_entity="input_boolean.guard",
                        activation_blocker_state_pattern=r"(on)\1",
                        states=self.states_for({"input_boolean.guard": state}),
                    ),
                )

    def test_manual_off_duration_mapping_is_summed_in_seconds(self):
        self.assertEqual(
            93784,
            self.render(
                "manual_off_duration_seconds",
                manual_off_duration={
                    "days": 1,
                    "hours": 2,
                    "minutes": 3,
                    "seconds": 4,
                },
            ),
        )
        self.assertEqual(
            3723,
            self.render(
                "manual_off_duration_seconds",
                manual_off_duration={"hours": 1, "minutes": 2, "seconds": 3},
            ),
        )
        self.assertEqual(
            1.75,
            self.render(
                "manual_off_duration_seconds",
                manual_off_duration={"seconds": 1.5, "milliseconds": 250},
            ),
        )

    def test_manual_off_lockout_remaining_seconds_for_single_target(self):
        now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
        state = SimpleNamespace(
            state="off", last_changed=now - timedelta(seconds=10)
        )
        self.assertEqual(
            20,
            self.render(
                "manual_off_lockout_remaining_seconds",
                manual_off_enabled=True,
                manual_off_duration_seconds=30,
                manual_off_state_pattern="off",
                target_entities=["light.main"],
                states=self.States({"light.main": state}),
                now=lambda: now,
                as_timestamp=self.as_timestamp,
            ),
        )

    def test_manual_off_lockout_uses_max_remainder_for_staggered_targets(self):
        now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
        states = self.States(
            {
                "light.first": SimpleNamespace(
                    state="off", last_changed=now - timedelta(seconds=20)
                ),
                "light.second": SimpleNamespace(
                    state="OFF", last_changed=now - timedelta(seconds=5)
                ),
                "light.expired": SimpleNamespace(
                    state="off", last_changed=now - timedelta(seconds=40)
                ),
            }
        )
        self.assertEqual(
            25,
            self.render(
                "manual_off_lockout_remaining_seconds",
                manual_off_enabled=True,
                manual_off_duration_seconds=30,
                manual_off_state_pattern="off",
                target_entities=["light.first", "light.second", "light.expired"],
                states=states,
                now=lambda: now,
                as_timestamp=self.as_timestamp,
            ),
        )

    def test_manual_off_lockout_remainder_is_zero_when_inactive_or_expired(self):
        now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
        for enabled, duration, state_value, age in (
            (False, 30, "off", 10),
            (True, 0, "off", 0),
            (True, 30, "on", 10),
            (True, 30, "off", 30),
            (True, 30, "off", 31),
            (True, 30, "off", -1),
        ):
            with self.subTest(
                enabled=enabled,
                duration=duration,
                state=state_value,
                age=age,
            ):
                state = SimpleNamespace(
                    state=state_value,
                    last_changed=now - timedelta(seconds=age),
                )
                self.assertEqual(
                    0,
                    self.render(
                        "manual_off_lockout_remaining_seconds",
                        manual_off_enabled=enabled,
                        manual_off_duration_seconds=duration,
                        manual_off_state_pattern="off",
                        target_entities=["light.main"],
                        states=self.States({"light.main": state}),
                        now=lambda: now,
                        as_timestamp=self.as_timestamp,
                    ),
                )

    def test_manual_off_lockout_remainder_preserves_fractional_precision(self):
        now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
        state = SimpleNamespace(
            state="off", last_changed=now - timedelta(seconds=0.25)
        )
        self.assertEqual(
            1.5,
            self.render(
                "manual_off_lockout_remaining_seconds",
                manual_off_enabled=True,
                manual_off_duration_seconds=1.75,
                manual_off_state_pattern="off",
                target_entities=["light.main"],
                states=self.States({"light.main": state}),
                now=lambda: now,
                as_timestamp=self.as_timestamp,
            ),
        )

    def test_manual_off_lockout_active_is_derived_from_positive_remainder(self):
        self.assertFalse(
            self.render(
                "manual_off_lockout_active",
                manual_off_lockout_remaining_seconds=0,
            )
        )
        self.assertTrue(
            self.render(
                "manual_off_lockout_active",
                manual_off_lockout_remaining_seconds=0.001,
            )
        )

    def test_manual_off_lockout_pattern_is_fully_anchored(self):
        now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
        for pattern, target_state, expected in (
            ("off", "offering", False),
            ("off", "cutoff", False),
            ("off", "off\n", False),
            (r"(off)\1", "offoff", True),
        ):
            with self.subTest(pattern=pattern, target_state=target_state):
                state = SimpleNamespace(
                    state=target_state,
                    last_changed=now - timedelta(seconds=10),
                )
                self.assertIs(
                    expected,
                    self.render(
                        "manual_off_lockout_remaining_seconds",
                        manual_off_enabled=True,
                        manual_off_duration_seconds=30,
                        manual_off_state_pattern=pattern,
                        target_entities=["light.main"],
                        states=self.States({"light.main": state}),
                        now=lambda: now,
                        as_timestamp=self.as_timestamp,
                    )
                    > 0,
                )

    def test_manual_off_lockout_safely_ignores_missing_target_state(self):
        now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
        self.assertEqual(
            0,
            self.render(
                "manual_off_lockout_remaining_seconds",
                manual_off_enabled=True,
                manual_off_duration_seconds=30,
                manual_off_state_pattern="off",
                target_entities=["light.missing"],
                states=self.States({}),
                now=lambda: now,
                as_timestamp=self.as_timestamp,
            )
        )


if __name__ == "__main__":
    unittest.main()
