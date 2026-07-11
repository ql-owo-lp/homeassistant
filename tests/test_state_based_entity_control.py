from pathlib import Path
import unittest

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

    def test_blueprint_metadata_and_placeholder_runtime(self):
        self.assertEqual("State Based Entity Control v2", self.blueprint["name"])
        self.assertEqual("automation", self.blueprint["domain"])
        self.assertEqual("2026.7.0", self.blueprint["homeassistant"]["min_version"])
        self.assertTrue(self.blueprint["description"].strip())
        self.assertEqual("restart", self.document["mode"])
        self.assertEqual({}, self.document["variables"])
        self.assertEqual([], self.document["triggers"])
        self.assertEqual([], self.document["conditions"])
        self.assertEqual([], self.document["actions"])

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
            "manual_off_enabled": "boolean",
            "manual_off_duration": "duration",
            "execution_schedule": "entity",
            "logbook_enabled": "boolean",
        }
        for input_id, selector_type in expected_selectors.items():
            with self.subTest(input=input_id):
                self.assertIn(selector_type, self.inputs[input_id]["selector"])

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

    def test_repeating_daily_slots_have_exact_shape_and_defaults(self):
        execution_inputs = self.sections["execution_windows"]["input"]
        alternate_inputs = self.sections["alternate_timeouts"]["input"]
        self.assertEqual(10, len(execution_inputs))
        self.assertEqual(12, len(alternate_inputs))
        for slot in range(1, 4):
            with self.subTest(execution_slot=slot):
                self.assertIs(
                    False, execution_inputs[f"execution_window_{slot}_enabled"]["default"]
                )
                for boundary in ("start", "end"):
                    config = execution_inputs[f"execution_window_{slot}_{boundary}"]
                    self.assertEqual("00:00:00", config["default"])
                    self.assertIn("time", config["selector"])
            with self.subTest(alternate_timeout_slot=slot):
                self.assertIs(
                    False, alternate_inputs[f"alternate_timeout_{slot}_enabled"]["default"]
                )
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


if __name__ == "__main__":
    unittest.main()
