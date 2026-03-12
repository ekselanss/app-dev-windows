import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = '@videocheviri_server_url';
const DEFAULT_URL = 'https://ski-nearby-cruise-drawn.trycloudflare.com';

let cachedUrl: string | null = null;

/**
 * Sunucu URL'sini AsyncStorage'dan yükle.
 * Uygulama başlangıcında bir kez çağrılır.
 */
export async function loadServerUrl(): Promise<string> {
  try {
    const saved = await AsyncStorage.getItem(STORAGE_KEY);
    cachedUrl = saved || DEFAULT_URL;
  } catch {
    cachedUrl = DEFAULT_URL;
  }
  return cachedUrl;
}

/**
 * Sunucu URL'sini güncelle ve kaydet.
 * Örnek: "https://abc123.ngrok-free.app" veya "http://192.168.1.50:8000"
 */
export async function saveServerUrl(url: string): Promise<void> {
  // Sondaki slash'ı kaldır
  const cleaned = url.replace(/\/+$/, '');
  cachedUrl = cleaned;
  await AsyncStorage.setItem(STORAGE_KEY, cleaned);
}

/**
 * Mevcut sunucu URL'sini getir (senkron, cache'den).
 * loadServerUrl() daha önce çağrılmış olmalı.
 */
export function getServerUrl(): string {
  return cachedUrl || DEFAULT_URL;
}

/**
 * WebSocket URL'lerini oluştur.
 */
export function getWsUrls() {
  const base = getServerUrl();
  const wsBase = base.replace(/^http/, 'ws');
  return {
    translate: `${wsBase}/ws/translate`,
    fast: `${wsBase}/ws/fast`,
    http: base,
  };
}
