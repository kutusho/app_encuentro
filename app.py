# app.py
import os
import io
import uuid
import time
import qrcode
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread

# ==========================
# CONFIGURACIÓN BÁSICA
# ==========================
st.set_page_config(
    page_title="Primer Encuentro Internacional de Guías de Turistas en Chiapas",
    page_icon="✅",
    layout="wide",
)

DEFAULT_BASE_URL = st.secrets.get("base_url", "https://encuentro.streamlit.app")

LOGO_PATH = "assets/logo_colegio.png"
HERO_PATH = "assets/hero.png"

PRIMARY_COLOR = "#0b5f8a"   # azul institucional
ACCENT_COLOR  = "#2fa24b"   # verde institucional

# ==========================
# UTILIDADES
# ==========================
@st.cache_resource(show_spinner=False)
def get_gspread_client():
    sa = st.secrets["gcp_service_account"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(sa, scopes=scopes)
    return gspread.authorize(creds)

@st.cache_resource(show_spinner=False)
def get_worksheets():
    gc = get_gspread_client()
    ss_id = st.secrets["sheets"]["spreadsheet_id"]
    ws_att = st.secrets["sheets"]["attendees_ws"]
    ws_chk = st.secrets["sheets"]["checkins_ws"]
    ss = gc.open_by_key(ss_id)
    w_att = ss.worksheet(ws_att)
    w_chk = ss.worksheet(ws_chk)
    # Garantizar encabezados
    ensure_headers(w_att, ["timestamp","nombre","institucion","cuota","email","telefono","token","sede_default"])
    ensure_headers(w_chk, ["timestamp","token","sede","origen"])
    return w_att, w_chk

def ensure_headers(ws, headers):
    cur = ws.row_values(1)
    if [h.lower() for h in cur] != [h.lower() for h in headers]:
        ws.clear()
        ws.append_row(headers)

def df_attendees():
    w_att, _ = get_worksheets()
    vals = w_att.get_all_values()
    if not vals: return pd.DataFrame(columns=["timestamp","nombre","institucion","cuota","email","telefono","token","sede_default"])
    df = pd.DataFrame(vals[1:], columns=vals[0])
    return df

def df_checkins():
    _, w_chk = get_worksheets()
    vals = w_chk.get_all_values()
    if not vals: return pd.DataFrame(columns=["timestamp","token","sede","origen"])
    df = pd.DataFrame(vals[1:], columns=vals[0])
    return df

def add_attendee(nombre, institucion, cuota, email, telefono, sede_default):
    token = str(uuid.uuid4())
    w_att, _ = get_worksheets()
    w_att.append_row([
        datetime.now().isoformat(timespec="seconds"),
        nombre, institucion, cuota, email, telefono, token, sede_default
    ])
    return token

def record_checkin(token, sede, origen="url"):
    _, w_chk = get_worksheets()
    w_chk.append_row([datetime.now().isoformat(timespec="seconds"), token, sede, origen])

def attendee_by_token(token):
    df = df_attendees()
    if df.empty: return None
    hit = df[df["token"] == token]
    if hit.empty: return None
    return hit.iloc[0].to_dict()

def has_checkin(token):
    d = df_checkins()
    if d.empty: return False
    return any(d["token"] == token)

def build_verify_url(token, sede):
    base = st.session_state.get("base_url", DEFAULT_BASE_URL)
    return f"{base}/?token={token}&sede={sede}"

def qr_img_bytes(url: str) -> bytes:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def big_result_box(txt: str, color: str):
    st.markdown(
        f"""
        <div style="
            border-radius:16px;padding:24px;
            background:{color};color:white;
            font-size:22px;font-weight:800;text-align:center;">
            {txt}
        </div>
        """,
        unsafe_allow_html=True
    )

# ==========================
# ENCABEZADO
# ==========================
col_logo, col_title = st.columns([1,3], gap="large")
with col_logo:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=140)
with col_title:
    st.title("Primer Encuentro Internacional de Guías de Turistas en Chiapas")
    st.subheader("14–16 de noviembre de 2025")
    st.caption("Saberes que unen, culturas que inspiran. • Colegio de Guías de Turistas de Chiapas A.C.")

# ==========================
# VERIFICACIÓN POR URL (modo pantalla grande para el staff)
# ==========================
qp = st.experimental_get_query_params()
qp = st.query_params
token = (qp.get("token") or "").strip()
sede  = (qp.get("sede")  or "Sede general").strip()
if token:
    # … (deja igual el resto de la lógica de verificación)

    st.markdown("---")
    st.header("Verificación de acceso")
    att = attendee_by_token(token)
    if not att:
        big_result_box("❌ QR inválido / token no encontrado", "#b91c1c")
        st.stop()

    if has_checkin(token):
        big_result_box("🟡 Ya registrado anteriormente", "#d97706")
        st.write(f"**Nombre:** {att['nombre']}")
        st.write(f"**Cuota:** {att['cuota']}")
        st.stop()

    # marcar check-in
    record_checkin(token, sede, origen="url")
    big_result_box("🟢 Acceso verificado", "#15803d")
    st.write(f"**Nombre:** {att['nombre']}")
    st.write(f"**Cuota:** {att['cuota']}")
    st.stop()

# ==========================
# TABS
# ==========================
tabs = st.tabs(["📝 Registro", "📊 Reportes", "⚙️ Ajustes", "🛡️ Staff"])

# --------------------------
# REGISTRO
# --------------------------
with tabs[0]:
    st.subheader("Registrar nuevo asistente")
    st.info(f"Base URL actual para generar QR: {st.session_state.get('base_url', DEFAULT_BASE_URL)}")

    c1, c2 = st.columns(2)
    with c1:
        nombre = st.text_input("Nombre completo *", key="reg_nombre")
        instit = st.text_input("Institución / Empresa", key="reg_inst")
        cuota  = st.selectbox("Tipo de cuota", ["Guía Chiapas", "Público general", "Estudiante"], key="reg_cuota")
    with c2:
        email = st.text_input("Email", key="reg_email")
        tel   = st.text_input("Teléfono", key="reg_tel")

    sede_default = st.selectbox("Sede por defecto para el check-in vía URL",
                                ["Holiday Inn Tuxtla (Día 1)",
                                 "Ex Convento Santo Domingo (Día 2)",
                                 "Museo de los Altos (Día 3)"],
                                 key="reg_sede_def")

    if st.button("Registrar", type="primary", key="btn_registrar"):
        if not nombre.strip():
            st.warning("El nombre es obligatorio.")
        else:
            token = add_attendee(nombre.strip(), instit.strip(), cuota, email.strip(), tel.strip(), sede_default)
            url = build_verify_url(token, sede_default)
            st.success("¡Registro guardado!")
            st.write("URL de verificación / QR:")
            st.code(url, language="text")
            st.download_button("Descargar QR", qr_img_bytes(url), file_name=f"qr_{nombre}.png", mime="image/png")

    st.divider()
    st.subheader("Listado (vista rápida)")
    df = df_attendees()
    st.dataframe(df, use_container_width=True, height=320)

# --------------------------
# REPORTES
# --------------------------
with tabs[1]:
    st.subheader("Reportes")
    dfa = df_attendees()
    dfc = df_checkins()

    colA, colB, colC = st.columns(3)
    colA.metric("Asistentes registrados", len(dfa))
    colB.metric("Check-ins realizados", len(dfc))
    pct = 0 if len(dfa)==0 else round(100*len(dfc)/len(dfa),1)
    colC.metric("% Asistencia", f"{pct}%")

    st.markdown("#### Detalle de check-ins")
    st.dataframe(dfc.sort_values("timestamp", ascending=False), use_container_width=True, height=320)

# --------------------------
# AJUSTES
# --------------------------
with tabs[2]:
    st.subheader("Ajustes")
    base = st.text_input("Base URL del sistema (para generar/verificar QR)", value=st.session_state.get("base_url", DEFAULT_BASE_URL), key="base_url_input")
    if st.button("Guardar Base URL", key="btn_save_base"):
        st.session_state["base_url"] = base.strip() or DEFAULT_BASE_URL
        st.success(f"Base URL actualizada a: {st.session_state['base_url']}")
    st.caption("Sugerido: tu dominio de Streamlit Cloud de esta app.")

# ---- Staff — Lector continuo (llaves escapadas) ----
with tabs[3]:
    st.subheader("Modo Staff — Escaneo con cámara")
    st.caption("Si el lector no abre en iPhone, usa el modo por foto de abajo. En Android/PC el lector continuo funciona bien.")

    sede_staff_live = st.selectbox(
        "Sede por defecto si el QR trae solo token (sin URL):",
        ["Holiday Inn Tuxtla (Día 1)", "Ex Convento Santo Domingo (Día 2)", "Museo de los Altos (Día 3)"],
        index=0,
        key="sede_staff_live"
    )
    sede_val_live = sede_staff_live.replace('"', '\\"')
    base_url_live = st.session_state.get("base_url", DEFAULT_BASE_URL)

    scanner_html = f"""
    <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">
      <div style="max-width:380px;">
        <div id="reader" style="width:360px;height:360px;border:1px solid #e5e7eb;border-radius:10px;display:flex;align-items:center;justify-content:center;color:#6b7280">
          <div style="text-align:center">
            <div id="status" style='margin-bottom:10px;'>Cargando lector…</div>
            <button id="startBtn" disabled style="padding:12px 16px;border-radius:12px;border:0;background:#9ca3af;color:#fff;font-weight:800">Iniciar escaneo</button>
          </div>
        </div>
        <div style="margin-top:6px">
          <button id="stopBtn" disabled style="padding:8px 12px;border-radius:10px;border:1px solid #d1d5db;background:#fff">Detener</button>
        </div>
      </div>
      <div style="flex:1;min-width:260px;">
        <div id="log" style="font-size:14px;white-space:pre-wrap;color:#374151"></div>
      </div>
    </div>

    <script>
      // Cargar librería desde CDNJS y habilitar botón cuando esté lista
      (function loadLib(){{
        var s = document.createElement('script');
        s.src = "https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.10/html5-qrcode.min.js";
        s.async = true;
        s.onload = function(){{
          document.getElementById('status').innerText = "Lector listo. Pulsa Iniciar escaneo.";
          var btn = document.getElementById('startBtn');
          btn.disabled = false; btn.style.background = "{PRIMARY_COLOR}";
        }};
        s.onerror = function(){{
          document.getElementById('status').innerText = "❌ No se pudo cargar la librería. Recarga la página.";
        }};
        document.head.appendChild(s);
      }})();

      const baseUrl = "{base_url_live}";
      const sedeDef = "{sede_val_live}";
      let html5Qr = null;
      let running = false;

      function addLog(msg){{
        const el = document.getElementById("log");
        el.innerText = (el.innerText ? el.innerText + "\\n" : "") + msg;
      }}

      function buildUrlFromToken(token){{
        return baseUrl + "/?token=" + encodeURIComponent(token) + "&sede=" + encodeURIComponent(sedeDef);
      }}

      function onDecode(text){{
        try {{
          let t = (text||"").trim();
          let url = /^https?:\\/\\//i.test(t) ? t : buildUrlFromToken(t);
          addLog("✅ QR: " + t + "\\n→ " + url);
          if (running && html5Qr) {{
            html5Qr.stop().catch(()=>{{}}).finally(()=>{{ running=false; }});
          }}
          window.location.href = url;
        }} catch(e) {{
          addLog("❌ Error procesando QR: " + e);
        }}
      }}

      function waitForLib(ms) {{
        return new Promise((res, rej) => {{
          const t0 = Date.now();
          (function check(){{
            if (window.Html5Qrcode) return res();
            if (Date.now() - t0 > ms) return rej(new Error("html5-qrcode no disponible"));
            setTimeout(check, 100);
          }})();
        }});
      }}

      async function startWith(constraints, label){{
        addLog("• Intentando: " + label);
        try {{
          document.getElementById("reader").innerHTML = "";
          html5Qr = new Html5Qrcode("reader", false);
          await html5Qr.start(
            constraints,
            {{ fps: 12, qrbox: {{ width: 260, height: 260 }}, aspectRatio: 1.0, disableFlip: true }},
            onDecode,
            () => {{}}
          );
          running = true;
          document.getElementById("stopBtn").disabled = false;
          addLog("📷 Cámara iniciada con: " + label);
          return true;
        }} catch(e) {{
          addLog("× Falló (" + label + "): " + (e && e.message ? e.message : e));
          return false;
        }}
      }}

      async function startScanner(){{
        document.getElementById('status').innerText = "Abriendo cámara…";
        document.getElementById('startBtn').disabled = true;
        try {{ await waitForLib(4000); }} catch(e) {{
          addLog("× Librería no lista: " + e.message);
          document.getElementById('startBtn').disabled = false;
          return;
        }}
        let cams = [];
        try {{ cams = await Html5Qrcode.getCameras(); }} catch(e) {{ addLog("× No se pudieron listar cámaras: " + e); }}

        if (cams && cams.length){{
          let camId = cams[0].id;
          const back = cams.find(d=>/back|rear|environment/i.test(d.label));
          if (back) camId = back.id;
          if (await startWith({{ deviceId: {{ exact: camId }} }}, "deviceId exact (trasera si hay)")) return;
        }}
        if (await startWith({{ facingMode: {{ exact: "environment" }} }}, "facingMode exact environment")) return;
        if (await startWith({{ facingMode: {{ ideal: "environment" }} }}, "facingMode ideal environment")) return;
        await startWith({{ facingMode: "user" }}, "facingMode user");
      }}

      document.getElementById("startBtn").addEventListener("click", startScanner);
      document.getElementById("stopBtn").addEventListener("click", ()=>{{
        if (running && html5Qr){{
          html5Qr.stop().catch(()=>{{}}).finally(()=>{{
            running=false;
            document.getElementById("stopBtn").disabled = true;
            document.getElementById('status').innerText = "Escaneo detenido";
          }});
        }}
      }});
    </script>
    """
    components.html(scanner_html, height=700, scrolling=False)
    components.html(diag_html,    height=420, scrolling=False)
    components.html(html_photo,   height=180, scrolling=False)


    # (Debajo deja tu Diagnóstico y el Modo por foto tal como los tienes, con keys únicos)

# ==========================
# FIN
# ==========================
