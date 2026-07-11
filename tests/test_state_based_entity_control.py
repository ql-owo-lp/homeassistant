import re
import unittest
from pathlib import Path

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
                "target_state_stable",
                "manual_lockout_expired",
            ],
            [trigger["id"] for trigger in triggers],
        )
        self.assertEqual(
            ["event", "homeassistant", "state", "state", "state"],
            [trigger["trigger"] for trigger in triggers],
        )
        self.assertEqual("automation_reloaded", triggers[0]["event_type"])
        self.assertEqual("start", triggers[1]["event"])
        self.assertEqual({"!input": "trigger_entities"}, triggers[2]["entity_id"])
        self.assertEqual({"!input": "target_entities"}, triggers[3]["entity_id"])
        self.assertEqual({"seconds": 3}, triggers[3]["for"])
        self.assertEqual({"!input": "target_entities"}, triggers[4]["entity_id"])
        self.assertEqual({"!input": "manual_off_duration"}, triggers[4]["for"])

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

    def test_root_condition_requires_an_available_trigger(self):
        self.assertEqual(1, len(self.document["conditions"]))
        condition = self.document["conditions"][0]
        self.assertEqual("Require at least one available trigger entity", condition["alias"])
        self.assertEqual("template", condition["condition"])
        self.assertIn("available_trigger_entities | count > 0", condition["value_template"])

    def test_actions_are_reserved_for_later_runtime_tasks(self):
        self.assertEqual([], self.document["actions"])


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

    def test_only_target_stability_blocks_activation_by_trigger_source(self):
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
                    self.render("trigger_source_allows_activation", trigger=trigger)
                )
        stable = type("Trigger", (), {"id": "target_state_stable"})()
        self.assertFalse(
            self.render("trigger_source_allows_activation", trigger=stable)
        )


if __name__ == "__main__":
    unittest.main()
