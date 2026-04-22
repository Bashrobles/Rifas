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

datos_boletos = {}
if isinstance(datos_crudos, list):
    for i, info in enumerate(datos_crudos):
        if info: datos_boletos[str(i).zfill(len(str(len(datos_crudos)-1)))] = info
else:
    datos_boletos = datos_crudos or {}

# --- 4. DIÁLOGOS ---
@st.dialog("🛒 Confirmar Venta")
def confirmar_venta(nombre, telefono, boletos, v_id, v_nombre):
    st.write(f"**Cliente:** {nombre}")
    st.write(f"**Boletos:** {', '.join(sorted(boletos))}")
    st.write(f"**Total a cobrar:** ${len(boletos)*PRECIO_BOLETO}")
    if st.button("✅ Confirmar Pago y Registrar", use_container_width=True):
        for b in boletos:
            boletos_ref.child(b).update({
                "estado":"ocupado", "dueño":nombre, "telefono":telefono, 
                "notificado":False, "vendedor": v_nombre
            })
        v_actuales = vendedores_datos[v_id].get('ventas', 0)
        vendedores_ref.child(v_id).update({'ventas': v_actuales + len(boletos)})
        st.session_state.seleccionados = []
        st.rerun()

# --- 5. PANEL ADMINISTRADOR COMPLETO ---
with st.sidebar:
    st.header("⚙️ Panel de Control")
    if st.toggle("Desbloquear Modo Admin"):
        pwd = st.text_input("Clave Maestra:", type="password")
        if pwd == st.secrets.get("ADMIN_PASSWORD", "1234"):
            st.success("Acceso Autorizado")
            
            # --- PROGRESO ---
            ocupados_list = [k for k, v in datos_boletos.items() if v['estado'] == 'ocupado']
            total_n = len(datos_boletos)
            progreso = len(ocupados_list)/total_n if total_n > 0 else 0
            st.subheader("📈 Avance")
            st.progress(progreso)
            st.write(f"Ventas: {len(ocupados_list)}/{total_n} (${len(ocupados_list)*PRECIO_BOLETO})")
            
            # --- WHATSAPP PENDIENTES ---
            st.subheader("📩 Mensajes Pendientes")
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
                            st.link_button("📲 Mandar WhatsApp", f"https://wa.me/{t}?text={urllib.parse.quote(msj)}", use_container_width=True)
                        
                        c_env, c_can = st.columns(2)
                        if c_env.button("✅ Enviado", key=f"not_{lista[0]}"):
                            for b in lista: boletos_ref.child(b).update({"notificado": True})
                            st.rerun()
                        if c_can.button("🚫 Cancelar", key=f"can_{lista[0]}", type="primary"):
                            for b in lista: boletos_ref.child(b).update({"estado":"disponible","dueño":"","telefono":"","vendedor":"","notificado":False})
                            st.rerun()
            else:
                st.info("No hay mensajes pendientes.")
            
            # --- BUSCADOR POR BOLETO ---
            st.subheader("🔍 Buscar Comprador")
            if ocupados_list:
                b_sel_admin = st.selectbox("Elegir boleto vendido:", sorted(ocupados_list, key=int))
                info_admin = datos_boletos[b_sel_admin]
                st.info(f"👤 **{info_admin['dueño']}**\n\n📞 **{info_admin['telefono']}**")
                if st.button("🔓 Liberar este número específico", type="primary"):
                    boletos_ref.child(b_sel_admin).update({"estado":"disponible","dueño":"","telefono":"","vendedor":"","notificado":False})
                    st.rerun()

            # --- GESTIÓN VENDEDORES ---
            st.subheader("👥 Equipo")
            with st.expander("➕ Añadir Vendedor"):
                nv = st.text_input("Nombre:")
                cv = st.text_input("Clave:", type="password")
                if st.button("Crear"):
                    vendedores_ref.push({'nombre': nv, 'clave': cv, 'ventas': 0})
                    st.rerun()
            
            if vendedores_datos:
                with st.expander("🗑️ Eliminar Vendedor"):
                    v_opc_del = {v['nombre']: k for k, v in vendedores_datos.items()}
                    v_target = st.selectbox("Selecciona vendedor a eliminar:", list(v_opc_del.keys()))
                    if st.button("Confirmar Eliminación", type="primary"):
                        vendedores_ref.child(v_opc_del[v_target]).delete()
                        st.rerun()

                st.write("**Corte de Caja:**")
                for vid, vinfo in vendedores_datos.items():
                    st.write(f"- {vinfo['nombre']}: {vinfo.get('ventas', 0)}")
                if st.button("💰 Resetear Corte a Cero"):
                    for vid in vendedores_datos: vendedores_ref.child(vid).update({'ventas': 0})
                    st.rerun()

            # --- EXPORTAR Y PRECIO ---
            st.subheader("📊 Extras")
            
            # Lógica para CSV completo
            todos_vendidos = {}
            for n, i in datos_boletos.items():
                if i['estado'] == 'ocupado':
                    k = (i['dueño'], i['telefono'])
                    if k not in todos_vendidos: todos_vendidos[k] = []
                    todos_vendidos[k].append(n)
            
            csv_final = "Nombre,Telefono,Boletos\n"
            for (n, t), b_list in todos_vendidos.items():
                csv_final += f"{n},{t},{' '.join(b_list)}\n"
                
            st.download_button("📥 Descargar CSV de Ventas", csv_final, "ventas_rifa.csv")

            # Precio
            np = st.number_input("Nuevo Precio por boleto:", value=float(PRECIO_BOLETO))
            if st.button("Guardar Precio"):
                config_ref.update({"precio_boleto": np})
                st.rerun()

            if st.button("🚨 REINICIAR TODO (PELIGRO)", type="primary"):
                boletos_ref.delete()
                st.rerun()

# --- 6. INTERFAZ VENDEDOR ---
st.title("🎟️ Sistema de Rifas - Apoyo Estudiantil")
st.write(f"**Precio: ${PRECIO_BOLETO} MXN**")

# Formulario de datos
c1, c2, c3, c4 = st.columns(4)
with c1: n_comp = st.text_input("👤 Cliente:")
with c2: t_comp = st.text_input("📞 WhatsApp:")
with c3: 
    v_nombres = {v['nombre']: k for k, v in vendedores_datos.items()}
    v_sel = st.selectbox("🧤 Vendedor:", ["Seleccionar..."] + list(v_nombres.keys()))
with c4: c_vend_v = st.text_input("🔑 Tu Clave:", type="password")

st.divider()

# --- NUEVA SECCIÓN: SELECCIÓN DE BOLETOS ---
col_cant, col_manual = st.columns([2, 3])

with col_cant:
    cant = st.number_input("🎟️ ¿Cuántos boletos?", min_value=1, value=1)

with col_manual:
    # Ingreso manual de número
    boleto_manual = st.text_input("🔢 Ingresar número manualmente:", placeholder="Ej: 025")
    if st.button("➕ Agregar Número"):
        # Validamos que el número exista en nuestra base
        if boleto_manual in datos_boletos:
            info_m = datos_boletos[boleto_manual]
            if info_m['estado'] == 'disponible':
                if len(st.session_state.seleccionados) < cant:
                    if boleto_manual not in st.session_state.seleccionados:
                        st.session_state.seleccionados.append(boleto_manual)
                        st.success(f"Número {boleto_manual} agregado")
                        st.rerun()
                    else:
                        st.warning("Ese número ya está en tu lista")
                else:
                    st.error(f"Ya alcanzaste el límite de {cant} boletos")
            else:
                st.error("Ese número ya está vendido")
        else:
            st.error("El número no existe")

# Botones de ayuda rápida
ca, cl, _ = st.columns([2, 2, 6])
if ca.button("🎲 Aleatorio"):
    libres = [n for n, v in datos_boletos.items() if v['estado'] == 'disponible']
    st.session_state.seleccionados = random.sample(libres, min(cant, len(libres)))
    st.rerun()
if cl.button("🗑️ Limpiar"):
    st.session_state.seleccionados = []
    st.rerun()

st.write(f"Seleccionados: **{', '.join(sorted(st.session_state.seleccionados))}**")

# Lógica de venta automática
if len(st.session_state.seleccionados) == cant and n_comp and v_sel != "Seleccionar...":
    vid = v_nombres[v_sel]
    if c_vend_v == vendedores_datos[vid]['clave']:
        confirmar_venta(n_comp, t_comp, st.session_state.seleccionados, vid, v_sel)
    elif c_vend_v != "":
        st.error("🔑 Clave de vendedor incorrecta.")

# --- 7. CUADRÍCULA DE BOLETOS (VERSIÓN DEFINITIVA Y LIGERA) ---
st.divider()

# 1. Estilos para los boletos
st.markdown("""
    <style>
    .contenedor-rifa {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: center;
    }
    .boleto-link {
        text-decoration: none;
    }
    .boleto-btn {
        width: 70px;
        height: 50px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 8px;
        border: 1px solid #444;
        font-weight: bold;
        cursor: pointer;
        transition: 0.3s;
        background-color: #0e1117;
        color: white;
    }
    .boleto-btn:hover {
        border-color: #ff4b4b;
        transform: scale(1.05);
    }
    .disponible { background-color: #1e2329; }
    .seleccionado { background-color: #ffd700; color: black; border-color: #ffd700; }
    .vendido { background-color: #333; color: #777; cursor: not-allowed; border: none; }
    </style>
    """, unsafe_allow_html=True)

# 2. Render de boletos con botones nativos de Streamlit para que la lógica siga funcionando
# Pero usaremos un contenedor para que fluyan
boletos_lista = sorted(datos_boletos.items())

# Usamos un contenedor de Streamlit para meter los botones
# IMPORTANTE: No usamos columns() aquí, solo un loop normal
with st.container():
    # Este estilo de 'flex' hará que se acomoden solos
    st.write('<div class="contenedor-rifa">', unsafe_allow_html=True)
    
    # Para que Streamlit no se pierda, usaremos un loop normal pero con botones de ancho fijo
    # El truco es 'use_container_width=False' y meterlos en un bloque CSS
    cols = st.columns([1]*12 if not st.sidebar.state == "expanded" else [1]*8) # Ajuste visual básico

    # MEJOR AÚN: Vamos a usar el diseño nativo pero con un ancho fijo de columna pequeña
    # Esto evita el error de la imagen anterior
    columnas_fluidas = st.columns(10) # Forzamos 10 en PC, en Celular Streamlit las apilará
    
    for i, (num, info) in enumerate(boletos_lista):
        with columnas_fluidas[i % 10]:
            if info['estado'] == 'disponible':
                if num in st.session_state.seleccionados:
                    if st.button(f"🟡{num}", key=f"n_{num}", use_container_width=True):
                        st.session_state.seleccionados.remove(num)
                        st.rerun()
                else:
                    des = len(st.session_state.seleccionados) >= cant
                    if st.button(num, key=f"n_{num}", disabled=des, use_container_width=True):
                        if cliente:
                            st.session_state.seleccionados.append(num)
                            st.rerun()
                        else:
                            st.warning("Nombre")
            else:
                st.button("❌", key=f"n_{num}", disabled=True, use_container_width=True)
