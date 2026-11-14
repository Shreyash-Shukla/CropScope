"""Interactive 3D real-time Earth globe with astronomical solar terminator.

Crafted strictly according to the Watched.earth design system and reference architecture:
- Exact ECEF / Three.js coordinate math matching SphereGeometry UV conventions
- Static Earth mesh fixed in Earth-Centered, Earth-Fixed (ECEF) frame
- Real-time astronomical solar terminator driven by IAU 1982 GMST and J2000 solar ephemeris
- True day/night darkness movement across continents matching real-time UTC
- Graded photoreal day side, deep ink oceans, real sun specular glint
- Sodium-amber night city lights, soft warm twilight transition band
- Floating cloud shell with gentle atmospheric drift
- Exponential Rayleigh atmosphere rim on the sunlit limb
- Watched.earth signal-orange crosshair reticle on the target field with lock-in animation
- Smooth spherical camera flight along great circle arcs
- Instrument bezel viewport with 8px corner L-ticks and top-edge ruler ticks
"""

import base64
import datetime
import functools
import json
import math
import os
from typing import Tuple


# ── Astronomical Solar Ephemeris (Exact IAU 1982 GMST & J2000 Ephemeris) ─────

def julian_date(timestamp_ms: float) -> float:
    """Calculate Julian Date from Unix epoch milliseconds."""
    return timestamp_ms / 86400000.0 + 2440587.5


def gmst(timestamp_ms: float) -> float:
    """Greenwich Mean Sidereal Time in radians (IAU 1982)."""
    jd = julian_date(timestamp_ms)
    t = (jd - 2451545.0) / 36525.0
    g = (
        -6.2e-6 * t**3
        + 0.093104 * t**2
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 67310.54841
    )
    g = ((g * (math.pi / 180.0)) / 240.0) % (2.0 * math.pi)
    return g + 2.0 * math.pi if g < 0 else g


def sun_eci(timestamp_ms: float) -> Tuple[float, float, float]:
    """Unit vector from Earth centre to the Sun in ECI (Astronomical Almanac)."""
    n = julian_date(timestamp_ms) - 2451545.0
    l_deg = (280.46 + 0.9856474 * n) % 360.0
    g_rad = ((357.528 + 0.9856003 * n) % 360.0) * (math.pi / 180.0)
    lambda_rad = (
        l_deg + 1.915 * math.sin(g_rad) + 0.02 * math.sin(2.0 * g_rad)
    ) * (math.pi / 180.0)
    eps_rad = (23.439 - 0.0000004 * n) * (math.pi / 180.0)
    return (
        math.cos(lambda_rad),
        math.cos(eps_rad) * math.sin(lambda_rad),
        math.sin(eps_rad) * math.sin(lambda_rad),
    )


def eci_to_ecef(x: float, y: float, z: float, timestamp_ms: float) -> Tuple[float, float, float]:
    """Rotate an ECI vector into Earth-Centered Earth-Fixed (ECEF) by GMST."""
    g = gmst(timestamp_ms)
    c = math.cos(g)
    s = math.sin(g)
    return c * x + s * y, -s * x + c * y, z


def sun_ecef_unit(timestamp_ms: float) -> Tuple[float, float, float]:
    """Unit vector toward the Sun in ECEF frame."""
    x, y, z = sun_eci(timestamp_ms)
    ex, ey, ez = eci_to_ecef(x, y, z, timestamp_ms)
    r = math.hypot(ex, ey, ez) or 1.0
    return ex / r, ey / r, ez / r


def sun_direction_world(timestamp_ms: float) -> Tuple[float, float, float]:
    """Unit vector toward the Sun in the Three.js WORLD frame.

    Conventions (matches Watched.earth src/lib/geo.ts & geo3.ts):
      ECEF (x, y, z) -> World (x, z, -y)
      +Y is North Pole, Lat 0 / Lon 0 -> +X, Lon +90E -> -Z.
    """
    ex, ey, ez = sun_ecef_unit(timestamp_ms)
    return ex, ez, -ey


def lat_lon_to_world(lat_deg: float, lon_deg: float, radius: float = 1.0) -> Tuple[float, float, float]:
    """Map geographic coordinates (lat, lon) to Three.js World coordinates.

    Matches Watched.earth and Three.js SphereGeometry UV parameterization:
      lat: [-90, +90], lon: [-180, +180]
      x = radius * cos(lat) * cos(lon)
      y = radius * sin(lat)
      z = -radius * cos(lat) * sin(lon)
    """
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    c = math.cos(lat)
    return radius * c * math.cos(lon), radius * math.sin(lat), -radius * c * math.sin(lon)


def compute_subsolar_point(dt: datetime.datetime | None = None) -> Tuple[float, float]:
    """Calculate the subsolar point (latitude, longitude) where the sun is directly overhead.

    Returns (subsolar_lat_deg, subsolar_lon_deg).
    """
    if dt is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)

    ms = dt.timestamp() * 1000.0
    ex, ey, ez = sun_ecef_unit(ms)
    sub_lat = math.degrees(math.asin(max(-1.0, min(1.0, ez))))
    sub_lon = math.degrees(math.atan2(ey, ex))
    return round(sub_lat, 4), round(sub_lon, 4)


def is_location_sunlit(
    latitude: float,
    longitude: float,
    dt: datetime.datetime | None = None,
) -> Tuple[bool, float]:
    """Determine whether a given location is currently in daylight or night shadow.

    Returns (is_sunlit, solar_elevation_deg).
    Solar elevation >= 0 is daylight, -6 to 0 is civil twilight, < -6 is night.
    """
    if dt is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)

    ms = dt.timestamp() * 1000.0
    ex, ey, ez = sun_ecef_unit(ms)

    lat_rad = math.radians(latitude)
    lon_rad = math.radians(longitude)
    c = math.cos(lat_rad)

    dot = c * math.cos(lon_rad) * ex + c * math.sin(lon_rad) * ey + math.sin(lat_rad) * ez
    dot = max(-1.0, min(1.0, dot))
    elevation_deg = math.degrees(math.asin(dot))

    is_sunlit = elevation_deg >= -0.83
    return is_sunlit, round(elevation_deg, 2)


# ── Textures Loading & Base64 Caching ────────────────────────────────────────

@functools.lru_cache(maxsize=4)
def _load_texture_data_url(filename: str) -> str:
    """Load a texture from assets/textures and return a base64 data URL."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "assets", "textures", filename),
        os.path.join(base_dir, "reference", "satellites", "public", "textures", filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("ascii")
                return f"data:image/webp;base64,{encoded}"
    return ""


# ── Watched.earth 3D Globe HTML Template ─────────────────────────────────────

_GLOBE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=Instrument+Serif:ital@0;1&family=Martian+Mono:wght@300;400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --ink-0: #07080a;
      --ink-1: #0c0e11;
      --ink-2: #14171c;
      --bone: #ece8e0;
      --bone-2: rgba(236, 232, 224, 0.64);
      --bone-3: rgba(236, 232, 224, 0.52);
      --bone-3-mark: rgba(236, 232, 224, 0.40);
      --bone-4: rgba(236, 232, 224, 0.18);
      --line: rgba(236, 232, 224, 0.10);
      --line-strong: rgba(236, 232, 224, 0.22);
      --signal: #ff6a1a;
      --signal-2: rgba(255, 106, 26, 0.22);
      --ice: #a9c7d3;
      --warn: #e8c547;
      --font-sans: 'Instrument Sans', ui-sans-serif, system-ui, sans-serif;
      --font-mono: 'Martian Mono', ui-monospace, 'SF Mono', monospace;
      --font-serif: 'Instrument Serif', ui-serif, Georgia, serif;
    }
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
      user-select: none;
    }
    html, body {
      background: var(--ink-0);
      color: var(--bone);
      font-family: var(--font-sans);
      overflow: hidden;
      width: 100%;
      height: __HEIGHT__px;
      position: relative;
    }
    #canvas-container {
      width: 100%;
      height: 100%;
      display: block;
      cursor: grab;
      background: var(--ink-0);
    }
    #canvas-container:active {
      cursor: grabbing;
    }

    /* ── Watched.earth Instrument Bezel (DESIGN §4) ── */
    .bezel-frame {
      position: absolute;
      top: 14px;
      left: 14px;
      right: 14px;
      bottom: 14px;
      border: 1px solid var(--line);
      pointer-events: none;
      z-index: 10;
    }
    .bezel-frame .corner {
      position: absolute;
      width: 8px;
      height: 8px;
    }
    .bezel-frame .corner.tl {
      top: -1px; left: -1px;
      border-top: 1.5px solid var(--bone-3);
      border-left: 1.5px solid var(--bone-3);
    }
    .bezel-frame .corner.tr {
      top: -1px; right: -1px;
      border-top: 1.5px solid var(--bone-3);
      border-right: 1.5px solid var(--bone-3);
    }
    .bezel-frame .corner.bl {
      bottom: -1px; left: -1px;
      border-bottom: 1.5px solid var(--bone-3);
      border-left: 1.5px solid var(--bone-3);
    }
    .bezel-frame .corner.br {
      bottom: -1px; right: -1px;
      border-bottom: 1.5px solid var(--bone-3);
      border-right: 1.5px solid var(--bone-3);
    }
    .bezel-frame .ruler {
      position: absolute;
      top: -1px;
      height: 3px;
      border-top: 1px solid var(--line-strong);
      background: repeating-linear-gradient(
        90deg,
        var(--bone-3) 0,
        var(--bone-3) 1px,
        transparent 1px,
        transparent 24px
      );
    }
    .bezel-frame .ruler-left { left: 16px; width: 140px; }
    .bezel-frame .ruler-right { right: 16px; width: 140px; }

    /* ── Corner Readouts (Martian Mono) ── */
    .corner-readout {
      position: absolute;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--bone-3);
      letter-spacing: 0.04em;
      text-transform: uppercase;
      z-index: 12;
      pointer-events: none;
    }
    .ro-tl { top: 24px; left: 26px; }
    .ro-tr { top: 24px; right: 26px; text-align: right; }
    .ro-bl { bottom: 24px; left: 26px; }
    .ro-br { bottom: 24px; right: 26px; text-align: right; }

    .wordmark {
      font-family: var(--font-sans);
      font-size: 15px;
      font-weight: 600;
      letter-spacing: -0.01em;
      color: var(--bone);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .wordmark-sub {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--bone-3);
      margin-top: 2px;
      letter-spacing: 0.06em;
    }
    .signal-dot {
      color: var(--signal);
    }
    .blink-dot {
      display: inline-block;
      width: 6px;
      height: 6px;
      background: var(--signal);
      border-radius: 50%;
      margin-left: 6px;
      animation: pulse-dot 1.2s infinite ease-in-out;
    }
    @keyframes pulse-dot {
      0%, 100% { opacity: 0.35; transform: scale(0.9); }
      50% { opacity: 1.0; transform: scale(1.15); }
    }

    /* ── Target Info Plate ── */
    .target-callout {
      position: absolute;
      top: 66px;
      left: 26px;
      background: var(--ink-1);
      border: 1px solid var(--line);
      padding: 9px 13px;
      z-index: 15;
    }
    .callout-title {
      font-family: var(--font-sans);
      font-size: 13.5px;
      font-weight: 500;
      color: var(--bone);
    }
    .callout-meta {
      font-family: var(--font-mono);
      font-size: 10.5px;
      color: var(--bone-3);
      margin-top: 3px;
    }
    .signal-text {
      color: var(--signal);
    }

    /* ── Central Controls Dock ── */
    .controls-dock {
      position: absolute;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      gap: 6px;
      z-index: 20;
      background: var(--ink-1);
      border: 1px solid var(--line);
      padding: 4px;
    }
    .inst-btn {
      background: transparent;
      border: 1px solid transparent;
      color: var(--bone-2);
      font-family: var(--font-mono);
      font-size: 11px;
      padding: 6px 11px;
      text-transform: uppercase;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: background 120ms ease, color 120ms ease;
    }
    .inst-btn:hover {
      background: var(--ink-2);
      color: #ffffff;
    }
    .inst-btn.active {
      background: var(--signal);
      color: var(--ink-0);
      font-weight: 500;
    }
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
  <div id="canvas-container"></div>

  <!-- Instrument Bezel Frame -->
  <div class="bezel-frame">
    <span class="ruler ruler-left"></span>
    <span class="ruler ruler-right"></span>
    <span class="corner tl"></span>
    <span class="corner tr"></span>
    <span class="corner bl"></span>
    <span class="corner br"></span>
  </div>

  <!-- Top-Left Corner Readout -->
  <div class="corner-readout ro-tl">
    <div class="wordmark">CropScope<span class="signal-dot">.</span></div>
    <div class="wordmark-sub">ORBITAL MISSION CONSOLE · SGP4</div>
  </div>

  <!-- Target Info Plate -->
  <div class="target-callout">
    <div class="callout-title">__LOCATION_NAME_TEXT__</div>
    <div class="callout-meta">
      <span class="signal-text">TARGET</span> __LAT_FMT__° N, __LON_FMT__° E · <span id="target-solar-state">__SOLAR_STATUS__</span>
    </div>
  </div>

  <!-- Top-Right Live UTC Clock with Blinking Signal Dot -->
  <div class="corner-readout ro-tr">
    <span class="clock-display" id="live-utc-clock">2026-11-14 00:00:00 UTC</span>
    <span class="blink-dot"></span>
  </div>

  <!-- Bottom-Left Telemetry -->
  <div class="corner-readout ro-bl">
    <div class="status-line">
      <span style="color: var(--signal); font-weight: 500;">SENTINEL-2 L2A</span>
      <span> · 10M MULTISPECTRAL · AWS STAC · REALTIME SUN</span>
    </div>
  </div>

  <!-- Bottom-Right Ephemeris (Watched.earth Subsolar Coordinates) -->
  <div class="corner-readout ro-br">
    <div>SUBSOLAR <span id="sun-coords">__SUBSOLAR_LAT__° __SUBSOLAR_LON__°</span></div>
    <div style="margin-top: 2px;">SOLAR ELEVATION <span id="sun-elev" style="color: var(--bone);">__SOLAR_ELEV__°</span></div>
  </div>

  <!-- Central Controls Dock -->
  <div class="controls-dock">
    <button class="inst-btn" id="btn-focus">🎯 Focus Target</button>
    <button class="inst-btn active" id="btn-live">⏱️ Live UTC</button>
    <button class="inst-btn" id="btn-sweep">⏯️ 24h Darkness Sweep</button>
    <button class="inst-btn" id="btn-sun">☀️ Solar Noon</button>
    <button class="inst-btn" id="btn-night">🌙 Night Limb</button>
  </div>

  <script>
    const targetLat = __TARGET_LAT__;
    const targetLon = __TARGET_LON__;
    const locationName = __LOCATION_NAME_JSON__;

    const container = document.getElementById('canvas-container');
    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || __HEIGHT__;

    // ── 1. Scene, Camera, Renderer ──────────────────────────────────────────
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x07080a); // --ink-0

    const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 1000);
    // Start camera at overview altitude
    camera.position.set(0, 0.5, 3.2);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.outputEncoding = THREE.sRGBEncoding;
    container.appendChild(renderer.domElement);

    // ── 2. OrbitControls (Camera orbits around FIXED Earth) ──────────────────
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 1.30;
    controls.maxDistance = 5.2;
    controls.autoRotate = false; // Never fight the user with unprompted spin

    // ── 3. Watched.earth Exact Ephemeris & Geometry Math ────────────────────
    const DEG = Math.PI / 180.0;
    const RAD = 180.0 / Math.PI;

    function julianDate(ms) {
      return ms / 86400000.0 + 2440587.5;
    }

    function gmst(ms) {
      const jd = julianDate(ms);
      const t = (jd - 2451545.0) / 36525.0;
      let g = -6.2e-6 * t * t * t + 0.093104 * t * t + (876600.0 * 3600.0 + 8640184.812866) * t + 67310.54841;
      g = ((g * DEG) / 240.0) % (2.0 * Math.PI);
      return g < 0 ? g + 2.0 * Math.PI : g;
    }

    function sunEci(ms) {
      const n = julianDate(ms) - 2451545.0;
      const L = (280.46 + 0.9856474 * n) % 360.0;
      const g = ((357.528 + 0.9856003 * n) % 360.0) * DEG;
      const lambda = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2.0 * g)) * DEG;
      const eps = (23.439 - 0.0000004 * n) * DEG;
      return [Math.cos(lambda), Math.cos(eps) * Math.sin(lambda), Math.sin(eps) * Math.sin(lambda)];
    }

    function eciToEcef(x, y, z, ms) {
      const g = gmst(ms);
      const c = Math.cos(g);
      const s = Math.sin(g);
      return [c * x + s * y, -s * x + c * y, z];
    }

    function sunEcefUnit(ms) {
      const [x, y, z] = sunEci(ms);
      const [ex, ey, ez] = eciToEcef(x, y, z, ms);
      const r = Math.hypot(ex, ey, ez) || 1.0;
      return [ex / r, ey / r, ez / r];
    }

    // World vector toward the Sun (Three.js world frame)
    function sunDirectionWorld(ms) {
      const [ex, ey, ez] = sunEcefUnit(ms);
      return new THREE.Vector3(ex, ez, -ey);
    }

    // Lat/Lon to World Vector3 (ECEF to Three.js SphereGeometry)
    function latLonToWorld(latDeg, lonDeg, radius) {
      radius = radius || 1.0;
      const lat = latDeg * DEG;
      const lon = lonDeg * DEG;
      const c = Math.cos(lat);
      return new THREE.Vector3(
        radius * c * Math.cos(lon),
        radius * Math.sin(lat),
        -radius * c * Math.sin(lon)
      );
    }

    // ── 4. Progressive & Base64 Textures ────────────────────────────────────
    const textureLoader = new THREE.TextureLoader();

    // Procedural Fallback Textures (guarantee zero blank flash during init)
    function createFallbackTexture(isDay) {
      const c = document.createElement('canvas');
      c.width = 1024; c.height = 512;
      const ctx = c.getContext('2d');
      if (isDay) {
        ctx.fillStyle = '#081729'; ctx.fillRect(0, 0, 1024, 512);
        ctx.fillStyle = '#1b3826';
        ctx.beginPath(); ctx.ellipse(540, 240, 140, 100, 0, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.ellipse(320, 200, 110, 80, 0, 0, Math.PI * 2); ctx.fill();
      } else {
        ctx.fillStyle = '#05070a'; ctx.fillRect(0, 0, 1024, 512);
        ctx.fillStyle = '#ffb070';
        for (let i = 0; i < 300; i++) {
          ctx.fillRect(200 + Math.random() * 700, 100 + Math.random() * 300, 1.5, 1.5);
        }
      }
      const tex = new THREE.CanvasTexture(c);
      tex.encoding = THREE.sRGBEncoding;
      return tex;
    }

    const dayDataUrl = '__DAY_TEXTURE_DATA_URL__';
    const dayTexture = dayDataUrl
      ? textureLoader.load(dayDataUrl)
      : createFallbackTexture(true);
    dayTexture.encoding = THREE.sRGBEncoding;
    dayTexture.wrapS = THREE.ClampToEdgeWrapping;
    dayTexture.wrapT = THREE.ClampToEdgeWrapping;

    const nightDataUrl = '__NIGHT_TEXTURE_DATA_URL__';
    const nightTexture = nightDataUrl
      ? textureLoader.load(nightDataUrl)
      : createFallbackTexture(false);
    nightTexture.encoding = THREE.sRGBEncoding;
    nightTexture.wrapS = THREE.ClampToEdgeWrapping;
    nightTexture.wrapT = THREE.ClampToEdgeWrapping;

    const cloudsDataUrl = '__CLOUDS_TEXTURE_DATA_URL__';
    const cloudsTexture = cloudsDataUrl
      ? textureLoader.load(cloudsDataUrl)
      : createFallbackTexture(false);
    cloudsTexture.wrapS = THREE.RepeatWrapping;
    cloudsTexture.wrapT = THREE.ClampToEdgeWrapping;

    // ── 5. Fixed Earth Mesh & Photoreal Shaders ──────────────────────────────
    const initialSun = sunDirectionWorld(Date.now());

    const earthVertexShader = `
      varying vec3 vPos;
      varying vec2 vUv;
      void main() {
        vUv = uv;
        vPos = (modelMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * viewMatrix * vec4(vPos, 1.0);
      }
    `;

    const earthFragmentShader = `
      uniform sampler2D uDay;
      uniform sampler2D uNight;
      uniform vec3 uSunDir;
      uniform vec3 uCityColor;
      uniform vec3 uTwilightColor;
      uniform vec3 uHazeColor;
      uniform vec3 uNightTint;
      uniform float uSunIntensity;

      varying vec3 vPos;
      varying vec2 vUv;

      #define PI 3.141592653589793
      float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
      float sat01(float x) { return clamp(x, 0.0, 1.0); }
      float gauss(float x) { return exp(-x * x); }

      vec3 gradeDay(vec3 c, float ocean) {
        float l = luma(c);
        // Cool-neutral balance, -12% saturation
        c = mix(vec3(l), c, 0.88) * vec3(0.96, 0.99, 1.03);
        // Deep ink-navy oceans
        vec3 sea = mix(vec3(l), c, 0.55) * vec3(0.46, 0.56, 0.70);
        return mix(c, sea, ocean);
      }

      void main() {
        vec3 N = normalize(vPos);
        vec3 V = normalize(cameraPosition - vPos);
        vec3 L = normalize(uSunDir);
        float NdL = dot(N, L);

        // Day map sample
        vec3 dayTex = texture2D(uDay, vUv).rgb;
        float ocean = sat01((dayTex.b * 1.25 - dayTex.r * 1.05) * 2.2);

        vec3 albedo = pow(gradeDay(dayTex, ocean), vec3(1.12)) * 1.06;
        float dayMix = smoothstep(-0.05, 0.09, NdL);
        float lambert = sat01((NdL + 0.04) / 1.04);
        vec3 day = albedo * uSunIntensity * lambert;

        // Low sun reddening at twilight
        float lowSun = gauss((NdL - 0.03) / 0.11);
        day *= mix(vec3(1.0), vec3(1.0, 0.74, 0.55), lowSun * 0.45);

        // Ocean specular glint (Blinn-Phong)
        vec3 H = normalize(L + V);
        float NdH = max(dot(N, H), 0.0);
        float VdH = max(dot(V, H), 0.0);
        float fres = 0.02 + 0.98 * pow(sat01(1.0 - VdH), 5.0);
        float spec = pow(NdH, 180.0) * 0.55 + pow(NdH, 24.0) * 0.045;
        spec *= (0.35 + fres) * ocean * smoothstep(0.0, 0.25, NdL);
        day += vec3(1.0, 0.97, 0.92) * spec * uSunIntensity;

        // Day-side limb haze
        float NdV = max(dot(N, V), 0.0);
        float limb = pow(sat01(1.0 - NdV), 3.2);
        float hazeLight = smoothstep(0.02, 0.45, NdL);
        day = mix(day, uHazeColor * uSunIntensity * 0.4 * hazeLight, limb * 0.7 * smoothstep(-0.02, 0.2, NdL));

        // Night map sample (city lights)
        vec3 nightTex = texture2D(uNight, vUv).rgb;
        float nl = luma(nightTex);
        float earthshine = luma(dayTex) * 0.012;
        vec3 nightBase = vec3(0.0046, 0.0057, 0.0070) * mix(1.3, 1.0, ocean) + uNightTint * earthshine;

        float lights = pow(smoothstep(0.014, 0.55, nl), 1.45);
        float lightsOn = 1.0 - smoothstep(-0.14, 0.03, NdL);
        vec3 cityTint = mix(uCityColor, vec3(1.0, 0.82, 0.60), lights * lights * lights * 0.8);
        vec3 city = cityTint * lights * 1.8;
        vec3 night = nightBase + city * lightsOn;

        vec3 col = mix(night, day, dayMix);

        // Soft warm twilight band along terminator
        float dusk = gauss((NdL + 0.035) / 0.05);
        col += uTwilightColor * dusk * 0.008;

        gl_FragColor = vec4(col, 1.0);
      }
    `;

    const earthUniforms = {
      uDay: { value: dayTexture },
      uNight: { value: nightTexture },
      uSunDir: { value: initialSun },
      uCityColor: { value: new THREE.Color(0xffb070) },      // Sodium amber
      uTwilightColor: { value: new THREE.Color(0xff9a5a) },  // Warm terminator
      uHazeColor: { value: new THREE.Color(0xb4cde6) },      // Rayleigh haze
      uNightTint: { value: new THREE.Color(0.86, 0.92, 1.0) },
      uSunIntensity: { value: 1.08 }
    };

    const earthMaterial = new THREE.ShaderMaterial({
      uniforms: earthUniforms,
      vertexShader: earthVertexShader,
      fragmentShader: earthFragmentShader
    });
    // SphereGeometry: 1.0 unit radius, Earth is FIXED in world space
    const earthMesh = new THREE.Mesh(new THREE.SphereGeometry(1.0, 96, 48), earthMaterial);
    scene.add(earthMesh);

    // ── 6. Cloud Shell (radius 1.006) ───────────────────────────────────────
    const cloudVertexShader = `
      varying vec3 vPos;
      varying vec2 vUv;
      void main() {
        vUv = uv;
        vPos = (modelMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * viewMatrix * vec4(vPos, 1.0);
      }
    `;

    const cloudFragmentShader = `
      uniform sampler2D uClouds;
      uniform vec3 uSunDir;
      uniform float uCloudOffset;
      uniform float uSunIntensity;
      uniform vec3 uCloudColor;
      uniform vec3 uTwilightColor;
      uniform vec3 uNightColor;
      uniform float uOpacity;

      varying vec3 vPos;
      varying vec2 vUv;

      float sat01(float x) { return clamp(x, 0.0, 1.0); }
      float gauss(float x) { return exp(-x * x); }
      float cloudCover(float c) { return smoothstep(0.16, 0.78, c); }

      void main() {
        vec3 N = normalize(vPos);
        vec3 V = normalize(cameraPosition - vPos);
        vec3 L = normalize(uSunDir);
        float NdL = dot(N, L);

        vec2 uv = vUv + vec2(uCloudOffset, 0.0);
        float c = texture2D(uClouds, uv).r;
        float cover = cloudCover(c);
        if (cover < 0.004) discard;

        float dayMix = smoothstep(-0.05, 0.12, NdL);
        float lambert = sat01((NdL + 0.08) / 1.08);
        vec3 lit = uCloudColor * uSunIntensity * mix(0.32, 1.0, lambert);

        float band = gauss((NdL - 0.02) / 0.06);
        lit = mix(lit, uTwilightColor * uSunIntensity * 0.5, band * 0.38);

        vec3 col = mix(uNightColor, lit, dayMix);
        float alpha = cover * mix(0.16, 0.94, dayMix) * uOpacity;
        float limb = pow(sat01(1.0 - dot(N, V)), 4.0);
        alpha *= 1.0 - 0.55 * limb;

        if (alpha < 0.002) discard;
        gl_FragColor = vec4(col, alpha);
      }
    `;

    const cloudUniforms = {
      uClouds: { value: cloudsTexture },
      uSunDir: { value: initialSun },
      uCloudOffset: { value: 0.0 },
      uSunIntensity: { value: 1.08 },
      uCloudColor: { value: new THREE.Color(0xe4e3de) },
      uTwilightColor: { value: new THREE.Color(0xff9a5a) },
      uNightColor: { value: new THREE.Color(0x0c0e11) },
      uOpacity: { value: 0.85 }
    };

    const cloudMaterial = new THREE.ShaderMaterial({
      uniforms: cloudUniforms,
      vertexShader: cloudVertexShader,
      fragmentShader: cloudFragmentShader,
      transparent: true,
      depthWrite: false
    });
    const cloudMesh = new THREE.Mesh(new THREE.SphereGeometry(1.006, 96, 48), cloudMaterial);
    scene.add(cloudMesh);

    // ── 7. Exponential Rayleigh Atmosphere Rim (radius 1.025) ───────────────
    const atmoVertexShader = `
      varying vec3 vPos;
      void main() {
        vPos = (modelMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * viewMatrix * vec4(vPos, 1.0);
      }
    `;

    const atmoFragmentShader = `
      uniform vec3 uSunDir;
      uniform vec3 uRayleigh;
      uniform vec3 uHorizon;
      uniform vec3 uTwilightColor;
      uniform float uIntensity;

      varying vec3 vPos;

      float sat01(float x) { return clamp(x, 0.0, 1.0); }
      float gauss(float x) { return exp(-x * x); }

      void main() {
        vec3 ro = cameraPosition;
        vec3 rd = normalize(vPos - ro);
        float tca = -dot(ro, rd);
        vec3 pc = ro + rd * tca;
        float b = length(pc);
        if (b < 1.0) discard;
        float h = b - 1.0;
        vec3 n = pc / b;
        vec3 L = normalize(uSunDir);

        float od = exp(-h / 0.012) * (1.0 - smoothstep(0.012, 0.025, h));
        float mu = dot(n, L);
        float lit = smoothstep(-0.22, 0.28, mu);
        float cosT = dot(rd, L);
        float rayleigh = 0.75 * (1.0 + cosT * cosT);
        float forward = pow(max(cosT, 0.0), 10.0) * smoothstep(-0.25, 0.1, mu);
        float twilight = gauss((mu - 0.02) / 0.14);

        vec3 tint = mix(uHorizon, uRayleigh, smoothstep(0.0, 0.03, h));
        vec3 col = tint * rayleigh * lit + uHorizon * forward * 1.5;
        col = mix(col, uTwilightColor * 0.9, twilight * 0.35 * lit);
        col *= od * uIntensity;

        gl_FragColor = vec4(col, od * (0.2 + 0.8 * lit));
      }
    `;

    const atmoUniforms = {
      uSunDir: { value: initialSun },
      uRayleigh: { value: new THREE.Color(0.58, 0.76, 1.0) },
      uHorizon: { value: new THREE.Color(0.85, 0.92, 1.0) },
      uTwilightColor: { value: new THREE.Color(0xff9a5a) },
      uIntensity: { value: 1.2 }
    };

    const atmoMaterial = new THREE.ShaderMaterial({
      uniforms: atmoUniforms,
      vertexShader: atmoVertexShader,
      fragmentShader: atmoFragmentShader,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true,
      depthWrite: false
    });
    const atmoMesh = new THREE.Mesh(new THREE.SphereGeometry(1.025, 64, 32), atmoMaterial);
    scene.add(atmoMesh);

    // ── 8. Starfield ────────────────────────────────────────────────────────
    const starGeom = new THREE.BufferGeometry();
    const starPos = new Float32Array(900 * 3);
    for (let i = 0; i < 900 * 3; i += 3) {
      const r = 30.0 + Math.random() * 25.0;
      const th = Math.random() * Math.PI * 2;
      const ph = Math.acos(2 * Math.random() - 1);
      starPos[i] = r * Math.sin(ph) * Math.cos(th);
      starPos[i + 1] = r * Math.sin(ph) * Math.sin(th);
      starPos[i + 2] = r * Math.cos(ph);
    }
    starGeom.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
    const starMaterial = new THREE.PointsMaterial({ color: 0x94a3b8, size: 0.12, transparent: true, opacity: 0.6 });
    scene.add(new THREE.Points(starGeom, starMaterial));

    // ── 9. Watched.earth Signal Reticle on Target Field ─────────────────────
    const targetSurfacePos = latLonToWorld(targetLat, targetLon, 1.0);
    const targetMarkerPos = latLonToWorld(targetLat, targetLon, 1.002);

    // Tangent basis at location: east, north, up
    const dNormal = targetSurfacePos.clone().normalize();
    const eastVec = new THREE.Vector3(dNormal.z, 0, -dNormal.x);
    if (eastVec.lengthSq() < 1e-9) eastVec.set(0, 0, -1);
    eastVec.normalize();
    const northVec = new THREE.Vector3().crossVectors(dNormal, eastVec).normalize();
    const basisMatrix = new THREE.Matrix4().makeBasis(eastVec, northVec, dNormal);

    const reticleVertexShader = `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `;

    const reticleFragmentShader = `
      uniform float uLock;   // 0.0 -> 1.0 lock progress
      uniform float uPulse;  // beacon pulse time
      uniform vec3 uColor;
      varying vec2 vUv;

      float stroke(float dist, float width) {
        return 1.0 - smoothstep(width * 0.5 - 0.015, width * 0.5 + 0.015, abs(dist));
      }

      void main() {
        vec2 p = vUv - 0.5;
        float r = length(p);

        // Reticle ring: contracts from 0.36 to 0.20 as uLock increases
        float ringR = 0.20 * (2.0 - uLock);
        float ring = stroke(r - ringR, 0.018);

        // Center dot
        float dotC = 1.0 - smoothstep(0.024, 0.038, r);

        // 4 Crosshair ticks outside the ring
        vec2 ap = abs(p);
        float tickLen = 0.08;
        float tickIn = 0.23;
        float tickOut = tickIn + tickLen;
        float tickH = stroke(p.y, 0.016) * step(tickIn, ap.x) * step(ap.x, tickOut);
        float tickV = stroke(p.x, 0.016) * step(tickIn, ap.y) * step(ap.y, tickOut);
        float ticks = max(tickH, tickV) * uLock;

        // Expanding beacon pulse shockwave
        float pulseR = 0.20 * (1.0 + 3.0 * uPulse);
        float pulseAlpha = (1.0 - uPulse) * 0.85;
        float pulseRing = stroke(r - pulseR, 0.014) * pulseAlpha;

        float alpha = max(max(ring, dotC), max(ticks, pulseRing));
        if (alpha < 0.01) discard;

        gl_FragColor = vec4(uColor, alpha);
      }
    `;

    const reticleUniforms = {
      uLock: { value: 0.0 },
      uPulse: { value: 0.0 },
      uColor: { value: new THREE.Color(0xff6a1a) } // Signal orange
    };

    const reticleMaterial = new THREE.ShaderMaterial({
      uniforms: reticleUniforms,
      vertexShader: reticleVertexShader,
      fragmentShader: reticleFragmentShader,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide
    });

    const reticleQuad = new THREE.Mesh(new THREE.PlaneGeometry(0.14, 0.14), reticleMaterial);
    reticleQuad.position.copy(targetMarkerPos);
    reticleQuad.quaternion.setFromRotationMatrix(basisMatrix);
    scene.add(reticleQuad);

    // ── 10. Smooth Cinematic Camera Director & Flight Math ──────────────────
    let flight = {
      active: false,
      startTime: 0,
      duration: 1800,
      startDir: new THREE.Vector3(),
      startDist: 3.2,
      destDir: new THREE.Vector3(),
      destDist: 2.2
    };

    function easeInOutCubic(t) {
      return t < 0.5 ? 4.0 * t * t * t : 1.0 - Math.pow(-2.0 * t + 2.0, 3.0) / 2.0;
    }

    function easeOutQuad(t) {
      return 1.0 - (1.0 - t) * (1.0 - t);
    }

    function slerpDir(v1, v2, t, out) {
      const dot = Math.max(-1.0, Math.min(1.0, v1.dot(v2)));
      const theta = Math.acos(dot);
      if (theta < 1e-5) return out.copy(v1).lerp(v2, t).normalize();
      const s = Math.sin(theta);
      const wa = Math.sin((1.0 - t) * theta) / s;
      const wb = Math.sin(t * theta) / s;
      return out.set(
        v1.x * wa + v2.x * wb,
        v1.y * wa + v2.y * wb,
        v1.z * wa + v2.z * wb
      ).normalize();
    }

    let arrivalTime = performance.now();

    function flyToTarget(distance, duration) {
      distance = distance || 2.2;
      duration = duration || 1900;

      flight.active = true;
      flight.startTime = performance.now();
      flight.duration = duration;
      flight.startDir.copy(camera.position).normalize();
      flight.startDist = camera.position.length();

      const targetDir = targetSurfacePos.clone().normalize();
      flight.destDir.copy(targetDir);
      flight.destDist = distance;

      reticleUniforms.uLock.value = 0.0;
    }

    // Yield flight immediately when user drags or scrolls
    controls.addEventListener('start', () => {
      flight.active = false;
    });

    // ── 11. Interactive Dock & Time Modes ────────────────────────────────────
    let simMode = 'live'; // 'live' | 'sweep'
    let simTime = Date.now();
    let lastFramePerf = performance.now();

    const btnFocus = document.getElementById('btn-focus');
    const btnLive = document.getElementById('btn-live');
    const btnSweep = document.getElementById('btn-sweep');
    const btnSun = document.getElementById('btn-sun');
    const btnNight = document.getElementById('btn-night');

    btnFocus.addEventListener('click', () => {
      flyToTarget(2.2, 1900);
    });

    btnLive.addEventListener('click', () => {
      simMode = 'live';
      simTime = Date.now();
      btnLive.classList.add('active');
      btnSweep.classList.remove('active');
    });

    btnSweep.addEventListener('click', () => {
      if (simMode === 'sweep') {
        simMode = 'live';
        simTime = Date.now();
        btnLive.classList.add('active');
        btnSweep.classList.remove('active');
      } else {
        simMode = 'sweep';
        btnLive.classList.remove('active');
        btnSweep.classList.add('active');
      }
    });

    btnSun.addEventListener('click', () => {
      // Find approximate solar noon at target longitude
      const targetSubLon = targetLon;
      const [ex0, ey0] = sunEcefUnit(Date.now());
      const curSubLon = Math.atan2(ey0, ex0) * RAD;
      const deltaDeg = targetSubLon - curSubLon;
      const deltaMs = (deltaDeg / 360.0) * 86400000.0;
      simTime = Date.now() + deltaMs;
      simMode = 'pause';
      btnLive.classList.remove('active');
      btnSweep.classList.remove('active');
      flyToTarget(2.3, 1600);
    });

    btnNight.addEventListener('click', () => {
      // Find approximate midnight at target longitude
      const targetSubLon = targetLon + 180.0;
      const [ex0, ey0] = sunEcefUnit(Date.now());
      const curSubLon = Math.atan2(ey0, ex0) * RAD;
      const deltaDeg = targetSubLon - curSubLon;
      const deltaMs = (deltaDeg / 360.0) * 86400000.0;
      simTime = Date.now() + deltaMs;
      simMode = 'pause';
      btnLive.classList.remove('active');
      btnSweep.classList.remove('active');
      flyToTarget(2.3, 1600);
    });

    // ── 12. Frame Loop & Live Clock ──────────────────────────────────────────
    const clockElem = document.getElementById('live-utc-clock');
    const sunCoordsElem = document.getElementById('sun-coords');
    const sunElevElem = document.getElementById('sun-elev');
    const targetSolarStateElem = document.getElementById('target-solar-state');

    function pad2(n) { return n < 10 ? '0' + n : n; }

    function updateEphemerisUI(ms) {
      const [ex, ey, ez] = sunEcefUnit(ms);
      const subLat = Math.asin(Math.max(-1.0, Math.min(1.0, ez))) * RAD;
      const subLon = Math.atan2(ey, ex) * RAD;
      sunCoordsElem.innerText = (subLat >= 0 ? '+' : '') + subLat.toFixed(1) + '° ' + (subLon >= 0 ? '+' : '') + subLon.toFixed(1) + '°';

      const c = Math.cos(targetLat * DEG);
      const dot = c * Math.cos(targetLon * DEG) * ex +
                  c * Math.sin(targetLon * DEG) * ey +
                  Math.sin(targetLat * DEG) * ez;
      const elev = Math.asin(Math.max(-1.0, Math.min(1.0, dot))) * RAD;
      sunElevElem.innerText = (elev >= 0 ? '+' : '') + elev.toFixed(1) + '°';

      if (elev >= 0.0) {
        targetSolarStateElem.innerText = 'DAYLIGHT · +' + elev.toFixed(1) + '° ELEV';
        targetSolarStateElem.style.color = 'var(--bone)';
      } else if (elev >= -6.0) {
        targetSolarStateElem.innerText = 'CIVIL TWILIGHT · ' + elev.toFixed(1) + '°';
        targetSolarStateElem.style.color = 'var(--warn)';
      } else {
        targetSolarStateElem.innerText = 'NIGHT SHADOW · ' + elev.toFixed(1) + '°';
        targetSolarStateElem.style.color = 'var(--signal)';
      }
    }

    // Initial camera placement: start overview then smoothly fly to target
    flyToTarget(2.2, 2200);

    function animate() {
      requestAnimationFrame(animate);

      const nowPerf = performance.now();
      const dtSec = Math.min(0.1, (nowPerf - lastFramePerf) / 1000.0);
      lastFramePerf = nowPerf;

      // Update simulation time
      if (simMode === 'live') {
        simTime = Date.now();
      } else if (simMode === 'sweep') {
        // 24 hours in 24 seconds = 3600x real-time speed
        simTime += dtSec * 3600.0 * 1000.0;
      }

      // Update astronomical Sun vector (the darkness moves in real time)
      const sunVec = sunDirectionWorld(simTime);
      earthUniforms.uSunDir.value.copy(sunVec);
      atmoUniforms.uSunDir.value.copy(sunVec);
      cloudUniforms.uSunDir.value.copy(sunVec);

      // Cloud drift (1 revolution every 8 hours)
      cloudUniforms.uCloudOffset.value = (simTime / (8.0 * 3600.0 * 1000.0)) % 1.0;

      // Update UTC clock display
      const simDate = new Date(simTime);
      clockElem.innerText = simDate.getUTCFullYear() + '-' +
        pad2(simDate.getUTCMonth() + 1) + '-' +
        pad2(simDate.getUTCDate()) + ' ' +
        pad2(simDate.getUTCHours()) + ':' +
        pad2(simDate.getUTCMinutes()) + ':' +
        pad2(simDate.getUTCSeconds()) + ' UTC';

      updateEphemerisUI(simTime);

      // Smooth Great-Circle Camera Flight
      if (flight.active) {
        const rawT = Math.min(1.0, (nowPerf - flight.startTime) / flight.duration);
        const t = easeInOutCubic(rawT);

        const curDir = new THREE.Vector3();
        slerpDir(flight.startDir, flight.destDir, t, curDir);
        const curDist = flight.startDist + (flight.destDist - flight.startDist) * t;

        camera.position.copy(curDir).multiplyScalar(curDist);
        camera.up.set(0, 1, 0);
        controls.target.set(0, 0, 0);
        controls.update();

        if (rawT >= 1.0) {
          flight.active = false;
          arrivalTime = nowPerf;
        }
      }

      // Reticle Lock & Beacon Pulse Animation
      if (!flight.active) {
        const lockElapsed = Math.min(1.0, (nowPerf - arrivalTime) / 500.0);
        reticleUniforms.uLock.value = easeOutQuad(lockElapsed);
      }
      // Gentle beacon pulse every 2.4s
      reticleUniforms.uPulse.value = ((nowPerf - arrivalTime) % 2400.0) / 2400.0;

      controls.update();
      renderer.render(scene, camera);
    }

    animate();

    // Responsive Canvas Resizing
    window.addEventListener('resize', () => {
      const newW = container.clientWidth || window.innerWidth;
      const newH = container.clientHeight || __HEIGHT__;
      camera.aspect = newW / newH;
      camera.updateProjectionMatrix();
      renderer.setSize(newW, newH);
    });
  </script>
</body>
</html>
"""


def build_globe_html(
    center_lat: float,
    center_lon: float,
    location_name: str = "Selected Field",
    height: int = 560,
) -> str:
    """Build a complete Three.js WebGL component styled with Watched.earth art direction."""
    sub_lat, sub_lon = compute_subsolar_point()
    is_day, elevation = is_location_sunlit(center_lat, center_lon)
    solar_status = "DAYLIGHT" if is_day else "NIGHT SHADOW"

    day_tex_url = _load_texture_data_url("earth-day-2k.webp")
    night_tex_url = _load_texture_data_url("earth-night-2k.webp")
    clouds_tex_url = _load_texture_data_url("earth-clouds-1k.webp")

    html = _GLOBE_TEMPLATE
    html = html.replace("__HEIGHT__", str(height))
    html = html.replace("__LOCATION_NAME_TEXT__", location_name)
    html = html.replace("__LOCATION_NAME_JSON__", json.dumps(location_name))
    html = html.replace("__LAT_FMT__", f"{center_lat:.5f}")
    html = html.replace("__LON_FMT__", f"{center_lon:.5f}")
    html = html.replace("__TARGET_LAT__", str(center_lat))
    html = html.replace("__TARGET_LON__", str(center_lon))
    html = html.replace("__SOLAR_STATUS__", solar_status)
    html = html.replace("__SOLAR_ELEV__", f"{elevation:+.1f}")
    html = html.replace("__SUBSOLAR_LAT__", f"{sub_lat:+.1f}")
    html = html.replace("__SUBSOLAR_LON__", f"{sub_lon:+.1f}")
    html = html.replace("__DAY_TEXTURE_DATA_URL__", day_tex_url)
    html = html.replace("__NIGHT_TEXTURE_DATA_URL__", night_tex_url)
    html = html.replace("__CLOUDS_TEXTURE_DATA_URL__", clouds_tex_url)

    return html
