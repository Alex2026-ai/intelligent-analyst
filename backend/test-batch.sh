#!/usr/bin/env bash
# Test script for batch processing with Firebase auth
# Usage: ./test-batch.sh <firebase_id_token>

set -euo pipefail

TOKEN="${1:-}"
API_URL="${2:-http://localhost:8080}"

if [ -z "$TOKEN" ]; then
    echo "Usage: ./test-batch.sh <firebase_id_token> [api_url]"
    echo ""
    echo "To get a Firebase ID token:"
    echo "1. Open http://localhost:5173 in browser"
    echo "2. Login with Firebase"
    echo "3. Open browser console and run:"
    echo "   await firebase.auth().currentUser.getIdToken()"
    echo ""
    echo "Or test via the UI by uploading a file."
    exit 1
fi

echo "Testing batch processing on: $API_URL"

# Health check
echo -e "\n▶ Health check:"
curl -s "$API_URL/health" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Status: {d[\"status\"]}, Env: {d.get(\"environment\", \"unknown\")}, Firestore: {d[\"firestore_available\"]}')"

# Submit batch
echo -e "\n▶ Submitting test batch..."
RESULT=$(curl -s -X POST "$API_URL/batch" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"data": [{"company_name": "Apple Inc"}, {"company_name": "Microsoft Corp"}, {"company_name": "xyz garbage 123"}]}')

echo "$RESULT" | python3 -m json.tool

# Get batches to verify
echo -e "\n▶ Recent batches:"
curl -s "$API_URL/batches?limit=3" \
    -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for b in data.get('batches', [])[:3]:
    counts = b.get('counts', {})
    print(f'  {b.get(\"trace_id\", \"?\")}: status={b.get(\"status\", \"?\")} duration={b.get(\"duration_seconds\", 0):.2f}s total={b.get(\"total\", 0)} l4={counts.get(\"l4_flagged\", \"?\")}')
"

echo -e "\n✅ Test complete"
