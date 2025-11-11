import streamlit as st, pandas as pd, numpy as np, qrcode
from PIL import Image
import io, sqlite3
from datetime import datetime
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe
EVENT_NAME="Primer Encuentro Internacional de Guías de Turistas en Chiapas"
EVENT_DATES="14–16 de noviembre de 2025"
EVENT_TAGLINE="Saberes que unen, culturas que inspiran."
ORG_NAME="Colegio de Guías de Turistas de Chiapas A.C."
ASSETS=Path("assets")
LOGO=ASSETS/"logo_colegio.jpg"
POSTER=ASSETS/"poster_encuentro.jpg"
PRIMARY_COLOR="#116699"
SUCCESS_COLOR="#16a34a"
DANGER_COLOR="#dc2626"
WARNING_COLOR="#f59e0b"
APP_TITLE=f"Registro y Acceso | {EVENT_NAME}"
DB_PATH="data/app.db"
DEFAULT_BASE_URL=st.secrets.get("base_url","https://TU-APP.streamlit.app")
st.set_page_config(page_title=APP_TITLE, page_icon=str(LOGO), layout='wide')
st.markdown('<style>.status{color:#fff;padding:24px;border-radius:16px;text-align:center;font-size:28px;font-weight:800;}</style>', unsafe_allow_html=True)
col_logo,col_title=st.columns([1,3])

with col_logo:
    if LOGO.exists():
        st.image(str(LOGO), use_column_width=True)
with col_title:
    st.markdown(f"<h1 style='margin-bottom:0'>{EVENT_NAME}</h1>", unsafe_allow_html=True)
    st.markdown(f"<h4 style='margin-top:0;color:#374151'>{EVENT_DATES}</h4>", unsafe_allow_html=True)
    st.caption(f"{EVENT_TAGLINE} • {ORG_NAME}")
def init_db():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS attendees (id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT UNIQUE, nombre TEXT, institucion TEXT, tipo_cuota TEXT, email TEXT, telefono TEXT, qr_token TEXT UNIQUE, registrado_en TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS checkins (id INTEGER PRIMARY KEY AUTOINCREMENT, attendee_id INTEGER, sede TEXT, realizado_en TEXT, FOREIGN KEY(attendee_id) REFERENCES attendees(id))''')
    cur.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    con.commit(); con.close()
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)
def next_folio(con):
    df=pd.read_sql_query('SELECT folio FROM attendees ORDER BY id DESC LIMIT 1', con)
    if df.empty: return 'CGTCH-25-0001'
    last=df.folio.iloc[0]
    try:
        num=int(last.split('-')[-1]); return f'CGTCH-25-{num+1:04d}'
    except Exception:
        import time; return f'CGTCH-25-{int(time.time())%10000:04d}'
def get_setting(con,key,default=None):
    df=pd.read_sql_query('SELECT value FROM settings WHERE key = ?', con, params=(key,))
    return (df.iloc[0]['value'] if not df.empty else default)
def set_setting(con,key,value):
    cur=get_conn().cursor()
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor(); cur.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value)); con.commit(); con.close()
def add_attendee(con,data):
    folio=next_folio(con)
    import time,random
    token=f'TKN-{int(time.time())}-{random.randint(1000,9999)}'
    now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur=con.cursor(); cur.execute('''INSERT INTO attendees (folio,nombre,institucion,tipo_cuota,email,telefono,qr_token,registrado_en) VALUES (?,?,?,?,?,?,?,?)''',(folio,data['nombre'],data.get('institucion',''),data.get('tipo_cuota',''),data.get('email',''),data.get('telefono',''),token,now)); con.commit(); return folio,token
def find_attendee_by_token(con,token):
    df=pd.read_sql_query('SELECT * FROM attendees WHERE qr_token = ?', con, params=(token,))
    return df.iloc[0].to_dict() if not df.empty else None
def get_checkins_for_attendee(con,attendee_id):
    return pd.read_sql_query('SELECT * FROM checkins WHERE attendee_id = ? ORDER BY id DESC', con, params=(attendee_id,))
def add_checkin(con,attendee_id,sede):
    now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur=con.cursor(); cur.execute('INSERT INTO checkins (attendee_id,sede,realizado_en) VALUES (?,?,?)',(attendee_id,sede,now)); con.commit()
def big_status(text,bg):
    st.markdown(f"<div class='status' style='background:{bg}'>{text}</div>", unsafe_allow_html=True)
def generate_qr_image(data_text:str)->Image.Image:
    qr=qrcode.QRCode(version=1, box_size=10, border=2); qr.add_data(data_text); qr.make(fit=True); return qr.make_image(fill_color='black', back_color='white')
init_db(); conn=get_conn()
params=st.query_params
if 'token' in params:
    token=params.get('token')
    sede=params.get('sede',['Holiday Inn Tuxtla (Día 1)'])[0]
    rec=find_attendee_by_token(conn, token)
    if not rec:
        big_status('❌ QR inválido o no encontrado', '#dc2626'); st.stop()
    checks=get_checkins_for_attendee(conn, rec['id'])
    already= (not checks[checks['sede']==sede].empty) if not checks.empty else False
    if not already:
        add_checkin(conn, rec['id'], sede); big_status('✅ Verificado • Acceso concedido', '#16a34a')
    else:
        big_status('🟡 Ya registrado en esta sede', '#f59e0b')
    st.write('**Asistente:**', rec['nombre']); st.write('**Folio:**', rec['folio']); st.write('**Tipo de cuota:**', rec['tipo_cuota']); st.write('**Sede:**', sede); st.stop()
tabs=st.tabs(['📝 Registro','📊 Reportes','⚙️ Ajustes'])
with tabs[0]:
    st.subheader('Registrar nuevo asistente')
    base_url=get_setting(conn,'base_url',DEFAULT_BASE_URL)
    st.info(f'Base URL actual para generar QR: {base_url}')
    with st.form('registro_form'):
        cols=st.columns(2)
        nombre=cols[0].text_input('Nombre completo *')
        institucion=cols[1].text_input('Institución / Empresa')
        cols2=st.columns(3)
        tipo_cuota=cols2[0].selectbox('Tipo de cuota',["Guía Chiapas","Público general","Estudiante","Ponente","Invitado especial"]) 
        email=cols2[1].text_input('Email')
        telefono=cols2[2].text_input('Teléfono')
        sede_default=st.selectbox('Sede por defecto para el check-in vía URL',["Holiday Inn Tuxtla (Día 1)","Ex Convento Santo Domingo (Día 2)","Museo de los Altos (Día 3)"])
        submitted=st.form_submit_button('Registrar')
    if submitted:
        if not nombre.strip():
            st.error('Por favor ingresa el nombre completo.')
        else:
            folio,token=add_attendee(conn,{'nombre':nombre.strip(),'institucion':institucion.strip(),'tipo_cuota':tipo_cuota,'email':email.strip(),'telefono':telefono.strip()})
            qr_url=f"{base_url}/?token={token}&sede={sede_default}"
            img=generate_qr_image(qr_url); buf=io.BytesIO(); img.save(buf, format='PNG')
            st.success(f'Registro exitoso. Folio: {folio}')
            st.image(buf.getvalue(), caption=f'QR de {nombre}', width=220)
            st.code(qr_url, language='text')
            st.download_button('Descargar QR (PNG)', data=buf.getvalue(), file_name=f'{folio}.png', mime='image/png')
    st.divider(); st.subheader('Listado rápido (últimos 50)')
    df=pd.read_sql_query('SELECT folio,nombre,institucion,tipo_cuota,email,telefono,registrado_en FROM attendees ORDER BY id DESC LIMIT 50', conn)
    st.dataframe(df, use_container_width=True)
with tabs[1]:
    st.subheader('Reportes y exportación')
    c1,c2=st.columns(2)
    with c1:
        st.caption('Asistentes registrados')
        df_a=pd.read_sql_query('SELECT folio,nombre,institucion,tipo_cuota,email,telefono,registrado_en FROM attendees ORDER BY id DESC', conn)
        st.dataframe(df_a, use_container_width=True)
        st.download_button('Descargar asistentes (CSV)', data=df_a.to_csv(index=False).encode('utf-8'), file_name='asistentes.csv', mime='text/csv')
    with c2:
        st.caption('Check-ins realizados')
        df_c=pd.read_sql_query('SELECT c.id,a.folio,a.nombre,c.sede,c.realizado_en FROM checkins c JOIN attendees a ON a.id=c.attendee_id ORDER BY c.id DESC', conn)
        st.dataframe(df_c, use_container_width=True)
        st.download_button('Descargar check-ins (CSV)', data=df_c.to_csv(index=False).encode('utf-8'), file_name='checkins.csv', mime='text/csv')
with tabs[2]:
    st.subheader('Ajustes de la app')
    base_url_current=get_setting(conn,'base_url',DEFAULT_BASE_URL)
    new_url=st.text_input('Base URL para generar los QR (incluye https://)', value=base_url_current)
    if st.button('Guardar Base URL'):
        if new_url.startswith('http'):
            set_setting(conn,'base_url',new_url.strip()); st.success('Base URL actualizada.')
        else:
            st.error('La URL debe iniciar con http o https.')
