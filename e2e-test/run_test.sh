#!/bin/bash
# E2E Latency Test - Tam Otomasyon
# VideoCheviri uygulamasinin BBC News videosu ile gercek E2E latency testi
#
# Gereksinimler:
#   - Docker container "videocheviri-backend" calisir durumda
#   - ADB bagli Android cihaz
#   - Brave browser yuklu
#   - Overlay + Mikrofon izinleri verilmis
#
# Kullanim: bash e2e-test/run_test.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/last_run.log"
RESULT_FILE="$SCRIPT_DIR/last_result.txt"
VIDEO_URL="https://www.youtube.com/watch?v=TlU6rNFFO6s"
APP_PKG="com.videotranslatorapp"
BRAVE_PKG="com.brave.browser"
COLLECT_SECONDS=120

echo "============================================"
echo "  VideoCheviri E2E Latency Test"
echo "  BBC News: 2025 third hottest year"
echo "============================================"
echo ""

# --- 1. Pre-flight checks ---
echo "[1/8] Pre-flight kontrol..."
docker inspect videocheviri-backend --format='{{.State.Health.Status}}' 2>/dev/null | grep -q healthy || {
  echo "HATA: Backend container saglikli degil!"
  echo "  docker compose up -d --build backend"
  exit 1
}
adb devices 2>/dev/null | grep -q "device$" || {
  echo "HATA: ADB cihaz bulunamadi!"
  exit 1
}
echo "  Backend: healthy"
echo "  ADB: connected"

# --- 2. Izinleri ver ---
echo "[2/8] Izinler kontrol ediliyor..."
adb shell pm grant $APP_PKG android.permission.RECORD_AUDIO 2>/dev/null || true
adb shell appops set $APP_PKG SYSTEM_ALERT_WINDOW allow 2>/dev/null || true
echo "  RECORD_AUDIO: granted"
echo "  SYSTEM_ALERT_WINDOW: allow"

# --- 3. Tum uygulamalari durdur ---
echo "[3/8] Uygulamalar durduruluyor..."
adb shell am force-stop $APP_PKG 2>/dev/null
adb shell am force-stop $BRAVE_PKG 2>/dev/null
adb shell am force-stop com.google.android.youtube 2>/dev/null
sleep 1
echo "  Temizlendi"

# --- 4. VideoTranslatorApp baslat ---
echo "[4/8] VideoTranslatorApp baslatiliyor..."
adb shell am start -n $APP_PKG/.MainActivity 2>/dev/null | head -1
sleep 5

# LogBox banner'i kapat (React Native dev mode)
# X butonu: [965,2231][1020,2286] merkez=(992,2258)
echo "  LogBox dismiss ediliyor..."
adb shell input tap 992 2258 2>/dev/null
sleep 2

# BASLAT butonuna tap: [403,2029][678,2304] merkez=(540,2167)
T_TAP=$(date '+%H:%M:%S.%3N')
T_LOG_START=$(date '+%Y-%m-%dT%H:%M:%S')
adb shell input tap 540 2167
echo "  App BASLAT tap: $T_TAP"
sleep 3

# Backend chunk geliyor mu kontrol
CHUNKS=$(docker logs videocheviri-backend --since=5s 2>&1 | grep -c "Ses RMS" || true)
CHUNKS=$(echo "$CHUNKS" | tr -d '[:space:]')
CHUNKS=${CHUNKS:-0}
if [ "$CHUNKS" -eq 0 ] 2>/dev/null; then
  echo "  UYARI: Chunk gelmiyor, tekrar tap deneniyor..."
  adb shell input tap 540 2167
  sleep 4
  CHUNKS=$(docker logs videocheviri-backend --since=5s 2>&1 | grep -c "Ses RMS" || true)
  CHUNKS=$(echo "$CHUNKS" | tr -d '[:space:]')
  CHUNKS=${CHUNKS:-0}
fi
echo "  Chunk durumu: $CHUNKS chunk/5s"

# --- 5. BBC videoyu Brave'de ac ---
echo "[5/8] BBC videosu Brave'de aciliyor..."
T_VIDEO_OPEN=$(date '+%H:%M:%S.%3N')
adb shell am start -a android.intent.action.VIEW -d "$VIDEO_URL" $BRAVE_PKG 2>/dev/null | head -1
echo "  Video URL acildi: $T_VIDEO_OPEN"
echo "  YouTube yukleme bekleniyor (10s)..."
sleep 10

# Video play butonuna tap (thumbnail center)
T_PLAY=$(date '+%H:%M:%S.%3N')
adb shell input tap 540 350
echo "  Play tap: $T_PLAY"
sleep 2

# --- 6. Sesi yukselt ---
echo "[6/8] Telefon sesi yukseltiyor..."
for i in $(seq 1 15); do
  adb shell input keyevent KEYCODE_VOLUME_UP 2>/dev/null
done
echo "  Ses max"

# --- 7. Log toplama (COLLECT_SECONDS saniye) ---
echo "[7/8] Log toplama basliyor ($COLLECT_SECONDS saniye)..."
echo "  T_video_play: $T_PLAY"
echo ""

# Eski log dosyasini temizle
> "$LOG_FILE"

# COLLECT_SECONDS saniye bekle, periyodik progress goster
for i in $(seq 1 $COLLECT_SECONDS); do
  sleep 1
  if [ $((i % 15)) -eq 0 ]; then
    COUNT=$(docker logs videocheviri-backend --since="$T_LOG_START" 2>&1 | grep "Transkript:" | grep -v "''" | wc -l)
    COUNT=$(echo "$COUNT" | tr -d '[:space:]')
    echo "  [$i/${COLLECT_SECONDS}s] $COUNT transkript toplandi"
  fi
done

# Tum loglari kaydet
docker logs videocheviri-backend --since="$T_LOG_START" 2>&1 | grep "Transkript:" | grep -v "''" > "$LOG_FILE"
COUNT=$(wc -l < "$LOG_FILE" 2>/dev/null || echo "0")
COUNT=$(echo "$COUNT" | tr -d '[:space:]')
echo "  Toplam: $COUNT transkript"

# --- 8. Analiz ---
echo "[8/8] E2E analizi calistiriliyor..."
echo ""

# Python script ve log dosyasini container'a kopyala (cat|tee - docker cp Windows'ta sorunlu)
cat "$SCRIPT_DIR/e2e_latency_test.py" | docker exec -i videocheviri-backend tee /app/e2e-test/e2e_latency_test.py > /dev/null
cat "$LOG_FILE" | docker exec -i videocheviri-backend tee /app/e2e-test/last_run.log > /dev/null

docker exec videocheviri-backend python3 /app/e2e-test/e2e_latency_test.py \
  --analyze \
  --log-file /app/e2e-test/last_run.log \
  --video-start "$T_PLAY" 2>&1 | tee "$RESULT_FILE"

echo ""
echo "============================================"
echo "  Loglar: $LOG_FILE"
echo "  Sonuc:  $RESULT_FILE"
echo "============================================"

# Cleanup: Brave'i durdur (app acik kalsin)
echo ""
echo "Uygulamalar durduruluyor..."
adb shell am force-stop $BRAVE_PKG 2>/dev/null
echo "Bitti."
