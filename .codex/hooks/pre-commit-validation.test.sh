#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/.codex/hooks/pre-commit-validation.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TMP_DIR/bin"

payload_for_command() {
  local command="$1"
  python3 - "$TMP_DIR" "$command" <<'PY'
import json
import sys

print(json.dumps({"cwd": sys.argv[1], "tool_input": {"command": sys.argv[2]}}))
PY
}

run_hook() {
  local command="$1"
  printf '%s' "$(payload_for_command "$command")" | (
    cd "$TMP_DIR"
    PATH="$TMP_DIR/bin:$PATH" bash "$SCRIPT"
  )
}

write_harness_config() {
  mkdir -p "$TMP_DIR/.harness"
  cat > "$TMP_DIR/.harness/validation.json" <<'JSON'
{
  "schemaVersion": 1,
  "mode": "profile",
  "profiles": ["node"],
  "commands": [
    {"name": "lint", "command": ["npm", "run", "lint"], "reason": "lint", "roles": ["stop"]},
    {"name": "test", "command": ["npm", "run", "test"], "reason": "test", "roles": ["stop"]}
  ],
  "stopChecks": ["lint", "test"]
}
JSON
}

write_fake_npm() {
  local mode="$1"
  cat > "$TMP_DIR/bin/npm" <<SH
#!/usr/bin/env bash
set -euo pipefail
echo "\$*"
if [[ "$mode" == "fail-test" && "\$*" == "run test" ]]; then
  echo "test failed" >&2
  exit 1
fi
SH
  chmod +x "$TMP_DIR/bin/npm"
}

assert_ignores_non_commit() {
  write_harness_config
  write_fake_npm pass
  local output
  output="$(run_hook "npm run build")"
  [[ -z "$output" ]]
}

assert_allows_without_package_json() {
  rm -f "$TMP_DIR/.harness/validation.json"
  write_fake_npm fail-test
  local output
  output="$(run_hook "git commit -m test")"
  [[ -z "$output" ]]
}

assert_runs_all_scripts_before_commit() {
  write_harness_config
  write_fake_npm pass
  local output
  output="$(run_hook "git commit -m test")"
  [[ -z "$output" ]]
}

assert_blocks_when_validation_fails() {
  write_harness_config
  write_fake_npm fail-test
  local output
  output="$(run_hook "git commit -m test")"
  [[ "$output" == *'"decision": "block"'* ]]
  [[ "$output" == *'npm run test'* ]]
}

assert_ignores_non_commit
assert_allows_without_package_json
assert_runs_all_scripts_before_commit
assert_blocks_when_validation_fails
