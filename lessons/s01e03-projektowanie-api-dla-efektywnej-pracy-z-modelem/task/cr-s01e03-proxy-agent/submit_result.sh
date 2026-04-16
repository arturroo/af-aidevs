#!/bin/bash

# submit_result.sh
# Skrypt do manualnego weryfikowania zadania HitL i wysłania pod adres weryfikacyjny.

AIDEVS_API_VERIFY=${AIDEVS_API_VERIFY:?"Błąd: Zmienna AIDEVS_API_VERIFY nie jest ustawiona."}
AIDEVS_API_KEY=${AIDEVS_API_KEY:?"Błąd: Zmienna AIDEVS_API_KEY nie jest ustawiona."}

echo "Podaj kod z STDOUT agenta (Confirmation Code):"
read CODE

echo "Podaj Twój Publiczny URL endpointa (Agent HTTP Server):"
read URL

echo "Podaj dowolne SessionID użyte podczas testu:"
read SESSIONID

DATA=$(cat <<EOF
{
  "apikey": "$AIDEVS_API_KEY",
  "task": "proxy",
  "answer": {
    "url": "$URL",
    "sessionID": "$SESSIONID",
    "code": "$CODE"
  }
}
EOF
)

echo "Wysyłanie na $AIDEVS_API_VERIFY ..."

curl -X POST "$AIDEVS_API_VERIFY" \
     -H "Content-Type: application/json" \
     -d "$DATA"

echo ""
echo "Gotowe!"
