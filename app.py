import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestión Villa Soñada", layout="centered")

# --- CONEXIÓN ROBUSTA (GSPREAD) ---
def conectar_google_sheet():
    # Definimos los permisos que necesita el robot
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Cargamos las credenciales desde los Secretos
    creds_dict = dict(st.secrets["connections"]["gsheets"]["service_account"])
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    
    # Autorizamos
    gc = gspread.authorize(credentials)
    
    # Abrimos la hoja usando el link
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    return gc.open_by_url(url)

# --- FUNCIONES DE DATOS ---
def cargar_datos():
    sh = conectar_google_sheet()
    try:
        # Intenta buscar la pestaña por nombre
        worksheet = sh.worksheet("Movimientos")
    except:
        # Si falla, agarra la primera (índice 0)
        worksheet = sh.get_worksheet(0)
    
    # Baja todos los datos
    datos = worksheet.get_all_records()
    return pd.DataFrame(datos)

def guardar_movimiento(fecha, tipo, categoria, socio, concepto, monto):
    sh = conectar_google_sheet()
    try:
        worksheet = sh.worksheet("Movimientos")
    except:
        worksheet = sh.get_worksheet(0)
    
    # Prepara la fila nueva (una lista simple)
    # Orden: Fecha, Tipo, Categoria, Socio, Concepto, Monto
    nueva_fila = [
        fecha.strftime("%Y-%m-%d"),
        tipo,
        categoria,
        socio,
        concepto,
        float(monto)
    ]
    
    # Agrega la fila al final (append_row es más seguro)
    worksheet.append_row(nueva_fila)
    st.cache_data.clear()
    return True

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

# --- INTERFAZ GRÁFICA ---
st.title("🏡 Villa Soñada (GSpread)")

menu = st.sidebar.radio("Menú", ["Cargar", "Cuentas", "Caja"])

if menu == "Cargar":
    st.header("📝 Nuevo Movimiento")
    tipo = st.selectbox("Tipo", ["Gasto", "Ingreso"])
    
    with st.form("carga"):
        fecha = st.date_input("Fecha", datetime.now())
        if tipo == "Ingreso":
            socio = st.selectbox("Socio", SOCIOS)
            cat = "Particular"
            concepto = st.text_input("Detalle", "Expensas")
        else:
            destino = st.radio("Destino", ["General", "Particular"])
            socio = st.selectbox("Socio", SOCIOS) if destino == "Particular" else "TODOS"
            cat = "Particular" if destino == "Particular" else "General"
            concepto = st.text_input("Detalle", "")
            
        monto = st.number_input("Monto", min_value=0.0, step=100.0)
        
        if st.form_submit_button("Guardar"):
            try:
                guardar_movimiento(fecha, tipo, cat, socio, concepto, monto)
                st.success("✅ ¡Guardado con éxito!")
            except Exception as e:
                st.error(f"Error al guardar: {e}")

elif menu == "Cuentas":
    st.header("🔎 Ver Saldo")
    if st.button("🔄 Actualizar Datos"):
        st.cache_data.clear()
        
    df = cargar_datos()
    if not df.empty:
        vecino = st.selectbox("Seleccionar Vecino", SOCIOS)
        # Filtrado simple
        df["Monto"] = pd.to_numeric(df["Monto"])
        mis_movs = df[df["Socio"] == vecino]
        generales = df[df["Socio"] == "TODOS"].copy()
        
        if not generales.empty:
            generales["Monto"] = generales["Monto"] / 20
            generales["Concepto"] = generales["Concepto"] + " (Prorrateo)"
            
        final = pd.concat([mis_movs, generales])
        st.dataframe(final)

elif menu == "Caja":
    st.header("💰 Caja Total")
    if st.button("🔄 Refrescar"):
        st.cache_data.clear()
    df = cargar_datos()
    if not df.empty:
        st.dataframe(df)
