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

if 'seleccionados' not in st.session_state: st.session_state.seleccionados = []
if 'promo_activa' not in st.session_state: st.session_state.promo_activa = False

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
    if con_promo: st.write(f"**Subtotal:** ${subtotal} | **Descuento Promo:** -$50")
    st.write(f"### **Total a cobrar:** ${total}")
    
    if st.button("✅ Registrar Venta", use_container_width=True):
        # Calculamos cuánto vale cada boleto realmente en esta venta
        ingreso_por_boleto = total / len(boletos)
        
        for b in boletos:
            boletos_ref.child(b).update({
                "estado":"ocupado", "dueño":nombre, "telefono":telefono, 
                "notificado":False, "vendedor": v_nombre, "ingreso": ingreso_por_boleto
            })
            
        v_act_bol = vendedores_datos[v_id].get('ventas', 0)
        v_act_ing = vendedores_datos[v_id].get('ingresos', v_act_bol * PRECIO_BOLETO) # Fallback para datos viejos
        
        # Guardamos boletos vendidos Y el dinero que ingresó
        vendedores_ref.child(v_id).update({
            'ventas': v_act_bol + len(boletos),
            'ingresos': v_act_ing + total
        })
        
        st.session_state.seleccionados = []
        st.session_state.promo_activa = False
        st.rerun()

# --- 5. PANEL ADMINISTRADOR ---
with st.sidebar:
    st.header("⚙️ Panel de Control")
    if st.toggle("Desbloquear Modo Admin"):
        pwd = st.text_input("Clave Maestra:", type="password")
        if pwd == st.secrets.get("ADMIN_PASSWORD", "1234"):
            st.success("Autorizado")
            
            # PROGRESO
            ocupados_list = [k for k, v in datos_boletos.items() if v['estado'] == 'ocupado']
            total_n = len(datos_boletos)
            st.progress(len(ocupados_list)/total_n if total_n > 0 else 0)
            
            # Total de dinero global (sumando todos los boletos para ser exactos con las promos)
            dinero_global = sum([v.get('ingreso', PRECIO_BOLETO) for k, v in datos_boletos.items() if v['estado'] == 'ocupado'])
            st.write(f"Ventas: {len(ocupados_list)}/{total_n} (${dinero_global:,.2f})")
            
            # --- FUNCIÓN RESTAURADA: EDITOR DE PLANTILLA ---
            st.subheader("📝 Plantilla WhatsApp")
            with st.expander("Editar Mensaje"):
                st.caption("Usa {{nombre}} y {{boletos}} como variables.")
                nueva_plantilla = st.text_area("Cuerpo del mensaje:", value=MENSAJE_TEMPLATE, height=150)
                if st.button("Guardar Plantilla"):
                    config_ref.update({"mensaje_template": nueva_plantilla})
                    st.success("Plantilla actualizada exitosamente")
                    st.rerun()

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
                            
                        # CANCELAR LOTE RESTANDO DINERO EXACTO
                        if c_can.button("🚫 Cancelar Lote", key=f"can_{lista[0]}", type="primary"):
                            nom_vendedor = datos_boletos[lista[0]].get('vendedor', '')
                            v_id_target = next((vid for vid, v in vendedores_datos.items() if v.get('nombre') == nom_vendedor), None)
                            
                            if v_id_target:
                                v_act_bol = vendedores_datos[v_id_target].get('ventas', 0)
                                v_act_ing = vendedores_datos[v_id_target].get('ingresos', v_act_bol * PRECIO_BOLETO)
                                dinero_a_restar = sum([datos_boletos[b].get('ingreso', PRECIO_BOLETO) for b in lista])
                                
                                vendedores_ref.child(v_id_target).update({
                                    'ventas': max(0, v_act_bol - len(lista)),
                                    'ingresos': max(0, v_act_ing - dinero_a_restar)
                                })
                            
                            for b in lista: 
                                boletos_ref.child(b).update({"estado":"disponible","dueño":"","telefono":"","notificado":False,"vendedor":"","ingreso":0})
                            st.rerun()

            # BUSCADOR POR BOLETO
            st.subheader("🔍 Buscar")
            if ocupados_list:
                b_adm = st.selectbox("Elegir boleto vendido:", sorted(ocupados_list, key=int))
                info_a = datos_boletos[b_adm]
                st.info(f"👤 **{info_a['dueño']}**\n📞 **{info_a['telefono']}**")
                
                # LIBERAR UNO SOLO RESTANDO DINERO EXACTO
                if st.button("🔓 Liberar Número"):
                    nom_vendedor = info_a.get('vendedor', '')
                    v_id_target = next((vid for vid, v in vendedores_datos.items() if v.get('nombre') == nom_vendedor), None)
                    
                    if v_id_target:
                        v_act_bol = vendedores_datos[v_id_target].get('ventas', 0)
                        v_act_ing = vendedores_datos[v_id_target].get('ingresos', v_act_bol * PRECIO_BOLETO)
                        dinero_a_restar = info_a.get('ingreso', PRECIO_BOLETO)
                        
                        vendedores_ref.child(v_id_target).update({
                            'ventas': max(0, v_act_bol - 1),
                            'ingresos': max(0, v_act_ing - dinero_a_restar)
                        })

                    boletos_ref.child(b_adm).update({"estado":"disponible","dueño":"","telefono":"","vendedor":"","notificado":False,"ingreso":0})
                    st.rerun()

            # GESTIÓN DE EQUIPO
            st.subheader("👥 Vendedores")
            with st.expander("Añadir / Eliminar"):
                nv = st.text_input("Nombre:")
                cv = st.text_input("Clave:", type="password")
                if st.button("Crear"):
                    vendedores_ref.push({'nombre': nv, 'clave': cv, 'ventas': 0, 'ingresos': 0})
                    st.rerun()
                st.divider()
                if vendedores_datos:
                    v_del_map = {v['nombre']: k for k, v in vendedores_datos.items()}
                    target = st.selectbox("Eliminar vendedor:", list(v_del_map.keys()))
                    if st.button("🗑️ Eliminar Definitivamente", type="primary"):
                        vendedores_ref.child(v_del_map[target]).delete()
                        st.rerun()

            # CORTE DE CAJA (MUESTRA INGRESOS REALES)
            st.subheader("💰 Corte de Caja")
            if vendedores_datos:
                for vid, vinfo in vendedores_datos.items():
                    v_ventas = vinfo.get('ventas', 0)
                    v_ingresos = vinfo.get('ingresos', v_ventas * PRECIO_BOLETO) # Fallback para datos viejos
                    col_n, col_r = st.columns([3, 2])
                    with col_n:
                        st.write(f"**{vinfo['nombre']}**: {v_ventas} boletos (${v_ingresos:,.2f})")
                    with col_r:
                        if st.button("🔄 Reset", key=f"rst_{vid}"):
                            vendedores_ref.child(vid).update({'ventas': 0, 'ingresos': 0})
                            st.rerun()

            # EXTRAS
            st.divider()
            st.subheader("📊 Reportes y Config")
            csv_str = "Nombre,Telefono,Boletos\n"
            for n, i in datos_boletos.items():
                if i['estado'] == 'ocupado': csv_str += f"{i['dueño']},{i['telefono']},{n}\n"
            st.download_button("📥 Descargar CSV", csv_str, "ventas.csv")
            
            new_p = st.number_input("Precio Boleto:", value=float(PRECIO_BOLETO))
            if st.button("Actualizar Precio"):
                config_ref.update({"precio_boleto": new_p})
                st.rerun()

            if st.button("🚨 REINICIAR TODO", type="primary"):
                boletos_ref.delete()
                st.rerun()

# --- 6. INTERFAZ VENDEDOR ---
st.title("🎟️ Sistema de Rifas - CUCEI")
st.write(f"**Precio Unitario: ${PRECIO_BOLETO} MXN**")

# Datos Cliente
c1, c2, c3, c4 = st.columns(4)
with c1: cliente = st.text_input("👤 Cliente:")
with c2: tel = st.text_input("📞 WhatsApp:")
with c3:
    v_opc = {v['nombre']: k for k, v in vendedores_datos.items()}
    v_sel = st.selectbox("🧤 Vendedor:", ["Seleccionar..."] + list(v_opc.keys()))
with c4: v_pass = st.text_input("🔑 Clave:", type="password")

st.divider()

# Sección de Selección
col_c, col_m = st.columns([2, 3])
with col_c:
    cant = st.number_input("🎟️ Cantidad de boletos:", min_value=1, value=1)
    if cant >= 4:
        st.session_state.promo_activa = st.toggle("✨ Aplicar Promoción (-$50)", value=st.session_state.promo_activa)
    else:
        st.session_state.promo_activa = False

with col_m:
    manual_in = st.text_input("🔢 Agregar manual (comas o espacios):", placeholder="001, 005...")
    if st.button("➕ Agregar a la Lista"):
        nums = manual_in.replace(",", " ").split()
        for n in nums:
            n_p = n.zfill(len(str(len(datos_boletos)-1)))
            if n_p in datos_boletos and datos_boletos[n_p]['estado'] == 'disponible':
                if len(st.session_state.seleccionados) < cant and n_p not in st.session_state.seleccionados:
                    st.session_state.seleccionados.append(n_p)
        st.rerun()

# Ayuda Aleatorio
ca, cl, _ = st.columns([2, 2, 6])
if ca.button("🎲 Completar"):
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

# Venta
if len(st.session_state.seleccionados) == cant and cliente and v_sel != "Seleccionar...":
    vid = v_opc[v_sel]
    if v_pass == vendedores_datos[vid]['clave']:
        
        # 1. Extraemos solo los números de lo que haya escrito el usuario
        tel_limpio = "".join(filter(str.isdigit, tel))
        
        # 2. Verificamos que sean exactamente 10 dígitos
        if len(tel_limpio) == 10:
            # Pasamos el tel_limpio para que en la base de datos se guarde perfecto
            confirmar_venta(cliente, tel_limpio, st.session_state.seleccionados, vid, v_sel, st.session_state.promo_activa)
        else:
            # 3. Si no son 10, mostramos una alerta y detenemos la venta
            st.error("⚠️ El número de WhatsApp debe tener exactamente 10 dígitos (Ej: 3312345678).")
            
    else:
        st.error("🔑 Clave de vendedor incorrecta.")

# --- 7. CUADRÍCULA ESTABLE (10 COLS PC) ---
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
                        else: 
                            st.warning("Escribe el nombre")
            else: 
                st.button("❌", key=f"n_{num}", disabled=True)
