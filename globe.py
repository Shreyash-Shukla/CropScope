"""Interactive 3D real-time Earth globe with astronomical solar terminator.

Crafted strictly according to the Watched.earth design system (docs/DESIGN.md):
- Instrument bezel viewport with 8px corner L-ticks and top-edge 24px/120px ruler
- Fixed corner readouts in tabular Martian Mono + live ticking UTC clock with blinking sodium-orange indicator
- Graded photoreal Earth (cool-neutral day side, deep ink oceans, real sun specular glint)
- Real-time astronomical subsolar calculation (the terminator you see is real right now)
- Sodium-amber (#FFB070) night city lights, soft warm twilight transition band (#FF9A5A)
- Thin Rayleigh exponential atmosphere rim on the sunlit limb
- Signal-orange (#FF6A1A) crosshair reticle on the field target
- Flat ink panels, sharp 0px border-radius, pure bone/ink color tokens, zero decorative gradients
"""

import datetime
import json
import math
from typing import Tuple


def compute_subsolar_point(dt: datetime.datetime | None = None) -> Tuple[float, float]:
    """Calculate the subsolar point (latitude, longitude) where the sun is directly overhead.

    Uses standard astronomical approximation for solar declination and Greenwich Hour Angle.
    Returns (subsolar_lat_deg, subsolar_lon_deg).
    """
    if dt is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)

    # Days since J2000.0 (2000-01-01 12:00 UTC, Unix timestamp 946728000)
    timestamp = dt.timestamp()
    d = (timestamp - 946728000.0) / 86400.0

    # Mean anomaly of the Sun
    m_deg = (357.529 + 0.98560028 * d) % 360.0
    m_rad = math.radians(m_deg)

    # Mean ecliptic longitude of the Sun
    q_deg = 280.459 + 0.98564736 * d
    # True ecliptic longitude with equation of center
    l_deg = (q_deg + 1.915 * math.sin(m_rad) + 0.020 * math.sin(2.0 * m_rad)) % 360.0
    l_rad = math.radians(l_deg)

    # Obliquity of the ecliptic
    e_deg = 23.439 - 0.00000036 * d
    e_rad = math.radians(e_deg)

    # Solar declination (subsolar latitude)
    sin_dec = math.sin(e_rad) * math.sin(l_rad)
    dec_rad = math.asin(max(-1.0, min(1.0, sin_dec)))
    subsolar_lat = math.degrees(dec_rad)

    # Greenwich Hour Angle (GHA) of the Sun
    hours_utc = dt.hour + dt.minute / 60.0 + dt.second / 3600.0 + dt.microsecond / 3.6e9
    gha_deg = (hours_utc - 12.0) * 15.0
    subsolar_lon = -gha_deg

    while subsolar_lon < -180.0:
        subsolar_lon += 360.0
    while subsolar_lon > 180.0:
        subsolar_lon -= 360.0

    return round(subsolar_lat, 4), round(subsolar_lon, 4)


def is_location_sunlit(
    latitude: float,
    longitude: float,
    dt: datetime.datetime | None = None,
) -> Tuple[bool, float]:
    """Determine whether a given location is currently in daylight or night shadow.

    Returns (is_sunlit, solar_elevation_deg).
    Solar elevation > 0 indicates daytime; -6 to 0 is civil twilight; < -6 is night.
    """
    sub_lat, sub_lon = compute_subsolar_point(dt)

    lat1 = math.radians(latitude)
    lon1 = math.radians(longitude)
    lat2 = math.radians(sub_lat)
    lon2 = math.radians(sub_lon)

    # Great circle angular distance from location to subsolar point (zenith angle)
    cos_zenith = math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon1 - lon2)
    cos_zenith = max(-1.0, min(1.0, cos_zenith))

    zenith_angle_deg = math.degrees(math.acos(cos_zenith))
    solar_elevation_deg = 90.0 - zenith_angle_deg

    is_sunlit = solar_elevation_deg >= -0.83
    return is_sunlit, round(solar_elevation_deg, 2)


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
    .corner {
      position: absolute;
      width: 8px;
      height: 8px;
      border: 0 solid var(--bone-3-mark);
    }
    .tl { top: -1px; left: -1px; border-top-width: 1px; border-left-width: 1px; }
    .tr { top: -1px; right: -1px; border-top-width: 1px; border-right-width: 1px; }
    .bl { bottom: -1px; left: -1px; border-bottom-width: 1px; border-left-width: 1px; }
    .br { bottom: -1px; right: -1px; border-bottom-width: 1px; border-right-width: 1px; }

    /* Top-edge ruler: ticks every 24px, major every 120px */
    .ruler {
      position: absolute;
      top: 0;
      width: 50%;
      height: 6px;
      background-image:
        linear-gradient(to right, var(--bone-4) 1px, transparent 1px),
        linear-gradient(to right, var(--bone-4) 1px, transparent 1px);
      background-size: 120px 6px, 24px 3px;
      background-repeat: repeat-x;
    }
    .ruler-left {
      left: 20px;
      mask-image: linear-gradient(to right, #000 0, #000 20%, transparent 80%);
      -webkit-mask-image: linear-gradient(to right, #000 0, #000 20%, transparent 80%);
    }
    .ruler-right {
      right: 20px;
      background-position: right 0 top 0;
      mask-image: linear-gradient(to left, #000 0, #000 20%, transparent 80%);
      -webkit-mask-image: linear-gradient(to left, #000 0, #000 20%, transparent 80%);
    }

    /* ── Fixed Corner Readouts (Martian Mono tabular-nums) ── */
    .corner-readout {
      position: absolute;
      font-family: var(--font-mono);
      font-size: 10.5px;
      font-variant-numeric: tabular-nums;
      color: var(--bone-3);
      letter-spacing: 0.06em;
      pointer-events: auto;
      z-index: 20;
    }
    .ro-tl {
      top: 24px;
      left: 26px;
    }
    .wordmark {
      font-family: var(--font-serif);
      font-size: 20px;
      font-weight: 400;
      color: var(--bone);
      letter-spacing: -0.01em;
      display: block;
      margin-bottom: 2px;
    }
    .wordmark .signal-dot {
      color: var(--signal);
    }
    .wordmark-sub {
      font-family: var(--font-mono);
      font-size: 9.5px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--bone-3);
    }

    .ro-tr {
      top: 24px;
      right: 26px;
      text-align: right;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .clock-display {
      color: var(--bone);
      font-size: 11px;
    }
    .blink-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--signal);
      box-shadow: 0 0 6px var(--signal);
      animation: blink 1s steps(1) infinite;
    }
    @keyframes blink {
      0%, 49% { opacity: 1; }
      50%, 100% { opacity: 0.15; }
    }

    .ro-bl {
      bottom: 24px;
      left: 26px;
    }
    .ro-bl .status-line {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .status-tag {
      border: 1px solid var(--bone-4);
      padding: 1px 6px;
      font-size: 9px;
      color: var(--bone-2);
      text-transform: uppercase;
    }

    .ro-br {
      bottom: 24px;
      right: 26px;
      text-align: right;
    }

    /* ── Controls dock (Flat ink-1, hairline border, 0px radius) ── */
    .controls-dock {
      position: absolute;
      bottom: 22px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      gap: 1px;
      background: var(--line);
      border: 1px solid var(--line);
      padding: 0;
      z-index: 25;
    }
    .inst-btn {
      background: var(--ink-1);
      color: var(--bone);
      border: none;
      padding: 7px 12px;
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: background 120ms var(--ease-out, ease);
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

    /* Field Callout Plate */
    .target-callout {
      position: absolute;
      top: 66px;
      left: 26px;
      background: var(--ink-1);
      border: 1px solid var(--line);
      padding: 8px 12px;
      z-index: 15;
    }
    .callout-title {
      font-family: var(--font-sans);
      font-size: 13px;
      font-weight: 500;
      color: var(--bone);
    }
    .callout-meta {
      font-family: var(--font-mono);
      font-size: 10.5px;
      color: var(--bone-3);
      margin-top: 2px;
    }
    .signal-text {
      color: var(--signal);
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
      <span class="status-tag">SENTINEL-2 L2A</span>
      <span>10M MULTISPECTRAL · AWS STAC · REALTIME SUN</span>
    </div>
  </div>

  <!-- Bottom-Right Ephemeris -->
  <div class="corner-readout ro-br">
    <div>SUN <span id="sun-coords">__SUBSOLAR_LAT__° __SUBSOLAR_LON__°</span></div>
    <div style="margin-top: 2px;">SOLAR ELEVATION <span id="sun-elev" style="color: var(--bone);">__SOLAR_ELEV__°</span></div>
  </div>

  <!-- Central Controls Dock -->
  <div class="controls-dock">
    <button class="inst-btn" id="btn-focus">🎯 Focus Target</button>
    <button class="inst-btn active" id="btn-orbit">⏯️ Orbital Spin</button>
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

    // 1. Scene & Renderer
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x07080a); // --ink-0

    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 1000);
    camera.position.set(0, 0.4, 2.9);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    container.appendChild(renderer.domElement);

    // 2. Controls
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 1.35;
    controls.maxDistance = 5.5;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.45;

    // 3. Astronomical Ephemeris Calculator (Exact J2000 math from geo.ts)
    function getSubsolarVector(date) {
      const now = date || new Date();
      const d = (now.getTime() - 946728000000) / 86400000.0;
      const mRad = (357.529 + 0.98560028 * d) * Math.PI / 180.0;
      const qDeg = 280.459 + 0.98564736 * d;
      const lRad = (qDeg + 1.915 * Math.sin(mRad) + 0.020 * Math.sin(2.0 * mRad)) * Math.PI / 180.0;
      const eRad = (23.439 - 0.00000036 * d) * Math.PI / 180.0;
      const decRad = Math.asin(Math.max(-1.0, Math.min(1.0, Math.sin(eRad) * Math.sin(lRad))));

      const hoursUtc = now.getUTCHours() + now.getUTCMinutes() / 60.0 + now.getUTCSeconds() / 3600.0;
      const ghaDeg = (hoursUtc - 12.0) * 15.0;
      let subLonDeg = -ghaDeg;
      while (subLonDeg < -180.0) subLonDeg += 360.0;
      while (subLonDeg > 180.0) subLonDeg -= 360.0;

      const subLatRad = decRad;
      const subLonRad = subLonDeg * Math.PI / 180.0;

      const x = -Math.cos(subLatRad) * Math.cos(subLonRad);
      const y = Math.sin(subLatRad);
      const z = Math.cos(subLatRad) * Math.sin(subLonRad);
      return {
        vec: new THREE.Vector3(x, y, z).normalize(),
        lat: subLatRad * 180.0 / Math.PI,
        lon: subLonDeg
      };
    }

    function latLonToVector3(lat, lon, radius) {
      const phi = lat * Math.PI / 180.0;
      const theta = lon * Math.PI / 180.0;
      const x = -radius * Math.cos(phi) * Math.cos(theta);
      const y = radius * Math.sin(phi);
      const z = radius * Math.cos(phi) * Math.sin(theta);
      return new THREE.Vector3(x, y, z);
    }

    // 4. Procedural Fallback Textures (Guarantees zero blank screen while loading)
    function createFallbackTexture(isDay) {
      const canvas = document.createElement('canvas');
      canvas.width = 1024;
      canvas.height = 512;
      const ctx = canvas.getContext('2d');
      if (isDay) {
        ctx.fillStyle = '#071526';
        ctx.fillRect(0, 0, 1024, 512);
        ctx.fillStyle = '#1e3a2b';
        ctx.beginPath();
        ctx.ellipse(540, 240, 140, 100, 0, 0, Math.PI * 2);
        ctx.ellipse(320, 200, 110, 80, 0, 0, Math.PI * 2);
        ctx.ellipse(750, 340, 70, 50, 0, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.fillStyle = '#05070a';
        ctx.fillRect(0, 0, 1024, 512);
        ctx.fillStyle = '#ffb070';
        for (let i = 0; i < 350; i++) {
          const x = 200 + Math.random() * 700;
          const y = 100 + Math.random() * 300;
          ctx.fillRect(x, y, 1.5, 1.5);
        }
      }
      return new THREE.CanvasTexture(canvas);
    }

    const textureLoader = new THREE.TextureLoader();
    textureLoader.setCrossOrigin('anonymous');

    const dayTex = textureLoader.load(
      'https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg',
      undefined, undefined,
      () => { earthMaterial.uniforms.uDay.value = createFallbackTexture(true); }
    );
    const nightTex = textureLoader.load(
      'https://unpkg.com/three-globe/example/img/earth-night.jpg',
      undefined, undefined,
      () => { earthMaterial.uniforms.uNight.value = createFallbackTexture(false); }
    );
    const cloudsTex = textureLoader.load(
      'https://raw.githubusercontent.com/mrdoob/three.js/master/examples/textures/planets/earth_clouds_1024.png'
    );

    // 5. Earth Shader (Strict Watched.earth color grading: -12% sat, sodium lights, twilight band)
    const initialSun = getSubsolarVector();
    const earthUniforms = {
      uDay: { value: dayTex },
      uNight: { value: nightTex },
      uClouds: { value: cloudsTex },
      uSunDir: { value: initialSun.vec },
      uTime: { value: 0.0 }
    };

    const earthVertexShader = `
      varying vec2 vUv;
      varying vec3 vNormal;
      varying vec3 vPos;
      void main() {
        vUv = uv;
        vNormal = normalize(normalMatrix * normal);
        vPos = (modelMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * viewMatrix * vec4(vPos, 1.0);
      }
    `;

    const earthFragmentShader = `
      uniform sampler2D uDay;
      uniform sampler2D uNight;
      uniform sampler2D uClouds;
      uniform vec3 uSunDir;
      uniform float uTime;

      varying vec2 vUv;
      varying vec3 vNormal;
      varying vec3 vPos;

      float luma(vec3 c) {
        return dot(c, vec3(0.299, 0.587, 0.114));
      }

      vec3 gradeDay(vec3 c) {
        float l = luma(c);
        // Watched.earth art direction: -12% desaturation, cool-neutral tone balance
        return mix(vec3(l), c, 0.88) * vec3(0.96, 0.99, 1.03);
      }

      void main() {
        vec3 N = normalize(vNormal);
        vec3 L = normalize(uSunDir);
        float NdL = dot(N, L);

        vec4 daySample = texture2D(uDay, vUv);
        vec4 nightSample = texture2D(uNight, vUv);

        vec3 dayColor = gradeDay(daySample.rgb);

        // Sodium amber city lights (#FFB070)
        vec3 cityLights = nightSample.rgb * vec3(1.0, 0.69, 0.44) * 2.2;

        // Smooth day/night hemispheric blend on NdL
        float dayFactor = smoothstep(-0.08, 0.14, NdL);

        // Warm twilight terminator band (#FF9A5A)
        float terminatorFactor = 1.0 - clamp(abs(NdL) * 6.5, 0.0, 1.0);
        vec3 twilightColor = vec3(1.0, 0.60, 0.35) * terminatorFactor * 0.45;

        // Ocean specular glint from real sun
        vec3 V = normalize(cameraPosition - vPos);
        vec3 H = normalize(L + V);
        float NdotH = max(dot(N, H), 0.0);
        float spec = pow(NdotH, 24.0) * 0.38 * dayFactor;

        vec3 surface = mix(cityLights, dayColor, dayFactor) + twilightColor + vec3(spec);

        // Drifting clouds overlay
        vec2 cloudUv = vec2(vUv.x + uTime * 0.0005, vUv.y);
        vec4 clouds = texture2D(uClouds, cloudUv);
        float cloudLight = mix(0.12, 1.0, dayFactor);
        surface = mix(surface, clouds.rgb * cloudLight, clouds.r * 0.48);

        gl_FragColor = vec4(surface, 1.0);
      }
    `;

    const earthMaterial = new THREE.ShaderMaterial({
      uniforms: earthUniforms,
      vertexShader: earthVertexShader,
      fragmentShader: earthFragmentShader
    });
    const earthMesh = new THREE.Mesh(new THREE.SphereGeometry(1.0, 64, 64), earthMaterial);
    scene.add(earthMesh);

    // 6. Exponential Rayleigh Atmosphere Rim (BackSide additive)
    const atmoVertexShader = `
      varying vec3 vPos;
      void main() {
        vPos = (modelMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * viewMatrix * vec4(vPos, 1.0);
      }
    `;
    const atmoFragmentShader = `
      uniform vec3 uSunDir;
      varying vec3 vPos;
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
        float lit = smoothstep(-0.20, 0.28, mu);
        vec3 rimColor = vec3(0.58, 0.76, 1.0) * od * (0.2 + 0.8 * lit);
        gl_FragColor = vec4(rimColor, od * (0.25 + 0.75 * lit));
      }
    `;
    const atmoMaterial = new THREE.ShaderMaterial({
      uniforms: { uSunDir: { value: initialSun.vec } },
      vertexShader: atmoVertexShader,
      fragmentShader: atmoFragmentShader,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true
    });
    const atmoMesh = new THREE.Mesh(new THREE.SphereGeometry(1.025, 48, 48), atmoMaterial);
    scene.add(atmoMesh);

    // 7. Starfield (Sparse and dim, no twinkle)
    const starGeom = new THREE.BufferGeometry();
    const starPositions = new Float32Array(900 * 3);
    for (let i = 0; i < 900 * 3; i += 3) {
      const r = 24.0 + Math.random() * 20.0;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      starPositions[i] = r * Math.sin(phi) * Math.cos(theta);
      starPositions[i + 1] = r * Math.sin(phi) * Math.sin(theta);
      starPositions[i + 2] = r * Math.cos(phi);
    }
    starGeom.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
    const starMaterial = new THREE.PointsMaterial({ color: 0x94a3b8, size: 0.1, transparent: true, opacity: 0.55 });
    scene.add(new THREE.Points(starGeom, starMaterial));

    // 8. Place Marker: Watched.earth Crosshair Reticle (thin ring, 4 ticks, center dot)
    const targetPos = latLonToVector3(targetLat, targetLon, 1.008);
    const markerGroup = new THREE.Group();

    // Center dot (sodium orange)
    const dotGeom = new THREE.SphereGeometry(0.012, 16, 16);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0xff6a1a });
    const dotMesh = new THREE.Mesh(dotGeom, dotMat);
    dotMesh.position.copy(targetPos);
    markerGroup.add(dotMesh);

    // Thin reticle ring
    const ringGeom = new THREE.RingGeometry(0.024, 0.028, 32);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0xff6a1a, side: THREE.DoubleSide });
    const ringMesh = new THREE.Mesh(ringGeom, ringMat);
    ringMesh.position.copy(targetPos);
    ringMesh.lookAt(targetPos.clone().multiplyScalar(2));
    markerGroup.add(ringMesh);

    // 4 Crosshair ticks
    const tickLen = 0.014;
    const tickMat = new THREE.LineBasicMaterial({ color: 0xff6a1a });
    const northPt = latLonToVector3(targetLat + 0.8, targetLon, 1.008);
    const southPt = latLonToVector3(targetLat - 0.8, targetLon, 1.008);
    const eastPt = latLonToVector3(targetLat, targetLon + 0.8, 1.008);
    const westPt = latLonToVector3(targetLat, targetLon - 0.8, 1.008);

    function makeLine(p1, p2) {
      const g = new THREE.BufferGeometry().setFromPoints([p1, p2]);
      return new THREE.Line(g, tickMat);
    }
    markerGroup.add(makeLine(targetPos, northPt));
    markerGroup.add(makeLine(targetPos, southPt));
    markerGroup.add(makeLine(targetPos, eastPt));
    markerGroup.add(makeLine(targetPos, westPt));

    scene.add(markerGroup);

    // 9. Camera Director
    function focusTarget() {
      const camTargetPos = targetPos.clone().normalize().multiplyScalar(2.3);
      let step = 0;
      function animateCam() {
        step += 0.04;
        camera.position.lerp(camTargetPos, 0.08);
        controls.target.set(0, 0, 0);
        controls.update();
        if (step < 1.0) requestAnimationFrame(animateCam);
      }
      animateCam();
    }
    setTimeout(focusTarget, 500);

    // Button interactions
    const btnOrbit = document.getElementById('btn-orbit');
    document.getElementById('btn-focus').addEventListener('click', focusTarget);
    btnOrbit.addEventListener('click', () => {
      controls.autoRotate = !controls.autoRotate;
      btnOrbit.classList.toggle('active', controls.autoRotate);
    });
    document.getElementById('btn-sun').addEventListener('click', () => {
      const sunPos = earthUniforms.uSunDir.value.clone().multiplyScalar(2.5);
      camera.position.copy(sunPos);
      controls.target.set(0, 0, 0);
      controls.update();
    });
    document.getElementById('btn-night').addEventListener('click', () => {
      const nightPos = earthUniforms.uSunDir.value.clone().multiplyScalar(-2.5);
      camera.position.copy(nightPos);
      controls.target.set(0, 0, 0);
      controls.update();
    });

    // 10. Frame Loop & Live Clock
    const clock = new THREE.Clock();
    const clockElem = document.getElementById('live-utc-clock');
    const sunCoordsElem = document.getElementById('sun-coords');
    const sunElevElem = document.getElementById('sun-elev');

    function pad2(n) { return n < 10 ? '0' + n : n; }

    function animate() {
      requestAnimationFrame(animate);
      const elapsed = clock.getElapsedTime();

      // Update live UTC clock string
      const now = new Date();
      const utcStr = now.getUTCFullYear() + '-' +
        pad2(now.getUTCMonth() + 1) + '-' +
        pad2(now.getUTCDate()) + ' ' +
        pad2(now.getUTCHours()) + ':' +
        pad2(now.getUTCMinutes()) + ':' +
        pad2(now.getUTCSeconds()) + ' UTC';
      clockElem.innerText = utcStr;

      // Update sun direction every 2 seconds
      if (Math.floor(elapsed) % 2 === 0) {
        const sunData = getSubsolarVector(now);
        earthUniforms.uSunDir.value.copy(sunData.vec);
        atmoMaterial.uniforms.uSunDir.value.copy(sunData.vec);
        sunCoordsElem.innerText = (sunData.lat >= 0 ? '+' : '') + sunData.lat.toFixed(1) + '° ' + (sunData.lon >= 0 ? '+' : '') + sunData.lon.toFixed(1) + '°';
      }

      earthUniforms.uTime.value = elapsed;

      controls.update();
      renderer.render(scene, camera);
    }
    animate();

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

    return html
