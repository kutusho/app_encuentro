# app.py — versión compatible con secrets [sheets]
# Colegio de Guías de Turistas de Chiapas A.C.
# Primer Encuentro Internacional de Guías de Turistas en Chiapas

import os
import io
import base64
from datetime import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import qrcode
from PIL import Image
import gspread
from google.oauth2.service_account import Credentials

st.sidebar.write("🔍 gsheet_id detectado:", st.secrets.get("gsheet_id", "(no detectado)"))
st.sidebar.write("🧩 keys disponibles:", list(st.secrets.keys()))

# ==========================
# CONFIGURACIÓN GENERAL
# ==========================
st.set_page_config(
    page_title="Encuentro de Guías en Chiapas • Registro",
    page_icon="✅",
    layout="centered"
)

PRIMARY = "#0b6e99"
SUCCESS = "#21a67a"
DANGER = "#cc3d3d"
MUTED = "#6b7280"

LOGO_PATH = "assets/logo_colegio.png"
EVENT_TAGLINE = "Saberes que unen, culturas que inspiran. • Colegio de Guías de Turistas de Chiapas A.C."
SEDES = [
    "Holiday Inn Tuxtla (Día 1)",
    "Ex Convento Santo Domingo (Día 2)",
    "Museo de los Altos (Día 3)",
]

# ==========================
# FUNCIONES DE CONEXIÓN GOOGLE SHEETS
# ==========================
with st.expander("🔎 Diagnóstico de secrets"):
    try:
        s = st.secrets
        st.write("Tiene [gcp_service_account]:", "gcp_service_account" in s)
        st.write("client_email:", s.get("gcp_service_account", {}).get("client_email", "(no)"))
        st.write("gsheet_id raíz:", s.get("gsheet_id", "(no)"))
        st.write("gsheet_id en [sheets]:", s.get("sheets", {}).get("gsheet_id", "(no)"))
    except Exception as e:
        st.error(f"Error leyendo secrets: {e}")

def get_gspread_client():
    creds_dict = st.secrets["gcp_service_account"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def _get_sheet_id_from_secrets():
    s = st.secrets
    # Buscar gsheet_id en raíz o dentro de [sheets]
    if "gsheet_id" in s and s["gsheet_id"]:
        return s["gsheet_id"]
    if "sheets" in s and isinstance(s["sheets"], dict):
        if s["sheets"].get("gsheet_id"):
            return s["sheets"]["gsheet_id"]
        if s["sheets"].get("spreadsheet_id"):
            return s["sheets"]["spreadsheet_id"]
    raise KeyError("No se encontró 'gsheet_id' ni 'sheets.gsheet_id' en secrets.")


def _ws_names():
    s = st.secrets.get("sheets", {})
    asistentes = s.get("attendees_ws", "asistentes")
    checkins = s.get("checkins_ws", "checkins")
    return asistentes, checkins


def open_worksheet():
    gc = get_gspread_client()
    sh = gc.open_by_key(_get_sheet_id_from_secrets())
    asistentes_ws_name, checkins_ws_name = _ws_names()

    try:
        ws = sh.worksheet(asistentes_ws_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=asistentes_ws_name, rows=2000, cols=20)
        ws.update("A1:H1", [["timestamp", "nombre", "inst", "email", "telefono", "cuota", "sede_defecto", "token"]])

    try:
        chk = sh.worksheet(checkins_ws_name)
    except gspread.WorksheetNotFound:
        chk = sh.add_worksheet(title=checkins_ws_name, rows=5000, cols=20)
        chk.update("A1:E1", [["timestamp", "token", "sede", "ok", "detalle"]])

    return ws, chk


def find_row_by_token(ws, token):
    if not token:
        return None
    try:
        cells = ws.findall(token)
        for c in cells:
            if c.col == 8:  # token está en la columna H
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
    return qr.make_image(fill_color="black", back_color="white")


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
# ENCABEZADO
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
# LECTURA DE PARAMS URL
# ==========================
qp = st.query_params
incoming_token = (qp.get("token") or "").strip()
incoming_sede = (qp.get("sede") or "").strip()

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
        "Base URL actual para generar QR:",
        value="https://encuentro.streamlit.app",
        key="base_url_reg"
    )

    col1, col2 = st.columns(2)
    with col1:
        nombre = st.text_input("Nombre completo *")
        inst = st.text_input("Institución / Empresa")
        cuota = st.selectbox("Tipo de cuota", ["Guía Chiapas", "Guía (otro estado)", "Público general", "Estudiante"])
    with col2:
        email = st.text_input("Email")
        tel = st.text_input("Teléfono")
        sede_def = st.selectbox("Sede por defecto para check-in", SEDES)

    if st.button("Registrar", type="primary"):
        if not nombre.strip():
            error_badge("Nombre es obligatorio.")
        else:
            token = base64.urlsafe_b64encode(os.urandom(6)).decode().strip("=")
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ws.append_row([ts, nombre, inst, email, tel, cuota, sede_def, token], value_input_option="USER_ENTERED")

            vurl = f"{base_url}?token={token}&sede={sede_def}"
            img = make_qr(vurl, box=9)

            success_badge("Asistente registrado y QR generado.")
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown(img_to_html(img, 200), unsafe_allow_html=True)
            with c2:
                st.code(vurl, language="text")

# --------------------------
# REPORTES
# --------------------------
with tab_rep:
    ws, chk = open_worksheet()
    st.subheader("Asistentes registrados")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Aún no hay registros.")

    st.subheader("Check-ins")
    d2 = chk.get_all_records()
    df2 = pd.DataFrame(d2)
    if not df2.empty:
        st.dataframe(df2, use_container_width=True)
    else:
        st.info("Aún no hay check-ins.")

# --------------------------
# STAFF
# --------------------------
with tab_staff:
    ws, chk = open_worksheet()

    st.subheader("Modo Staff — Escaneo con cámara")
    sede_staff = st.selectbox("Sede por defecto:", SEDES)

    def verify_and_render(token, sede):
        row = find_row_by_token(ws, token)
        if row:
            append_checkin(chk, token, sede, True, "scan/url")
            vals = ws.row_values(row)
            nombre = vals[1] if len(vals) > 1 else "Asistente"
            st.success(f"✔ {nombre} verificado en {sede}")
        else:
            append_checkin(chk, token, sede, False, "token no encontrado")
            st.error("❌ Token no encontrado")

    if incoming_token:
        sede_for_url = incoming_sede or sede_staff
        verify_and_render(incoming_token, sede_for_url)

    st.markdown("### Escanear con cámara")
    scanner_html = f"""
    <div id="reader" width="250px"></div>
    <script src="https://unpkg.com/html5-qrcode"></script>
    <script>
    function startScanner() {{
        const reader = new Html5Qrcode("reader");
        Html5Qrcode.getCameras().then(devices => {{
            if (devices && devices.length) {{
                reader.start(
                    devices[0].id,
                    {{ fps: 10, qrbox: 250 }},
                    decodedText => {{
                        const sede = encodeURIComponent("{sede_staff}");
                        const base = window.location.origin + window.location.pathname;
                        window.location.href = base + "?token=" + encodeURIComponent(decodedText) + "&sede=" + sede;
                    }}
                );
            }} else {{
                document.getElementById("reader").innerHTML = "No se detectaron cámaras.";
            }}
        }});
    }}
    </script>
    <button onclick="startScanner()">📷 Iniciar cámara</button>
    """
    components.html(scanner_html, height=420)

    st.divider()
    st.markdown("### Verificar manualmente")
    manual = st.text_input("Pega aquí el token o la URL completa")
    if st.button("Verificar manual"):
        txt = manual.strip()
        if txt.startswith("http"):
            from urllib.parse import urlparse, parse_qs
            u = urlparse(txt)
            q = parse_qs(u.query)
            tok = (q.get("token") or [""])[0]
            sede = (q.get("sede") or [sede_staff])[0]
            verify_and_render(tok, sede)
        elif txt:
            verify_and_render(txt, sede_staff)
        else:
            st.warning("Introduce un token o URL válida.")
