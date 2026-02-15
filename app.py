import streamlit as st
import pandas as pd
import gspread
import json
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestión Villa Soñada", layout="centered")

# --- CONEXIÓN INFALIBLE (MÉTODO JSON PURO) ---
def conectar_google_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        # 1. Leemos el bloque de texto entero
        json_string = st.secrets["google_credentials"]["json_content"]
        
        # 2. Lo convertimos en diccionario (Python se encarga de los formatos raros)
        creds_dict = json.loads(json_string)
        
        # 3. Creamos credenciales
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        
        # 4. Autorizamos
        gc = gspread.authorize(credentials)
        
        # 5. Abrimos hoja
        url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        return gc.open_by_url(url)
        
    except Exception as e:
        st.error(f"❌ Error de Conexión: {e}")
        st.stop()

# --- FUNCIONES DE DATOS ---
def cargar_datos():
    sh = conectar_google_sheet()
    try:
        worksheet = sh.worksheet("Movimientos")
    except:
        worksheet = sh.get_worksheet(0)
    return pd.DataFrame(worksheet.get_all_records())

def guardar_movimiento(fecha, tipo, categoria, socio, concepto, monto):
    sh = conectar_google_sheet()
    try:
        worksheet = sh.worksheet("Movimientos")
    except:
        worksheet = sh.get_worksheet(0)
    
    nueva_fila = [fecha.strftime("%Y-%m-%d"), tipo, categoria, socio, concepto, float(monto)]
    worksheet.append_row(nueva_fila)
    st.cache_data.clear()
    return True

# --- INTERFAZ ---
st.title("🏡 Villa Soñada - Gestión")

menu = st.sidebar.radio("Menú", ["Cargar", "Ver Cuentas", "Caja"])
SOCIOS = ["A - Garcia", "B - Sierra", "C - Fernandez", "D - Novaretto", "E - Calderon", 
          "F - Rodriguez", "G - Diser", "H - Piñero", "I - Civale", "J - Molina", 
          "K - Barale", "L - Biscayart", "M - Garcia Wild", "N - Mendez", "O - Guillermo", 
          "P - Justet", "Q - Ruiz", "R - Root", "S - Pathauer", "S - Buss"]

if menu == "Cargar":
    st.subheader("Nuevo Movimiento")
    tipo = st.selectbox("Tipo", ["Gasto", "Ingreso"])
    with st.form("carga"):
        fecha = st.date_input("Fecha")
        monto = st.number_input("Monto", min_value=0.0)
        concepto = st.text_input("Detalle")
        
        if tipo == "Ingreso":
            socio = st.selectbox("Socio", SOCIOS)
            cat = "Particular"
        else:
            destino = st.radio("Destino", ["General", "Particular"])
            socio = st.selectbox("Socio", SOCIOS) if destino == "Particular" else "TODOS"
            cat = "General" if destino == "General" else "Particular"
            
        if st.form_submit_button("Guardar"):
            guardar_movimiento(fecha, tipo, cat, socio, concepto, monto)
            st.success("✅ Guardado!")

elif menu == "Ver Cuentas":
    if st.button("Actualizar"): st.cache_data.clear()
    df = cargar_datos()
    if not df.empty:
        vecino = st.selectbox("Vecino", SOCIOS)
        st.dataframe(df[df["Socio"] == vecino])

elif menu == "Caja":
    if st.button("Actualizar"): st.cache_data.clear()
    df = cargar_datos()
    if not df.empty:
        st.dataframe(df)
