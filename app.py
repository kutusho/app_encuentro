# app.py
import os
import time
import uuid
import datetime as dt

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ====== CONFIG ======
st.set_page_config(
    page_title="Encuentro Internacional de Guías – Registro y QR",
    page_icon="🧭",
    layout="centered"
)

# ====== UTILS: Google Sheets ======
# Requiere en st.secrets:
# [gcp_service_account] ... (tu JSON)
# [sheets]
# gsheet_id = "..."
# attendees_ws = "asistentes"
# checkins_ws  = "checkins"
def _open_sheets():
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        sa_info = dict(st.secrets["gcp_service_account"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
        gc = gspread.authorize(creds)

        sh = gc.open_by_key(st.secrets["sheets"]["gsheet_id"])
        ws_att = sh.worksheet(st.secrets["sheets"]["attendees_ws"])
        ws_chk = sh.worksheet(st.secrets["sheets"]["checkins_ws"])
        return sh, ws_att, ws_chk
    except Exception as e:
        st.warning(f"No se pudo abrir Google Sheets: {e}")
        return None, None, None

def append_checkin(ws_chk, data: dict):
    """Agrega un registro a la hoja de checkins."""
    try:
        headers = ws_chk.row_values(1)
        row = [data.get(h, "") for h in headers]
        ws_chk.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        st.error(f"No se pudo escribir en 'checkins': {e}")
        return False

# ====== ESTADO ======
if "last_scanned" not in st.session_state:
    st.session_state.last_scanned = ""
if "venue_default" not in st.session_state:
    st.session_state.venue_default = "Holiday Inn Tuxtla (Día 1)"

# ====== SIDEBAR ======
st.sidebar.markdown("### 🎟️ Encuentro Internacional de Guías")
st.sidebar.caption("Escaneo de QR y registro de asistentes")

venue = st.sidebar.selectbox(
    "Sede por defecto (si el QR solo trae token):",
    ["Holiday Inn Tuxtla (Día 1)", "Chiapa de Corzo (Día 2)", "Museo de los Altos (Día 3)"],
    index=["Holiday Inn Tuxtla (Día 1)", "Chiapa de Corzo (Día 2)", "Museo de los Altos (Día 3)"].index(st.session_state.venue_default),
)
st.session_state.venue_default = venue

st.sidebar.info(
    "Si en iPhone el lector no inicia, usa el **modo por foto** del mismo lector "
    "o pega el código manualmente abajo."
)

# ====== TÍTULO ======
st.title("🧾 Registro y Escáner de QR – Staff")

# ====== BLOQUE: ESCÁNER INTEGRADO ======
st.subheader("Escáner integrado (prueba primero aquí)")
st.caption("Este lector solicita permiso de cámara al presionar **Iniciar escaneo** (iOS/Android).")

scanner_html = f"""
<div id="scanner-root" style="display:flex;flex-direction:column;align-items:center;gap:12px;">
  <div id="status" style="font-family:system-ui, -apple-system, Segoe UI, Roboto;">
    Cargando lector…
  </div>
  <div id="qrbox" style="width:320px;max-width:90vw;border-radius:12px;overflow:hidden;"></div>
  <div style="display:flex;gap:8px;">
    <button id="btnStart" disabled style="padding:.6rem 1rem;border-radius:8px;border:none;background:#6e9bab;color:#fff;cursor:not-allowed;">Iniciar escaneo</button>
    <button id="btnStop" disabled style="padding:.6rem 1rem;border-radius:8px;border:1px solid #ccc;background:#f4f4f5;cursor:not-allowed;">Detener</button>
  </div>
  <button id="btnReloadLib" style="display:none;padding:.5rem .8rem;border-radius:8px;border:1px solid #ccc;background:#fff;">Reintentar cargar librería</button>

  <div style="margin-top:8px;font-size:.9rem;opacity:.8;">
    Si no abre la cámara en iPhone, baja a <b>Registro manual</b> o usa el modo foto del mismo lector.
  </div>
</div>

<script>
(function(){{
  const H5Q_URL = "https://unpkg.com/html5-qrcode@2.3.10/html5-qrcode.min.js";
  const statusEl = document.getElementById("status");
  const btnStart = document.getElementById("btnStart");
  const btnStop  = document.getElementById("btnStop");
  const btnReloadLib = document.getElementById("btnReloadLib");
  const box = document.getElementById("qrbox");
  let h5, cameraId;

  function loadLib(){{
    return new Promise((resolve, reject)=>{{
      if (window.Html5Qrcode) return resolve();
      const s = document.createElement("script");
      s.src = H5Q_URL;
      s.async = true;
      s.onload = ()=> resolve();
      s.onerror = ()=> reject(new Error("No se pudo cargar html5-qrcode"));
      document.head.appendChild(s);
    }});
  }}

  function setEnabled(el, on){{
    el.disabled = !on;
    el.style.cursor = on ? "pointer" : "not-allowed";
    if (el === btnStart) el.style.background = on ? "#4f7da0" : "#6e9bab";
  }}

  async function ensurePermissions(){{
    // Dispara el prompt de iOS
    await navigator.mediaDevices.getUserMedia({{ video: true }});
  }}

  function postToStreamlit(text){{
    // Devolvemos el texto al contenedor padre (Streamlit) para que lo capture.
    // Streamlit no expone una API oficial aquí, pero podemos inyectarlo en hash para copiar/pegar rápido.
    try {{
      window.parent.postMessage({{ type: "qr-decoded", payload: text }}, "*");
    }} catch (e) {{}}
    try {{
      // como respaldo, copiamos al portapapeles
      navigator.clipboard.writeText(text);
    }} catch (e) {{}}
  }}

  async function init(){{
    try {{
      statusEl.textContent = "Cargando librería…";
      await loadLib();
      statusEl.textContent = "Librería lista.";

      if (location.protocol !== "https:" && location.hostname !== "localhost") {{
        statusEl.innerHTML = "Esta página debe servirse por <b>HTTPS</b> para acceder a la cámara.";
        return;
      }}

      setEnabled(btnStart, true);

      btnStart.onclick = async ()=>{{
        try {{
          setEnabled(btnStart, false);
          await ensurePermissions(); // iOS prompt
          const devices = await Html5Qrcode.getCameras();
          if (!devices || !devices.length) throw new Error("No se encontró cámara");
          cameraId = devices.find(d => /back|rear|environment/i.test(d.label))?.id || devices[0].id;

          h5 = new Html5Qrcode("qrbox", {{ verbose: false }});
          await h5.start(
            {{ deviceId: {{ exact: cameraId }} }},
            {{ fps: 10, qrbox: 250, aspectRatio: 1.777 }},
            (decodedText)=> {{
              statusEl.textContent = "QR: " + decodedText;
              postToStreamlit(decodedText);
            }},
            (err)=> {{}}
          );
          statusEl.textContent = "Escaneando…";
          setEnabled(btnStop, true);
        }} catch(e) {{
          statusEl.textContent = e.message || String(e);
          setEnabled(btnStart, true);
        }}
      }};

      btnStop.onclick = async ()=>{{
        try {{
          if (h5) await h5.stop();
        }} finally {{
          if (h5) await h5.clear();
          setEnabled(btnStop, false);
          setEnabled(btnStart, true);
          statusEl.textContent = "Detenido.";
        }}
      }};

    }} catch(e) {{
      statusEl.innerHTML = "❌ No se pudo cargar la librería.";
      btnReloadLib.style.display = "inline-block";
      btnReloadLib.onclick = ()=> {{ btnReloadLib.style.display="none"; init(); }};
    }}
  }}

  // Listener para debug manual (opcional)
  window.addEventListener("message", (ev)=>{{
    // Puedes ver mensajes en la consola si lo necesitas
  }});

  init();
}})();
</script>
"""

# Render del lector (sin usar 'key' para evitar TypeError en algunos entornos)
components.html(scanner_html, height=520, scrolling=False)

st.divider()

# ====== BLOQUE: REGISTRO MANUAL / PASTE ======
st.subheader("Registro manual / Pegar resultado")
st.caption("Si el lector no puede usar la cámara del iPhone, pega aquí el texto del QR (se copia automáticamente al leer).")

col1, col2 = st.columns([3,1])
with col1:
    qr_text = st.text_input("Texto/URL/token leído", value=st.session_state.last_scanned, placeholder="Pega aquí el valor leído...")
with col2:
    if st.button("Limpiar"):
        st.session_state.last_scanned = ""
        st.rerun()

# Simula recepción por postMessage: si el frontend copia al clipboard, el staff suele pegar aquí.
# Si quieres automatizar más, podrías implementar una ruta externa con scanner y redirección ?code=...
if qr_text and qr_text != st.session_state.last_scanned:
    st.session_state.last_scanned = qr_text

# ====== GUARDAR CHECK-IN ======
st.subheader("Guardar check-in")
with st.form("checkin_form"):
    who = st.text_input("Nombre (si el QR no trae nombre)", "")
    sede = st.text_input("Sede (si el QR no trae sede)", st.session_state.venue_default)
    notes = st.text_input("Notas (opcional)", "")
    submitted = st.form_submit_button("Registrar check-in")

    if submitted:
        # Parseo muy básico por si viene una URL tipo https://.../?token=XYZ&name=Juan&sede=...
        from urllib.parse import urlparse, parse_qs

        token = st.session_state.last_scanned.strip()
        parsed = urlparse(token) if token else None
        q = parse_qs(parsed.query) if parsed and parsed.query else {}

        name_from_qr = (q.get("name",[None])[0] or who or "").strip()
        sede_from_qr = (q.get("sede",[None])[0] or sede or "").strip()
        token_val = (q.get("token",[None])[0] or token or "").strip()

        data = {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "token": token_val,
            "nombre": name_from_qr,
            "sede": sede_from_qr,
            "notas": notes,
            "origen": "app",
            "uuid": str(uuid.uuid4())[:8],
        }

        sh, ws_att, ws_chk = _open_sheets()
        if ws_chk:
            ok = append_checkin(ws_chk, data)
            if ok:
                st.success("✅ Check-in registrado.")
            else:
                st.warning("No se pudo registrar en Sheets. Revisa credenciales/ID/hojas en `st.secrets`.")
        else:
            st.warning("No se pudo conectar a Sheets. Guardado local temporal (muestra abajo).")
            st.json(data)

st.divider()
st.caption(
    "Consejos iOS: en Safari asegúrate de estar en **HTTPS** y haber dado permisos de **Cámara** al sitio. "
    "Si el visor no se muestra, suele ser por las restricciones de **iframe** en iOS."
)

# ====== FIN ======
