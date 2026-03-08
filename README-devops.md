# VideoÇeviri — DevOps Kurulum Kılavuzu

## Gereksinimler

- Docker 24+
- Docker Compose v2
- kubectl 1.28+
- Kubernetes kümesi (Minikube, k3s veya bulut)

---

## Docker ile Yerel Çalıştırma

### 1. Ortam Değişkenlerini Ayarla

```bash
cp .env.example .env
# .env dosyasına DEEPL_API_KEY değerini yaz
```

`.env` örneği:
```
DEEPL_API_KEY=your-deepl-api-key-here
```

### 2. Sadece Backend'i Başlat

```bash
docker compose up backend
```

Uygulama `http://localhost:8000` adresinde çalışır.
Sağlık kontrolü: `http://localhost:8000/api/health`

### 3. Nginx ile Başlat (Opsiyonel)

```bash
docker compose --profile with-nginx up
```

Nginx, port 80 üzerinden backend'e yönlendirir.

### 4. Arka Planda Çalıştır

```bash
docker compose up -d backend
docker compose logs -f backend
```

### 5. Durdur

```bash
docker compose down
docker compose down -v  # volume'ları da sil (Whisper cache temizlenir)
```

### 6. İmajı Manuel Build Et

```bash
docker build -t ekselanss/videocheviri-backend:latest ./translation-backend
```

---

## Kubernetes Deployment

### 1. Namespace Oluştur

```bash
kubectl apply -f kubernetes/namespace.yaml
```

### 2. Secret'ı Güncelle

`kubernetes/secret.yaml` dosyasında `DEEPL_API_KEY` base64 formatındadır. Kendi anahtarını eklemek için:

```bash
echo -n "your-actual-deepl-api-key" | base64
```

Çıktıyı `kubernetes/secret.yaml` dosyasındaki `DEEPL_API_KEY` değeriyle değiştir, ardından uygula:

```bash
kubectl apply -f kubernetes/secret.yaml
```

### 3. Tüm Kaynakları Uygula

```bash
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secret.yaml
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml
kubectl apply -f kubernetes/ingress.yaml
```

Ya da tek komutla:

```bash
kubectl apply -f kubernetes/
```

### 4. Deployment Durumunu Kontrol Et

```bash
kubectl get all -n videocheviri
kubectl rollout status deployment/videocheviri-backend -n videocheviri
```

### 5. Pod Loglarını İzle

```bash
kubectl logs -f deployment/videocheviri-backend -n videocheviri
```

### 6. Ingress ile Erişim (videocheviri.local)

`/etc/hosts` dosyasına ekle:
```
<INGRESS_IP>  videocheviri.local
```

Ingress IP'yi almak için:
```bash
kubectl get ingress -n videocheviri
```

### 7. Port Forward ile Doğrudan Erişim

```bash
kubectl port-forward svc/videocheviri-backend 8000:8000 -n videocheviri
```

### 8. Deployment'ı Güncelle (Yeni İmaj)

```bash
kubectl set image deployment/videocheviri-backend \
  backend=ekselanss/videocheviri-backend:latest \
  -n videocheviri
kubectl rollout status deployment/videocheviri-backend -n videocheviri
```

### 9. Kaynakları Sil

```bash
kubectl delete -f kubernetes/
kubectl delete namespace videocheviri
```

---

## CI/CD Pipeline

GitHub Actions otomatik olarak şu işleri yapar:

| Job | Tetikleyici | Açıklama |
|-----|------------|----------|
| `test-backend` | Her push/PR | Python bağımlılıklarını kurar, import smoke testi çalıştırır |
| `build-docker` | Sadece `main` push | Docker imajını build eder, Docker Hub'a push eder |
| `lint-mobile` | Her push/PR | ESLint ile TypeScript kodunu kontrol eder |

### Docker Hub Secrets Ayarı

GitHub repo Settings > Secrets and variables > Actions altına ekle:

- `DOCKER_USERNAME` — Docker Hub kullanıcı adın
- `DOCKER_TOKEN` — Docker Hub Access Token (Settings > Security > Access Tokens)

---

## Mimari Notlar

- Whisper CPU modunda çalışır, GPU gerekmez.
- `emptyDir` volume: Pod yeniden başladığında Whisper modeli tekrar indirilir. Kalıcı cache için `emptyDir` yerine `PersistentVolumeClaim` kullan.
- WebSocket bağlantıları (`/ws/translate/{session_id}`) için Ingress'te `proxy-read-timeout` 3600 saniyeye ayarlanmıştır.
- DRM'li içerikler (Spotify, Netflix) AudioPlaybackCapture tarafından yakalanamaz — Android kısıtlaması.
