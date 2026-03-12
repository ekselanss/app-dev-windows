import io
import os
import logging
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


class WhisperService:
    """
    faster-whisper ile ses -> metin donusumu.
    openai-whisper'dan 4-8x daha hizli, ayni kalite.
    """

    def __init__(self, model_name: str = "base"):
        self.model_name = model_name
        self.model = None
        self.device = "cpu"
        # Dil kilidi: İngilizce kilitli başla (TRT World, YouTube EN içerik)
        # 5+ farklı dil tespiti gelirse kilit kırılır
        self._locked_language: str | None = "en"
        self._lock_votes: int = 5

    async def load_model(self):
        from faster_whisper import WhisperModel
        logger.info(f"faster-whisper '{self.model_name}' yukleniyor (CPU int8)...")
        cpu_threads = int(os.environ.get("CPU_THREADS", "6"))
        self.model = WhisperModel(
            self.model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=cpu_threads,
            num_workers=2,  # paralel decode worker
        )
        logger.info("faster-whisper hazir")

    def transcribe(self, audio_bytes: bytes) -> dict:
        if self.model is None:
            raise RuntimeError("Whisper modeli henuz yuklenmedi!")

        try:
            audio_array = self._bytes_to_numpy(audio_bytes)

            if len(audio_array) < 16000 * 0.5:
                return {"text": "", "language": "unknown", "confidence": 0.0}

            # Ses normalizasyonu: hoparlör→mikrofon yolu tutarsız seviye üretir
            audio_array = self._normalize(audio_array)

            # Ses enerjisi log: sessizlik mi yoksa gerçek ses mi?
            rms = float(np.sqrt(np.mean(audio_array ** 2)))
            logger.info(f"Ses RMS: {rms:.4f}")
            if rms < 0.02:
                logger.info("Ses çok sessiz, atlandı")
                return {"text": "", "language": "unknown", "confidence": 0.0}

            segments, info = self.model.transcribe(
                audio_array,
                task="transcribe",
                language=self._locked_language,
                temperature=0.0,
                best_of=1,
                beam_size=1,
                condition_on_previous_text=False,
                initial_prompt=None,
                compression_ratio_threshold=2.4,
                no_speech_threshold=0.45,
                log_prob_threshold=-1.0,
                vad_filter=True,
                vad_parameters={
                    "threshold": 0.5,
                    "min_speech_duration_ms": 200,
                    "min_silence_duration_ms": 400,
                    "speech_pad_ms": 200,
                },
            )

            segments = list(segments)
            text = " ".join(s.text for s in segments).strip()
            language = info.language
            confidence = round(max(0.0, min(1.0, info.language_probability)), 2)

            # Dil kilidi güncelle
            self._update_language_lock(language, confidence)

            # Halüsinasyon tespiti
            if text and self._is_hallucination(text):
                logger.warning(f"Halüsinasyon tespit edildi, atlandı: {text[:60]}")
                return {"text": "", "language": language, "confidence": confidence}

            logger.info(f"[{language} {confidence:.0%}] lock={self._locked_language}: {text[:80]}")
            return {"text": text, "language": language, "confidence": confidence}

        except Exception as e:
            logger.error(f"Transkript hatasi: {e}")
            return {"text": "", "language": "unknown", "confidence": 0.0, "error": str(e)}

    def _normalize(self, audio: np.ndarray) -> np.ndarray:
        """Ses seviyesini -1..1 aralığına normalize et."""
        peak = np.max(np.abs(audio))
        if peak > 0.01:          # sessizliği normalize etme
            audio = audio / peak * 0.95
        return audio

    def _update_language_lock(self, language: str, confidence: float):
        """3 ardışık yüksek-güven tespitte dili kilitle, farklı dil gelince kilidi sıfırla."""
        if confidence < 0.75:
            return
        if language == self._locked_language:
            self._lock_votes = min(self._lock_votes + 1, 10)
        else:
            if self._lock_votes <= 2:
                # Henüz kilitlenmemiş, yeni dile geç
                self._locked_language = language
                self._lock_votes = 1
            else:
                # Kilitli dili değiştirmek için 3 ardışık farklı tespit gerekir
                self._lock_votes -= 1
                if self._lock_votes == 0:
                    self._locked_language = language
                    self._lock_votes = 1

    def _is_hallucination(self, text: str) -> bool:
        """Tekrar eden kelime/ifade döngüsü tespiti."""
        words = text.split()
        if len(words) < 6:
            return False
        third = len(words) // 3
        p1 = " ".join(words[:third])
        p2 = " ".join(words[third:2 * third])
        if p1.strip() and p1.strip() == p2.strip():
            return True
        n = 4
        if len(words) >= n * 3:
            for i in range(len(words) - n):
                ngram = tuple(words[i:i + n])
                count = sum(
                    1 for j in range(len(words) - n)
                    if tuple(words[j:j + n]) == ngram
                )
                if count >= 3:
                    return True
        return False

    def _bytes_to_numpy(self, audio_bytes: bytes) -> np.ndarray:
        try:
            with io.BytesIO(audio_bytes) as buf:
                audio, sample_rate = sf.read(buf, dtype='float32')
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            if sample_rate != 16000:
                ratio = 16000 / sample_rate
                new_len = int(len(audio) * ratio)
                indices = np.linspace(0, len(audio) - 1, new_len)
                audio = np.interp(indices, np.arange(len(audio)), audio)
            return audio
        except Exception:
            audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
            return audio / 32768.0
