#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEM_YAML="${1:-${ROOT_DIR}/examples/medical_diagnosis.yaml}"
AI_ACT_BIN="${AI_ACT_BIN:-ai-act}"
OUTPUT_DIR="${2:-}"
USE_UV_FALLBACK=0
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "${OUTPUT_DIR}" ]]; then
  OUTPUT_DIR="$(mktemp -d)"
  CLEANUP_OUTPUT_DIR=1
else
  mkdir -p "${OUTPUT_DIR}"
  CLEANUP_OUTPUT_DIR=0
fi

cleanup() {
  if [[ "${CLEANUP_OUTPUT_DIR}" == "1" ]]; then
    rm -rf "${OUTPUT_DIR}"
  fi
}
trap cleanup EXIT

if ! command -v "${AI_ACT_BIN}" >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    USE_UV_FALLBACK=1
  else
    echo "Error: '${AI_ACT_BIN}' command not found. Install project first (pip install -e \".[dev]\")." >&2
    exit 1
  fi
fi

if [[ ! -f "${SYSTEM_YAML}" ]]; then
  echo "Error: Descriptor not found: ${SYSTEM_YAML}" >&2
  exit 1
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v uv >/dev/null 2>&1; then
    PYTHON_BIN="uv run python"
  else
    echo "Error: Python interpreter not found." >&2
    exit 1
  fi
fi

run_ai_act() {
  if [[ "${USE_UV_FALLBACK}" == "1" ]]; then
    uv run "${AI_ACT_BIN}" "$@"
  else
    "${AI_ACT_BIN}" "$@"
  fi
}

CLASSIFY_JSON="${OUTPUT_DIR}/classify.json"
CHECK_JSON="${OUTPUT_DIR}/check.json"
REPORT_JSON="${OUTPUT_DIR}/report.json"
REPORT_HTML="${OUTPUT_DIR}/report.html"

echo "[quickstart-smoke] validate"
run_ai_act validate "${SYSTEM_YAML}" >/dev/null

echo "[quickstart-smoke] classify --json"
run_ai_act classify "${SYSTEM_YAML}" --json > "${CLASSIFY_JSON}"

echo "[quickstart-smoke] check --json"
run_ai_act check "${SYSTEM_YAML}" --json > "${CHECK_JSON}"

echo "[quickstart-smoke] report --format json"
run_ai_act report "${SYSTEM_YAML}" --format json -o "${REPORT_JSON}" >/dev/null

echo "[quickstart-smoke] report --format html"
run_ai_act report "${SYSTEM_YAML}" --format html -o "${REPORT_HTML}" >/dev/null

${PYTHON_BIN} - "${CLASSIFY_JSON}" "${CHECK_JSON}" "${REPORT_JSON}" "${REPORT_HTML}" <<'PY'
import json
import pathlib
import sys

classify_path, check_path, report_path, report_html_path = sys.argv[1:]

with open(classify_path, encoding="utf-8") as f:
    classify = json.load(f)
with open(check_path, encoding="utf-8") as f:
    check = json.load(f)
with open(report_path, encoding="utf-8") as f:
    report = json.load(f)

for key in ("system_name", "risk_tier", "confidence", "reasoning", "articles_applicable"):
    if key not in classify:
        raise SystemExit(f"classify output missing key: {key}")

summary = check.get("summary")
if not isinstance(summary, dict):
    raise SystemExit("check output missing summary object")
for key in (
    "total_requirements",
    "compliant_count",
    "non_compliant_count",
    "partial_count",
    "not_assessed_count",
    "compliance_percentage",
):
    if key not in summary:
        raise SystemExit(f"check.summary missing key: {key}")

for key in ("system_name", "risk_tier", "compliance_summary", "recommended_actions"):
    if key not in report:
        raise SystemExit(f"report json missing key: {key}")

html_path = pathlib.Path(report_html_path)
if not html_path.exists() or html_path.stat().st_size == 0:
    raise SystemExit("report html was not generated correctly")
PY

echo "[quickstart-smoke] success: ${SYSTEM_YAML}"
echo "[quickstart-smoke] outputs: ${OUTPUT_DIR}"
