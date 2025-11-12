# app.py
# Primer Encuentro Internacional de Guías de Turistas en Chiapas
# Colegio de Guías de Turistas de Chiapas, A.C.

import os
import io
import time
import base64
from datetime import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import qrcode
from PIL import Image
import gspread
from google.oauth2.service_account import Credentials

# ==========================
# CONFIGURACIÓN DE LA APP
# ==========================
st.set_page_config(
    page_title="Encuentro de Guías en Chiapas • Registro",
    page_icon="✅",
    layout="centered"
)

PRIMARY = "#0b6e99"      # azul colegiado
SUCCESS = "#21a67a"
DANGER  = "#cc3d3d"
MUTED   = "#6b7280"

LOGO_PATH = "assets/logo_colegio.png"  # ajusta si tu archivo tiene otro nombre
EVENT_TAGLINE = "Saberes que unen, culturas que inspiran. • Colegio de Guías de Turistas de Chiapas A.C."

SEDES = [
    "Holiday Inn Tuxtla (Día 1)",
    "Ex Convento Santo Domingo (Día 2)",
    "Museo de los Altos (Día 3)",
]

# ==========================
# CONEXIÓN GOOGLE SHEETS
# ==========================
def get_gspread_client():
    creds_dict = st.secrets["gcp_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def open_worksheet():
    gc = get_gspread_client()
    sh = gc.open_by_key(st.secrets["gsheet_id"])
    # Hoja principal de asistentes
    try:
        ws = sh.worksheet("asistentes")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="asistentes", rows=2000, cols=20)
        ws.update("A1:H1", [["timestamp","nombre","inst","email","telefono","cuota","sede_defecto","token"]])
    # Hoja de checkins
    try:
        chk = sh.worksheet("checkins")
    except gspread.WorksheetNotFound:
        chk = sh.add_worksheet(title="checkins", rows=5000, cols=20)
        chk.update("A1:E1", [["timestamp","token","sede","ok","detalle"]])
    return ws, chk

def find_row_by_token(ws, token):
    if not token:
        return None
    try:
        cells = ws.findall(token)
        for c in cells:
            # token está en la columna H según encabezado anterior
            if c.col == 8:
                return c.row
    except gspread.exceptions.APIError:
        pass
    return None

def append_checkin(chk_ws, token, sede, ok, detalle=""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chk_ws.append_row([ts, token, sede, "TRUE" if ok else "FALSE", detalle], value_input_option="USER_ENTERED")

# ==========================
# UTILIDADES
# ==========================
def make_qr(url: str, box=10):
    qr = qrcode.QRCode(box_size=box, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img

def img_to_html(img: Image.Image, width=220):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'<img src="data:image/png;base64,{b64}" width="{width}" />'

def success_badge(text: str):
    st.markdown(
        f"""
        <div style="padding:14px;border-radius:12px;background:{SUCCESS}20;border:1px solid {SUCCESS}40;">
            <span style="color:{SUCCESS};font-weight:700;">{text}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

def error_badge(text: str):
    st.markdown(
        f"""
        <div style="padding:14px;border-radius:12px;background:{DANGER}10;border:1px solid {DANGER}30;">
            <span style="color:{DANGER};font-weight:700;">{text}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

# ==========================
# HEADER
# ==========================
col_logo, col_t = st.columns([1, 3], vertical_alignment="center")
with col_logo:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=120)
with col_t:
    st.markdown(
        f"""
        <h1 style="margin-bottom:0">Primer Encuentro Internacional de<br>Guías de Turistas en Chiapas</h1>
        <p style="color:{MUTED};margin-top:6px;">14–16 de noviembre de 2025</p>
        <p style="color:{MUTED};margin-top:-10px;">{EVENT_TAGLINE}</p>
        """,
        unsafe_allow_html=True
    )

# ==========================
# LECTURA DE URL (?token=&sede=)
# ==========================
qp = st.query_params
incoming_token = (qp.get("token") or "").strip()
incoming_sede  = (qp.get("sede")  or "").strip()

# ==========================
# TABS
# ==========================
tab_reg, tab_rep, tab_cfg, tab_staff = st.tabs(["✍️ Registro", "📊 Reportes", "⚙️ Ajustes", "🛡️ Staff"])

# --------------------------
# REGISTRO
# --------------------------
with tab_reg:
    ws, chk = open_worksheet()

    st.subheader("Registrar nuevo asistente")
    base_url = st.text_input(
        "Base URL actual para generar QR (para staff, escaneo con URL completa):",
        value="https://encuentro.streamlit.app",
        key="base_url_reg",
        help="Usa el dominio público de tu app (https)."
    )

    col1, col2 = st.columns(2)
    with col1:
        nombre = st.text_input("Nombre completo *")
        inst   = st.text_input("Institución / Empresa")
        cuota  = st.selectbox("Tipo de cuota", ["Guía Chiapas","Guía (otro estado)","Público general","Estudiante"], key="cuota_reg")
    with col2:
        email = st.text_input("Email")
        tel   = st.text_input("Teléfono")
        sede_def = st.selectbox("Sede por defecto para el check-in vía URL", SEDES, key="sede_def_reg")

    if st.button("Registrar", type="primary"):
        if not nombre.strip():
            error_badge("Nombre es obligatorio.")
        else:
            # genera token único
            token = base64.urlsafe_b64encode(os.urandom(6)).decode().strip("=")
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ws.append_row([ts, nombre, inst, email, tel, cuota, sede_def, token], value_input_option="USER_ENTERED")

            # genera liga y QR
            vurl = f"{base_url}?token={token}&sede={sede_def}"
            img = make_qr(vurl, box=9)

            success_badge("Asistente registrado y QR generado.")
            c1, c2 = st.columns([1,2])
            with c1:
                st.markdown(img_to_html(img, 200), unsafe_allow_html=True)
            with c2:
                st.code(vurl, language="text")

# --------------------------
# REPORTES
# --------------------------
with tab_rep:
    ws, chk = open_worksheet()
    st.subheader("Asistentes")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=360)
    else:
        st.info("Aún no hay registros.")

    st.subheader("Check-ins")
    d2 = chk.get_all_records()
    df2 = pd.DataFrame(d2)
    if not df2.empty:
        st.dataframe(df2, use_container_width=True, height=360)
    else:
        st.info("Aún no hay check-ins.")

# --------------------------
# AJUSTES
# --------------------------
with tab_cfg:
    st.subheader("Ajustes rápidos")
    st.markdown("- Verifica que **Secrets** tenga `gcp_service_account` y `gsheet_id`.\n- Usa HTTPS para cámara en móviles.\n- Si iPhone no muestra permiso: Safari → aA → Website Settings → **Camera: Allow**.")

# --------------------------
# STAFF
# --------------------------
with tab_staff:
    ws, chk = open_worksheet()

    st.subheader("Modo Staff — Escaneo con cámara")
    st.caption("En iOS/Safari: toca el ícono **aA → Website Settings → Camera: Allow** si no aparece el permiso.")

    sede_staff = st.selectbox(
        "Sede por defecto si el QR trae solo token (sin URL):",
        SEDES, index=0, key="sede_staff_select"
    )

    # ---------- 1) PROCESO AUTOMÁTICO POR URL
    # Si llegó token por la URL, verificamos y mostramos resultado:
    def verify_and_render(token: str, sede: str):
        row = find_row_by_token(ws, token)
        if row:
            append_checkin(chk, token, sede, True, "scan/url")
            vals = ws.row_values(row)
            nombre = vals[1] if len(vals) > 1 else "Asistente"
            st.markdown(
                f"""
                <div style="border:2px solid {SUCCESS};border-radius:14px;padding:18px;background:#eafff7">
                    <h3 style="color:{SUCCESS};margin:0">✔ Verificado</h3>
                    <p style="margin:8px 0 0 0"><b>{nombre}</b><br/><span style="color:{MUTED}">{sede}</span></p>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            append_checkin(chk, token, sede, False, "token no encontrado")
            error_badge("Token no encontrado. Revisa que el QR sea el correcto.")

    if incoming_token:
        sede_for_url = incoming_sede or sede_staff
        verify_and_render(incoming_token, sede_for_url)

    # ---------- 2) SCAN CON CÁMARA (html5-qrcode)
    st.divider()
    st.markdown("#### Escanear ahora con la cámara")

    scanner_html = f"""
    <div id="scanZone"></div>
    <div id="scanResult" style="margin-top:8px;color:{MUTED}"></div>

    <script src="https://cdn.jsdelivr.net/npm/html5-qrcode@2.3.11/minified/html5-qrcode.min.js"></script>
    <script>
      const zone = document.getElementById('scanZone');
      const res  = document.getElementById('scanResult');

      function handle(urlOrToken) {{
        try {{
          const u = new URL(urlOrToken);
          // Si trae URL completa, redirigimos para que la app muestre el verificado
          window.location.href = urlOrToken;
          return;
        }} catch (e) {{
          // No es URL → construimos con sede por defecto
          const sede = encodeURIComponent("{sede_staff}");
          const base = window.location.origin + window.location.pathname;
          window.location.href = base + "?token=" + encodeURIComponent(urlOrToken) + "&sede=" + sede;
        }}
      }}

      function startScanner() {{
        if (!window.Html5Qrcode) {{
          res.innerHTML = "No se pudo iniciar el lector (Html5Qrcode no disponible).";
          return;
        }}
        const html5QrCode = new Html5Qrcode("scanZone");
        const config = {{
          fps: 10,
          qrbox: 240,
          aspectRatio: 1.0,
          rememberLastUsedCamera: true
        }};
        Html5Qrcode.getCameras().then(cams => {{
          const camId = cams && cams.length ? cams[0].id : null;
          if (!camId) {{
            res.innerHTML = "No se encontraron cámaras disponibles.";
            return;
          }}
          html5QrCode.start(
            camId,
            config,
            decodedText => {{
              res.innerHTML = "Leyendo…";
              html5QrCode.stop().then(() => {{
                handle(decodedText);
              }});
            }},
            errorMsg => {{
              // silencioso
            }});
        }}).catch(err => {{
          res.innerHTML = "No fue posible listar cámaras: " + err;
        }});
      }}

      // Botón ligero para iniciar (necesario en iOS por gesto del usuario)
      const btn = document.createElement("button");
      btn.textContent = "Abrir cámara y escanear";
      btn.style = "padding:10px 14px;border-radius:10px;border:1px solid #ddd;background:'{PRIMARY}';";
      btn.onclick = startScanner;
      zone.appendChild(btn);
    </script>
    """

    components.html(scanner_html, height=420, scrolling=False)

    # ---------- 3) VERIFICACIÓN MANUAL (pegando token o URL)
    st.markdown("#### Verificar manualmente")
    manual = st.text_input("Pega aquí el token o la URL completa del QR", key="manual_input_staff")
    if st.button("Verificar", key="manual_btn_staff"):
        txt = (manual or "").strip()
        if not txt:
            error_badge("Introduce token o URL.")
        else:
            if txt.startswith("http"):
                try:
                    from urllib.parse import urlparse, parse_qs
                    u = urlparse(txt)
                    q = parse_qs(u.query)
                    tok = (q.get("token") or [""])[0]
                    sede = (q.get("sede") or [sede_staff])[0]
                    verify_and_render(tok, sede)
                except Exception:
                    error_badge("URL inválida.")
            else:
                verify_and_render(txt, sede_staff)
