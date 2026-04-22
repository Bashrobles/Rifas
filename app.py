import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import random
import urllib.parse
import json

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(
    page_title="Gestión de Rifa Pro",
    page_icon="🎟️",
    layout="wide",
    initial_sidebar_state="collapsed" 
)

# --- 1. CONEXIÓN A FIREBASE ---

# --- 1. CONEXIÓN A FIREBASE ---
# --- 1. CONEXIÓN A FIREBASE ---
if not firebase_admin._apps:
    try:
        if "firebase_json" in st.secrets:
            # Obtenemos la info como diccionario
            cred_info = dict(st.secrets["firebase_json"])
            
            # 🛠️ TRUCO MAESTRO: Limpiar la llave de cualquier error de pegado
            # Reemplaza barras dobles por simples y asegura que \n sea un salto real
            raw_key = cred_info["private_key"]
            clean_key = raw_key.replace("\\n", "\n")
            cred_info["private_key"] = clean_key
            
            cred = credentials.Certificate(cred_info)
        else:
            # Local
            cred = credentials.Certificate("credenciales.json")
        
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://rifa-app-cfe3a-default-rtdb.firebaseio.com/' 
        })
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        st.stop()


boletos_ref = db.reference('boletos')
config_ref = db.reference('configuracion')
vendedores_ref = db.reference('vendedores')

# --- 2. FUNCIONES DE INICIALIZACIÓN ---
def inicializar_bd(total=1000):
    nuevos_boletos = {}
    digitos = len(str(total - 1))
    for i in range(0, total):
        num_str = str(i).zfill(digitos) 
        nuevos_boletos[num_str] = {"estado": "disponible", "dueño": "", "telefono": "", "notificado": False, "vendedor": ""}
    boletos_ref.set(nuevos_boletos)
    
    # NUEVA PLANTILLA ACTUALIZADA SEGÚN TU SOLICITUD
    default_msg = (
        "Hola {{nombre}}, gracias por colaborar a las rifas para apoyo estudiantil. "
        "Confirmamos la compra de tus boletos: {{boletos}}. "
        "La rifa se llevara a cabo el 21 de agosto en base a los ultimos 3 digitos del premio mayor de la loteria nacional mexicana. "
        "Puedes seguir el proceso y ver los resultados en nuestras redes sociales: "
        "Facebook: [LINK DE TU PÁGINA] "
        "Instagram: https://www.instagram.com/rifas_cucei?utm_source=qr&igsh=ZjRpaTA1b3VwanJ5 "
        "Mucha suerte."
    )
    
    config_ref.set({
        "mensaje_template": default_msg,
        "precio_boleto": 50.0
    })

# Carga de Datos
datos_crudos = boletos_ref.get()
config_datos = config_ref.get()
vendedores_datos = vendedores_ref.get() or {}

if not datos_crudos:
    # Por defecto inicia con 100 si la base está vacía
    inicializar_bd(100)
    st.rerun()

MENSAJE_TEMPLATE = config_datos.get('mensaje_template', "")
PRECIO_BOLETO = config_datos.get('precio_boleto', 0.0)

if 'seleccionados' not in st.session_state:
    st.session_state.seleccionados = []

# Procesamiento de formato de boletos
datos_boletos = {}
if isinstance(datos_crudos, list):
    for i, info in enumerate(datos_crudos):
        if info is not None: datos_boletos[str(i).zfill(len(str(len(datos_crudos)-1)))] = info
elif isinstance(datos_crudos, dict):
    datos_boletos = datos_crudos

# --- 3. DIÁLOGOS (MODALES) ---
@st.dialog("📝 Editar Plantilla de Mensaje")
def ventana_mensaje():
    nuevo_texto = st.text_area("Cuerpo del mensaje:", value=MENSAJE_TEMPLATE, height=200)
    if st.button("💾 Guardar Plantilla"):
        config_ref.update({"mensaje_template": nuevo_texto})
        st.success("Guardado correctamente.")
        st.rerun()

@st.dialog("🛒 Confirmar Venta")
def confirmar_venta(nombre, telefono, boletos, vendedor_id, vendedor_nombre):
    st.write(f"**Cliente:** {nombre}")
    st.write(f"**Boletos:** {', '.join(sorted(boletos))}")
    st.write(f"**Vendedor:** {vendedor_nombre}")
    
    col_si, col_no = st.columns(2)
    if col_si.button("✅ Registrar", use_container_width=True):
        for b in boletos:
            boletos_ref.child(b).update({
                "estado":"ocupado", "dueño":nombre, "telefono":telefono, 
                "notificado":False, "vendedor": vendedor_nombre
            })
        ventas_actuales = vendedores_datos[vendedor_id].get('ventas', 0)
        vendedores_ref.child(vendedor_id).update({'ventas': ventas_actuales + len(boletos)})
        st.session_state.seleccionados = []
        st.rerun()
    if col_no.button("❌ Cancelar", use_container_width=True):
        st.session_state.seleccionados = []
        st.rerun()

# --- 4. PANEL ADMINISTRADOR ---
with st.sidebar:
    st.header("⚙️ Panel Admin")
    if st.toggle("Desbloquear Opciones"):
        password = st.text_input("Clave Maestra:", type="password", autocomplete="new-password")
        
        if password == "1234":
            st.success("Acceso Autorizado")
            st.divider()

            # --- 📊 BARRA DE PROGRESO ---
            total_b = len(datos_boletos)
            ocupados_list = [k for k, v in datos_boletos.items() if v['estado'] == 'ocupado']
            vendidos_n = len(ocupados_list)
            porcentaje = (vendidos_n / total_b) if total_b > 0 else 0
            
            st.subheader("📈 Avance de Ventas")
            st.progress(porcentaje)
            st.write(f"Progreso: **{porcentaje*100:.1f}%** ({vendidos_n}/{total_b})")
            st.divider()

            # --- 📩 1. PENDIENTES WHATSAPP ---
            st.subheader("📩 Mensajes Pendientes")
            pendientes = {k: v for k, v in datos_boletos.items() if v['estado'] == 'ocupado' and not v.get('notificado', False)}
            if pendientes:
                agrupados = {}
                for num, info in pendientes.items():
                    llave = (info['dueño'], info['telefono'])
                    if llave not in agrupados: agrupados[llave] = []
                    agrupados[llave].append(num)
                
                for (comprador, tel), lista in agrupados.items():
                    llave_base = f"{comprador}_{tel}_{lista[0]}"
                    with st.expander(f"👤 {comprador} ({len(lista)})"):
                        if tel:
                            t_limpio = "".join(filter(str.isdigit, tel))
                            if len(t_limpio) == 10: t_limpio = "52" + t_limpio
                            msj = MENSAJE_TEMPLATE.replace("{{nombre}}", comprador).replace("{{boletos}}", ", ".join(lista))
                            st.link_button("📲 Enviar WhatsApp", f"https://wa.me/{t_limpio}?text={urllib.parse.quote(msj)}")
                        
                        col_e, col_c = st.columns(2)
                        if col_e.button("✅ Enviado", key=f"btn_env_{llave_base}"):
                            for b in lista: boletos_ref.child(b).update({"notificado": True})
                            st.rerun()
                        if col_c.button("🚫 Cancelar", key=f"btn_can_{llave_base}", type="primary"):
                            for b in lista: boletos_ref.child(b).update({"estado":"disponible", "dueño":"", "vendedor":"", "telefono": "", "notificado": False})
                            st.rerun()
            else:
                st.info("No hay pendientes.")
            st.divider()

            # --- 🔍 2. BUSCAR / LIBERAR ---
            st.subheader("🔍 Gestión de Números")
            if ocupados_list:
                b_rev = st.selectbox("Elegir boleto vendido:", sorted(ocupados_list, key=int))
                info_b = datos_boletos[b_rev]
                st.write(f"Dueño: {info_b['dueño']} | Vendedor: {info_b.get('vendedor', 'N/A')}")
                if st.button("🔓 Liberar Número", type="primary"):
                    boletos_ref.child(b_rev).update({"estado": "disponible", "dueño": "", "telefono": "", "notificado": False, "vendedor": ""})
                    st.rerun()
            st.divider()

            # --- 👥 3. VENDEDORES ---
            st.subheader("👥 Vendedores")
            with st.expander("➕ Nuevo Vendedor"):
                n_vend = st.text_input("Nombre:")
                c_vend = st.text_input("Clave de acceso:", type="password")
                if st.button("Crear"):
                    vendedores_ref.push({'nombre': n_vend, 'clave': c_vend, 'ventas': 0})
                    st.rerun()
            
            if vendedores_datos:
                with st.expander("🗑️ Eliminar Vendedor"):
                    v_opciones_del = {v['nombre']: k for k, v in vendedores_datos.items()}
                    v_a_borrar = st.selectbox("Seleccionar para borrar:", options=list(v_opciones_del.keys()))
                    if st.button("⚠️ Borrar Definitivamente"):
                        vendedores_ref.child(v_opciones_del[v_a_borrar]).delete()
                        st.rerun()

                st.write("**Corte de Caja:**")
                for vid, vinfo in vendedores_datos.items():
                    st.write(f"- {vinfo['nombre']}: {vinfo.get('ventas', 0)} vendidos")
                
                if st.button("💰 Resetear Corte (Cero)"):
                    for vid in vendedores_datos: vendedores_ref.child(vid).update({'ventas': 0})
                    st.rerun()
            st.divider()

            # --- 4. EXTRAS ---
            if st.button("📧 Editar Mensaje", use_container_width=True):
                ventana_mensaje()
            
            st.subheader("📢 Difusión")
            contactos = {v['telefono']: v['dueño'] for v in datos_boletos.values() if v['estado'] == 'ocupado' and v['telefono']}
            if contactos:
                csv = "Name,Phone\n" + "\n".join([f"{n},{t}" for t, n in contactos.items()])
                st.download_button("📥 Descargar Contactos CSV", csv, "contactos.csv", "text/csv", use_container_width=True)
            
            st.divider()
            st.subheader("⚠️ Zona Peligrosa")
            nuevo_t = st.number_input("Cantidad total:", value=len(datos_boletos))
            precio_t = st.number_input("Precio:", value=PRECIO_BOLETO)
            if st.button("🚨 REINICIAR TODO"):
                inicializar_bd(nuevo_t)
                config_ref.update({"precio_boleto": precio_t})
                st.session_state.seleccionados = []
                st.rerun()
        elif password != "":
            st.error("Clave Incorrecta")

# --- 5. INTERFAZ VENDEDOR ---
st.title("🎟️ Sistema de Rifas - Apoyo Estudiantil")

# Fila superior de datos
c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 1.2])
with c1: n_comp = st.text_input("👤 Nombre Cliente:")
with c2: t_comp = st.text_input("📞 WhatsApp (10 dígitos):")
with c3: 
    v_opc = {v['nombre']: k for k, v in vendedores_datos.items()}
    v_sel = st.selectbox("🧤 Vendedor:", ["Seleccionar..."] + list(v_opc.keys()))
with c4: c_vend_v = st.text_input("🔑 Clave Vendedor:", type="password")

st.divider()

# Proceso de Selección
cant = st.number_input("🎟️ ¿Cuántos boletos?", min_value=1, max_value=len(datos_boletos), value=1)

if len(st.session_state.seleccionados) == cant:
    if not n_comp or v_sel == "Seleccionar...":
        st.error("⚠️ Falta el nombre del cliente o el vendedor.")
    else:
        v_id = v_opc[v_sel]
        if c_vend_v == vendedores_datos[v_id]['clave']:
            confirmar_venta(n_comp, t_comp, st.session_state.seleccionados, v_id, v_sel)
        else:
            st.error("🔑 Clave de vendedor incorrecta.")

# Botones de ayuda
col_a, col_l, _ = st.columns([2, 2, 6])
if col_a.button("🎲 Selección Aleatoria"):
    libres = [n for n, i in datos_boletos.items() if i['estado'] == 'disponible' and n not in st.session_state.seleccionados]
    if len(libres) >= (cant - len(st.session_state.seleccionados)):
        st.session_state.seleccionados.extend(random.sample(libres, cant - len(st.session_state.seleccionados)))
        st.rerun()
if col_l.button("🗑️ Limpiar Selección"):
    st.session_state.seleccionados = []
    st.rerun()

# Cuadrícula de Boletos
cols = st.columns(10)
for i, (num, info) in enumerate(sorted(datos_boletos.items())):
    with cols[i % 10]:
        if info['estado'] == 'disponible':
            if num in st.session_state.seleccionados:
                if st.button(f"🟡 {num}", key=f"b_{num}"):
                    st.session_state.seleccionados.remove(num)
                    st.rerun()
            else:
                if st.button(f"{num}", key=f"b_{num}", disabled=len(st.session_state.seleccionados) >= cant):
                    if n_comp:
                        st.session_state.seleccionados.append(num)
                        st.rerun()
                    else:
                        st.warning("Escribe el nombre primero")
        else:
            st.button("❌", key=f"b_{num}", disabled=True, help=f"Vendido por: {info.get('vendedor', 'N/A')}")
