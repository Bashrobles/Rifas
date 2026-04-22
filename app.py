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

# --- 3. CARGA DE DATOS Y ESTADO ---
datos_crudos = boletos_ref.get()
config_datos = config_ref.get() or {}
vendedores_datos = vendedores_ref.get() or {}

PRECIO_BOLETO = config_datos.get('precio_boleto', 50.0)
MENSAJE_TEMPLATE = config_datos.get('mensaje_template', "Hola {{nombre}}, tus boletos son: {{boletos}}")

# Inicializar estados si no existen
if 'seleccionados' not in st.session_state: st.session_state.seleccionados = []
if 'promo_activa' not in st.session_state: st.session_state.promo_activa = False

# Estados para limpiar inputs
if 'input_cliente' not in st.session_state: st.session_state.input_cliente = ""
if 'input_tel' not in st.session_state: st.session_state.input_tel = ""
if 'input_clave' not in st.session_state: st.session_state.input_clave = ""

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
    st.write(f"**Cliente:** {nombre} | **Números:** {', '.join(sorted(boletos))}")
    if con_promo: st.write(f"**Subtotal:** ${subtotal} | **Descuento:** -$50")
    st.write(f"### **Total:** ${total}")
    if st.button("✅ Registrar Venta", use_container_width=True):
        for b in boletos:
            boletos_ref.child(b).update({"estado":"ocupado", "dueño":nombre, "telefono":telefono, "notificado":False, "vendedor": v_nombre})
        vendedores_ref.child(v_id).update({'ventas': vendedores_datos[v_id].get('ventas', 0) + len(boletos)})
        st.session_state.seleccionados = []
        st.session_state.promo_activa = False
        st.rerun()

# --- 5. PANEL ADMINISTRADOR (REINTEGRADO COMPLETO) ---
with st.sidebar:
    st.header("⚙️ Admin")
    if st.toggle("Desbloquear Modo Admin"):
        pwd = st.text_input("Clave Maestra:", type="password")
        if pwd == st.secrets.get("ADMIN_PASSWORD", "1234"):
            st.success("Autorizado")
            ocupados_list = [k for k, v in datos_boletos.items() if v['estado'] == 'ocupado']
            st.progress(len(ocupados_list)/len(datos_boletos) if datos_boletos else 0)
            st.write(f"Ventas: {len(ocupados_list)}/{len(datos_boletos)}")

            # WHATSAPP PENDIENTES
            st.subheader("📩 Pendientes")
            pendientes = {k: v for k, v in datos_boletos.items() if v['estado'] == 'ocupado' and not v.get('notificado')}
            if pendientes:
                agrupados = {}
                for n, i in pendientes.items():
                    key = (i['dueño'], i['telefono'])
                    if key not in agrupados: agrupados[key] = []
                    agrupados[key].append(n)
                for (comp, tel_cli), lista in agrupados.items():
                    with st.expander(f"👤 {comp} ({len(lista)})"):
                        if tel_cli:
                            t = "".join(filter(str.isdigit, tel_cli))
                            if len(t) == 10: t = "52" + t
                            msj = MENSAJE_TEMPLATE.replace("{{nombre}}", comp).replace("{{boletos}}", ", ".join(lista))
                            st.link_button("📲 WhatsApp", f"https://wa.me/{t}?text={urllib.parse.quote(msj)}", use_container_width=True)
                        c_env, c_can = st.columns(2)
                        if c_env.button("✅ Enviado", key=f"env_{lista[0]}"):
                            for b in lista: boletos_ref.child(b).update({"notificado": True})
                            st.rerun()
                        if c_can.button("🚫 Cancelar", key=f"can_{lista[0]}", type="primary"):
                            for b in lista: boletos_ref.child(b).update({"estado":"disponible","dueño":"","telefono":"","notificado":False})
                            st.rerun()

            # BUSCADOR
            st.subheader("🔍 Buscar")
            if ocupados_list:
                b_adm = st.selectbox("Boleto:", sorted(ocupados_list, key=int))
                info_a = datos_boletos[b_adm]
                st.info(f"👤 {info_a['dueño']}\n📞 {info_a['telefono']}")
                if st.button("🔓 Liberar Número"):
                    boletos_ref.child(b_adm).update({"estado":"disponible","dueño":"","telefono":"","vendedor":""})
                    st.rerun()

            # EQUIPO
            st.subheader("👥 Equipo")
            with st.expander("Gestionar"):
                nv = st.text_input("Nombre:")
                cv = st.text_input("Clave:", type="password")
                if st.button("➕ Crear"):
                    vendedores_ref.push({'nombre': nv, 'clave': cv, 'ventas': 0})
                    st.rerun()
                st.divider()
                if vendedores_datos:
                    v_del = {v['nombre']: k for k, v in vendedores_datos.items()}
                    target = st.selectbox("Eliminar:", list(v_del.keys()))
                    if st.button("🗑️ Eliminar Definitivamente"):
                        vendedores_ref.child(v_del[target]).delete()
                        st.rerun()

            # EXTRAS
            st.subheader("📊 Extras")
            csv_str = "Nombre,Telefono,Boletos\n"
            for n, i in datos_boletos.items():
                if i['estado'] == 'ocupado': csv_str += f"{i['dueño']},{i['telefono']},{n}\n"
            st.download_button("📥 Descargar CSV", csv_str, "ventas.csv")
            
            new_p = st.number_input("Precio:", value=float(PRECIO_BOLETO))
            if st.button("Guardar Precio"):
                config_ref.update({"precio_boleto": new_p}); st.rerun()

# --- 6. INTERFAZ VENDEDOR ---
st.title("🎟️ Rifa CUCEI Pro")
st.write(f"**Precio: ${PRECIO_BOLETO} MXN**")

# Función para limpiar (se llama mediante el botón)
def limpiar_datos_vendedor():
    # Solo reseteamos los valores que NO están ligados a widgets bloqueados
    # O simplemente forzamos un reset de los componentes
    st.session_state.seleccionados = []
    st.session_state.promo_activa = False
    # Para los inputs, usaremos una técnica de "empty keys" o simplemente rerun
    # Pero lo más efectivo en Streamlit es resetear por fragmento o refrescar
    for key in ["input_cliente", "input_tel", "input_clave", "manual_in"]:
        if key in st.session_state:
            st.session_state[key] = ""

# Inputs 
# TIP: No les pongas el mismo nombre a la variable y a la key
c1, c2, c3, c4 = st.columns(4)
with c1: cliente = st.text_input("👤 Cliente:", key="input_cliente")
with c2: tel = st.text_input("📞 WhatsApp:", key="input_tel")
with c3:
    v_opc = {v['nombre']: k for k, v in vendedores_datos.items()}
    v_sel = st.selectbox("🧤 Vendedor:", ["Seleccionar..."] + list(v_opc.keys()))
with c4: v_pass = st.text_input("🔑 Clave:", type="password", key="input_clave")

# BOTÓN DE LIMPIEZA CORREGIDO
# Usamos on_click para ejecutar la limpieza antes de renderizar
if st.button("🗑️ Limpiar Datos Cliente", use_container_width=True):
    # En lugar de asignar directamente aquí (que da el error),
    # simplemente limpiamos lo que NO es widget y forzamos el reinicio.
    # Streamlit limpiará los widgets al no encontrar valores previos si no usamos value=
    st.session_state.seleccionados = []
    st.session_state.promo_activa = False
    # Borramos las llaves del estado para que los widgets se reinicien
    del st.session_state["input_cliente"]
    del st.session_state["input_tel"]
    del st.session_state["input_clave"]
    st.rerun()

st.divider()
# --- 7. CUADRÍCULA 10 COLS ---
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
                    if st.button(f"🟡{num}", key=f"n_{num}"): st.session_state.seleccionados.remove(num); st.rerun()
                else:
                    des = len(st.session_state.seleccionados) >= cant
                    if st.button(num, key=f"n_{num}", disabled=des):
                        if cliente: st.session_state.seleccionados.append(num); st.rerun()
                        else: st.warning("Escribe nombre")
            else: st.button("❌", key=f"n_{num}", disabled=True)
