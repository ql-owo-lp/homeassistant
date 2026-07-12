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
  manual_trigger:
  manual_target:
  changes_trigger:
  changes_target:
  expiry_trigger:
  expiry_target:
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
- alias: Manual-off lockout runtime test
  use_blueprint:
    path: local/state_based_entity_control.yaml
    input:
      trigger_entities:
        - input_boolean.manual_trigger
      target_entities:
        - input_boolean.manual_target
      main_timeout:
        seconds: 0.2
      manual_off_enabled: true
      manual_off_duration:
        seconds: 1.5
      logbook_enabled: false
- alias: Trigger changes during lockout runtime test
  use_blueprint:
    path: local/state_based_entity_control.yaml
    input:
      trigger_entities:
        - input_boolean.changes_trigger
      target_entities:
        - input_boolean.changes_target
      main_timeout:
        seconds: 0.2
      target_state_tracking: false
      manual_off_enabled: true
      manual_off_duration:
        seconds: 1.5
      logbook_enabled: false
- alias: Lockout expiry runtime test
  use_blueprint:
    path: local/state_based_entity_control.yaml
    input:
      trigger_entities:
        - input_boolean.expiry_trigger
      target_entities:
        - input_boolean.expiry_target
      main_timeout:
        seconds: 0.2
      manual_off_enabled: true
      manual_off_duration:
        seconds: 1.5
      logbook_enabled: false
YAML

docker_command=(
  docker run --rm
  --user "$(id -u):$(id -g)"
  -v "${config_dir}:/config"
  -v "${repo_dir}/tests:/workspace/tests:ro"
  ghcr.io/home-assistant/home-assistant:2026.7.2
  python /workspace/tests/run_state_based_entity_control_runtime.py /config
)

if command -v timeout >/dev/null 2>&1; then
  timeout 90s "${docker_command[@]}"
else
  "${docker_command[@]}"
fi
