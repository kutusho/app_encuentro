import streamlit as st
import pandas as pd
import numpy as np
import qrcode
from PIL import Image
import io
import sqlite3
from datetime import datetime
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe
import streamlit.components.v1 as components


# ============================
# CONFIGURACIÓN GENERAL
# ============================
EVENT_NAME = "Primer Encuentro Internacional de Guías de Turistas en Chiapas"
EVENT_DATES = "14–16 de noviembre de 2025"
EVENT_TAGLINE = "Saberes que unen, culturas que inspiran."
ORG_NAME = "Colegio de Guías de Turistas de Chiapas A.C."

ASSETS = Path("assets")
LOGO = ASSETS / "logo_colegio.jpg"

PRIMARY_COLOR = "#116699"
SUCCESS_COLOR = "#16a34a"
DANGER_COLOR  = "#dc2626"
WARNING_COLOR = "#f59e0b"

APP_TITLE = f"Registro y Acceso | {EVENT_NAME}"

# Ruta local de la base de datos
DATA_DIR = Path.cwd() / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DATA_DIR / "app.db")

DEFAULT_BASE_URL = st.secrets.get("base_url", "https://encuentro-app.streamlit.app")

st.set_page_config(page_title=APP_TITLE, page_icon=str(LOGO), layout="wide")

st.markdown("""
<style>
.stButton>button {padding: 0.6rem 1rem; border-radius: 10px; font-weight: 600;}
.block-container {padding-top: 2rem;}
.status {color:#fff;padding:24px;border-radius:16px;text-align:center;
         font-size:28px;font-weight:800;}
</style>
""", unsafe_allow_html=True)

# ============================
# ENCABEZADO
# ============================
col_logo, col_title = st.columns([1,3], vertical_alignment="center")
with col_logo:
    if LOGO.exists():
        st.image(str(LOGO), use_column_width=True)
with col_title:
    st.markdown(f"<h1 style='margin-bottom:0'>{EVENT_NAME}</h1>", unsafe_allow_html=True)
    st.markdown(f"<h4 style='margin-top:0;color:#374151'>{EVENT_DATES}</h4>", unsafe_allow_html=True)
    st.caption(f"{EVENT_TAGLINE} • {ORG_NAME}")

# ============================
# BASE DE DATOS LOCAL (SQLite)
# ============================
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE,
            nombre TEXT,
            institucion TEXT,
            tipo_cuota TEXT,
            email TEXT,
            telefono TEXT,
            qr_token TEXT UNIQUE,
            registrado_en TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attendee_id INTEGER,
            sede TEXT,
            realizado_en TEXT,
            FOREIGN KEY(attendee_id) REFERENCES attendees(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    con.commit()
    con.close()

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def next_folio(con):
    df = pd.read_sql_query("SELECT folio FROM attendees ORDER BY id DESC LIMIT 1", con)
    if df.empty:
        return "CGTCH-25-0001"
    last = df.folio.iloc[0]
    try:
        num = int(last.split("-")[-1])
        return f"CGTCH-25-{num+1:04d}"
    except Exception:
        import time
        return f"CGTCH-25-{int(time.time())%10000:04d}"

def get_setting(con, key, default=None):
    df = pd.read_sql_query("SELECT value FROM settings WHERE key = ?", con, params=(key,))
    return (df.iloc[0]["value"] if not df.empty else default)

def set_setting(con, key, value):
    cur = con.cursor()
    cur.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value)
    )
    con.commit()

def add_attendee(con, data):
    folio = next_folio(con)
    import time, random
    token = f"TKN-{int(time.time())}-{random.randint(1000,9999)}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = con.cursor()
    cur.execute("""
        INSERT INTO attendees (folio, nombre, institucion, tipo_cuota,
            email, telefono, qr_token, registrado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (folio, data["nombre"], data.get("institucion",""),
          data.get("tipo_cuota",""), data.get("email",""),
          data.get("telefono",""), token, now))
    con.commit()
    return folio, token

def find_attendee_by_token(con, token):
    df = pd.read_sql_query("SELECT * FROM attendees WHERE qr_token = ?", con, params=(token,))
    return df.iloc[0].to_dict() if not df.empty else None

def get_checkins_for_attendee(con, attendee_id):
    return pd.read_sql_query(
        "SELECT * FROM checkins WHERE attendee_id = ? ORDER BY id DESC",
        con, params=(attendee_id,)
    )

def add_checkin(con, attendee_id, sede):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = con.cursor()
    cur.execute(
        "INSERT INTO checkins (attendee_id, sede, realizado_en) VALUES (?, ?, ?)",
        (attendee_id, sede, now)
    )
    con.commit()

def big_status(text, bg):
    st.markdown(f"<div class='status' style='background:{bg}'>{text}</div>",
                unsafe_allow_html=True)

def generate_qr_image(data_text: str) -> Image.Image:
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img

# ============================
# GOOGLE SHEETS (gspread)
# ============================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPES
)
gc = gspread.authorize(creds)

SHEET_ID = st.secrets["sheets"]["spreadsheet_id"]
ATT_WS = st.secrets["sheets"]["attendees_ws"]
CHK_WS = st.secrets["sheets"]["checkins_ws"]

@st.cache_resource(show_spinner=False)
def get_or_create_spreadsheet():
    sh = gc.open_by_key(SHEET_ID)
    try:
        sh.worksheet(ATT_WS)
    except gspread.WorksheetNotFound:
        sh.add_worksheet(title=ATT_WS, rows=1000, cols=30)
    try:
        sh.worksheet(CHK_WS)
    except gspread.WorksheetNotFound:
        sh.add_worksheet(title=CHK_WS, rows=1000, cols=30)
    return sh

sh = get_or_create_spreadsheet()

def append_attendee_row(row_dict: dict):
    cols = ["folio","nombre","institucion","tipo_cuota","email","telefono","registrado_en","qr_token"]
    ws = sh.worksheet(ATT_WS)
    ws.append_row([row_dict.get(c,"") for c in cols], value_input_option="USER_ENTERED")

def append_checkin_row(row_dict: dict):
    cols = ["folio","nombre","sede","realizado_en"]
    ws = sh.worksheet(CHK_WS)
    ws.append_row([row_dict.get(c,"") for c in cols], value_input_option="USER_ENTERED")

def full_sync_to_sheets(conn):
    ws_a = sh.worksheet(ATT_WS)
    ws_c = sh.worksheet(CHK_WS)
    df_a = pd.read_sql_query(
        "SELECT folio, nombre, institucion, tipo_cuota, email, telefono, registrado_en, qr_token FROM attendees ORDER BY id",
        conn
    )
    df_c = pd.read_sql_query(
        "SELECT a.folio, a.nombre, c.sede, c.realizado_en "
        "FROM checkins c JOIN attendees a ON a.id=c.attendee_id ORDER BY c.id",
        conn
    )
    ws_a.clear(); ws_c.clear()
    if not df_a.empty:
        set_with_dataframe(ws_a, df_a)
    if not df_c.empty:
        set_with_dataframe(ws_c, df_c)

# ============================
# INICIO DE APP
# ============================
init_db()
conn = get_conn()

# ============================
# VERIFICACIÓN POR URL (QR)
# ============================
params = st.query_params
if "token" in params:
    token = params.get("token")
    sede = params.get("sede", ["Holiday Inn Tuxtla (Día 1)"])[0]
    rec = find_attendee_by_token(conn, token)
    if not rec:
        big_status("❌ QR inválido o no encontrado", DANGER_COLOR)
        st.stop()
    checks = get_checkins_for_attendee(conn, rec["id"])
    already_here = (not checks[checks["sede"] == sede].empty) if not checks.empty else False
    if not already_here:
        add_checkin(conn, rec["id"], sede)
        try:
            append_checkin_row({
                "folio": rec["folio"],
                "nombre": rec["nombre"],
                "sede": sede,
                "realizado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            st.warning(f"No se pudo enviar el check-in a Sheets: {e}")
        big_status("✅ Verificado • Acceso concedido", SUCCESS_COLOR)
    else:
        big_status("🟡 Ya registrado en esta sede", WARNING_COLOR)
    st.write("**Asistente:**", rec["nombre"])
    st.write("**Folio:**", rec["folio"])
    st.write("**Tipo de cuota:**", rec["tipo_cuota"])
    st.write("**Sede:**", sede)
    st.stop()

# ============================
# PESTAÑAS PRINCIPALES
# ============================
tabs = st.tabs(["📝 Registro", "📊 Reportes", "⚙️ Ajustes", "🛡️ Staff"])

# ---- Registro ----
with tabs[0]:
    st.subheader("Registrar nuevo asistente")
    base_url = get_setting(conn, "base_url", DEFAULT_BASE_URL)
    st.info(f"Base URL actual para generar QR: {base_url}")

    with st.form("registro_form"):
        cols = st.columns(2)
        nombre = cols[0].text_input("Nombre completo *")
        institucion = cols[1].text_input("Institución / Empresa")
        cols2 = st.columns(3)
        tipo_cuota = cols2[0].selectbox(
            "Tipo de cuota",
            ["Guía Chiapas", "Público general", "Estudiante", "Ponente", "Invitado especial"]
        )
        email = cols2[1].text_input("Email")
        telefono = cols2[2].text_input("Teléfono")
        sede_default = st.selectbox(
            "Sede por defecto para el check-in vía URL",
            ["Holiday Inn Tuxtla (Día 1)", "Ex Convento Santo Domingo (Día 2)", "Museo de los Altos (Día 3)"]
        )
        submitted = st.form_submit_button("Registrar")

    if submitted:
        if not nombre.strip():
            st.error("Por favor ingresa el nombre completo.")
        else:
            folio, token = add_attendee(conn, {
                "nombre": nombre.strip(),
                "institucion": institucion.strip(),
                "tipo_cuota": tipo_cuota,
                "email": email.strip(),
                "telefono": telefono.strip(),
            })
            qr_url = f"{base_url}/?token={token}&sede={sede_default}"
            img = generate_qr_image(qr_url)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            st.success(f"Registro exitoso. Folio: {folio}")
            st.image(buf.getvalue(), caption=f"QR de {nombre}", width=220)
            st.code(qr_url, language="text")
            st.download_button("Descargar QR (PNG)", data=buf.getvalue(),
                               file_name=f"{folio}.png", mime="image/png")
            # ---- enviar a Sheets ----
            try:
                append_attendee_row({
                    "folio": folio,
                    "nombre": nombre.strip(),
                    "institucion": institucion.strip(),
                    "tipo_cuota": tipo_cuota,
                    "email": email.strip(),
                    "telefono": telefono.strip(),
                    "registrado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "qr_token": token
                })
            except Exception as e:
                st.warning(f"No se pudo enviar a Sheets en este momento: {e}")

    st.divider()
    st.subheader("Listado rápido (últimos 50)")
    df = pd.read_sql_query(
        "SELECT folio, nombre, institucion, tipo_cuota, email, telefono, registrado_en "
        "FROM attendees ORDER BY id DESC LIMIT 50", conn)
    st.dataframe(df, use_container_width=True)
         

# ---- Staff (v4: múltiples estrategias de arranque iOS) ----
with tabs[3]:
    st.subheader("Modo Staff — Escaneo con cámara")
    st.caption("Apunta la cámara al QR. Si el QR contiene la URL completa, redirige de inmediato a la verificación.")

    sede_staff = st.selectbox(
        "Sede por defecto si el QR trae solo token (sin URL):",
        ["Holiday Inn Tuxtla (Día 1)", "Ex Convento Santo Domingo (Día 2)", "Museo de los Altos (Día 3)"],
        index=0
    )
    sede_val = sede_staff.replace('"', '\\"')
    base_url = st.secrets.get("base_url", DEFAULT_BASE_URL)

    scanner_html = f"""
    <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">
      <div style="max-width:380px;">
        <div id="reader" style="width:360px;height:360px;border:1px solid #e5e7eb;border-radius:10px;display:flex;align-items:center;justify-content:center;color:#6b7280">
          <div style="text-align:center">
            <div style='margin-bottom:10px;'>Pulsa para iniciar el escaneo</div>
            <button id="startBtn" style="padding:12px 16px;border-radius:12px;border:0;background:#2563eb;color:#fff;font-weight:800">Iniciar escaneo</button>
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

    <script src="https://unpkg.com/html5-qrcode@2.3.10/minified/html5-qrcode.min.js"></script>
    <script>
      const baseUrl = "{base_url}";
      const sedeDef = "{sede_val}";
      let html5Qr = null;
      let running = false;

      function addLog(msg) {{
        const el = document.getElementById("log");
        el.innerText = (el.innerText ? el.innerText + "\\n" : "") + msg;
      }}

      function buildUrlFromToken(token) {{
        return baseUrl + "/?token=" + encodeURIComponent(token) + "&sede=" + encodeURIComponent(sedeDef);
      }}

      function onDecode(text) {{
        try {{
          let url = /^https?:\\/\\//i.test(text) ? text.trim() : buildUrlFromToken(text.trim());
          addLog("✅ QR: " + text + "\\n→ " + url);
          if (running && html5Qr) {{
            html5Qr.stop().catch(()=>{{}}).finally(()=>{{ running=false; }});
          }}
          window.location.href = url;
        }} catch (e) {{
          addLog("❌ Error procesando QR: " + e);
        }}
      }}

      async function startWithConstraints(constraints, label) {{
        addLog("• Intentando: " + label);
        try {{
          document.getElementById("reader").innerHTML = "";
          html5Qr = new Html5Qrcode("reader", /* verbose= */ false);
          await html5Qr.start(
            constraints,
            {{
              fps: 12,
              qrbox: {{ width: 260, height: 260 }},
              aspectRatio: 1.0,
              disableFlip: true,
              experimentalFeatures: {{ useBarCodeDetectorIfSupported: true }}
            }},
            onDecode,
            () => {{ /* silencioso por frame */ }}
          );
          running = true;
          addLog("📷 Cámara iniciada con: " + label);
          document.getElementById("stopBtn").disabled = false;
          return true;
        }} catch(e) {{
          addLog("× Falló (" + label + "): " + (e && e.message ? e.message : e));
          return false;
        }}
      }}

      async function startScanner() {{
        document.getElementById("stopBtn").disabled = true;
        // 1) listar cámaras tras gesto del usuario
        let cams = [];
        try {{ cams = await Html5Qrcode.getCameras(); }} catch(e) {{
          addLog("× No se pudieron listar cámaras: " + e);
        }}

        // 1) deviceId (trasera si existe)
        if (cams && cams.length) {{
          let camId = cams[0].id;
          const back = cams.find(d => /back|rear|environment/i.test(d.label));
          if (back) camId = back.id;
          if (await startWithConstraints({{ deviceId: {{ exact: camId }} }}, "deviceId exact (trasera si hay)")) return;
        }}

        // 2) facingMode exact environment
        if (await startWithConstraints({{ facingMode: {{ exact: "environment" }} }}, "facingMode exact environment")) return;

        // 3) facingMode ideal environment
        if (await startWithConstraints({{ facingMode: {{ ideal: "environment" }} }}, "facingMode ideal environment")) return;

        // 4) último recurso: frontal
        await startWithConstraints({{ facingMode: "user" }}, "facingMode user");
      }}

      document.getElementById("startBtn").addEventListener("click", startScanner);
      document.getElementById("stopBtn").addEventListener("click", () => {{
        if (running && html5Qr) {{
          html5Qr.stop().catch(()=>{{}}).finally(()=>{{ running=false; document.getElementById("stopBtn").disabled = true; addLog("⏹️ Cámara detenida"); }});
        }}
      }});
    </script>
    """

    components.html(scanner_html, height=680, scrolling=False)

    st.divider()
    st.markdown("### 🔍 Diagnóstico rápido (preview sin escanear)")
    diag_html = """
    <video id="videoTest" autoplay playsinline style="width:100%;max-width:360px;border-radius:8px;background:#000"></video>
    <div id="diagMsg" style="font-size:14px;color:#6b7280;margin-top:6px"></div>
    <script>
      const msg = document.getElementById('diagMsg');
      navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } } })
      .then(stream => { document.getElementById('videoTest').srcObject = stream; msg.innerText = "Preview activo"; })
      .catch(e => { msg.innerText = "❌ " + e.message; });
    </script>
    """
    components.html(diag_html, height=420)

    st.divider()
    st.markdown("### Alternativa manual")
    manual_token = st.text_input("Pega aquí el token o la URL completa del QR")
    if st.button("Verificar manualmente"):
        if manual_token.strip():
            if manual_token.strip().lower().startswith("http"):
                st.markdown(f"[Ir a verificación]({manual_token.strip()})")
            else:
                url = f"{base_url}/?token={manual_token.strip()}&sede={sede_staff}"
                st.markdown(f"[Ir a verificación]({url})")
        else:
            st.warning("Ingresa un token o URL.")

# ---- Staff (fallback iPhone: escaneo por foto con jsQR) ----
with tabs[3]:
    st.subheader("Modo Staff — Escaneo por foto (compatibilidad iPhone)")
    st.caption("Toma una foto del QR. Decodificamos y te enviamos a la verificación. Funciona incluso si el lector continuo no abre el visor en iOS.")

    sede_staff = st.selectbox(
        "Sede por defecto si el QR trae solo token (sin URL):",
        ["Holiday Inn Tuxtla (Día 1)", "Ex Convento Santo Domingo (Día 2)", "Museo de los Altos (Día 3)"],
        index=0,
        key="sede_foto"
    )
    sede_val = sede_staff.replace('"', '\\"')
    base_url = st.secrets.get("base_url", DEFAULT_BASE_URL)

    html = f"""
    <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">
      <div style="max-width:420px;">
        <input id="qrFile" type="file" accept="image/*" capture="environment"
               style="padding:12px;border:1px solid #e5e7eb;border-radius:12px;width:100%">
        <canvas id="qrCanvas" style="display:none"></canvas>
        <div id="result" style="margin-top:10px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,Helvetica,Arial;"></div>
      </div>
      <div style="flex:1;min-width:260px;color:#374151;font-size:14px;white-space:pre-wrap" id="log"></div>
    </div>

    <!-- jsQR para decodificar QR en imágenes -->
    <script src="https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js"></script>
    <script>
      const baseUrl = "{base_url}";
      const sedeDef = "{sede_val}";

      function log(msg) {{
        const el = document.getElementById("log");
        el.innerText = (el.innerText ? el.innerText + "\\n" : "") + msg;
      }}

      function toVerifyUrl(text) {{
        const t = (text||"").trim();
        if (/^https?:\\/\\//i.test(t)) return t;
        return baseUrl + "/?token=" + encodeURIComponent(t) + "&sede=" + encodeURIComponent(sedeDef);
      }}

      document.getElementById("qrFile").addEventListener("change", async (ev) => {{
        const file = ev.target.files && ev.target.files[0];
        if (!file) return;
        const img = new Image();
        const url = URL.createObjectURL(file);
        img.onload = () => {{
          try {{
            const canvas = document.getElementById("qrCanvas");
            const ctx = canvas.getContext("2d");
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            ctx.drawImage(img, 0, 0);
            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const code = jsQR(imageData.data, canvas.width, canvas.height, {{ inversionAttempts: "attemptBoth" }});
            if (code && code.data) {{
              const dest = toVerifyUrl(code.data);
              document.getElementById("result").innerHTML = "✅ QR leído:<br><code>" + code.data + "</code><br>Abriendo verificación…";
              window.location.href = dest;
            }} else {{
              document.getElementById("result").innerHTML = "❌ No se detectó un QR claro en la foto. Intenta acercar y enfocar.";
            }}
          }} catch(e) {{
            document.getElementById("result").innerHTML = "❌ Error al procesar la imagen: " + e;
            log(e.toString());
          }} finally {{
            URL.revokeObjectURL(url);
          }}
        }};
        img.onerror = () => {{
          document.getElementById("result").textContent = "❌ No se pudo cargar la imagen.";
          URL.revokeObjectURL(url);
        }};
        img.src = url;
      }});
    </script>
    """
    components.html(html, height=260, scrolling=False)

    st.info("Sugerencia: usa este modo en iPhone. En Android/computadora puedes usar el lector continuo.")


# ---- Reportes ----
with tabs[1]:
    st.subheader("Reportes y exportación")
    c1, c2 = st.columns(2)

    with c1:
        st.caption("Asistentes registrados")
        df_a = pd.read_sql_query(
            "SELECT folio, nombre, institucion, tipo_cuota, email, telefono, registrado_en "
            "FROM attendees ORDER BY id DESC", conn)
        st.dataframe(df_a, use_container_width=True)
        st.download_button("Descargar asistentes (CSV)",
                           data=df_a.to_csv(index=False).encode("utf-8"),
                           file_name="asistentes.csv", mime="text/csv")

    with c2:
        st.caption("Check-ins realizados")
        df_c = pd.read_sql_query(
            "SELECT c.id, a.folio, a.nombre, c.sede, c.realizado_en "
            "FROM checkins c JOIN attendees a ON a.id=c.attendee_id ORDER BY c.id DESC", conn)
        st.dataframe(df_c, use_container_width=True)
        st.download_button("Descargar check-ins (CSV)",
                           data=df_c.to_csv(index=False).encode("utf-8"),
                           file_name="checkins.csv", mime="text/csv")

# ---- Ajustes ----
with tabs[2]:
    st.subheader("Ajustes de la app")
    base_url_current = get_setting(conn, "base_url", DEFAULT_BASE_URL)
    new_url = st.text_input("Base URL para generar los QR (incluye https://)", value=base_url_current)
    if st.button("Guardar Base URL"):
        if new_url.startswith("http"):
            set_setting(conn, "base_url", new_url.strip())
            st.success("Base URL actualizada.")
        else:
            st.error("La URL debe iniciar con http o https.")

    st.markdown("—")
    st.caption("Sincronización con Google Sheets")
    if st.button("Subir TODO el histórico a Sheets"):
        try:
            full_sync_to_sheets(conn)
            st.success("Sincronización completa realizada.")
        except Exception as e:
            st.error(f"Error al sincronizar: {e}")
