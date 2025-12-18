#!/usr/bin/env sh
set -eu

# Seed 3 SOAP notes per seeded patient by calling the API endpoint, so that
# derived structured data is created exactly as in normal application flows.
#
# This script is designed to be safe to re-run:
# - It skips patients that already have >=3 notes.
#
# Requirements:
# - API must be reachable (default: http://localhost:8000)
# - python available (for JSON-safe payload generation)

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
EXAMPLES_DIR="${EXAMPLES_DIR:-/app/data/exampleFiles}"
PATIENT_LIMIT="${PATIENT_LIMIT:-100}"

echo "Seeding patient notes via API at ${API_BASE_URL} ..."

wait_for_health() {
  i=0
  while [ "$i" -lt 60 ]; do
    if curl -fsS "${API_BASE_URL}/health" >/dev/null 2>&1; then
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "API health check failed after 60s" >&2
  return 1
}

wait_for_health

PATIENTS_JSON="$(curl -fsS "${API_BASE_URL}/patients?limit=${PATIENT_LIMIT}&sort=name&order=asc")"
export PATIENTS_JSON

# Extract patient ids without jq (keep container deps minimal).
PATIENT_IDS="$(python - <<'PY'
import json, os, sys
payload = json.loads(os.environ["PATIENTS_JSON"])
items = payload.get("items") or []
for it in items:
    pid = it.get("id")
    if pid:
        print(pid)
PY
)"

COUNT="$(printf "%s\n" "${PATIENT_IDS}" | sed '/^$/d' | wc -l | tr -d ' ')"
if [ "${COUNT}" -ne 15 ]; then
  echo "Expected 15 patients from seed; got ${COUNT}. Aborting." >&2
  exit 1
fi

# Get the 45 synthetic SOAP files and map them 3-per-patient in sorted order.
SOAP_FILES="$(ls -1 "${EXAMPLES_DIR}"/ai_generated_soap_*.txt 2>/dev/null | sort || true)"
SOAP_COUNT="$(printf "%s\n" "${SOAP_FILES}" | sed '/^$/d' | wc -l | tr -d ' ')"
if [ "${SOAP_COUNT}" -lt 45 ]; then
  echo "Expected at least 45 ai_generated SOAP files under ${EXAMPLES_DIR}; got ${SOAP_COUNT}." >&2
  exit 1
fi

post_note() {
  patient_id="$1"
  soap_path="$2"

  payload="$(python - <<'PY'
import json, os
from datetime import datetime, timezone

patient_id = os.environ["PATIENT_ID"]
soap_path = os.environ["SOAP_PATH"]
text = open(soap_path, "r", encoding="utf-8").read()

body = {
    "taken_at": datetime.now(timezone.utc).isoformat(),
    "note_type": "soap",
    "content_text": text,
    "content_mime_type": "text/plain",
}
print(json.dumps(body))
PY
)"

  # Do not echo payload (may contain PHI in non-synthetic setups).
  code="$(curl -sS -o /dev/null -w "%{http_code}" \
    -H "Content-Type: application/json" \
    -d "${payload}" \
    "${API_BASE_URL}/patients/${patient_id}/notes" || true)"

  if [ "${code}" != "201" ]; then
    echo "Failed creating note for patient ${patient_id} (http=${code})" >&2
    exit 1
  fi
}

patient_idx=0
printf "%s\n" "${PATIENT_IDS}" | while IFS= read -r pid; do
  if [ -z "${pid}" ]; then
    continue
  fi

  # Check how many notes already exist for this patient.
  NOTES_JSON="$(curl -fsS "${API_BASE_URL}/patients/${pid}/notes?limit=100")"
  export NOTES_JSON
  existing="$(python - <<'PY'
import json, os
payload = json.loads(os.environ["NOTES_JSON"])
items = payload.get("items") or []
print(len(items))
PY
)"

  if [ "${existing}" -ge 3 ]; then
    echo "Patient ${patient_idx}/15 already has ${existing} notes; skipping."
    patient_idx=$((patient_idx + 1))
    continue
  fi

  # Assign 3 files deterministically.
  base=$((patient_idx * 3))
  f1="$(printf "%s\n" "${SOAP_FILES}" | sed -n "$((base + 1))p")"
  f2="$(printf "%s\n" "${SOAP_FILES}" | sed -n "$((base + 2))p")"
  f3="$(printf "%s\n" "${SOAP_FILES}" | sed -n "$((base + 3))p")"

  echo "Seeding notes for patient ${patient_idx}/15 ..."

  PATIENT_ID="${pid}" SOAP_PATH="${f1}" export PATIENT_ID SOAP_PATH
  post_note "${pid}" "${f1}"
  PATIENT_ID="${pid}" SOAP_PATH="${f2}" export PATIENT_ID SOAP_PATH
  post_note "${pid}" "${f2}"
  PATIENT_ID="${pid}" SOAP_PATH="${f3}" export PATIENT_ID SOAP_PATH
  post_note "${pid}" "${f3}"

  patient_idx=$((patient_idx + 1))
done

echo "Done seeding notes."


