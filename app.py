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
    ss_id = st.secrets["sheets"].get("gsheet_id") or st.secrets["sheets"]["spreadsheet_id"]
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
qp = st.query_params
if "token" in qp:
    token = qp.get("token", [""])[0].strip()
    sede  = qp.get("sede",  [""])[0].strip() or "Sede general"
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

# --- BLOQUE STAFF: CONTROL DE ACCESOS CON ESCÁNER QR ---

with tabs[3]:
    st.subheader("Modo Staff — Escaneo con cámara")

    st.write(
        "Si en iPhone el lector no inicia, usa el **modo por foto** de abajo. "
        "En Android/PC el lector continuo funciona bien."
    )

    # Aviso para que el usuario sepa que se usará la cámara
    st.info(
        "Para registrar los accesos se utilizará la cámara del dispositivo. "
        "Al iniciar el escaneo, tu navegador te pedirá permiso para usar la cámara."
    )

    # 👉 aquí puedes conservar tu selector de sede por defecto si ya lo tenías
    # por ejemplo:
    # sede_defecto = st.selectbox(
    #     "Sede por defecto si el QR trae solo token (sin URL):",
    #     ["Holiday Inn Tuxtla (Día 1)", "Chiapa de Corzo (Día 2)", "San Cristóbal (Día 3)"],
    # )

    # 1) Cargar la librería de html5-qrcode una sola vez
    components.html(
        """
        <script type="text/javascript"
                src="https://unpkg.com/html5-qrcode@2.3.11/html5-qrcode.min.js">
        </script>
        """,
        height=0,
    )

    # 2) Estado del escaneo
    if "scan_activo" not in st.session_state:
        st.session_state["scan_activo"] = False

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Iniciar escaneo"):
            st.session_state["scan_activo"] = True

    with col2:
        if st.button("Detener escaneo"):
            st.session_state["scan_activo"] = False

    st.markdown("---")

    # 3) Mostrar el visor solo si el escaneo está activo
    if st.session_state["scan_activo"]:

        html_qr = """
        <div style="display:flex;flex-direction:column;align-items:center;">
          <div id="qr-reader"
               style="width: 320px; max-width: 100%; border:1px solid #ccc;"></div>
          <div id="qr-reader-results"
               style="margin-top:10px;font-size:14px;color:#444;"></div>
        </div>

        <script>
          async function startScanner() {

            // Verificar que la librería realmente se haya cargado
            if (!window.Html5Qrcode) {
              document.getElementById("qr-reader").innerHTML =
                "<p style='color:red;font-size:14px;'>" +
                "❌ No se pudo cargar la librería. Recarga la página." +
                "</p>";
              return;
            }

            const html5QrCode = new Html5Qrcode("qr-reader");

            function onScanSuccess(decodedText, decodedResult) {
              document.getElementById("qr-reader-results").innerHTML =
                "Código leído: <strong>" + decodedText + "</strong>";

              // Mandar el resultado a Streamlit
              window.parent.postMessage(
                { type: "qr-scan", data: decodedText },
                "*"
              );

              // Detener después de un escaneo exitoso (opcional)
              html5QrCode.stop().catch(e => console.log(e));
            }

            function onScanFailure(errorMessage) {
              // Errores normales de lectura, se pueden ignorar
            }

            try {
              await html5QrCode.start(
                { facingMode: "environment" },
                {
                  fps: 10,
                  qrbox: { width: 250, height: 250 }
                },
                onScanSuccess,
                onScanFailure
              );
            } catch (err) {
              console.error(err);
              document.getElementById("qr-reader").innerHTML =
                "<p style='color:red;font-size:14px;'>" +
                "❌ No se pudo iniciar el escaneo. "
                + "Verifica los permisos de la cámara." +
                "</p>";
            }
          }

          // Iniciar cuando se inyecta este HTML
          startScanner();
        </script>
        """

        components.html(html_qr, height=450)

        st.caption(
            "Si ves el mensaje de error en rojo, cierra la página y ábrela "
            "de nuevo asegurándote de usar HTTPS y el navegador actualizado."
        )

    else:
        st.warning(
            "Haz clic en **Iniciar escaneo** para activar la cámara y comenzar a leer códigos QR."
        )

    # Debajo de aquí, si quieres, luego añadimos:
    # - recibir el postMessage en Streamlit
    # - buscar al asistente en la hoja
    # - registrar el check-in en 'checkins'


# ==========================
# FIN
# ==========================
