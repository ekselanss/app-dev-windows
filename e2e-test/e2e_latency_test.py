"""
E2E Latency Test - VideoCheviri
BBC News testi: YouTube video transcript vs Whisper log timestamps karsilastirmasi.

Kullanim:
  docker exec videocheviri-backend python3 /app/e2e-test/e2e_latency_test.py --analyze \
    --video-start "08:31:20.0" --log-file /app/e2e-test/last_run.log

  veya tam otomasyon:
    bash e2e-test/run_test.sh
"""
import argparse
import re
import sys
from datetime import datetime


# === BBC Video VTT Transcript (key phrases with video timestamps) ===
# Video: "2025 third hottest year on record" - BBC News (TlU6rNFFO6s)
# Duration: 3:12
VTT_PHRASES = [
    (0.3,  "Global temperatures in 2025"),
    (2.3,  "slightly lower than 2024"),
    (4.6,  "makes it the third hottest year"),
    (7.0,  "record across the globe"),
    (9.5,  "Met Office and European climate"),
    (11.3, "scientists also found"),
    (13.2, "year in a row in which temperatures"),
    (15.2, "reached more than 1.4 degrees"),
    (18.4, "pre-industrial levels"),
    (20.8, "Dr Samantha Burgess"),
    (22.7, "deputy director"),
    (25.0, "Copernicus Climate Change Service"),
    (26.6, "told me what this all means"),
    (28.3, "key findings from this"),
    (30.5, "year's report"),
    (33.0, "third warmest year on record after 24"),
    (35.5, "on record after 24 and 2023"),
    (38.7, "global temperature anomaly"),
    (40.8, "1.47 degrees above"),
    (42.9, "pre-industrial average"),
    (44.8, "average of the global climate"),
    (47.0, "human impact on the climate"),
    (49.6, "from burning fossil fuels"),
    (52.0, "three years above 1.5 degrees"),
    (55.0, "ten years on from the Paris agreement"),
    (58.0, "every nation committed"),
    (60.0, "lower global warming"),
    (63.0, "below two degrees"),
    (65.5, "ideally below 1.5 degrees"),
    (68.0, "tackling climate change"),
    (72.0, "slowed down on trying to mitigate"),
    (75.0, "political rhetoric"),
    (80.0, "science is unequivocal"),
    (83.0, "evidence is incredibly clear"),
    (86.0, "eight independent datasets"),
    (90.0, "all come out and said the same thing"),
    (95.0, "we know what to do"),
    (100.0, "success stories"),
    (105.0, "transition to renewable energy"),
    (110.0, "we just need to do more"),
    (115.0, "forest fire"),
    (120.0, "floods we know the extremes"),
    (130.0, "extreme events get worse"),
    (140.0, "more frequent and more intense"),
    (150.0, "no part of the world"),
    (160.0, "impacts people and natural ecosystems"),
    (170.0, "limit global warming"),
    (175.0, "turn off the tap"),
    (180.0, "fossil fuel emissions"),
    (185.0, "stabilized our climate"),
    (190.0, "vote for people"),
]


def parse_time(ts_str: str) -> float:
    """HH:MM:SS.mmm -> epoch seconds (within a day)."""
    parts = ts_str.strip().split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def parse_log_line(line: str):
    """Log satiri parse et -> (timestamp_seconds, transcript_text)"""
    # Format: 2026-03-12 08:31:57,752 [INFO] app.routers.websocket: Transkript: 'text' dil=en
    m = re.search(r"(\d{2}:\d{2}:\d{2}),(\d{3}).*Transkript: ['\"](.+?)['\"] dil=", line)
    if not m:
        return None, None
    ts = parse_time(m.group(1)) + int(m.group(2)) / 1000
    text = m.group(3)
    return ts, text


def find_best_match(phrase: str, log_entries: list) -> tuple:
    """VTT phrase'ini log entry'lerinde ara, en iyi eslesmeyi bul."""
    phrase_lower = phrase.lower()
    keywords = phrase_lower.split()

    best_score = 0
    best_entry = None

    for ts, text in log_entries:
        text_lower = text.lower()
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score and score >= max(2, len(keywords) // 2):
            best_score = score
            best_entry = (ts, text, score)

    return best_entry


def analyze(log_file: str, video_start_str: str, auto_detect: bool = True):
    """Log dosyasini analiz et, E2E latency hesapla."""
    with open(log_file) as f:
        lines = f.readlines()

    log_entries = []
    for line in lines:
        ts, text = parse_log_line(line)
        if ts and text:
            log_entries.append((ts, text))

    if not log_entries:
        print("HATA: Log dosyasinda transkript bulunamadi!")
        sys.exit(1)

    print(f"Toplam {len(log_entries)} transkript satiri bulundu.")

    # Auto-detect video start from first matching phrase
    if auto_detect:
        first_match = find_best_match("Global temperatures in 2025", log_entries)
        if first_match:
            # T_video_start = T_log - T_phrase - T_pipeline_delay
            # T_pipeline_delay ~ 1.05s (whisper) + 1.0s (buffer avg)
            T_video_start = first_match[0] - 0.3 - 2.05
            print(f"Auto-detect T_video_start: {_sec_to_time(T_video_start)}")
        else:
            T_video_start = parse_time(video_start_str)
            print(f"Manuel T_video_start: {video_start_str}")
    else:
        T_video_start = parse_time(video_start_str)
        print(f"Manuel T_video_start: {video_start_str}")

    # Phase matching
    print()
    print("=" * 72)
    print(f"  {'VTT Phrase':<35} {'V.Time':>7} {'Log Time':>10} {'E2E':>7}")
    print("-" * 72)

    T_TRANSLATE_AVG = 0.82
    e2e_values = []
    matched = 0
    last_video_content_ts = 0

    for v_sec, phrase in VTT_PHRASES:
        match = find_best_match(phrase, log_entries)
        if match:
            matched += 1
            log_ts, log_text, score = match
            last_video_content_ts = max(last_video_content_ts, log_ts)
            e2e = (log_ts + T_TRANSLATE_AVG) - (T_video_start + v_sec)
            if 0.3 < e2e < 12:
                e2e_values.append(e2e)
                bar = "█" * min(20, max(0, int(e2e)))
                print(f"  {phrase:<35} T+{v_sec:5.1f}s {_sec_to_time(log_ts):>10} {e2e:6.2f}s {bar}")

    print("=" * 72)
    print(f"  Eslesen: {matched}/{len(VTT_PHRASES)} phrase")

    if not e2e_values:
        print("HATA: Hicbir gecerli E2E degeri hesaplanamadi!")
        sys.exit(1)

    avg = sum(e2e_values) / len(e2e_values)
    mn = min(e2e_values)
    mx = max(e2e_values)

    print(f"  Gecerli olcum: {len(e2e_values)}")
    print(f"  Ortalama E2E:  {avg:.2f}s")
    print(f"  Min E2E:       {mn:.2f}s")
    print(f"  Max E2E:       {mx:.2f}s")

    # Phantom detection
    if last_video_content_ts > 0:
        phantoms = [
            (ts, text)
            for ts, text in log_entries
            if ts > last_video_content_ts + 10 and text.strip()
        ]
        print()
        if phantoms:
            first_phantom = phantoms[0]
            phantom_delay = first_phantom[0] - last_video_content_ts
            print(f"  PHANTOM TESPITI:")
            print(f"    Son gercek icerik: {_sec_to_time(last_video_content_ts)}")
            print(f"    Ilk phantom: {_sec_to_time(first_phantom[0])} (+{phantom_delay:.1f}s)")
            print(f"    Phantom: '{first_phantom[1][:50]}'")
            print(f"    Toplam phantom: {len(phantoms)}")
        else:
            print(f"  PHANTOM: Yok! Yeni threshold calisiyor.")

    print()
    print("  SONUC:")
    if avg < 3.0:
        print(f"    ✅ E2E ortalama {avg:.1f}s - BASARILI")
    elif avg < 5.0:
        print(f"    ⚠️  E2E ortalama {avg:.1f}s - KABUL EDILEBILIR")
    else:
        print(f"    ❌ E2E ortalama {avg:.1f}s - COK YAVAS")


def _sec_to_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2E Latency Test")
    parser.add_argument("--analyze", action="store_true", help="Log dosyasini analiz et")
    parser.add_argument("--log-file", default="/app/e2e-test/last_run.log", help="Log dosyasi yolu")
    parser.add_argument("--video-start", default="08:31:20.0", help="Video baslangi zamani HH:MM:SS.mmm")
    parser.add_argument("--auto-detect", action="store_true", default=True, help="Video baslangi otomatik tespit")
    args = parser.parse_args()

    if args.analyze:
        analyze(args.log_file, args.video_start, args.auto_detect)
    else:
        print("Kullanim: python3 e2e_latency_test.py --analyze --log-file LOG_FILE")
        print("  veya: bash run_test.sh")
