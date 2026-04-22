import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import tempfile
import os
import random
import urllib.parse

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Rifa Apoyo Estudiantil",
    page_icon="🎟️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 1. CONEXIÓN A FIREBASE (VERSIÓN BLINDADA) ---
# --- 1. CONEXIÓN A FIREBASE (VERSIÓN SIN ARCHIVOS) ---
# --- 1. CONEXIÓN A FIREBASE (VERSIÓN DIRECTA) ---
if not firebase_admin._apps:
    try:
        if "FIREBASE_RAW_JSON" in st.secrets:
            # Cargamos el string de los secrets
            cred_dict = json.loads(st.secrets["FIREBASE_RAW_JSON"])
            
            # Limpieza básica por si el copiado agrega basura
            if "private_key" in cred_dict:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            
            # Inicialización directa con el diccionario
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://rifa-app-cfe3a-default-rtdb.firebaseio.com/'
            })
        else:
            st.error("❌ No se encontró el secreto FIREBASE_RAW_JSON.")
            st.stop()
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        st.stop()
# Referencias
boletos_ref = db.reference('boletos')
config_ref = db.reference('configuracion')
vendedores_ref = db.reference('vendedores')

# --- 2. CARGA DE DATOS ---
datos_crudos = boletos_ref.get()
config_datos = config_ref.get() or {}
vendedores_datos = vendedores_ref.get() or {}

# Si la base de datos está vacía, inicializar
if datos_crudos is None:
    def inicializar_bd(total=100):
        nuevos_boletos = {}
        digitos = len(str(total - 1))
        for i in range(0, total):
            num_str = str(i).zfill(digitos)
            nuevos_boletos[num_str] = {"estado": "disponible", "dueño": "", "telefono": "", "notificado": False, "vendedor": ""}
        boletos_ref.set(nuevos_boletos)
        
        msg = (
            "Hola {{nombre}}, gracias por colaborar a las rifas para apoyo estudiantil. "
            "Confirmamos tus boletos: {{boletos}}. La rifa se llevara a cabo el 21 de agosto "
            "en base a los ultimos 3 digitos del premio mayor de la loteria nacional mexicana. "
            "Sigue los resultados en: Facebook: [LINK] e Instagram: [USUARIO]. Suerte."
        )
        config_ref.set({"mensaje_template": msg, "precio_boleto": 50.0})
    
    inicializar_bd(100) # Inicializa con 100 por defecto
    st.rerun()

MENSAJE_TEMPLATE = config_datos.get('mensaje_template', "")
PRECIO_BOLETO = config_datos.get('precio_boleto', 0.0)

if 'seleccionados' not in st.session_state:
    st.session_state.seleccionados = []

# Procesar formato de boletos (Firebase puede devolver lista o dict)
datos_boletos = {}
if isinstance(datos_crudos, list):
    for i, info in enumerate(datos_crudos):
        if info: datos_boletos[str(i).zfill(len(str(len(datos_crudos)-1)))] = info
else:
    datos_boletos = datos_crudos

# --- 3. DIÁLOGOS ---
@st.dialog("🛒 Confirmar Venta")
def confirmar_venta(nombre, telefono, boletos, v_id, v_nombre):
    st.write(f"**Cliente:** {nombre}")
    st.write(f"**Números:** {', '.join(boletos)}")
    st.write(f"**Vendedor:** {v_nombre}")
    if st.button("✅ Registrar Venta Ahora", use_container_width=True):
        for b in boletos:
            boletos_ref.child(b).update({
                "estado":"ocupado", "dueño":nombre, "telefono":telefono, 
                "notificado":False, "vendedor": v_nombre
            })
        v_ventas = vendedores_datos[v_id].get('ventas', 0)
        vendedores_ref.child(v_id).update({'ventas': v_ventas + len(boletos)})
        st.session_state.seleccionados = []
        st.rerun()

# --- 4. PANEL DE CONTROL (SIDEBAR) ---
with st.sidebar:
    st.header("⚙️ Admin")
    if st.toggle("Modo Admin"):
        password = st.text_input("Clave:", type="password")
        correct_password = st.secrets.get("ADMIN_PASSWORD", "clave_temporal_99")
        if password == correct_password:
            st.success("Acceso concedido")
            
            # Métricas
            total = len(datos_boletos)
            vendidos = len([k for k, v in datos_boletos.items() if v['estado'] == 'ocupado'])
            st.metric("Ventas", f"{vendidos}/{total}", f"{int((vendidos/total)*100)}%")
            
            # Pendientes WhatsApp
            st.subheader("📲 Pendientes")
            pendientes = [k for k, v in datos_boletos.items() if v['estado'] == 'ocupado' and not v.get('notificado')]
            if pendientes:
                agrupados = {}
                for b in pendientes:
                    info = datos_boletos[b]
                    llave = (info['dueño'], info['telefono'])
                    if llave not in agrupados: agrupados[llave] = []
                    agrupados[llave].append(b)
                
                for (dueño, tel), nums in agrupados.items():
                    with st.expander(f"👤 {dueño}"):
                        if tel:
                            t_clean = "".join(filter(str.isdigit, tel))
                            if len(t_clean) == 10: t_clean = "52" + t_clean
                            texto = MENSAJE_TEMPLATE.replace("{{nombre}}", dueño).replace("{{boletos}}", ", ".join(nums))
                            st.link_button("Enviar WhatsApp", f"https://wa.me/{t_clean}?text={urllib.parse.quote(texto)}")
                        if st.button("✅ Notificado", key=f"notif_{nums[0]}"):
                            for n in nums: boletos_ref.child(n).update({"notificado": True})
                            st.rerun()
            
            st.divider()
            if st.button("🚨 REINICIAR TODO"):
                boletos_ref.delete()
                st.rerun()

# --- 5. INTERFAZ DE VENTAS ---
st.title("🎟️ Rifa Apoyo Estudiantil")

col1, col2, col3, col4 = st.columns(4)
with col1: cliente = st.text_input("Nombre del Cliente:")
with col2: telefono = st.text_input("WhatsApp (10 dígitos):")
with col3: 
    v_nombres = {v['nombre']: k for k, v in vendedores_datos.items()}
    vendedor_sel = st.selectbox("Tu Nombre (Vendedor):", ["Seleccionar..."] + list(v_nombres.keys()))
with col4: v_pass = st.text_input("Tu Clave:", type="password")

st.divider()

# Botones Rápidos
c_ran, c_lim, _ = st.columns([2, 2, 6])
cant = st.number_input("Cantidad de boletos:", min_value=1, value=1)

if c_ran.button("🎲 Números Aleatorios"):
    libres = [n for n, v in datos_boletos.items() if v['estado'] == 'disponible' and n not in st.session_state.seleccionados]
    if len(libres) >= cant:
        st.session_state.seleccionados = random.sample(libres, cant)
        st.rerun()

if c_lim.button("🗑️ Limpiar Selección"):
    st.session_state.seleccionados = []
    st.rerun()

# Confirmación de Venta
if len(st.session_state.seleccionados) >= cant and cliente and vendedor_sel != "Seleccionar...":
    v_id = v_nombres[vendedor_sel]
    if v_pass == vendedores_datos[v_id]['clave']:
        confirmar_venta(cliente, telefono, st.session_state.seleccionados, v_id, vendedor_sel)

# Render de Boletos
cols = st.columns(10)
for i, (num, info) in enumerate(sorted(datos_boletos.items())):
    with cols[i % 10]:
        if info['estado'] == 'disponible':
            if num in st.session_state.seleccionados:
                if st.button(f"🟡 {num}", key=f"btn_{num}"):
                    st.session_state.seleccionados.remove(num)
                    st.rerun()
            else:
                if st.button(f"{num}", key=f"btn_{num}", disabled=len(st.session_state.seleccionados) >= cant):
                    if cliente:
                        st.session_state.seleccionados.append(num)
                        st.rerun()
                    else:
                        st.error("Escribe el nombre")
        else:
            st.button("❌", key=f"btn_{num}", disabled=True, help=f"Vendido por: {info.get('vendedor')}")
