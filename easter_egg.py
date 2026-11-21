"""CropScope Secret Orbital Recon & Retro Sci-Fi Flight Deck Easter Egg.

Triggerable via:
1. Keyboard: The classic Konami Code (Up Up Down Down Left Right Left Right B A).
2. Mouse/Touch: Clicking the header 🛰️ satellite icon 3 times.
3. Kisan Mitra Chatbot: Asking about 'konami', 'mars', 'easter egg', or 'who built cropscope'.
"""

import streamlit as st


def render_orbital_recon_easter_egg() -> None:
    """Injects the secret Orbital Flight Deck HUD listener and interactive retro modal."""
    st.components.v1.html(
        """
        <script>
        (function() {
          const parentDoc = window.parent.document;
          const parentWin = window.parent;
          if (!parentDoc || !parentWin) return;

          // Prevent duplicate HUD injection
          if (parentDoc.getElementById("cs-orbital-hud-overlay")) return;

          // 1. Synthesize 8-bit retro arcade chime via Web Audio API
          function playChiptuneFanfare() {
            try {
              const AudioContext = parentWin.AudioContext || parentWin.webkitAudioContext;
              if (!AudioContext) return;
              const ctx = new AudioContext();
              // Arpeggio: C4, E4, G4, C5, E5, G5, C6
              const frequencies = [261.63, 329.63, 392.00, 523.25, 659.25, 783.99, 1046.50];
              frequencies.forEach((freq, i) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'square';
                osc.frequency.setValueAtTime(freq, ctx.currentTime + i * 0.075);
                gain.gain.setValueAtTime(0.12, ctx.currentTime + i * 0.075);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.075 + 0.12);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(ctx.currentTime + i * 0.075);
                osc.stop(ctx.currentTime + i * 0.075 + 0.13);
              });
            } catch (e) {
              console.warn("Audio playback not permitted yet", e);
            }
          }

          // 2. Build the Retro Sci-Fi CRT Flight Deck Overlay
          const overlay = parentDoc.createElement("div");
          overlay.id = "cs-orbital-hud-overlay";
          overlay.style.cssText = [
            "position: fixed",
            "top: 0",
            "left: 0",
            "width: 100vw",
            "height: 100vh",
            "background: rgba(5, 10, 15, 0.92)",
            "backdrop-filter: blur(8px)",
            "z-index: 9999999",
            "display: none",
            "justify-content: center",
            "align-items: center",
            "font-family: 'Martian Mono', ui-monospace, monospace",
            "color: #00ff66",
            "box-sizing: border-box",
            "padding: 20px",
            "user-select: none"
          ].join(";");

          overlay.innerHTML = `
            <div id="cs-hud-terminal" style="
              width: 900px;
              max-width: 95vw;
              max-height: 90vh;
              overflow-y: auto;
              background: #061109;
              border: 2px solid #00ff66;
              box-shadow: 0 0 35px rgba(0, 255, 102, 0.35), inset 0 0 20px rgba(0, 255, 102, 0.15);
              padding: 28px;
              position: relative;
              border-radius: 4px;
            ">
              <!-- CRT Scanline Effect Overlay -->
              <div style="
                position: absolute; top:0; left:0; width:100%; height:100%;
                background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.35) 50%);
                background-size: 100% 4px; pointer-events: none; z-index: 10;
              "></div>

              <!-- Header Bar -->
              <div style="display:flex; justify-content:space-between; align-items:center; border-bottom: 1px solid #00ff66; padding-bottom: 12px; margin-bottom: 16px;">
                <div style="display:flex; align-items:center; gap:10px;">
                  <span style="font-size: 24px; animation: blink 1s infinite;">🛰️</span>
                  <div>
                    <div style="font-size: 14px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase;">
                      CROPSCOPE // ORBITAL RECON FLIGHT DECK
                    </div>
                    <div style="font-size: 10px; opacity: 0.8; letter-spacing: 0.08em;">
                      LEVEL 5 CLASSIFIED TELEMETRY &bull; ISRO / ESA SENTINEL-2 NODE
                    </div>
                  </div>
                </div>
                <button id="cs-hud-close" style="
                  background: transparent; border: 1px solid #00ff66; color: #00ff66;
                  font-family: inherit; font-size: 14px; font-weight: 700; padding: 4px 12px;
                  cursor: pointer; text-transform: uppercase; letter-spacing: 0.1em;
                ">✕ ABORT [ESC]</button>
              </div>

              <!-- Main Terminal Layout: Telemetry + Live Radar -->
              <div style="display:flex; flex-wrap:wrap; gap: 20px; margin-bottom: 20px;">
                <!-- Telemetry Readout -->
                <div style="flex: 1 1 450px; font-size: 11.5px; line-height: 1.6; opacity: 0.95;">
                  <div style="color: #66ff99; margin-bottom: 6px;">[ SATELLITE CONSTELLATION STATUS ]</div>
                  <div>&bull; ACTIVE PLATFORM: <span style="color:#fff;">SENTINEL-2B (COPERNICUS)</span></div>
                  <div>&bull; ORBITAL ALTITUDE: <span style="color:#fff;">786.2 KM SUN-SYNCHRONOUS</span></div>
                  <div>&bull; DOWNLINK STATION: <span style="color:#fff;">NRSC GROUND SEGMENT, SHADNAGAR (IN)</span></div>
                  <div>&bull; INCLINATION: <span style="color:#fff;">98.62° &bull; REVISIT: 5 DAYS</span></div>
                  <div>&bull; SPECTRAL BANDS: <span style="color:#fff;">13 CHANNELS (VNIR / SWIR @ 10m)</span></div>
                  <div style="margin-top: 10px; color: #66ff99;">[ MISSION DIRECTIVE &amp; TRIBUTE ]</div>
                  <div style="color: #e2e8f0; background: rgba(0, 255, 102, 0.08); padding: 10px; border-left: 3px solid #00ff66; margin-top: 4px;">
                    <em>"Dedicated to the 150 million farmers of India — the Annadatas feeding 1.4 billion lives. Space-age remote sensing belongs in your soil."</em>
                    <div style="margin-top: 6px; font-size: 10.5px; color: #66ff99;">
                      — Engineered with ❤️ by <strong>Shreyash Shukla</strong> &amp; the CropScope Team.
                    </div>
                  </div>
                </div>

                <!-- Live Rotating Radar Canvas -->
                <div style="flex: 0 0 200px; display:flex; flex-direction:column; align-items:center;">
                  <canvas id="cs-radar-canvas" width="180" height="180" style="background: #020804; border: 1px solid #00ff66; border-radius: 50%; box-shadow: 0 0 15px rgba(0,255,102,0.25);"></canvas>
                  <div style="font-size: 9.5px; color: #66ff99; margin-top: 6px; text-transform: uppercase;">
                    LIVE SAT-TRACKER // 28.6°N 77.2°E
                  </div>
                </div>
              </div>

              <!-- Interactive Mission Actions -->
              <div style="border-top: 1px dashed #00ff66; padding-top: 16px; display:flex; gap: 12px; flex-wrap: wrap;">
                <button id="cs-btn-mars" style="
                  background: rgba(255, 106, 26, 0.15); border: 1px solid #ff6a1a; color: #ff6a1a;
                  font-family: inherit; font-size: 11px; font-weight: 700; padding: 8px 14px;
                  cursor: pointer; text-transform: uppercase; letter-spacing: 0.08em;
                ">🚀 WARP TO MARS SOL 54 (ARES III POTATO FARM)</button>

                <button id="cs-btn-matrix" style="
                  background: rgba(0, 255, 102, 0.15); border: 1px solid #00ff66; color: #00ff66;
                  font-family: inherit; font-size: 11px; font-weight: 700; padding: 8px 14px;
                  cursor: pointer; text-transform: uppercase; letter-spacing: 0.08em;
                ">🟢 TOGGLE MATRIX CYBER RAIN</button>

                <button id="cs-btn-sound" style="
                  background: transparent; border: 1px solid rgba(0, 255, 102, 0.5); color: #00ff66;
                  font-family: inherit; font-size: 11px; padding: 8px 12px;
                  cursor: pointer; text-transform: uppercase;
                ">🔊 REPLAY 8-BIT FANFARE</button>
              </div>

              <!-- Secret Terminal Message Output -->
              <div id="cs-hud-console-output" style="margin-top: 12px; font-size: 11px; min-height: 20px; color: #ffeb3b;"></div>
            </div>
          `;

          parentDoc.body.appendChild(overlay);

          // Radar sweep animation loop
          let radarAngle = 0;
          let radarAnimationId = null;
          function drawRadar() {
            const canvas = parentDoc.getElementById("cs-radar-canvas");
            if (!canvas) return;
            const ctx = canvas.getContext("2d");
            if (!ctx) return;
            const w = canvas.width;
            const h = canvas.height;
            const cx = w / 2;
            const cy = h / 2;
            const r = w / 2 - 4;

            ctx.fillStyle = "rgba(2, 8, 4, 0.18)";
            ctx.fillRect(0, 0, w, h);

            // Radar rings
            ctx.strokeStyle = "rgba(0, 255, 102, 0.28)";
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.arc(cx, cy, r * 0.33, 0, Math.PI * 2); ctx.stroke();
            ctx.beginPath(); ctx.arc(cx, cy, r * 0.66, 0, Math.PI * 2); ctx.stroke();
            ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();

            // Crosshairs
            ctx.beginPath();
            ctx.moveTo(cx, 0); ctx.lineTo(cx, h);
            ctx.moveTo(0, cy); ctx.lineTo(w, cy);
            ctx.stroke();

            // Rotating sweep beam
            radarAngle += 0.04;
            const x = cx + Math.cos(radarAngle) * r;
            const y = cy + Math.sin(radarAngle) * r;
            ctx.strokeStyle = "#00ff66";
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(x, y);
            ctx.stroke();

            // Satellite Blips
            const s1x = cx + Math.cos(radarAngle - 1.2) * (r * 0.7);
            const s1y = cy + Math.sin(radarAngle - 1.2) * (r * 0.7);
            ctx.fillStyle = "#ff6a1a";
            ctx.fillRect(s1x - 2, s1y - 2, 5, 5);

            const s2x = cx + Math.cos(radarAngle - 2.8) * (r * 0.45);
            const s2y = cy + Math.sin(radarAngle - 2.8) * (r * 0.45);
            ctx.fillStyle = "#00ffff";
            ctx.fillRect(s2x - 2, s2y - 2, 5, 5);

            radarAnimationId = requestAnimationFrame(drawRadar);
          }

          // Matrix Rain Overlay Toggle
          let matrixCanvas = null;
          let matrixInterval = null;
          function toggleMatrixRain() {
            if (matrixCanvas) {
              clearInterval(matrixInterval);
              matrixCanvas.remove();
              matrixCanvas = null;
              matrixInterval = null;
              return;
            }
            matrixCanvas = parentDoc.createElement("canvas");
            matrixCanvas.id = "cs-matrix-rain";
            matrixCanvas.style.cssText = "position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:9999998;pointer-events:none;opacity:0.65;";
            matrixCanvas.width = parentWin.innerWidth;
            matrixCanvas.height = parentWin.innerHeight;
            parentDoc.body.appendChild(matrixCanvas);

            const mCtx = matrixCanvas.getContext("2d");
            const chars = "0123456789ABCDEFCOPERNICUSSENTINELKISANMITRA🌾🛰️";
            const fontSize = 14;
            const cols = Math.floor(matrixCanvas.width / fontSize);
            const drops = Array(cols).fill(1);

            matrixInterval = setInterval(() => {
              mCtx.fillStyle = "rgba(0, 0, 0, 0.06)";
              mCtx.fillRect(0, 0, matrixCanvas.width, matrixCanvas.height);
              mCtx.fillStyle = "#00ff66";
              mCtx.font = fontSize + "px monospace";
              for (let i = 0; i < drops.length; i++) {
                const text = chars.charAt(Math.floor(Math.random() * chars.length));
                mCtx.fillText(text, i * fontSize, drops[i] * fontSize);
                if (drops[i] * fontSize > matrixCanvas.height && Math.random() > 0.975) {
                  drops[i] = 0;
                }
                drops[i]++;
              }
            }, 35);
          }

          function openOrbitalHud() {
            overlay.style.display = "flex";
            playChiptuneFanfare();
            if (!radarAnimationId) {
              drawRadar();
            }
          }

          function closeOrbitalHud() {
            overlay.style.display = "none";
            if (radarAnimationId) {
              cancelAnimationFrame(radarAnimationId);
              radarAnimationId = null;
            }
          }

          // Button click listeners
          parentDoc.getElementById("cs-hud-close").addEventListener("click", closeOrbitalHud);
          parentDoc.getElementById("cs-btn-sound").addEventListener("click", playChiptuneFanfare);
          parentDoc.getElementById("cs-btn-matrix").addEventListener("click", () => {
            toggleMatrixRain();
            const out = parentDoc.getElementById("cs-hud-console-output");
            out.innerText = matrixCanvas ? "🟢 MATRIX CYBER-RAIN STREAM ONLINE." : "⚪ MATRIX CYBER-RAIN DISABLED.";
          });
          parentDoc.getElementById("cs-btn-mars").addEventListener("click", () => {
            const out = parentDoc.getElementById("cs-hud-console-output");
            out.innerText = "🚀 ORBITAL TRANSFER INITIATED: ARES III ACIDALIA PLANITIA (31.5°N, 33.2°W). Crop: Sol 54 Potato.";
            playChiptuneFanfare();
            // Switch terminal to Martian red/amber theme
            const term = parentDoc.getElementById("cs-hud-terminal");
            term.style.borderColor = "#ff4400";
            term.style.boxShadow = "0 0 35px rgba(255, 68, 0, 0.4)";
          });

          // Close on ESC key or backdrop click
          parentWin.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && overlay.style.display === "flex") {
              closeOrbitalHud();
            }
          });
          overlay.addEventListener("click", (e) => {
            if (e.target === overlay) closeOrbitalHud();
          });

          // 3. LISTENERS
          // A) KONAMI CODE: Up Up Down Down Left Right Left Right B A
          const konamiSequence = [
            "arrowup", "arrowup", "arrowdown", "arrowdown",
            "arrowleft", "arrowright", "arrowleft", "arrowright",
            "b", "a"
          ];
          let konamiIdx = 0;
          parentWin.addEventListener("keydown", function(e) {
            // Ignore keystrokes when typing inside text inputs or chat
            const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : "";
            if (tag === "input" || tag === "textarea") return;

            const pressed = e.key.toLowerCase();
            if (pressed === konamiSequence[konamiIdx]) {
              konamiIdx++;
              if (konamiIdx === konamiSequence.length) {
                konamiIdx = 0;
                openOrbitalHud();
              }
            } else {
              konamiIdx = (pressed === konamiSequence[0]) ? 1 : 0;
            }
          });

          // B) 3-CLICK HEADER SATELLITE ICON TRIGGER (Mobile & Desktop)
          function bindHeaderIcon() {
            const satIcon = parentDoc.querySelector(".app-header-icon") ||
                            parentDoc.querySelector("[data-testid='cropscope-header'] .app-header-icon");
            if (satIcon && !satIcon._easterEggBound) {
              satIcon._easterEggBound = true;
              satIcon.style.cursor = "pointer";
              satIcon.title = "🛰️ Satellite Node (Click 3x for Orbital Recon)";
              let clicks = 0;
              let timer = null;
              satIcon.addEventListener("click", () => {
                clicks++;
                clearTimeout(timer);
                if (clicks >= 3) {
                  clicks = 0;
                  openOrbitalHud();
                } else {
                  timer = setTimeout(() => { clicks = 0; }, 800);
                }
              });
            }
          }
          bindHeaderIcon();
          setInterval(bindHeaderIcon, 2000);

        })();
        </script>
        """,
        height=0,
    )
