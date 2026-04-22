import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import random
import urllib.parse
import json
import tempfile
import os

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Gestión de Rifa Pro",
    page_icon="🎟️",
    layout="wide",
    initial_sidebar_state="collapsed" 
)

# --- 2. CSS PARA RESPONSIVIDAD (VERSIÓN GRID FORZADO) ---
st.markdown("""
    <style>
    /* Estilo para los botones */
    div.stButton > button {
        width: 100% !important;
        padding: 4px 0px !important;
        font-size: 12px !important;
    }

    /* FUERZA BRUTA: Cuadrícula en Móvil */
    @media (max-width: 768px) {
        /* Buscamos el contenedor de las columnas */
        [data-testid="stHorizontalBlock"] {
            display: grid !important;
            grid-template-columns: repeat(5, 1fr) !important; /* 5 columnas fijas */
            gap: 4px !important;
        }
        /* Anulamos el comportamiento de columna de Streamlit */
        [data-testid="column"] {
            width: 100% !important;
            min-width: 0px !important;
            flex: none !important;
        }
    }

    /* Ajuste para PC (10 columnas) */
    @media (min-width: 769px) {
        [data-testid="stHorizontalBlock"] {
            display: grid !important;
            grid-template-columns: repeat(10, 1fr) !important;
            gap: 8px !important;
        }
        [data-testid="column"] {
            width: 100% !important;
            min-width: 0px !important;
            flex: none !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. CONEXIÓN A FIREBASE ---
if not firebase_admin._apps:
    try:
        if "FIREBASE_RAW_JSON" in st.secrets:
            cred_dict = json.loads(st.secrets["FIREBASE_RAW_JSON"])
            if "private_key" in cred_dict:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            
            with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".json") as temp_f:
                json.dump(cred_dict, temp_f)
                temp_path = temp_f.name
            
            cred = credentials.Certificate(temp_path)
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://rifa-app-cfe3a-default-rtdb.firebaseio.com/' 
            })
            os.remove(temp_path)
        else:
            cred = credentials.Certificate("credenciales.json")
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://rifa-app-cfe3a-default-rtdb.firebaseio.com/' 
            })
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        st.stop()

# Referencias de Base de Datos
boletos_ref = db.reference('boletos')
config_ref = db.reference('configuracion')
vendedores_ref = db.reference('vendedores')

# --- 4. FUNCIONES DE APOYO ---
def inicializar_bd(total=100):
    nuevos_boletos = {}
    digitos = len(str(total - 1))
    for i in range(0, total):
        num_str = str(i).zfill(digitos) 
        nuevos_boletos[num_str] = {"estado": "disponible", "dueño": "", "telefono": "", "notificado": False, "vendedor": ""}
    boletos_ref.set(nuevos_boletos)
    
    default_msg = (
        "Hola {{nombre}}, gracias por colaborar a las rifas para apoyo estudiantil. "
        "Confirmamos tus boletos: {{boletos}}. La rifa es el 21 de agosto. "
        "Instagram: https://www.instagram.com/rifas_cucei"
    )
    config_ref.set({"mensaje_template": default_msg, "precio_boleto": 50.0})

# Carga de datos inicial
datos_crudos = boletos_ref.get()
config_datos = config_ref.get() or {}
vendedores_datos = vendedores_ref.get() or {}

if not datos_crudos:
    inicializar_bd(100)
    st.rerun()

MENSAJE_TEMPLATE = config_datos.get('mensaje_template', "")
PRECIO_BOLETO = config_datos.get('precio_boleto', 0.0)

if 'seleccionados' not in st.session_state:
    st.session_state.seleccionados = []

# Procesar boletos
datos_boletos = {}
if isinstance(datos_crudos, list):
    for i, info in enumerate(datos_crudos):
        if info: datos_boletos[str(i).zfill(len(str(len(datos_crudos)-1)))] = info
else:
    datos_boletos = datos_crudos

# --- 5. MODALES (DIÁLOGOS) ---
@st.dialog("🛒 Confirmar Venta")
def confirmar_venta(nombre, telefono, boletos, v_id, v_nombre):
    st.write(f"**Cliente:** {nombre} | **Vendedor:** {v_nombre}")
    st.write(f"**Boletos:** {', '.join(sorted(boletos))}")
    if st.button("✅ Registrar Venta", use_container_width=True):
        for b in boletos:
            boletos_ref.child(b).update({
                "estado":"ocupado", "dueño":nombre, "telefono":telefono, 
                "notificado":False, "vendedor": v_nombre
            })
        v_actuales = vendedores_datos[v_id].get('ventas', 0)
        vendedores_ref.child(v_id).update({'ventas': v_actuales + len(boletos)})
        st.session_state.seleccionados = []
        st.rerun()

# --- 6. PANEL ADMINISTRADOR (SIDEBAR) ---
with st.sidebar:
    st.header("⚙️ Admin")
    if st.toggle("Modo Admin"):
        password = st.text_input("Clave:", type="password")
        if password == st.secrets.get("ADMIN_PASSWORD", "1234"):
            st.success("Autorizado")
            
            # Progreso
            total_b = len(datos_boletos)
            ocupados = [k for k, v in datos_boletos.items() if v['estado'] == 'ocupado']
            st.write(f"Ventas: {len(ocupados)}/{total_b}")
            st.progress(len(ocupados)/total_b)
            
            # Pendientes WhatsApp
            st.subheader("📲 WhatsApp")
            pendientes = {k: v for k, v in datos_boletos.items() if v['estado'] == 'ocupado' and not v.get('notificado')}
            if pendientes:
                agrupados = {}
                for n, i in pendientes.items():
                    key = (i['dueño'], i['telefono'])
                    if key not in agrupados: agrupados[key] = []
                    agrupados[key].append(n)
                
                for (comprador, tel), lista in agrupados.items():
                    with st.expander(f"👤 {comprador}"):
                        if tel:
                            t = "".join(filter(str.isdigit, tel))
                            if len(t) == 10: t = "52" + t
                            m = MENSAJE_TEMPLATE.replace("{{nombre}}", comprador).replace("{{boletos}}", ", ".join(lista))
                            st.link_button("Enviar", f"https://wa.me/{t}?text={urllib.parse.quote(m)}")
                        if st.button("Marcar Enviado", key=f"not_{lista[0]}"):
                            for b in lista: boletos_ref.child(b).update({"notificado": True})
                            st.rerun()
            
            # Gestión de Vendedores
            st.subheader("👥 Vendedores")
            for vid, vinfo in vendedores_datos.items():
                st.write(f"{vinfo['nombre']}: {vinfo.get('ventas',0)}")
            
            if st.button("🚨 Reiniciar Todo"):
                boletos_ref.delete()
                st.rerun()

# --- 7. INTERFAZ PÚBLICA / VENDEDOR ---
st.title("🎟️ Rifa Apoyo Estudiantil")

# Inputs principales
c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 1.2])
with c1: cliente = st.text_input("👤 Cliente:")
with c2: tel = st.text_input("📞 WhatsApp:")
with c3: 
    v_nombres = {v['nombre']: k for k, v in vendedores_datos.items()}
    v_sel = st.selectbox("🧤 Vendedor:", ["Seleccionar..."] + list(v_nombres.keys()))
with c4: v_pass = st.text_input("🔑 Clave:", type="password")

st.divider()

# Cantidad y Ayuda
cant = st.number_input("Boletos a comprar:", min_value=1, value=1)
if len(st.session_state.seleccionados) == cant and cliente and v_sel != "Seleccionar...":
    vid = v_nombres[v_sel]
    if v_pass == vendedores_datos[vid]['clave']:
        confirmar_venta(cliente, tel, st.session_state.seleccionados, vid, v_sel)

ca, cl, _ = st.columns([2, 2, 6])
if ca.button("🎲 Aleatorio"):
    libres = [n for n, v in datos_boletos.items() if v['estado'] == 'disponible']
    st.session_state.seleccionados = random.sample(libres, cant)
    st.rerun()
if cl.button("🗑️ Limpiar"):
    st.session_state.seleccionados = []
    st.rerun()

st.write(f"Seleccionados: {', '.join(st.session_state.seleccionados)}")

# --- 8. CUADRÍCULA DE BOLETOS (VERSIÓN GRID ÚNICO) ---
st.divider()
boletos_lista = sorted(datos_boletos.items())

# Creamos un solo bloque de columnas (Streamlit repartirá los botones en el grid de CSS)
# Ponemos 10 columnas, pero el CSS 'grid-template-columns' es el que manda al final
columnas = st.columns(10)

for i, (num, info) in enumerate(boletos_lista):
    # Usamos el operador módulo para ciclar entre las columnas creadas
    with columnas[i % 10]:
        if info['estado'] == 'disponible':
            if num in st.session_state.seleccionados:
                if st.button(f"🟡{num}", key=f"btn_{num}"):
                    st.session_state.seleccionados.remove(num)
                    st.rerun()
            else:
                des = len(st.session_state.seleccionados) >= cant
                if st.button(num, key=f"btn_{num}", disabled=des):
                    if cliente:
                        st.session_state.seleccionados.append(num)
                        st.rerun()
                    else:
                        st.warning("Nombre")
        else:
            st.button("❌", key=f"btn_{num}", disabled=True)

# Usamos 10 columnas en el código, el CSS de arriba las ajustará a 5 en móvil
cols = st.columns(10)
for i, (num, info) in enumerate(boletos_lista):
    with cols[i % 10]:
        if info['estado'] == 'disponible':
            if num in st.session_state.seleccionados:
                if st.button(f"🟡{num}", key=f"btn_{num}"):
                    st.session_state.seleccionados.remove(num)
                    st.rerun()
            else:
                des = len(st.session_state.seleccionados) >= cant
                if st.button(num, key=f"btn_{num}", disabled=des):
                    if cliente:
                        st.session_state.seleccionados.append(num)
                        st.rerun()
                    else:
                        st.warning("Nombre")
        else:
            st.button("❌", key=f"btn_{num}", disabled=True)
