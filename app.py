import streamlit as st
import pandas as pd
import gspread
import json
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Villa Soñada", layout="wide")

# --- 1. CONEXIÓN INFALIBLE A GOOGLE SHEETS ---
def conectar_google_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        # Leemos el bloque JSON desde los secretos
        json_string = st.secrets["google_credentials"]["json_content"]
        creds_dict = json.loads(json_string)
        
        # Corrección de seguridad para saltos de línea
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(credentials)
        return gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
        
    except Exception as e:
        st.error(f"❌ Error de Conexión: {e}")
        st.stop()

# --- 2. FUNCIONES DE BASE DE DATOS ---

def obtener_lista_socios():
    """Lee la hoja 'Socios' para llenar los desplegables"""
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Socios")
        df = pd.DataFrame(ws.get_all_records())
        if not df.empty and "Nombre" in df.columns:
            return df["Nombre"].tolist(), df
        else:
            return [], pd.DataFrame()
    except:
        # Si falla, devolvemos una lista vacía para no romper la app
        return ["A - Genérico", "B - Genérico"], pd.DataFrame()

def obtener_datos_luz_historicos(socio_seleccionado):
    """Busca en qué número quedó el medidor la última vez"""
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Lecturas")
        datos = ws.get_all_records()
        df = pd.DataFrame(datos)
        
        if df.empty:
            return 0, 100.0 # Valores por defecto
            
        # 1. Buscar último precio usado
        ultimo_precio = float(df.iloc[-1]["Precio_kWh"]) if "Precio_kWh" in df.columns else 100.0
        
        # 2. Buscar la última lectura de ESTE socio
        if "Socio" in df.columns:
            lecturas_socio = df[df["Socio"] == socio_seleccionado]
            if not lecturas_socio.empty:
                # La lectura "Actual" anterior pasa a ser la "Anterior" de hoy
                ultima_lec = int(lecturas_socio.iloc[-1]["Lectura_Act"])
                return ultima_lec, ultimo_precio
        
        return 0, ultimo_precio
            
    except Exception as e:
        return 0, 100.0

def guardar_lote_movimientos(lista_filas):
    """Guarda muchas filas de golpe (útil para prorrateo)"""
    sh = conectar_google_sheet()
    ws = sh.worksheet("Movimientos")
    ws.append_rows(lista_filas)
    st.cache_data.clear()

def guardar_lectura_tecnica(fila_lectura):
    """Guarda el registro técnico en la hoja Lecturas"""
    sh = conectar_google_sheet()
    ws = sh.worksheet("Lecturas")
    ws.append_row(fila_lectura)

def cargar_movimientos():
    """Descarga todos los movimientos para ver saldos"""
    sh = conectar_google_sheet()
    ws = sh.worksheet("Movimientos")
    return pd.DataFrame(ws.get_all_records())

# --- 3. INTERFAZ GRÁFICA (FRONTEND) ---

st.title("🏡 Administración Villa Soñada")

# Cargamos socios al iniciar
lista_nombres, df_socios_completo = obtener_lista_socios()

if not lista_nombres:
    st.warning("⚠️ No se encontró la hoja 'Socios' o está vacía. Usando lista genérica.")
    lista_nombres = [f"Lote {i}" for i in range(1, 21)]

# Menú Lateral
menu = st.sidebar.radio("Navegación:", [
    "1. 📝 Cargar Gastos/Ingresos", 
    "2. ⚡ Medidor de Luz (Auto)", 
    "3. 📈 Ajuste Inflación/Interés", 
    "4. 🔍 Cuentas Corrientes",
    "5. 📲 WhatsApp Cobranza"
])

# ---------------------------------------------------------
# MÓDULO 1: CARGA GENERAL (CON PRORRATEO)
# ---------------------------------------------------------
if menu == "1. 📝 Cargar Gastos/Ingresos":
    st.header("Nueva Operación")
    
    with st.form("form_carga"):
        col1, col2 = st.columns(2)
        fecha = col1.date_input("Fecha", datetime.now())
        tipo = col2.selectbox("Tipo de Operación", ["Gasto (Salida)", "Ingreso (Cobro)"])
        
        monto = col1.number_input("Monto Total ($)", min_value=0.0, step=1000.0)
        concepto = col2.text_input("Concepto / Detalle")
        
        # Lógica de destinatario
        if tipo == "Ingreso (Cobro)":
            socio = st.selectbox("¿Quién paga?", lista_nombres)
            destino_gasto = "Particular"
        else:
            # Es Gasto
            destino_gasto = st.radio("¿Cómo se asigna este gasto?", ["General (Dividir entre TODOS)", "Particular (Asignar a UNO)"])
            if "General" in destino_gasto:
                socio = "TODOS"
                cant_socios = len(lista_nombres)
                monto_individual = monto / cant_socios if cant_socios > 0 else 0
                st.info(f"ℹ️ Se dividirán ${monto:,.2f} entre {cant_socios} vecinos. (${monto_individual:,.2f} c/u)")
            else:
                socio = st.selectbox("¿A quién se le carga?", lista_nombres)

        if st.form_submit_button("💾 Guardar Operación"):
            fecha_str = fecha.strftime("%Y-%m-%d")
            filas_a_guardar = []
            
            if tipo == "Gasto (Salida)" and "General" in destino_gasto:
                # PRORRATEO AUTOMÁTICO
                for vecino in lista_nombres:
                    filas_a_guardar.append([
                        fecha_str, "Egreso", "General Prorrateado", vecino, f"{concepto} (Cuota Parte)", monto_individual
                    ])
            else:
                # CARGA SIMPLE
                tipo_real = "Ingreso" if "Ingreso" in tipo else "Egreso"
                cat_real = "Particular" if "Particular" in destino_gasto or tipo == "Ingreso (Cobro)" else "General"
                filas_a_guardar.append([
                    fecha_str, tipo_real, cat_real, socio, concepto, monto
                ])
            
            with st.spinner("Guardando en la nube..."):
                guardar_lote_movimientos(filas_a_guardar)
                st.success("✅ Operación registrada con éxito.")

# ---------------------------------------------------------
# MÓDULO 2: LUZ INTELIGENTE
# ---------------------------------------------------------
elif menu == "2. ⚡ Medidor de Luz (Auto)":
    st.header("Carga de Luz")
    
    socio_luz = st.selectbox("Seleccionar Vecino", lista_nombres)
    
    # Buscamos datos históricos automáticos
    with st.spinner("Consultando medidor anterior..."):
        lectura_sugerida, precio_sugerido = obtener_datos_luz_historicos(socio_luz)
    
    st.info(f"El medidor de **{socio_luz}** quedó en **{lectura_sugerida}**.")

    with st.form("form_luz"):
        c1, c2, c3 = st.columns(3)
        lec_ant = c1.number_input("Lectura Anterior", value=int(lectura_sugerida), step=1)
        lec_act = c2.number_input("Lectura Actual", min_value=int(lectura_sugerida), step=1)
        precio = c3.number_input("Precio kWh ($)", value=float(precio_sugerido), step=0.5)
        
        consumo = lec_act - lec_ant
        total = consumo * precio
        
        st.metric("Consumo del Mes", f"{consumo} kWh")
        st.metric("Total a Pagar", f"$ {total:,.2f}")
        
        if st.form_submit_button("💾 Guardar Lectura y Deuda"):
            if consumo < 0:
                st.error("Error: La lectura actual es menor a la anterior.")
            else:
                hoy = datetime.now().strftime("%Y-%m-%d")
                
                # 1. Guardar técnico
                guardar_lectura_tecnica([hoy, socio_luz, lec_ant, lec_act, consumo, precio, total])
                
                # 2. Guardar financiero (Deuda)
                detalle = f"Luz: {lec_ant} a {lec_act} ({consumo} kWh)"
                guardar_lote_movimientos([[hoy, "Egreso", "Luz", socio_luz, detalle, total]])
                
                st.success(f"✅ Cargado: {socio_luz} debe ${total:,.2f}")

# ---------------------------------------------------------
# MÓDULO 3: INTERESES E INFLACIÓN
# ---------------------------------------------------------
elif menu == "3. 📈 Ajuste Inflación/Interés":
    st.header("Aplicar Recargos Masivos")
    st.warning("⚠️ Esto buscará a todos los deudores y les sumará deuda nueva.")
    
    col1, col2 = st.columns(2)
    inf = col1.number_input("% Inflación", value=5.0)
    int_pun = col2.number_input("% Interés Punitorio", value=3.0)
    factor = (inf + int_pun) / 100
    
    if st.button("🔍 Calcular Deudores"):
        df = cargar_movimientos()
        if not df.empty:
            df["Monto"] = pd.to_numeric(df["Monto"])
            filas_ajuste = []
            hoy = datetime.now().strftime("%Y-%m-%d")
            
            st.write("---")
            hay_deudores = False
            for vecino in lista_nombres:
                movs = df[df["Socio"] == vecino]
                saldo = movs[movs["Tipo"] == "Ingreso"]["Monto"].sum() - movs[movs["Tipo"] == "Egreso"]["Monto"].sum()
                
                if saldo < -100: # Tolerancia de $100
                    hay_deudores = True
                    recargo = abs(saldo) * factor
                    st.error(f"👤 **{vecino}**: Debe ${abs(saldo):,.2f} ➡️ Recargo: **${recargo:,.2f}**")
                    
                    filas_ajuste.append([
                        hoy, "Egreso", "Financiero", vecino, 
                        f"Ajuste Mora ({inf}% Inf + {int_pun}% Int)", recargo
                    ])
            
            if not hay_deudores:
                st.success("🎉 ¡Nadie tiene deuda significativa!")
            else:
                if st.button("🔥 APLICAR CARGOS AHORA"):
                    guardar_lote_movimientos(filas_ajuste)
                    st.success("✅ Recargos aplicados a todas las cuentas.")

# ---------------------------------------------------------
# MÓDULO 4: CUENTAS CORRIENTES
# ---------------------------------------------------------
elif menu == "4. 🔍 Cuentas Corrientes":
    st.header("Estado de Cuenta")
    if st.button("🔄 Actualizar Datos"): st.cache_data.clear()
    
    df = cargar_movimientos()
    if not df.empty:
        df["Monto"] = pd.to_numeric(df["Monto"])
        vecino = st.selectbox("Ver Vecino", lista_nombres)
        
        movs = df[df["Socio"] == vecino].sort_values(by="Fecha", ascending=False)
        
        ingresos = movs[movs["Tipo"] == "Ingreso"]["Monto"].sum()
        egresos = movs[movs["Tipo"] == "Egreso"]["Monto"].sum()
        saldo = ingresos - egresos
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Pagos", f"${ingresos:,.0f}")
        c2.metric("Consumos", f"${egresos:,.0f}")
        c3.metric("Saldo Final", f"${saldo:,.2f}", delta_color="normal" if saldo >= 0 else "inverse")
        
        st.dataframe(movs[["Fecha", "Concepto", "Tipo", "Monto"]], use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 5: WHATSAPP
# ---------------------------------------------------------
elif menu == "5. 📲 WhatsApp Cobranza":
    st.header("Enviar Recordatorios")
    
    df = cargar_movimientos()
    if not df.empty and not df_socios_completo.empty:
        df["Monto"] = pd.to_numeric(df["Monto"])
        
        st.info("Hacé clic en el enlace para abrir WhatsApp Web o la App.")
        
        for index, row in df_socios_completo.iterrows():
            nombre = row["Nombre"]
            tel = str(row["Telefono"]).replace("+", "").strip()
            
            # Calculo saldo
            movs = df[df["Socio"] == nombre]
            saldo = movs[movs["Tipo"] == "Ingreso"]["Monto"].sum() - movs[movs["Tipo"] == "Egreso"]["Monto"].sum()
            
            if saldo < 0:
                color = "🔴"
                msg = f"Hola {nombre}, te contacto de la Administración. Tu saldo actual es -${abs(saldo):,.2f} (Deuda). Por favor regularizar."
            else:
                color = "🟢"
                msg = f"Hola {nombre}, tu saldo actual es a favor: ${saldo:,.2f}. ¡Gracias!"
            
            link = f"https://wa.me/{tel}?text={msg.replace(' ', '%20')}"
            
            with st.expander(f"{color} {nombre} (Saldo: ${saldo:,.0f})"):
                st.markdown(f"👉 **[ENVIAR MENSAJE AHORA]({link})**")
                st.code(msg, language=None)
