import streamlit as st
import pandas as pd
import gspread
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
        # Leemos los secretos como diccionario (Formato TOML estándar)
        # Esto evita el error de "Invalid control character" del JSON
        creds_dict = dict(st.secrets["service_account"])
        
        # Corrección de seguridad para saltos de línea en la clave
        if "\\n" in creds_dict["private_key"]:
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
        # Limpieza de nombres de columnas por si hay espacios
        df.columns = df.columns.str.strip()
        
        if not df.empty and "Nombre" in df.columns:
            return df["Nombre"].tolist(), df
        else:
            return [], pd.DataFrame()
    except:
        return ["A - Genérico", "B - Genérico"], pd.DataFrame()

def obtener_datos_luz_historicos(socio_seleccionado):
    """Busca en qué número quedó el medidor la última vez"""
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Lecturas")
        datos = ws.get_all_records()
        df = pd.DataFrame(datos)
        
        if df.empty:
            return 0, 100.0
            
        ultimo_precio = float(df.iloc[-1]["Precio_kWh"]) if "Precio_kWh" in df.columns else 100.0
        
        if "Socio" in df.columns:
            lecturas_socio = df[df["Socio"] == socio_seleccionado]
            if not lecturas_socio.empty:
                ultima_lec = int(lecturas_socio.iloc[-1]["Lectura_Act"])
                return ultima_lec, ultimo_precio
        
        return 0, ultimo_precio
    except:
        return 0, 100.0

def guardar_lote_movimientos(lista_filas):
    sh = conectar_google_sheet()
    ws = sh.worksheet("Movimientos")
    ws.append_rows(lista_filas)
    st.cache_data.clear()

def guardar_lectura_tecnica(fila_lectura):
    sh = conectar_google_sheet()
    ws = sh.worksheet("Lecturas")
    ws.append_row(fila_lectura)

def cargar_movimientos():
    sh = conectar_google_sheet()
    ws = sh.worksheet("Movimientos")
    return pd.DataFrame(ws.get_all_records())

# --- 3. INTERFAZ GRÁFICA ---

st.title("🏡 Administración Villa Soñada")

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

# MÓDULO 1: CARGA
if menu == "1. 📝 Cargar Gastos/Ingresos":
    st.header("Nueva Operación")
    with st.form("form_carga"):
        col1, col2 = st.columns(2)
        fecha = col1.date_input("Fecha", datetime.now())
        tipo = col2.selectbox("Tipo", ["Gasto (Salida)", "Ingreso (Cobro)"])
        monto = col1.number_input("Monto Total ($)", min_value=0.0, step=1000.0)
        concepto = col2.text_input("Concepto")
        
        if tipo == "Ingreso (Cobro)":
            socio = st.selectbox("¿Quién paga?", lista_nombres)
            destino_gasto = "Particular"
        else:
            destino_gasto = st.radio("Asignación", ["General (Todos)", "Particular (Uno)"])
            if "General" in destino_gasto:
                socio = "TODOS"
                cant = len(lista_nombres)
                monto_ind = monto / cant if cant > 0 else 0
                st.info(f"Se dividirán ${monto:,.2f} entre {cant} vecinos (${monto_ind:,.2f} c/u).")
            else:
                socio = st.selectbox("A quién cargar", lista_nombres)

        if st.form_submit_button("💾 Guardar"):
            hoy = fecha.strftime("%Y-%m-%d")
            filas = []
            if tipo == "Gasto (Salida)" and "General" in destino_gasto:
                for vec in lista_nombres:
                    filas.append([hoy, "Egreso", "General Prorrateado", vec, f"{concepto} (Cuota)", monto_ind])
            else:
                t_real = "Ingreso" if "Ingreso" in tipo else "Egreso"
                c_real = "Particular" if "Particular" in destino_gasto or "Ingreso" in tipo else "General"
                filas.append([hoy, t_real, c_real, socio, concepto, monto])
            
            guardar_lote_movimientos(filas)
            st.success("✅ Guardado.")

# MÓDULO 2: LUZ
elif menu == "2. ⚡ Medidor de Luz (Auto)":
    st.header("Carga de Luz")
    socio_luz = st.selectbox("Vecino", lista_nombres)
    with st.spinner("Buscando lectura anterior..."):
        l_sug, p_sug = obtener_datos_luz_historicos(socio_luz)
    st.info(f"Medidor anterior: **{l_sug}**")
    
    with st.form("luz"):
        c1, c2, c3 = st.columns(3)
        ant = c1.number_input("Anterior", value=int(l_sug), step=1)
        act = c2.number_input("Actual", min_value=int(l_sug), step=1)
        pr = c3.number_input("Precio", value=float(p_sug), step=0.1)
        cons = act - ant
        tot = cons * pr
        st.metric("Consumo", f"{cons} kWh")
        st.metric("A Pagar", f"${tot:,.2f}")
        
        if st.form_submit_button("💾 Guardar"):
            if cons < 0: st.error("Error: Lectura negativa")
            else:
                hoy = datetime.now().strftime("%Y-%m-%d")
                guardar_lectura_tecnica([hoy, socio_luz, ant, act, cons, pr, tot])
                guardar_lote_movimientos([[hoy, "Egreso", "Luz", socio_luz, f"Luz {cons}kWh", tot]])
                st.success("✅ Cargado.")

# MÓDULO 3: INTERESES
elif menu == "3. 📈 Ajuste Inflación/Interés":
    st.header("Recargos Masivos")
    c1, c2 = st.columns(2)
    inf = c1.number_input("% Inflación", 5.0)
    pun = c2.number_input("% Interés", 3.0)
    fact = (inf + pun) / 100
    
    if st.button("🔍 Calcular"):
        df = cargar_movimientos()
        df["Monto"] = pd.to_numeric(df["Monto"])
        filas = []
        hay = False
        st.write("---")
        for vec in lista_nombres:
            movs = df[df["Socio"] == vec]
            sal = movs[movs["Tipo"]=="Ingreso"]["Monto"].sum() - movs[movs["Tipo"]=="Egreso"]["Monto"].sum()
            if sal < -100:
                hay = True
                rec = abs(sal) * fact
                st.error(f"{vec}: Debe ${abs(sal):,.0f} -> Recargo ${rec:,.0f}")
                filas.append([datetime.now().strftime("%Y-%m-%d"), "Egreso", "Financiero", vec, f"Ajuste {inf}+{pun}%", rec])
        
        if hay:
            if st.button("🔥 APLICAR"):
                guardar_lote_movimientos(filas)
                st.success("✅ Hecho.")
        else: st.success("Nadie debe nada.")

# MÓDULO 4: CUENTAS
elif menu == "4. 🔍 Cuentas Corrientes":
    if st.button("Actualizar"): st.cache_data.clear()
    df = cargar_movimientos()
    if not df.empty:
        df["Monto"] = pd.to_numeric(df["Monto"])
        vec = st.selectbox("Vecino", lista_nombres)
        movs = df[df["Socio"] == vec].sort_values(by="Fecha", ascending=False)
        ing = movs[movs["Tipo"]=="Ingreso"]["Monto"].sum()
        egr = movs[movs["Tipo"]=="Egreso"]["Monto"].sum()
        sal = ing - egr
        c1, c2, c3 = st.columns(3)
        c1.metric("Pagos", f"${ing:,.0f}")
        c2.metric("Deuda", f"${egr:,.0f}")
        c3.metric("Saldo", f"${sal:,.2f}", delta_color="normal" if sal>=0 else "inverse")
        st.dataframe(movs[["Fecha", "Concepto", "Tipo", "Monto"]], use_container_width=True)

# MÓDULO 5: WHATSAPP
elif menu == "5. 📲 WhatsApp Cobranza":
    st.info("Clic para abrir WhatsApp")
    df = cargar_movimientos()
    if not df.empty and not df_socios_completo.empty:
        df["Monto"] = pd.to_numeric(df["Monto"])
        for i, row in df_socios_completo.iterrows():
            nom = row["Nombre"]
            tel = str(row["Telefono"]).replace("+", "").strip()
            movs = df[df["Socio"] == nom]
            sal = movs[movs["Tipo"]=="Ingreso"]["Monto"].sum() - movs[movs["Tipo"]=="Egreso"]["Monto"].sum()
            msg = f"Hola {nom}, saldo: ${sal:,.2f}"
            link = f"https://wa.me/{tel}?text={msg.replace(' ', '%20')}"
            with st.expander(f"{nom} (${sal:,.0f})"):
                st.markdown(f"[Enviar WhatsApp]({link})")
