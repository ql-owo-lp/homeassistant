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
