import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import random
import urllib.parse
import json
import tempfile
import os

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Rifa CUCEI Pro", page_icon="🎟️", layout="wide")

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

# --- 3. CARGA DE DATOS ---
datos_crudos = boletos_ref.get()
config_datos = config_ref.get() or {}
vendedores_datos = vendedores_ref.get() or {}

PRECIO_BOLETO = config_datos.get('precio_boleto', 50.0)
MENSAJE_TEMPLATE = config_datos.get('mensaje_template', "Hola {{nombre}}, tus boletos son: {{boletos}}")

if 'seleccionados' not in st.session_state:
    st.session_state.seleccionados = []
if 'promo_activa' not in st.session_state:
    st.session_state.promo_activa = False

datos_boletos = {}
if isinstance(datos_crudos, list):
    for i, info in enumerate(datos_crudos):
        if info: datos_boletos[str(i).zfill(len(str(len(datos_crudos)-1)))] = info
else:
    datos_boletos = datos_crudos or {}

# --- 4. DIÁLOGOS ---
@st.dialog("🛒 Confirmar Venta")
def confirmar_venta(nombre, telefono, boletos, v_id, v_nombre, con_promo):
    subtotal = len(boletos) * PRECIO_BOLETO
    total = subtotal - 50 if con_promo else subtotal
    
    st.write(f"**Cliente:** {nombre}")
    st.write(f"**Vendedor:** {v_nombre}")
    st.write(f"**Números:** {', '.join(sorted(boletos))}")
    if con_promo:
        st.write(f"**Subtotal:** ${subtotal} | **Descuento Promo:** -$50")
    st.write(f"### **Total a cobrar:** ${total}")
    
    if st.button("✅ Registrar y Finalizar", use_container_width=True):
        for b in boletos:
            boletos_ref.child(b).update({
                "estado":"ocupado", "dueño":nombre, "telefono":telefono, 
                "notificado":False, "vendedor": v_nombre
            })
        v_actuales = vendedores_datos[v_id].get('ventas', 0)
        vendedores_ref.child(v_id).update({'ventas': v_actuales + len(boletos)})
        st.session_state.seleccionados = []
        st.session_state.promo_activa = False
        st.rerun()

# --- 5. PANEL ADMINISTRADOR ---
with st.sidebar:
    st.header("⚙️ Panel Admin")
    if st.toggle("Modo Admin"):
        pwd = st.text_input("Clave Maestra:", type="password")
        if pwd == st.secrets.get("ADMIN_PASSWORD", "1234"):
            st.success("Acceso Autorizado")
            
            ocupados_list = [k for k, v in datos_boletos.items() if v['estado'] == 'ocupado']
            progreso = len(ocupados_list)/len(datos_boletos) if datos_boletos else 0
            st.progress(progreso)
            st.write(f"Ventas: {len(ocupados_list)}/{len(datos_boletos)}")

            # Buscador por comprador
            st.subheader("🔍 Buscador")
            if ocupados_list:
                b_admin = st.selectbox("Elegir boleto:", sorted(ocupados_list, key=int))
                info_a = datos_boletos[b_admin]
                st.info(f"👤 {info_a['dueño']} | 📞 {info_a['telefono']}")
                if st.button("🔓 Liberar Número"):
                    boletos_ref.child(b_admin).update({"estado":"disponible","dueño":"","telefono":"","vendedor":""})
                    st.rerun()

            # Gestión de Vendedores
            st.subheader("👥 Equipo")
            with st.expander("➕ Añadir / 🗑️ Eliminar"):
                nv = st.text_input("Nuevo Nombre:")
                cv = st.text_input("Nueva Clave:", type="password")
                if st.button("Crear Vendedor"):
                    vendedores_ref.push({'nombre': nv, 'clave': cv, 'ventas': 0})
                    st.rerun()
                
                st.divider()
                if vendedores_datos:
                    v_opc_del = {v['nombre']: k for k, v in vendedores_datos.items()}
                    v_target = st.selectbox("Eliminar a:", list(v_opc_del.keys()))
                    if st.button("Confirmar Borrado"):
                        vendedores_ref.child(v_opc_del[v_target]).delete()
                        st.rerun()

            # CSV y Precio
            st.subheader("📊 Extras")
            todos_v = {}
            for n, i in datos_boletos.items():
                if i['estado'] == 'ocupado':
                    k = (i['dueño'], i['telefono'])
                    if k not in todos_v: todos_v[k] = []
                    todos_v[k].append(n)
            csv_f = "Nombre,Telefono,Boletos\n"
            for (n, t), blist in todos_v.items():
                csv_f += f"{n},{t},{' '.join(blist)}\n"
            st.download_button("📥 Descargar CSV de Ventas", csv_f, "ventas.csv")

            np = st.number_input("Cambiar Precio:", value=float(PRECIO_BOLETO))
            if st.button("Guardar Nuevo Precio"):
                config_ref.update({"precio_boleto": np})
                st.rerun()

# --- 6. INTERFAZ VENDEDOR ---
st.title("🎟️ Sistema de Rifas - CUCEI")
st.write(f"**Precio Unitario: ${PRECIO_BOLETO}**")

# Datos del Cliente
with st.container():
    c1, c2, c3, c4 = st.columns(4)
    with c1: cliente = st.text_input("👤 Cliente:", key="c_nom")
    with c2: tel = st.text_input("📞 WhatsApp:", key="c_tel")
    with c3: 
        v_opc = {v['nombre']: k for k, v in vendedores_datos.items()}
        v_sel = st.selectbox("🧤 Vendedor:", ["Seleccionar..."] + list(v_opc.keys()))
    with c4: v_pass = st.text_input("🔑 Tu Clave:", type="password")
    
    if st.button("🗑️ Limpiar Datos del Cliente", use_container_width=True):
        st.rerun()

st.divider()

# Selección de Boletos
col_c, col_m = st.columns([2, 3])

with col_c:
    cant = st.number_input("🎟️ ¿Cuántos boletos?", min_value=1, value=1)
    if cant >= 4:
        st.session_state.promo_activa = st.toggle("✨ Aplicar Promo (-$50)", value=st.session_state.promo_activa)
    else:
        st.session_state.promo_activa = False
        st.caption("Promo disponible a partir de 4 boletos")

with col_m:
    manual_input = st.text_input("🔢 Agregar números manualmente (comas o espacios):")
    if st.button("➕ Agregar a la Lista"):
        nums = manual_input.replace(",", " ").split()
        for n in nums:
            n_pad = n.zfill(len(str(len(datos_boletos)-1)))
            if n_pad in datos_boletos and datos_boletos[n_pad]['estado'] == 'disponible':
                if len(st.session_state.seleccionados) < cant and n_pad not in st.session_state.seleccionados:
                    st.session_state.seleccionados.append(n_pad)
        st.rerun()

# Ayuda Rápida
ca, cl, _ = st.columns([2, 2, 6])
if ca.button("🎲 Rellenar con Aleatorios"):
    faltan = cant - len(st.session_state.seleccionados)
    if faltan > 0:
        libres = [n for n, v in datos_boletos.items() if v['estado'] == 'disponible' and n not in st.session_state.seleccionados]
        if len(libres) >= faltan:
            st.session_state.seleccionados.extend(random.sample(libres, faltan))
            st.rerun()
if cl.button("🗑️ Limpiar Selección"):
    st.session_state.seleccionados = []
    st.rerun()

st.write(f"Seleccionados: **{', '.join(sorted(st.session_state.seleccionados))}** ({len(st.session_state.seleccionados)}/{cant})")

# Venta Automática
if len(st.session_state.seleccionados) == cant and cliente and v_sel != "Seleccionar...":
    vid = v_opc[v_sel]
    if v_pass == vendedores_datos[vid]['clave']:
        confirmar_venta(cliente, tel, st.session_state.seleccionados, vid, v_sel, st.session_state.promo_activa)

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
