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

# --- 2. CONEXIÓN A FIREBASE (VERSIÓN ROBUSTA) ---
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

# Referencias
boletos_ref = db.reference('boletos')
config_ref = db.reference('configuracion')
vendedores_ref = db.reference('vendedores')

# --- 3. FUNCIONES DE APOYO ---
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

# Carga de datos
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

datos_boletos = {}
if isinstance(datos_crudos, list):
    for i, info in enumerate(datos_crudos):
        if info: datos_boletos[str(i).zfill(len(str(len(datos_crudos)-1)))] = info
else:
    datos_boletos = datos_crudos

# --- 4. DIÁLOGOS ---
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

# --- 5. PANEL ADMINISTRADOR (SIDEBAR RECARGADO) ---
with st.sidebar:
    st.header("⚙️ Panel de Control")
    if st.toggle("Desbloquear Opciones"):
        password = st.text_input("Clave Maestra:", type="password")
        
        # Seguridad con Secrets
        clave_correcta = st.secrets.get("ADMIN_PASSWORD", "1234")
        
        if password == clave_correcta:
            st.success("Acceso Autorizado")
            st.divider()

            # --- 📊 ESTADÍSTICAS Y PROGRESO ---
            total_b = len(datos_boletos)
            ocupados_list = [k for k, v in datos_boletos.items() if v['estado'] == 'ocupado']
            vendidos_n = len(ocupados_list)
            porcentaje = (vendidos_n / total_b) if total_b > 0 else 0
            
            st.subheader("📈 Avance de Ventas")
            st.progress(porcentaje)
            st.write(f"Ventas: **{vendidos_n}/{total_b}** ({porcentaje*100:.1f}%)")
            st.divider()

            # --- 📩 PENDIENTES WHATSAPP (AGRUPADOS) ---
            st.subheader("📩 Mensajes Pendientes")
            pendientes = {k: v for k, v in datos_boletos.items() if v['estado'] == 'ocupado' and not v.get('notificado', False)}
            
            if pendientes:
                agrupados = {}
                for num, info in pendientes.items():
                    llave = (info['dueño'], info['telefono'])
                    if llave not in agrupados: agrupados[llave] = []
                    agrupados[llave].append(num)
                
                for (comprador, tel), lista in agrupados.items():
                    with st.expander(f"👤 {comprador} ({len(lista)})"):
                        if tel:
                            t_limpio = "".join(filter(str.isdigit, tel))
                            if len(t_limpio) == 10: t_limpio = "52" + t_limpio
                            msj = MENSAJE_TEMPLATE.replace("{{nombre}}", comprador).replace("{{boletos}}", ", ".join(lista))
                            st.link_button("📲 Mandar WhatsApp", f"https://wa.me/{t_limpio}?text={urllib.parse.quote(msj)}")
                        
                        col_e, col_c = st.columns(2)
                        if col_e.button("✅ Enviado", key=f"btn_env_{lista[0]}"):
                            for b in lista: boletos_ref.child(b).update({"notificado": True})
                            st.rerun()
                        if col_c.button("🚫 Liberar", key=f"btn_lib_{lista[0]}", type="primary"):
                            for b in lista: boletos_ref.child(b).update({"estado":"disponible", "dueño":"", "vendedor":"", "telefono": "", "notificado": False})
                            st.rerun()
            else:
                st.info("No hay mensajes pendientes.")
            st.divider()

            # --- 🔍 GESTIÓN DE NÚMEROS VENDIDOS ---
            st.subheader("🔍 Buscar / Liberar")
            if ocupados_list:
                b_rev = st.selectbox("Boleto vendido:", sorted(ocupados_list, key=int))
                info_b = datos_boletos[b_rev]
                st.write(f"Comprador: **{info_b['dueño']}**")
                st.write(f"Vendedor: **{info_b.get('vendedor', 'N/A')}**")
                if st.button("🔓 Liberar este número", type="primary"):
                    boletos_ref.child(b_rev).update({"estado": "disponible", "dueño": "", "telefono": "", "notificado": False, "vendedor": ""})
                    st.rerun()

            st.divider()

            # --- 👥 GESTIÓN DE VENDEDORES ---
            st.subheader("👥 Equipo de Ventas")
            with st.expander("➕ Añadir Vendedor"):
                n_vend = st.text_input("Nombre:")
                c_vend = st.text_input("Clave personal:", type="password")
                if st.button("Guardar Vendedor"):
                    vendedores_ref.push({'nombre': n_vend, 'clave': c_vend, 'ventas': 0})
                    st.rerun()
            
            if vendedores_datos:
                with st.expander("🗑️ Eliminar Vendedor"):
                    v_opciones = {v['nombre']: k for k, v in vendedores_datos.items()}
                    v_borrar = st.selectbox("Selecciona:", list(v_opciones.keys()))
                    if st.button("⚠️ Eliminar Definitivamente"):
                        vendedores_ref.child(v_opciones[v_borrar]).delete()
                        st.rerun()

                st.write("**Corte de Caja:**")
                for vid, vinfo in vendedores_datos.items():
                    st.write(f"• {vinfo['nombre']}: {vinfo.get('ventas', 0)} boletos")
                
                if st.button("💰 Limpiar Ventas (Cero)"):
                    for vid in vendedores_datos: vendedores_ref.child(vid).update({'ventas': 0})
                    st.rerun()

            st.divider()

            # --- 📢 DIFUSIÓN Y SEGURIDAD ---
            st.subheader("📢 Exportar")
            contactos = {v['telefono']: v['dueño'] for v in datos_boletos.values() if v['estado'] == 'ocupado' and v['telefono']}
            if contactos:
                csv = "Name,Phone\n" + "\n".join([f"{n},{t}" for t, n in contactos.items()])
                st.download_button("📥 Descargar CSV de Contactos", csv, "rifa_contactos.csv", "text/csv")
            
            if st.button("🚨 REINICIAR TODA LA RIFA"):
                inicializar_bd(len(datos_boletos))
                st.rerun()
        elif password != "":
            st.error("Contraseña incorrecta")

# --- 6. INTERFAZ PÚBLICA / VENDEDOR (CUADRÍCULA ORIGINAL) ---
st.title("🎟️ Sistema de Rifas - Apoyo Estudiantil")

# Formulario
c1, c2, c3, c4 = st.columns(4)
with c1: cliente = st.text_input("👤 Nombre Cliente:")
with c2: tel = st.text_input("📞 WhatsApp:")
with c3: 
    v_opc = {v['nombre']: k for k, v in vendedores_datos.items()}
    v_sel = st.selectbox("🧤 Vendedor:", ["Seleccionar..."] + list(v_opc.keys()))
with c4: c_vend_v = st.text_input("🔑 Tu Clave:", type="password")

st.divider()

# Proceso
cant = st.number_input("¿Cuántos boletos?", min_value=1, value=1)

if len(st.session_state.seleccionados) == cant and cliente and v_sel != "Seleccionar...":
    v_id = v_opc[v_sel]
    if c_vend_v == vendedores_datos[v_id]['clave']:
        confirmar_venta(cliente, tel, st.session_state.seleccionados, v_id, v_sel)
    elif c_vend_v != "":
        st.error("🔑 Clave de vendedor incorrecta.")

col_a, col_l, _ = st.columns([2, 2, 6])
if col_a.button("🎲 Aleatorio"):
    libres = [n for n, v in datos_boletos.items() if v['estado'] == 'disponible']
    st.session_state.seleccionados = random.sample(libres, min(cant, len(libres)))
    st.rerun()
if col_l.button("🗑️ Limpiar"):
    st.session_state.seleccionados = []
    st.rerun()

st.write(f"Seleccionados: **{', '.join(st.session_state.seleccionados)}**")

# Cuadrícula de 10 columnas nativa (La que se ve bien en PC)
st.divider()
st.markdown("<style>div.stButton > button {width:100% !important;}</style>", unsafe_allow_html=True)

boletos_lista = sorted(datos_boletos.items())
cols_n = 10

for i in range(0, len(boletos_lista), cols_n):
    fila = boletos_lista[i : i + cols_n]
    columnas = st.columns(cols_n)
    for idx, (num, info) in enumerate(fila):
        with columnas[idx]:
            if info['estado'] == 'disponible':
                if num in st.session_state.seleccionados:
                    if st.button(f"🟡{num}", key=f"b_{num}"):
                        st.session_state.seleccionados.remove(num)
                        st.rerun()
                else:
                    des = len(st.session_state.seleccionados) >= cant
                    if st.button(num, key=f"b_{num}", disabled=des):
                        if cliente:
                            st.session_state.seleccionados.append(num)
                            st.rerun()
                        else:
                            st.warning("Nombre")
            else:
                st.button("❌", key=f"b_{num}", disabled=True)
# --- 7. CUADRÍCULA DE BOLETOS (10 COLUMNAS NATIVAS) ---
st.divider()

# CSS mínimo solo para ancho de botones, sin romper el layout
st.markdown("""
    <style>
    div.stButton > button {
        width: 100% !important;
    }
    </style>
    """, unsafe_allow_html=True)

boletos_lista = sorted(datos_boletos.items())
cols_n = 10 

for i in range(0, len(boletos_lista), cols_n):
    fila = boletos_lista[i : i + cols_n]
    columnas = st.columns(cols_n)
    
    for idx, (num, info) in enumerate(fila):
        with columnas[idx]:
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
