#!/bin/bash

# submit_result.sh
# Skrypt do manualnego weryfikowania zadania HitL i wysłania pod adres weryfikacyjny.

AIDEVS_VERIFY=${AIDEVS_VERIFY:?"Błąd: Zmienna AIDEVS_VERIFY nie jest ustawiona."}
AIDEVS_API_KEY=${AIDEVS_API_KEY:?"Błąd: Zmienna AIDEVS_API_KEY nie jest ustawiona."}
URL=${PROXY_AGENT_URL:?"Błąd: Zmienna PROXY_AGENT_URL nie jest ustawiona."}
SID=${SID:?"Błąd: Zmienna SID nie jest ustawiona."}

# echo "Podaj Twój Publiczny URL endpointa (Agent HTTP Server):"
# read URL
# 
# echo "Podaj dowolne SessionID, którego chcesz użyć podczas testu:"
# read SID

DATA=$(cat <<EOF
{
  "apikey": "$AIDEVS_API_KEY",
  "task": "proxy",
  "answer": {
    "url": "$URL",
    "sessionID": "$SID"
  }
}
EOF
)

echo "Wysyłanie powiadomienia na $AIDEVS_VERIFY ..."

curl -X POST "$AIDEVS_VERIFY" \
     -H "Content-Type: application/json" \
     -d "$DATA"

echo ""
echo "Gotowe!"
