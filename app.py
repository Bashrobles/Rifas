import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import random
import urllib.parse
import json
import tempfile
import os

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Rifa CUCEI", page_icon="🎟️", layout="wide")

# --- 2. CONEXIÓN FIREBASE ---
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
            firebase_admin.initialize_app(cred, {'databaseURL': 'https://rifa-app-cfe3a-default-rtdb.firebaseio.com/'})
            os.remove(temp_path)
        else:
            cred = credentials.Certificate("credenciales.json")
            firebase_admin.initialize_app(cred, {'databaseURL': 'https://rifa-app-cfe3a-default-rtdb.firebaseio.com/'})
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

boletos_ref = db.reference('boletos')
config_ref = db.reference('configuracion')
vendedores_ref = db.reference('vendedores')

# --- 3. DATOS ---
datos_crudos = boletos_ref.get()
config_datos = config_ref.get() or {}
vendedores_datos = vendedores_ref.get() or {}

PRECIO_BOLETO = config_datos.get('precio_boleto', 50.0)
MENSAJE_TEMPLATE = config_datos.get('mensaje_template', "Hola {{nombre}}, tus boletos son: {{boletos}}")

if 'seleccionados' not in st.session_state:
    st.session_state.seleccionados = []

datos_boletos = {}
if isinstance(datos_crudos, list):
    for i, info in enumerate(datos_crudos):
        if info: datos_boletos[str(i).zfill(len(str(len(datos_crudos)-1)))] = info
else:
    datos_boletos = datos_crudos or {}

# --- 4. DIÁLOGOS ---
@st.dialog("🛒 Confirmar Registro")
def confirmar_venta(nombre, telefono, boletos, v_id, v_nombre):
    total_pago = len(boletos) * PRECIO_BOLETO
    st.write(f"**Cliente:** {nombre} | **Total:** ${total_pago}")
    st.write(f"**Números:** {', '.join(sorted(boletos))}")
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

# --- 5. SIDEBAR (EL MENÚ CHIDO) ---
with st.sidebar:
    st.header("⚙️ Admin")
    if st.toggle("Acceso Admin"):
        pwd = st.text_input("Clave:", type="password")
        if pwd == st.secrets.get("ADMIN_PASSWORD", "1234"):
            # Métricas
            ocupados = [k for k, v in datos_boletos.items() if v['estado'] == 'ocupado']
            st.metric("Ventas Totales", f"{len(ocupados)}/{len(datos_boletos)}")
            st.metric("Recaudado", f"${len(ocupados)*PRECIO_BOLETO}")
            
            # Buscador (Lo que pediste: Nombre y Teléfono)
            st.subheader("🔍 Buscar Comprador")
            if ocupados:
                b_ver = st.selectbox("Elegir boleto:", sorted(ocupados, key=int))
                info = datos_boletos[b_ver]
                st.info(f"👤 **{info['dueño']}**\n\n📞 **{info['telefono']}**")
                if st.button("🔓 Liberar Número"):
                    boletos_ref.child(b_ver).update({"estado":"disponible","dueño":"","telefono":"","vendedor":""})
                    st.rerun()

            # CSV (Lo que pediste)
            st.subheader("📊 Reportes")
            csv_data = "Nombre,Telefono,Boletos\n"
            contactos = {}
            for n, i in datos_boletos.items():
                if i['estado'] == 'ocupado':
                    key = (i['dueño'], i['telefono'])
                    if key not in contactos: contactos[key] = []
                    contactos[key].append(n)
            for (nom, tel), nums in contactos.items():
                csv_data += f"{nom},{tel},{'-'.join(nums)}\n"
            st.download_button("📥 Descargar CSV de Ventas", csv_data, "ventas_rifa.csv")

            # Configuración de Precio
            new_p = st.number_input("Precio por boleto:", value=float(PRECIO_BOLETO))
            if st.button("Actualizar Precio"):
                config_ref.update({"precio_boleto": new_p})
                st.rerun()

# --- 6. INTERFAZ VENDEDOR ---
st.title("🎟️ Rifa Apoyo Estudiantil")
st.write(f"**Precio por boleto: ${PRECIO_BOLETO} MXN**")

c1, c2, c3, c4 = st.columns(4)
with c1: cliente = st.text_input("👤 Cliente:")
with c2: tel = st.text_input("📞 WhatsApp:")
with c3: 
    v_nombres = {v['nombre']: k for k, v in vendedores_datos.items()}
    v_sel = st.selectbox("🧤 Vendedor:", ["Seleccionar..."] + list(v_nombres.keys()))
with c4: v_pass = st.text_input("🔑 Clave:", type="password")

st.divider()

# Input de Cantidad (Recuperado)
cant = st.number_input("🎟️ ¿Cuántos boletos?", min_value=1, value=1)

# Lógica de Venta
if len(st.session_state.seleccionados) == cant and cliente and v_sel != "Seleccionar...":
    vid = v_nombres[v_sel]
    if v_pass == vendedores_datos[vid]['clave']:
        confirmar_venta(cliente, tel, st.session_state.seleccionados, vid, v_sel)

ca, cl, _ = st.columns([2, 2, 6])
if ca.button("🎲 Aleatorio"):
    libres = [n for n, v in datos_boletos.items() if v['estado'] == 'disponible']
    st.session_state.seleccionados = random.sample(libres, min(cant, len(libres)))
    st.rerun()
if cl.button("🗑️ Limpiar"):
    st.session_state.seleccionados = []
    st.rerun()

st.write(f"Seleccionados: **{', '.join(st.session_state.seleccionados)}**")

# --- 7. CUADRÍCULA ---
st.divider()
st.markdown("<style>div.stButton > button {width:100% !important;}</style>", unsafe_allow_html=True)

boletos_lista = sorted(datos_boletos.items())
cols_n = 10
for i in range(0, len(boletos_lista), cols_n):
    fila = boletos_lista[i : i + cols_n]
    cols = st.columns(cols_n)
    for idx, (num, info) in enumerate(fila):
        with cols[idx]:
            if info['estado'] == 'disponible':
                if num in st.session_state.seleccionados:
                    if st.button(f"🟡{num}", key=f"n_{num}"):
                        st.session_state.seleccionados.remove(num)
                        st.rerun()
                else:
                    des = len(st.session_state.seleccionados) >= cant
                    if st.button(num, key=f"n_{num}", disabled=des):
                        if cliente:
                            st.session_state.seleccionados.append(num)
                            st.rerun()
                        else: st.warning("Nombre")
            else:
                st.button("❌", key=f"n_{num}", disabled=True)
