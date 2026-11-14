"""Interactive 3D real-time Earth globe with astronomical solar terminator.

Inspired by Watched.earth: renders the Earth in space with real-time solar tracking,
realistic day/night hemispheric division, glowing sodium-amber city lights,
twilight terminator gradient, Rayleigh atmospheric rim, and field target instrumentation.
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

    # Days since J2000.0 (2000-01-01 12:00 UTC)
    # Unix timestamp for 2000-01-01 12:00:00 UTC is 946728000
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
    # Solar noon at Greenwich corresponds to 12:00 UTC
    # 15 degrees per hour
    gha_deg = (hours_utc - 12.0) * 15.0
    subsolar_lon = -gha_deg

    # Normalize longitude to [-180, 180]
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

    # Sunrise/sunset occurs when solar elevation is approximately -0.83 degrees
    is_sunlit = solar_elevation_deg >= -0.83
    return is_sunlit, round(solar_elevation_deg, 2)


_GLOBE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
      user-select: none;
    }
    body {
      background: #030712;
      color: #f3f4f6;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
    }
    #canvas-container:active {
      cursor: grabbing;
    }
    /* Mission Control HUD Overlay */
    .hud-panel {
      position: absolute;
      background: rgba(15, 23, 42, 0.78);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 10px;
      padding: 10px 14px;
      pointer-events: auto;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
      z-index: 10;
    }
    .hud-top-left {
      top: 12px;
      left: 12px;
    }
    .hud-top-right {
      top: 12px;
      right: 12px;
      text-align: right;
    }
    .hud-bottom-left {
      bottom: 12px;
      left: 12px;
      display: flex;
      gap: 8px;
    }
    .hud-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 20px;
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
      margin-bottom: 6px;
    }
    .hud-badge .pulse {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
      animation: pulse 1.8s infinite;
    }
    @keyframes pulse {
      0% { opacity: 0.4; transform: scale(0.9); }
      50% { opacity: 1; transform: scale(1.3); }
      100% { opacity: 0.4; transform: scale(0.9); }
    }
    .hud-title {
      font-size: 13px;
      font-weight: 600;
      color: #f9fafb;
      max-width: 260px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .hud-sub {
      font-size: 11px;
      color: #94a3b8;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      margin-top: 2px;
    }
    .hud-btn {
      background: rgba(30, 41, 59, 0.85);
      color: #e2e8f0;
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .hud-btn:hover {
      background: rgba(51, 65, 85, 0.95);
      border-color: rgba(255, 255, 255, 0.3);
      color: #ffffff;
    }
    .telemetry-item {
      font-size: 11px;
      color: #cbd5e1;
      margin-bottom: 2px;
    }
    .telemetry-value {
      font-weight: 600;
      color: #38bdf8;
      font-family: ui-monospace, monospace;
    }
    /* Legend Pill */
    .legend-bar {
      position: absolute;
      bottom: 12px;
      right: 12px;
      background: rgba(15, 23, 42, 0.75);
      backdrop-filter: blur(8px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 8px;
      padding: 6px 12px;
      font-size: 10px;
      color: #94a3b8;
      display: flex;
      align-items: center;
      gap: 12px;
      z-index: 10;
    }
    .legend-item {
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
    }
    .dot-day { background: #38bdf8; box-shadow: 0 0 6px #38bdf8; }
    .dot-term { background: #fb923c; box-shadow: 0 0 6px #fb923c; }
    .dot-night { background: #f59e0b; box-shadow: 0 0 6px #f59e0b; }
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
  <div id="canvas-container"></div>

  <!-- Top Left: Location Info & Target -->
  <div class="hud-panel hud-top-left">
    <div class="hud-badge"><span class="pulse"></span> 3D Real-Time Orbital Globe</div>
    <div class="hud-title" id="hud-location-name">__LOCATION_NAME_TEXT__</div>
    <div class="hud-sub">Lat: __LAT_FMT__° &nbsp;·&nbsp; Lon: __LON_FMT__°</div>
  </div>

  <!-- Top Right: Astronomical Solar Telemetry -->
  <div class="hud-panel hud-top-right">
    <div class="telemetry-item">Solar Status: <span class="telemetry-value" id="solar-status-text">__SOLAR_STATUS__</span></div>
    <div class="telemetry-item">Solar Elevation: <span class="telemetry-value" id="solar-elev-text">__SOLAR_ELEV__°</span></div>
    <div class="telemetry-item">Subsolar Lon: <span class="telemetry-value" id="subsolar-lon-text">__SUBSOLAR_LON__°</span></div>
  </div>

  <!-- Bottom Left: Interactive Controls -->
  <div class="hud-bottom-left">
    <button class="hud-btn" id="btn-focus">🎯 Focus Target</button>
    <button class="hud-btn" id="btn-rotate">⏯️ Toggle Rotation</button>
    <button class="hud-btn" id="btn-sun">☀️ Subsolar View</button>
  </div>

  <!-- Bottom Right: Day / Night Legend -->
  <div class="legend-bar">
    <div class="legend-item"><span class="dot dot-day"></span> Daylight</div>
    <div class="legend-item"><span class="dot dot-term"></span> Twilight</div>
    <div class="legend-item"><span class="dot dot-night"></span> City Lights</div>
  </div>

  <script>
    const targetLat = __TARGET_LAT__;
    const targetLon = __TARGET_LON__;
    const locationName = __LOCATION_NAME_JSON__;

    const container = document.getElementById('canvas-container');
    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || __HEIGHT__;

    // 1. Scene, Camera, Renderer
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(0, 0.5, 3.2);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    container.appendChild(renderer.domElement);

    // 2. OrbitControls
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 1.35;
    controls.maxDistance = 6.0;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.4;

    // 3. Astronomical Subsolar Calculator
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
      return new THREE.Vector3(x, y, z).normalize();
    }

    // Convert Lat/Lon to 3D Sphere Position
    function latLonToVector3(lat, lon, radius) {
      const phi = lat * Math.PI / 180.0;
      const theta = lon * Math.PI / 180.0;
      const x = -radius * Math.cos(phi) * Math.cos(theta);
      const y = radius * Math.sin(phi);
      const z = radius * Math.cos(phi) * Math.sin(theta);
      return new THREE.Vector3(x, y, z);
    }

    // 4. Procedural Fallback Textures (Guarantees zero black screen while loading)
    function createFallbackTexture(isDay) {
      const canvas = document.createElement('canvas');
      canvas.width = 1024;
      canvas.height = 512;
      const ctx = canvas.getContext('2d');
      if (isDay) {
        ctx.fillStyle = '#0f2b48';
        ctx.fillRect(0, 0, 1024, 512);
        ctx.fillStyle = '#22543d';
        ctx.beginPath();
        ctx.ellipse(540, 240, 140, 100, 0, 0, Math.PI * 2);
        ctx.ellipse(320, 200, 110, 80, 0, 0, Math.PI * 2);
        ctx.ellipse(750, 340, 70, 50, 0, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.fillStyle = '#030712';
        ctx.fillRect(0, 0, 1024, 512);
        ctx.fillStyle = '#fbbf24';
        for (let i = 0; i < 400; i++) {
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
      () => { earthMaterial.uniforms.dayTexture.value = createFallbackTexture(true); }
    );
    const nightTex = textureLoader.load(
      'https://unpkg.com/three-globe/example/img/earth-night.jpg',
      undefined, undefined,
      () => { earthMaterial.uniforms.nightTexture.value = createFallbackTexture(false); }
    );
    const cloudsTex = textureLoader.load(
      'https://raw.githubusercontent.com/mrdoob/three.js/master/examples/textures/planets/earth_clouds_1024.png'
    );

    // 5. Custom Day/Night & Twilight Terminator Shader
    const sunDir = getSubsolarVector();
    const earthUniforms = {
      dayTexture: { value: dayTex },
      nightTexture: { value: nightTex },
      cloudTexture: { value: cloudsTex },
      sunDirection: { value: sunDir },
      time: { value: 0.0 }
    };

    const earthVertexShader = `
      varying vec2 vUv;
      varying vec3 vNormal;
      varying vec3 vPosition;
      void main() {
        vUv = uv;
        vNormal = normalize(normalMatrix * normal);
        vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `;

    const earthFragmentShader = `
      uniform sampler2D dayTexture;
      uniform sampler2D nightTexture;
      uniform sampler2D cloudTexture;
      uniform vec3 sunDirection;
      uniform float time;

      varying vec2 vUv;
      varying vec3 vNormal;
      varying vec3 vPosition;

      void main() {
        vec3 normal = normalize(vNormal);
        float cosTheta = dot(normal, normalize(sunDirection));

        vec4 dayColor = texture2D(dayTexture, vUv);
        vec4 nightColor = texture2D(nightTexture, vUv);

        // Sodium amber tint for city night lights
        vec3 cityLights = nightColor.rgb * vec3(1.15, 0.85, 0.55) * 1.6;

        // Smooth day/night hemispheric transition
        float dayFactor = smoothstep(-0.10, 0.15, cosTheta);

        // Soft warm twilight band along the terminator
        float terminatorFactor = 1.0 - clamp(abs(cosTheta) * 6.0, 0.0, 1.0);
        vec3 twilightColor = vec3(0.98, 0.45, 0.16) * terminatorFactor * 0.45;

        // Specular ocean glint towards the sun
        vec3 viewDir = normalize(-vPosition);
        vec3 halfVector = normalize(normalize(sunDirection) + viewDir);
        float NdotH = max(dot(normal, halfVector), 0.0);
        float specular = pow(NdotH, 20.0) * 0.35 * dayFactor;

        // Base surface blend
        vec3 surface = mix(cityLights, dayColor.rgb, dayFactor) + twilightColor + vec3(specular);

        // Drifting clouds overlay
        vec2 cloudUv = vec2(vUv.x + time * 0.0006, vUv.y);
        vec4 clouds = texture2D(cloudTexture, cloudUv);
        float cloudLight = mix(0.12, 1.0, dayFactor);
        surface = mix(surface, clouds.rgb * cloudLight, clouds.r * 0.52);

        gl_FragColor = vec4(surface, 1.0);
      }
    `;

    const earthGeometry = new THREE.SphereGeometry(1.0, 64, 64);
    const earthMaterial = new THREE.ShaderMaterial({
      uniforms: earthUniforms,
      vertexShader: earthVertexShader,
      fragmentShader: earthFragmentShader
    });
    const earthMesh = new THREE.Mesh(earthGeometry, earthMaterial);
    scene.add(earthMesh);

    // 6. Glowing Rayleigh Atmosphere Rim Shell
    const atmosphereVertexShader = `
      varying vec3 vNormal;
      varying vec3 vPosition;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `;
    const atmosphereFragmentShader = `
      varying vec3 vNormal;
      varying vec3 vPosition;
      uniform vec3 sunDirection;
      void main() {
        vec3 viewDir = normalize(-vPosition);
        float fresnel = pow(1.0 - max(dot(vNormal, viewDir), 0.0), 2.8);
        float sunFacing = max(dot(vNormal, normalize(sunDirection)), 0.0);
        vec3 glowColor = vec3(0.2, 0.65, 1.0) * fresnel * (0.35 + 0.65 * sunFacing);
        gl_FragColor = vec4(glowColor, fresnel * (0.3 + 0.7 * sunFacing));
      }
    `;
    const atmosphereMaterial = new THREE.ShaderMaterial({
      uniforms: { sunDirection: { value: sunDir } },
      vertexShader: atmosphereVertexShader,
      fragmentShader: atmosphereFragmentShader,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true
    });
    const atmosphereMesh = new THREE.Mesh(new THREE.SphereGeometry(1.025, 48, 48), atmosphereMaterial);
    scene.add(atmosphereMesh);

    // 7. Background Starfield
    const starGeometry = new THREE.BufferGeometry();
    const starCount = 1200;
    const starPositions = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount * 3; i += 3) {
      const r = 25.0 + Math.random() * 20.0;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      starPositions[i] = r * Math.sin(phi) * Math.cos(theta);
      starPositions[i + 1] = r * Math.sin(phi) * Math.sin(theta);
      starPositions[i + 2] = r * Math.cos(phi);
    }
    starGeometry.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
    const starMaterial = new THREE.PointsMaterial({ color: 0x94a3b8, size: 0.12, transparent: true, opacity: 0.7 });
    scene.add(new THREE.Points(starGeometry, starMaterial));

    // 8. Field Target Marker on Globe
    const targetPos = latLonToVector3(targetLat, targetLon, 1.012);
    const markerGroup = new THREE.Group();

    // Emerald center sphere
    const pinGeom = new THREE.SphereGeometry(0.016, 16, 16);
    const pinMat = new THREE.MeshBasicMaterial({ color: 0x10b981 });
    const pinMesh = new THREE.Mesh(pinGeom, pinMat);
    pinMesh.position.copy(targetPos);
    markerGroup.add(pinMesh);

    // Pulsing radar ring
    const ringGeom = new THREE.RingGeometry(0.024, 0.034, 32);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x34d399, side: THREE.DoubleSide, transparent: true, opacity: 0.85 });
    const ringMesh = new THREE.Mesh(ringGeom, ringMat);
    ringMesh.position.copy(targetPos);
    ringMesh.lookAt(targetPos.clone().multiplyScalar(2));
    markerGroup.add(ringMesh);

    scene.add(markerGroup);

    // 9. Camera Focus onto Target
    function focusTarget() {
      const camTargetPos = targetPos.clone().normalize().multiplyScalar(2.4);
      let step = 0;
      function animateCam() {
        step += 0.04;
        camera.position.lerp(camTargetPos, 0.08);
        controls.target.set(0, 0, 0);
        controls.update();
        if (step < 1.0) {
          requestAnimationFrame(animateCam);
        }
      }
      animateCam();
    }
    setTimeout(focusTarget, 600);

    // Interactive Button Listeners
    document.getElementById('btn-focus').addEventListener('click', focusTarget);
    document.getElementById('btn-rotate').addEventListener('click', () => {
      controls.autoRotate = !controls.autoRotate;
    });
    document.getElementById('btn-sun').addEventListener('click', () => {
      const sunPos = earthUniforms.sunDirection.value.clone().multiplyScalar(2.6);
      camera.position.copy(sunPos);
      controls.target.set(0, 0, 0);
      controls.update();
    });

    // 10. Animation Loop
    let clock = new THREE.Clock();
    function animate() {
      requestAnimationFrame(animate);
      const elapsedTime = clock.getElapsedTime();

      // Update solar direction every ~3 seconds
      if (Math.floor(elapsedTime) % 3 === 0) {
        const updatedSun = getSubsolarVector();
        earthUniforms.sunDirection.value.copy(updatedSun);
        atmosphereMaterial.uniforms.sunDirection.value.copy(updatedSun);
      }

      // Cloud drift & pulse animation
      earthUniforms.time.value = elapsedTime;
      const pulseScale = 1.0 + 0.25 * Math.sin(elapsedTime * 4.0);
      ringMesh.scale.set(pulseScale, pulseScale, pulseScale);

      controls.update();
      renderer.render(scene, camera);
    }
    animate();

    // 11. Handle Resizing
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
    height: int = 500,
) -> str:
    """Build a complete, standalone Three.js WebGL component showing a 3D Earth.

    Features:
    - Real-time astronomical day/night terminator with warm twilight gradient.
    - Blue Marble daytime earth & warm amber city night lights.
    - Drifting cloud layer and starry space background.
    - Pulsing mission-control target marker at the field coordinates.
    - Telemetry HUD with live solar altitude, daylight state, and UTC tracking.
    """
    sub_lat, sub_lon = compute_subsolar_point()
    is_day, elevation = is_location_sunlit(center_lat, center_lon)
    solar_status = "☀️ Sunlit (Daytime)" if is_day else "🌙 In Shadow (Night)"

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
    html = html.replace("__SUBSOLAR_LON__", f"{sub_lon:+.1f}")

    return html
