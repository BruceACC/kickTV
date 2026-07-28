# KickTV — Canal de Televisión Automático 24/7

<p align="center">
  <strong>Sistema automatizado para transmitir contenido de video continuamente a Kick vía RTMPS usando FFmpeg.</strong>
</p>

---

## ✨ Características

- 🎬 **Streaming 24/7** — Transmisión continua sin interrupciones
- 🔄 **Auto-recuperación** — Detecta errores y se reinicia automáticamente
- 🎯 **Cola Inteligente** — No repite videos, alterna categorías, autores y duraciones
- 🔌 **Proveedores Modulares** — Pexels, Pixabay, Internet Archive, Reddit, YouTube CC, Local
- 📊 **Dashboard Web** — Panel de control moderno con métricas en tiempo real
- 🔧 **API REST** — Control total vía endpoints HTTP
- 📝 **Logs en Tiempo Real** — WebSocket para streaming de logs
- 🐳 **Docker Ready** — Dockerfile y docker-compose incluidos

## 📋 Requisitos

- **Python 3.10+**
- **FFmpeg** (con soporte RTMPS/OpenSSL)
- **Cuenta de Kick** con stream key

## 🚀 Instalación Rápida

### 1. Clonar el proyecto

```bash
cd c:\Project\kick
```

### 2. Ejecutar el script de instalación

```bash
python scripts/install.py
```

### 3. Configurar

Edita el archivo `.env` con tu stream key de Kick y API keys opcionales:

```env
STREAM_URL=rtmps://fa723fc1b171.global-contribute.live-video.net/app
STREAM_KEY=tu_stream_key_aqui

# Opcional: API keys para más proveedores
PEXELS_API_KEY=tu_pexels_key
PIXABAY_API_KEY=tu_pixabay_key
```

### 4. Ejecutar

```bash
python run.py
```

### 5. Abrir el dashboard

Navega a **http://localhost:8000**

---

## 🐳 Docker

```bash
# Construir y ejecutar
docker-compose up -d

# Ver logs
docker-compose logs -f kicktv

# Detener
docker-compose down
```

---

## 📁 Estructura del Proyecto

```
kick/
├── app/
│   ├── main.py                 # FastAPI app factory
│   ├── config.py               # Settings (.env)
│   ├── database.py             # SQLite async
│   ├── models.py               # Pydantic models
│   ├── logger.py               # Logging setup
│   ├── core/
│   │   ├── stream_engine.py    # FFmpeg manager
│   │   ├── queue_manager.py    # Smart queue
│   │   ├── scheduler.py        # Background jobs
│   │   └── system_monitor.py   # CPU/RAM metrics
│   ├── providers/
│   │   ├── base.py             # Abstract provider
│   │   ├── local.py            # Local files
│   │   ├── pexels.py           # Pexels API
│   │   ├── pixabay.py          # Pixabay API
│   │   ├── archive.py          # Internet Archive
│   │   ├── youtube.py          # YouTube (CC)
│   │   └── reddit.py           # Reddit
│   ├── api/
│   │   ├── routes.py           # REST endpoints
│   │   └── websocket.py        # WebSocket
│   ├── web/
│   │   ├── views.py            # Jinja2 routes
│   │   ├── templates/          # HTML templates
│   │   └── static/             # CSS, JS
│   └── utils/
│       ├── video.py            # Video tools
│       └── helpers.py          # Misc helpers
├── data/                       # Runtime data
├── logs/                       # Log files
├── .env.example                # Config template
├── requirements.txt            # Python deps
├── Dockerfile                  # Docker image
├── docker-compose.yml          # Docker Compose
└── run.py                      # Entry point
```

---

## 🔌 API Endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/status` | GET | Estado del stream y métricas |
| `/api/start` | POST | Iniciar transmisión |
| `/api/stop` | POST | Detener transmisión |
| `/api/restart` | POST | Reiniciar transmisión |
| `/api/skip` | POST | Saltar video actual |
| `/api/queue` | GET | Cola de reproducción |
| `/api/queue/fill` | POST | Rellenar cola |
| `/api/queue/clear` | POST | Vaciar cola |
| `/api/history` | GET | Historial de reproducciones |
| `/api/providers` | GET | Lista de proveedores |
| `/api/providers/{name}` | PUT | Activar/desactivar proveedor |
| `/api/settings` | GET | Configuración actual |
| `/api/categories` | GET/POST | Gestión de categorías |
| `/api/logs` | GET | Últimos logs |
| `/api/stats` | GET | Estadísticas históricas |
| `/api/errors` | GET | Errores recientes |

### WebSocket

| Endpoint | Descripción |
|----------|-------------|
| `/ws/status` | Actualizaciones de estado en tiempo real |
| `/ws/logs` | Stream de logs en tiempo real |

---

## 🎯 Proveedores

| Proveedor | API Key | Descripción |
|-----------|---------|-------------|
| **Local** | No | Videos del directorio `data/videos/` |
| **Pexels** | Sí | Stock videos gratuitos de Pexels.com |
| **Pixabay** | Sí | Stock videos gratuitos de Pixabay.com |
| **Internet Archive** | No | Películas y documentales de dominio público |
| **YouTube** | No | Videos Creative Commons via yt-dlp (deshabilitado por defecto) |
| **Reddit** | No | Videos públicos de subreddits temáticos |

### Agregar un Nuevo Proveedor

1. Crea un archivo en `app/providers/tu_proveedor.py`
2. Hereda de `BaseProvider`
3. Implementa `search()`, `random()`, `next_video()`
4. Regístralo en `app/main.py` → `_register_providers()`

---

## 📂 Categorías

| Categoría | Keywords |
|-----------|----------|
| Terror | horror, scary, creepy |
| Curiosidades | facts, interesting, amazing |
| Documentales | documentary, investigation |
| Naturaleza | nature, landscape, ocean |
| Animales | animals, wildlife, pets |
| Gaming | gaming, videogames, gameplay |
| Tecnología | technology, gadgets, AI |
| Espacio | space, universe, NASA |
| Películas Clásicas | classic film, vintage, public domain |
| Memes | funny, humor, comedy |
| Shorts | short film, clip |
| Trailers | trailer, teaser, preview |
| Ciencia | science, physics, experiment |

---

## ⚙️ Configuración (.env)

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `STREAM_URL` | URL RTMPS de Kick | `rtmps://...` |
| `STREAM_KEY` | Tu stream key | — |
| `BITRATE` | Bitrate de video | `4500k` |
| `FPS` | Frames por segundo | `30` |
| `RESOLUTION` | Resolución de salida | `1920x1080` |
| `PRESET` | Preset de x264 | `veryfast` |
| `DASHBOARD_PORT` | Puerto del dashboard | `8000` |

---

## 📝 Licencia

Este proyecto es software libre para uso personal y educativo.
Los contenidos reproducidos deben cumplir con las licencias de cada fuente.
