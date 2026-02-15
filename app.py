import streamlit as st
import pandas as pd
import gspread
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

# --- CONEXIÓN A GOOGLE SHEETS ---
def conectar_google_sheet():
    # 1. Definimos permisos
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # 2. Leemos las credenciales desde Secrets (como diccionario)
    # Convertimos el objeto de Streamlit a un diccionario normal de Python
    creds_dict = dict(st.secrets["service_account"])
    
    # 3. LA CORRECCIÓN CLAVE PARA TU ERROR:
    # Reemplazamos los caracteres "\n" escapados por saltos de línea reales
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    
    # 4. Creamos las credenciales
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    
    # 5. Autorizamos y conectamos
    gc = gspread.authorize(credentials)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    return gc.open_by_url(url)

# --- FUNCIONES DE LECTURA Y ESCRITURA ---
def cargar_datos():
    sh = conectar_google_sheet()
    try:
        worksheet = sh.worksheet("Movimientos")
    except:
        worksheet = sh.get_worksheet(0)
    
    datos = worksheet.get_all_records()
    return pd.DataFrame(datos)

def guardar_movimiento(fecha, tipo, categoria, socio, concepto, monto):
    sh = conectar_google_sheet()
    try:
        worksheet = sh.worksheet("Movimientos")
    except:
        worksheet = sh.get_worksheet(0)
    
    # Preparamos la fila
    nueva_fila = [
        fecha.strftime("%Y-%m-%d"),
        tipo,
        categoria,
        socio,
        concepto,
        float(monto)
    ]
    
    # Agregamos la fila
    worksheet.append_row(nueva_fila)
    st.cache_data.clear()
    return True

# --- INTERFAZ GRÁFICA ---
st.title("🏡 Villa Soñada - Gestión")

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
                destino = st.radio("Afectación", ["General (Todos)", "Particular (Uno)"])
                if destino == "Particular (Uno)":
                    socio = st.selectbox("Vecino afectado", SOCIOS)
                    categoria = "Particular"
                else:
                    socio = "TODOS"
                    categoria = "General"
                concepto_def = ""
            
        concepto = st.text_input("Concepto / Detalle", value=concepto_def)
            
        enviado = st.form_submit_button("💾 Guardar en Google Drive")
        
        if enviado:
            with st.spinner("Guardando..."):
                try:
                    guardar_movimiento(fecha, "Ingreso" if "Ingreso" in tipo_operacion else "Egreso", categoria, socio, concepto, monto)
                    st.success("✅ ¡Guardado exitosamente!")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

# PANTALLA 2: CUENTAS
elif menu == "Cuentas Corrientes":
    st.header("🔎 Estado de Cuenta")
    if st.button("🔄 Actualizar"):
        st.cache_data.clear()
        
    try:
        df = cargar_datos()
        if not df.empty:
            vecino_selec = st.selectbox("Seleccionar Vecino", SOCIOS)
            
            # Filtros
            df["Monto"] = pd.to_numeric(df["Monto"])
            movs_propios = df[df["Socio"] == vecino_selec]
            movs_generales = df[df["Socio"] == "TODOS"].copy()
            
            if not movs_generales.empty:
                movs_generales["Monto"] = movs_generales["Monto"] / 20
                movs_generales["Concepto"] = movs_generales["Concepto"].astype(str) + " (Prorrateo)"
                
            estado_cuenta = pd.concat([movs_propios, movs_generales]).sort_values(by="Fecha", ascending=False)
            
            st.dataframe(estado_cuenta[["Fecha", "Tipo", "Concepto", "Monto"]], use_container_width=True)
            
            ingresos = estado_cuenta[estado_cuenta["Tipo"] == "Ingreso"]["Monto"].sum()
            egresos = estado_cuenta[estado_cuenta["Tipo"] == "Egreso"]["Monto"].sum()
            
            col1, col2 = st.columns(2)
            col1.metric("Pagado", f"${ingresos:,.0f}")
            col2.metric("Gastos/Deuda", f"${egresos:,.0f}")
            st.info(f"Saldo Final: ${ingresos - egresos:,.2f}")
    except Exception as e:
        st.error(f"Error cargando datos: {e}")

# PANTALLA 3: CAJA
elif menu == "Caja General":
    st.header("💰 Caja")
    if st.button("🔄 Actualizar"):
        st.cache_data.clear()
    try:
        df = cargar_datos()
        if not df.empty:
            df["Monto"] = pd.to_numeric(df["Monto"])
            ingresos = df[df["Tipo"] == "Ingreso"]["Monto"].sum()
            egresos = df[df["Tipo"] == "Egreso"]["Monto"].sum()
            st.metric("Saldo en Caja", f"$ {ingresos - egresos:,.2f}")
            st.dataframe(df)
    except Exception as e:
        st.error(f"Error: {e}")
