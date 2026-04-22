import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import random
import urllib.parse
import json
import tempfile
import os
import base6

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(
    page_title="Gestión de Rifa Pro",
    page_icon="🎟️",
    layout="wide",
    initial_sidebar_state="collapsed" 
)

# --- 1. CONEXIÓN A FIREBASE (GRADO INDUSTRIAL) ---
if not firebase_admin._apps:
    try:
        if "FIREBASE_BASE64" in st.secrets:
            # 1. Decodificar la base64 a un string JSON real
            base64_str = st.secrets["FIREBASE_BASE64"]
            decoded_bytes = base64.b64decode(base64_str)
            cred_dict = json.loads(decoded_bytes.decode("utf-8"))
            
            # 2. Reparar los saltos de línea (\n)
            if "private_key" in cred_dict:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            
            # 3. Crear archivo temporal para Firebase
            with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".json") as f:
                json.dump(cred_dict, f)
                temp_path = f.name
            
            # 4. Inicializar
            cred = credentials.Certificate(temp_path)
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://rifa-app-cfe3a-default-rtdb.firebaseio.com/' 
            })
            os.remove(temp_path)
        else:
            # Local
            cred = credentials.Certificate("credenciales.json")
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://rifa-app-cfe3a-default-rtdb.firebaseio.com/' 
            })
    except Exception as e:
        st.error(f"❌ Error de conexión definitiva: {e}")
        st.stop()
            
    except Exception as e:
        st.error(f"❌ Error crítico de conexión: {e}")
        st.stop()

# Referencias de Base de Datos
boletos_ref = db.reference('boletos')
config_ref = db.reference('configuracion')
vendedores_ref = db.reference('vendedores')

# --- 2. FUNCIONES DE APOYO ---
def inicializar_bd(total=100):
    nuevos_boletos = {}
    digitos = len(str(total - 1))
    for i in range(0, total):
        num_str = str(i).zfill(digitos) 
        nuevos_boletos[num_str] = {"estado": "disponible", "dueño": "", "telefono": "", "notificado": False, "vendedor": ""}
    boletos_ref.set(nuevos_boletos)
    
    default_msg = (
        "Hola {{nombre}}, gracias por colaborar a las rifas para apoyo estudiantil. "
        "Confirmamos la compra de tus boletos: {{boletos}}. "
        "La rifa se llevara a cabo el 21 de agosto en base a los ultimos 3 digitos del premio mayor de la loteria nacional mexicana. "
        "Puedes seguir el proceso en nuestras redes sociales: [Links Aquí]. Mucha suerte."
    )
    config_ref.set({"mensaje_template": default_msg, "precio_boleto": 50.0})

# Lectura inicial de datos
datos_crudos = boletos_ref.get()
config_datos = config_ref.get() or {}
vendedores_datos = vendedores_ref.get() or {}

if datos_crudos is None:
    inicializar_bd(100)
    st.rerun()

MENSAJE_TEMPLATE = config_datos.get('mensaje_template', "")
PRECIO_BOLETO = config_datos.get('precio_boleto', 0.0)

if 'seleccionados' not in st.session_state:
    st.session_state.seleccionados = []

# Procesar boletos (maneja listas o dicts de Firebase)
datos_boletos = {}
if isinstance(datos_crudos, list):
    for i, info in enumerate(datos_crudos):
        if info: datos_boletos[str(i).zfill(len(str(len(datos_crudos)-1)))] = info
else:
    datos_boletos = datos_crudos

# --- 3. MODALES ---
@st.dialog("📝 Editar Plantilla WhatsApp")
def ventana_mensaje():
    nuevo_texto = st.text_area("Cuerpo del mensaje:", value=MENSAJE_TEMPLATE, height=200)
    if st.button("💾 Guardar"):
        config_ref.update({"mensaje_template": nuevo_texto})
        st.rerun()

@st.dialog("🛒 Confirmar Venta")
def confirmar_venta(nombre, telefono, boletos, vendedor_id, vendedor_nombre):
    st.warning(f"¿Confirmar registro para {nombre}?")
    if st.button("✅ Confirmar y Registrar"):
        for b in boletos:
            boletos_ref.child(b).update({
                "estado":"ocupado", "dueño":nombre, "telefono":telefono, 
                "notificado":False, "vendedor": vendedor_nombre
            })
        ventas_actuales = vendedores_datos[vendedor_id].get('ventas', 0)
        vendedores_ref.child(vendedor_id).update({'ventas': ventas_actuales + len(boletos)})
        st.session_state.seleccionados = []
        st.rerun()

# --- 4. PANEL DE CONTROL (SIDEBAR) ---
with st.sidebar:
    st.title("⚙️ Administración")
    if st.toggle("Acceso Admin"):
        pw = st.text_input("Contraseña:", type="password")
        if pw == "1234":
            st.success("Autorizado")
            st.divider()
            
            # Progreso
            total_b = len(datos_boletos)
            vendidos = len([k for k, v in datos_boletos.items() if v['estado'] == 'ocupado'])
            st.metric("Boletos Vendidos", f"{vendidos}/{total_b}", f"{int((vendidos/total_b)*100)}%")
            
            # WhatsApp Pendientes
            st.subheader("📩 Pendientes")
            pendientes = [k for k, v in datos_boletos.items() if v['estado'] == 'ocupado' and not v.get('notificado')]
            if pendientes:
                # Agrupar por dueño para no mandar mil mensajes a la misma persona
                agrupados = {}
                for b in pendientes:
                    info = datos_boletos[b]
                    llave = (info['dueño'], info['telefono'])
                    if llave not in agrupados: agrupados[llave] = []
                    agrupados[llave].append(b)
                
                for (dueño, tel), nums in agrupados.items():
                    with st.expander(f"👤 {dueño}"):
                        if tel:
                            t = "".join(filter(str.isdigit, tel))
                            if len(t) == 10: t = "52" + t
                            m = MENSAJE_TEMPLATE.replace("{{nombre}}", dueño).replace("{{boletos}}", ", ".join(nums))
                            st.link_button("📲 Enviar", f"https://wa.me/{t}?text={urllib.parse.quote(m)}")
                        if st.button(f"Marcar como Enviado", key=f"env_{nums[0]}"):
                            for n in nums: boletos_ref.child(n).update({"notificado": True})
                            st.rerun()
            
            st.divider()
            if st.button("📧 Editar Mensaje"): ventana_mensaje()
            
            st.subheader("👥 Vendedores")
            v_nom = st.text_input("Nombre Nuevo:")
            v_cla = st.text_input("Clave Nueva:", type="password")
            if st.button("Añadir Vendedor"):
                vendedores_ref.push({'nombre': v_nom, 'clave': v_cla, 'ventas': 0})
                st.rerun()
                
            if st.button("🚨 REINICIAR RIFA"):
                inicializar_bd(len(datos_boletos))
                st.rerun()

# --- 5. INTERFAZ PÚBLICA / VENDEDORES ---
st.title("🎟️ Rifa Apoyo Estudiantil")
st.write("Selecciona los boletos y completa los datos para registrar la venta.")

c1, c2, c3, c4 = st.columns(4)
with c1: cliente = st.text_input("Cliente:")
with c2: tel = st.text_input("Teléfono:")
with c3: 
    v_nombres = {v['nombre']: k for k, v in vendedores_datos.items()}
    v_sel = st.selectbox("Vendedor:", ["Seleccionar..."] + list(v_nombres.keys()))
with c4: v_pass = st.text_input("Clave Vendedor:", type="password")

st.divider()

# Botones de acción
col_ran, col_del, _ = st.columns([2, 2, 6])
cant = st.number_input("Cantidad de boletos:", min_value=1, value=1)

if col_ran.button("🎲 Aleatorios"):
    libres = [n for n, v in datos_boletos.items() if v['estado'] == 'disponible' and n not in st.session_state.seleccionados]
    if len(libres) >= cant:
        st.session_state.seleccionados = random.sample(libres, cant)
        st.rerun()

if col_del.button("🗑️ Limpiar"):
    st.session_state.seleccionados = []
    st.rerun()

# Lógica de Venta
if len(st.session_state.seleccionados) >= cant and cliente and v_sel != "Seleccionar...":
    v_id = v_nombres[v_sel]
    if v_pass == vendedores_datos[v_id]['clave']:
        confirmar_venta(cliente, tel, st.session_state.seleccionados, v_id, v_sel)

# Cuadrícula
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
            st.button("❌", key=f"btn_{num}", disabled=True, help=f"Vendido por {info.get('vendedor')}")
