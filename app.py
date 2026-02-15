import streamlit as st
import pandas as pd
import gspread
import json
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestión Villa Soñada", layout="centered")

# --- LISTA DE SOCIOS ---
SOCIOS = [
    "A - Garcia Berberena", "B - Sierra Analisa", "C - Fernandez Natalia", 
    "D - Novaretto Emiliano", "E - Calderon José Luis", "F - Rodriguez Matias", 
    "G - Diser Javier", "H - Piñero Silvana", "I - Civale Florencia", 
    "J - Molina Angel", "K - Barale Fernando", "L - Biscayart Bernardo", 
    "M - Garcia Wild Anahi", "N - Mendez Pamela", "O - Guillermo Saul", 
    "P - Justet Luis", "Q - RUIZ DIEGO", "R - Root Silvana", 
    "S - Pathauer Carina", "S - Buss Valeria"
]

# --- CONEXIÓN A GOOGLE SHEETS (MÉTODO INFALIBLE) ---
def conectar_google_sheet():
    # 1. Definimos permisos
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # 2. Leemos el bloque JSON entero desde Secrets
    # Esto evita errores de formato en la clave privada
    try:
        json_content = st.secrets["service_account"]["credentials_json"]
        creds_dict = json.loads(json_content)
    except Exception as e:
        st.error(f"Error leyendo credenciales: {e}")
        st.stop()
    
    # 3. Creamos las credenciales
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    
    # 4. Autorizamos gspread
    gc = gspread.authorize(credentials)
    
    # 5. Abrimos la hoja por URL
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    return gc.open_by_url(url)

# --- FUNCIONES DE LECTURA Y ESCRITURA ---
def cargar_datos():
    sh = conectar_google_sheet()
    try:
        # Intenta buscar la pestaña "Movimientos"
        worksheet = sh.worksheet("Movimientos")
    except:
        # Si no la encuentra, usa la primera hoja disponible (Plan B)
        worksheet = sh.get_worksheet(0)
    
    datos = worksheet.get_all_records()
    return pd.DataFrame(datos)

def guardar_movimiento(fecha, tipo, categoria, socio, concepto, monto):
    sh = conectar_google_sheet()
    try:
        worksheet = sh.worksheet("Movimientos")
    except:
        worksheet = sh.get_worksheet(0)
    
    # Preparamos la fila. El orden debe coincidir con tus columnas en Excel
    nueva_fila = [
        fecha.strftime("%Y-%m-%d"), # Fecha
        tipo,                        # Tipo
        categoria,                   # Categoria
        socio,                       # Socio
        concepto,                    # Concepto
        float(monto)                 # Monto
    ]
    
    # Agregamos la fila al final
    worksheet.append_row(nueva_fila)
    st.cache_data.clear() # Limpiamos memoria para ver cambios al instante
    return True

# --- INTERFAZ GRÁFICA (FRONTEND) ---
st.title("🏡 Villa Soñada - Gestión")

# Menú Lateral
menu = st.sidebar.radio("Navegación", ["Cargar Movimiento", "Cuentas Corrientes", "Caja General"])

# PANTALLA 1: CARGA
if menu == "Cargar Movimiento":
    st.header("📝 Nuevo Registro")
    
    tipo_operacion = st.selectbox("¿Qué vas a registrar?", ["Gasto (Salida)", "Ingreso (Cobro)"])
    
    with st.form("formulario_carga"):
        col1, col2 = st.columns(2)
        with col1:
            fecha = st.date_input("Fecha", datetime.now())
            monto = st.number_input("Monto ($)", min_value=0.0, step=100.0)
        
        with col2:
            if tipo_operacion == "Ingreso (Cobro)":
                socio = st.selectbox("Vecino que paga", SOCIOS)
                categoria = "Particular"
                concepto_def = "Expensas"
            else:
                # Es Gasto
                destino = st.radio("Afectación", ["General (Todos)", "Particular (Uno)"])
                if destino == "Particular (Uno)":
                    socio = st.selectbox("Vecino afectado", SOCIOS)
                    categoria = "Particular"
                else:
                    socio = "TODOS"
                    categoria = "General"
                concepto_def = ""
            
        concepto = st.text_input("Concepto / Detalle", value=concepto_def)
            
        # Botón de Guardar
        enviado = st.form_submit_button("💾 Guardar en Google Drive")
        
        if enviado:
            with st.spinner("Guardando en la nube..."):
                try:
                    guardar_movimiento(fecha, "Ingreso" if "Ingreso" in tipo_operacion else "Egreso", categoria, socio, concepto, monto)
                    st.success("✅ ¡Guardado exitosamente!")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ Error al guardar: {e}")

# PANTALLA 2: CUENTAS CORRIENTES
elif menu == "Cuentas Corrientes":
    st.header("🔎 Estado de Cuenta")
    
    if st.button("🔄 Actualizar datos"):
        st.cache_data.clear()
        
    df = cargar_datos()
    
    if not df.empty:
        vecino_selec = st.selectbox("Seleccionar Vecino", SOCIOS)
        
        # Filtros y Cálculos
        # 1. Movimientos directos del vecino
        movs_propios = df[df["Socio"] == vecino_selec].copy()
        
        # 2. Movimientos generales (divididos por 20)
        movs_generales = df[df["Socio"] == "TODOS"].copy()
        
        if not movs_generales.empty:
            # Aseguramos que sea número para dividir
            movs_generales["Monto"] = pd.to_numeric(movs_generales["Monto"])
            movs_generales["Monto"] = movs_generales["Monto"] / 20
            movs_generales["Concepto"] = movs_generales["Concepto"].astype(str) + " (Prorrateo)"
            
        # Unimos ambas tablas
        estado_cuenta = pd.concat([movs_propios, movs_generales])
        
        if not estado_cuenta.empty:
            estado_cuenta = estado_cuenta.sort_values(by="Fecha", ascending=False)
            
            # Mostramos tabla
            st.dataframe(estado_cuenta[["Fecha", "Tipo", "Concepto", "Monto"]], use_container_width=True)
            
            # Calculamos Saldo
            ingresos = estado_cuenta[estado_cuenta["Tipo"] == "Ingreso"]["Monto"].sum()
            egresos = estado_cuenta[estado_cuenta["Tipo"] == "Egreso"]["Monto"].sum()
            saldo = ingresos - egresos
            
            col1, col2 = st.columns(2)
            col1.metric("Pagos Realizados", f"$ {ingresos:,.2f}")
            col2.metric("Deuda/Gastos Asignados", f"$ {egresos:,.2f}")
            
            if saldo < 0:
                st.error(f"❌ DEUDA ACTUAL: $ {saldo:,.2f}")
            else:
                st.success(f"✅ A FAVOR: $ {saldo:,.2f}")
        else:
            st.info("No hay movimientos para este vecino.")

# PANTALLA 3: CAJA
elif menu == "Caja General":
    st.header("💰 Caja del Consorcio")
    if st.button("🔄 Actualizar"):
        st.cache_data.clear()
        
    df = cargar_datos()
    if not df.empty:
        # Convertir a números por seguridad
        df["Monto"] = pd.to_numeric(df["Monto"])
        
        ingresos_totales = df[df["Tipo"] == "Ingreso"]["Monto"].sum()
        gastos_totales = df[df["Tipo"] == "Egreso"]["Monto"].sum()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Ingresos", f"$ {ingresos_totales:,.2f}")
        col2.metric("Total Gastos Reales", f"$ {gastos_totales:,.2f}")
        col3.metric("Saldo en Caja", f"$ {ingresos_totales - gastos_totales:,.2f}")
        
        st.subheader("Últimos 10 Movimientos")
        st.dataframe(df.tail(10).sort_values(by="Fecha", ascending=False))
