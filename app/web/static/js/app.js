/**
 * KickTV — Dashboard JavaScript
 *
 * Handles WebSocket connections, chart updates, stream controls,
 * and all interactive dashboard functionality.
 */

// ── Globals ──────────────────────────────────────

let statusWs = null;
let metricsChart = null;
const chartData = {
    labels: [],
    cpu: [],
    ram: [],
    fps: [],
};
const MAX_CHART_POINTS = 60;
let hls = null;
let playerInitTimeout = null;

// ── Utility Functions ────────────────────────────

function escapeHtml(text) {
    const el = document.createElement('div');
    el.textContent = text;
    return el.innerHTML;
}

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '0s';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    const parts = [];
    if (h) parts.push(`${h}h`);
    if (m) parts.push(`${m}m`);
    if (s || !parts.length) parts.push(`${s}s`);
    return parts.join(' ');
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast align-items-center border-0 bg-${type === 'success' ? 'success' : type === 'danger' ? 'danger' : type === 'warning' ? 'warning' : 'primary'} bg-opacity-75 text-white show`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${escapeHtml(message)}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// ── Stream Control ───────────────────────────────

async function controlStream(action) {
    try {
        const url = action === 'skip' ? '/api/skip' : `/api/${action}`;
        const resp = await fetch(url, { method: 'POST' });
        const data = await resp.json();
        showToast(data.message || `${action} ejecutado`, data.success ? 'success' : 'warning');
    } catch (e) {
        showToast(`Error al ejecutar ${action}`, 'danger');
    }
}

// ── Gauge Update ─────────────────────────────────

function updateGauge(id, value, max = 100) {
    const fill = document.getElementById(`gauge-${id}-fill`);
    const label = document.getElementById(`gauge-${id}-value`);
    if (!fill || !label) return;

    const circumference = 2 * Math.PI * 52; // r=52
    const pct = Math.min(value / max, 1);
    const offset = circumference * (1 - pct);
    fill.style.strokeDashoffset = offset;

    if (id === 'fps') {
        label.textContent = Math.round(value);
    } else if (id === 'bitrate') {
        label.textContent = typeof value === 'string' ? value : `${value}k`;
    } else {
        label.textContent = `${Math.round(value)}%`;
    }
}

// ── Chart Setup ──────────────────────────────────

function initChart() {
    const ctx = document.getElementById('metrics-chart');
    if (!ctx) return;

    metricsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: 'CPU %',
                    data: chartData.cpu,
                    borderColor: '#06b6d4',
                    backgroundColor: 'rgba(6, 182, 212, 0.1)',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 0,
                },
                {
                    label: 'RAM %',
                    data: chartData.ram,
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 0,
                },
                {
                    label: 'FPS',
                    data: chartData.fps,
                    borderColor: '#22c55e',
                    backgroundColor: 'rgba(34, 197, 94, 0.05)',
                    fill: false,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 0,
                    yAxisID: 'y1',
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 500 },
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: {
                    labels: {
                        color: '#94a3b8',
                        font: { family: 'Inter', size: 11 },
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 20,
                    },
                },
            },
            scales: {
                x: {
                    display: false,
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: { color: '#64748b', font: { size: 10 } },
                },
                y1: {
                    position: 'right',
                    min: 0,
                    max: 60,
                    grid: { display: false },
                    ticks: { color: '#22c55e', font: { size: 10 } },
                },
            },
        },
    });
}

function addChartPoint(cpu, ram, fps) {
    const now = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    chartData.labels.push(now);
    chartData.cpu.push(cpu);
    chartData.ram.push(ram);
    chartData.fps.push(fps);

    if (chartData.labels.length > MAX_CHART_POINTS) {
        chartData.labels.shift();
        chartData.cpu.shift();
        chartData.ram.shift();
        chartData.fps.shift();
    }

    if (metricsChart) {
        metricsChart.update('none');
    }
}

// ── Status WebSocket ─────────────────────────────

function connectStatusWs() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    statusWs = new WebSocket(`${protocol}//${window.location.host}/ws/status`);

    statusWs.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'status') {
                updateDashboard(msg.data);
            }
        } catch (e) {
            console.error('WS parse error:', e);
        }
    };

    statusWs.onclose = () => {
        setTimeout(connectStatusWs, 3000);
    };

    statusWs.onerror = () => {
        statusWs.close();
    };
}

function updateDashboard(data) {
    // State badge
    const badge = document.getElementById('state-badge');
    if (badge) {
        const state = data.state || 'stopped';
        badge.textContent = state.toUpperCase();
        badge.className = `state-badge ${state}`;
    }

    // Status dot
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    if (dot) {
        dot.className = `status-dot ${data.state || 'stopped'}`;
    }
    if (label) {
        const stateLabels = {
            stopped: 'Offline',
            starting: 'Iniciando...',
            live: 'EN VIVO',
            reconnecting: 'Reconectando...',
            error: 'Error',
        };
        label.textContent = stateLabels[data.state] || data.state;
    }

    // Player logic
    const state = data.state || 'stopped';
    if (state === 'live' || state === 'starting' || state === 'reconnecting') {
        initPlayer();
    } else {
        stopPlayer();
    }

    // Metrics
    const setEl = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };

    setEl('metric-uptime', data.uptime || '0h 0m');
    setEl('metric-videos', data.total_videos_played || 0);
    setEl('metric-reconnects', data.reconnect_count || 0);
    setEl('metric-queue', data.queue_size || 0);

    // Queue badge in sidebar
    const qBadge = document.getElementById('queue-badge');
    if (qBadge) qBadge.textContent = data.queue_size || 0;

    // Current video
    if (data.current_video) {
        setEl('current-title', data.current_video.title || 'Sin título');
        setEl('current-author', data.current_video.author || '—');
        setEl('current-category', data.current_video.category || '—');
        setEl('current-provider', data.current_video.provider || '—');
    } else {
        setEl('current-title', 'Sin reproducción');
        setEl('current-author', '—');
        setEl('current-category', '—');
        setEl('current-provider', '—');
    }

    // Next video
    if (data.next_video) {
        setEl('next-title', data.next_video.title || '—');
        setEl('next-meta', `${data.next_video.category || ''} • ${data.next_video.provider || ''}`);
    } else {
        setEl('next-title', '—');
        setEl('next-meta', '');
    }

    // Gauges
    updateGauge('cpu', data.cpu_percent || 0, 100);
    updateGauge('ram', data.ram_percent || 0, 100);
    updateGauge('fps', data.fps || 0, 60);

    // Bitrate gauge
    let bitrateNum = 0;
    const br = data.bitrate || '0k';
    if (typeof br === 'string') {
        bitrateNum = parseFloat(br.replace(/[^0-9.]/g, '')) || 0;
    } else {
        bitrateNum = br;
    }
    updateGauge('bitrate', bitrateNum > 100 ? bitrateNum / 1000 : bitrateNum, 10);
    const brLabel = document.getElementById('gauge-bitrate-value');
    if (brLabel) brLabel.textContent = br;

    // Quick stats
    setEl('stat-dropped', data.frames_dropped || 0);
    setEl('stat-ffmpeg-ram', `${data.ffmpeg_ram_mb || 0} MB`);
    setEl('stat-disk', `${data.disk_percent || 0}%`);

    // Chart
    addChartPoint(data.cpu_percent || 0, data.ram_percent || 0, data.fps || 0);
}

// ── Fetch Initial Stats ──────────────────────────

async function fetchInitialStatus() {
    try {
        const resp = await fetch('/api/status');
        const result = await resp.json();
        if (result.data) {
            setEl('stat-errors', result.data.total_errors || 0);
            setEl('stat-history', result.data.history_count || 0);
            setEl('stat-providers', result.data.providers_active || 0);
        }
    } catch (e) {
        console.error('Error fetching status:', e);
    }
}

function setEl(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

// ── Recent Activity ──────────────────────────────

async function loadActivity() {
    try {
        const resp = await fetch('/api/history?limit=10');
        const data = await resp.json();
        const items = data.data?.items || [];
        const list = document.getElementById('activity-list');
        if (!list) return;

        if (items.length === 0) {
            list.innerHTML = '<div class="activity-empty"><i class="bi bi-inbox"></i><p>Sin actividad reciente</p></div>';
            return;
        }

        list.innerHTML = items.map(item => `
            <div class="activity-item">
                <div class="activity-icon play"><i class="bi bi-play-fill"></i></div>
                <div>
                    <div class="activity-text">${escapeHtml(item.title || 'Sin título')}</div>
                    <div class="activity-time">${item.played_at ? new Date(item.played_at).toLocaleString('es') : '—'} • ${item.provider || ''}</div>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Error loading activity:', e);
    }
}

// ── Sidebar Toggle ───────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    if (toggle && sidebar) {
        toggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }
});

// ── Local Preview Player ─────────────────────────

function initPlayer() {
    const video = document.getElementById('preview-video');
    const container = document.getElementById('preview-container');
    const overlay = document.getElementById('preview-overlay');
    const msg = document.getElementById('preview-msg');
    
    if (!video || !container) return;
    
    // Only init if not already playing or trying to load
    if (hls || (video.src && video.src.includes('m3u8'))) return;
    
    container.style.display = 'block';
    overlay.style.display = 'flex';
    msg.textContent = 'Cargando stream local...';

    const sourceUrl = '/hls/stream.m3u8';

    if (Hls.isSupported()) {
        hls = new Hls({
            maxBufferLength: 10,
            manifestLoadingTimeOut: 10000,
            manifestLoadingMaxRetry: 5,
            levelLoadingTimeOut: 10000,
        });
        
        hls.loadSource(sourceUrl);
        hls.attachMedia(video);
        
        hls.on(Hls.Events.MANIFEST_PARSED, function() {
            video.play().catch(e => console.log('Autoplay blocked', e));
        });
        
        hls.on(Hls.Events.FRAG_BUFFERED, function() {
            if (overlay.style.display !== 'none') {
                overlay.style.display = 'none';
            }
        });

        hls.on(Hls.Events.ERROR, function(event, data) {
            if (data.fatal) {
                switch (data.type) {
                    case Hls.ErrorTypes.NETWORK_ERROR:
                        console.log('Network error, retrying...');
                        msg.textContent = 'Buscando señal...';
                        overlay.style.display = 'flex';
                        hls.startLoad();
                        break;
                    case Hls.ErrorTypes.MEDIA_ERROR:
                        console.log('Media error, recovering...');
                        hls.recoverMediaError();
                        break;
                    default:
                        console.log('Unrecoverable error, destroying player');
                        stopPlayer();
                        // Try to restart in a few seconds
                        clearTimeout(playerInitTimeout);
                        playerInitTimeout = setTimeout(initPlayer, 5000);
                        break;
                }
            }
        });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        // Safari fallback
        video.src = sourceUrl;
        video.addEventListener('loadedmetadata', function() {
            video.play();
        });
        video.addEventListener('playing', function() {
            overlay.style.display = 'none';
        });
        video.addEventListener('error', function() {
            stopPlayer();
            clearTimeout(playerInitTimeout);
            playerInitTimeout = setTimeout(initPlayer, 5000);
        });
    }
}

function stopPlayer() {
    const container = document.getElementById('preview-container');
    const video = document.getElementById('preview-video');
    
    if (hls) {
        hls.destroy();
        hls = null;
    }
    
    if (video) {
        video.removeAttribute('src');
        video.load();
    }
    
    if (container) {
        container.style.display = 'none';
    }
    
    clearTimeout(playerInitTimeout);
}

// ── Dashboard Init ───────────────────────────────

function initDashboard() {
    initChart();
    connectStatusWs();
    fetchInitialStatus();
    loadActivity();

    // Refresh activity every 30s
    setInterval(loadActivity, 30000);
    // Refresh stats every 15s
    setInterval(fetchInitialStatus, 15000);
}
