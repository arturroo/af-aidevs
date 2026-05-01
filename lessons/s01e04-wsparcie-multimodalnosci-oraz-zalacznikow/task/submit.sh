#!/bin/bash

# Phase 3: Submission Script for WSL/Linux
# Usage: ./submit.sh

# Load environment variables from .env
if [ -f .env ]; then
    # Filter out empty lines and comments, then export
    export $(grep -v '^#' .env | xargs)
fi

API_KEY="${AIDEVS_API_KEY}"
VERIFY_URL="${AIDEVS_VERIFY}"
DECLARATION_FILE="declaration.txt"

if [ ! -f "$DECLARATION_FILE" ]; then
    echo "Error: $DECLARATION_FILE not found. Run main.py first."
    exit 1
fi

# Read declaration and escape it for JSON
DECLARATION=$(cat "$DECLARATION_FILE")

# Construct JSON payload using jq if available, or simple printf
# We use python3 to safely escape the string for JSON if jq is not present
ESCAPED_DECLARATION=$(python3 -c "import json, sys; print(json.dumps(sys.stdin.read()))" <<EOF
$DECLARATION
EOF
)

# Build JSON body
JSON_BODY=$(cat <<EOF
{
  "apikey": "$API_KEY",
  "task": "sendit",
  "answer": {
    "declaration": $ESCAPED_DECLARATION
  }
}
EOF
)

echo "Submitting declaration to $VERIFY_URL..."
curl -X POST "$VERIFY_URL" \
     -H "Content-Type: application/json" \
     -d "$JSON_BODY" \
     | python3 -m json.tool
