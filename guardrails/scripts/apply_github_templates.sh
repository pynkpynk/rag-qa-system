#!/usr/bin/env bash

set -euo pipefail

show_help() {
  cat <<'EOF'
Usage: scripts/apply_github_templates.sh [--force]

Copies guardrails GitHub templates into the repository root:
- AGENTS.md
- .github/workflows/*
- .github/pull_request_template.md
- .github/pr_agent.toml

By default, existing files are left untouched. Pass --force to overwrite.
EOF
}

OVERWRITE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      OVERWRITE=true
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      show_help
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARDRAILS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$GUARDRAILS_DIR/.." && pwd)"
TEMPLATE_DIR="$GUARDRAILS_DIR/templates"

copy_file() {
  local src="$1"
  local dest="$2"
  local label="$3"

  if [[ ! -f "$src" ]]; then
    echo "Source missing: $src"
    exit 1
  fi

  mkdir -p "$(dirname "$dest")"

  if [[ -e "$dest" && "$OVERWRITE" == "false" ]]; then
    echo "Skipping $label (exists: $dest)"
    return
  fi

  cp "$src" "$dest"
  echo "Copied $label -> $dest"
}

echo "Applying GitHub templates (force=$OVERWRITE)"

copy_file "$TEMPLATE_DIR/AGENTS.md" "$REPO_ROOT/AGENTS.md" "AGENTS.md"

WORKFLOW_SRC_DIR="$TEMPLATE_DIR/github/workflows"
WORKFLOW_DEST_DIR="$REPO_ROOT/.github/workflows"

if [[ -d "$WORKFLOW_SRC_DIR" ]]; then
  mkdir -p "$WORKFLOW_DEST_DIR"
  for workflow in "$WORKFLOW_SRC_DIR"/*.yml "$WORKFLOW_SRC_DIR"/*.yaml; do
    [[ -e "$workflow" ]] || continue
    workflow_name="$(basename "$workflow")"
    copy_file "$workflow" "$WORKFLOW_DEST_DIR/$workflow_name" "workflow $workflow_name"
  done
fi

copy_file "$TEMPLATE_DIR/github/pull_request_template.md" \
  "$REPO_ROOT/.github/pull_request_template.md" \
  "pull request template"

copy_file "$TEMPLATE_DIR/github/pr_agent.toml" \
  "$REPO_ROOT/.github/pr_agent.toml" \
  "pr_agent.toml"

echo "Done."
