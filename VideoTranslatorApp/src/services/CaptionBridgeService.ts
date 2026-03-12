/**
 * CaptionBridgeService — Platform-agnostic gerçek zamanlı konuşma tanıma
 *
 * Android: SpeechRecognizerModule (Android built-in SpeechRecognizer API)
 *          - Sadece RECORD_AUDIO izni gerekir
 *          - Ekran izleme YOK, AccessibilityService YOK
 *          - Tüm Android cihazlarda çalışır (API 10+)
 *          - ~300-500ms gecikme (on-device)
 *
 * iOS:     SpeechModule (SFSpeechRecognizer)
 *          - On-device, ~300-500ms gecikme
 */

import { NativeModules, NativeEventEmitter, Platform } from 'react-native';

const { SpeechRecognizerModule, SpeechModule } = NativeModules;

export type CaptionMode = 'speech' | 'unavailable';

type CaptionTextHandler = (text: string) => void;
type StatusHandler = (status: string) => void;

class CaptionBridgeService {
  private textHandler: CaptionTextHandler | null = null;
  private statusHandler: StatusHandler | null = null;
  private subscriptions: any[] = [];
  private _isRunning = false;

  getMode(): CaptionMode {
    if (Platform.OS === 'android' && SpeechRecognizerModule) return 'speech';
    if (Platform.OS === 'ios' && SpeechModule) return 'speech';
    return 'unavailable';
  }

  isAvailable(): boolean {
    return this.getMode() !== 'unavailable';
  }

  isRunning(): boolean {
    return this._isRunning;
  }

  async start(
    onText: CaptionTextHandler,
    onStatus: StatusHandler,
    languageCode = 'en-US',
  ): Promise<boolean> {
    if (this._isRunning) return true;
    this.textHandler = onText;
    this.statusHandler = onStatus;

    if (this.getMode() === 'unavailable') return false;
    return this._startSpeech(languageCode);
  }

  async stop(): Promise<void> {
    this._isRunning = false;
    this.subscriptions.forEach(s => s?.remove?.());
    this.subscriptions = [];

    const module = Platform.OS === 'android' ? SpeechRecognizerModule : SpeechModule;
    if (module) {
      try { await module.stopListening(); } catch {}
    }

    this.statusHandler?.('stopped');
  }

  // Android: SpeechRecognizerModule
  // iOS:     SpeechModule
  // İkisi aynı event formatını kullanır: onSpeechText / onSpeechStatus
  private async _startSpeech(languageCode: string): Promise<boolean> {
    const module = Platform.OS === 'android' ? SpeechRecognizerModule : SpeechModule;
    if (!module) return false;

    try {
      const emitter = new NativeEventEmitter(module);

      this.subscriptions.push(
        emitter.addListener('onSpeechText', ({ text }: { text: string }) => {
          if (text?.trim()) this.textHandler?.(text.trim());
        }),
      );

      this.subscriptions.push(
        emitter.addListener('onSpeechStatus', ({ status }: { status: string }) => {
          this.statusHandler?.(status);
        }),
      );

      this.subscriptions.push(
        emitter.addListener('onSpeechError', ({ error }: { error: string }) => {
          console.warn('[CaptionBridge] SpeechError:', error);
        }),
      );

      const started: boolean = await module.startListening(languageCode);
      this._isRunning = started;
      return started;
    } catch (e) {
      console.error('[CaptionBridge] Başlatma hatası:', e);
      return false;
    }
  }
}

export const captionBridge = new CaptionBridgeService();
