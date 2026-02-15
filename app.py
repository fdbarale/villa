import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json

st.title("🕵️‍♂️ Modo Diagnóstico: Villa Soñada")
st.write("Vamos a probar la conexión paso a paso con Banderines.")

# --- BANDERÍN 1: LECTURA DE SECRETS ---
st.subheader("🚩 Paso 1: Leer Secrets")
try:
    # Intentamos leer como diccionario normal
    raw_creds = dict(st.secrets["service_account"])
    st.success("✅ Secrets encontrados y leídos como diccionario.")
    st.write(f"**Email del Robot:** `{raw_creds.get('client_email', 'NO ENCONTRADO')}`")
except Exception as e:
    st.error(f"❌ Falló Paso 1: No se pueden leer los secrets. {e}")
    st.stop()

# --- BANDERÍN 2: LIMPIEZA DE CLAVE PRIVADA (Aquí suele fallar) ---
st.subheader("🚩 Paso 2: Procesar Private Key")
try:
    p_key = raw_creds.get("private_key", "")
    st.write(f"Longitud original de la clave: {len(p_key)} caracteres")
    
    # Intento de limpieza agresiva
    # 1. Reemplazamos \\n literal por salto de línea real
    fixed_key = p_key.replace("\\n", "\n")
    
    # 2. Verificamos encabezados
    if "-----BEGIN PRIVATE KEY-----" not in fixed_key:
        st.error("❌ La clave no tiene el encabezado 'BEGIN PRIVATE KEY'. Está corrupta.")
        st.stop()
        
    st.info("Visualización de los primeros 50 caracteres (para ver si hay saltos):")
    st.code(fixed_key[:50]) # Mostramos el principio para ver si se ve bien
    
    # Actualizamos el diccionario con la clave arreglada
    raw_creds["private_key"] = fixed_key
    st.success("✅ Clave procesada sin errores de sintaxis Python.")

except Exception as e:
    st.error(f"❌ Falló Paso 2: Error procesando el texto de la clave. {e}")
    st.stop()

# --- BANDERÍN 3: CREAR OBJETO CREDENCIALES (Aquí salta el PEM Error) ---
st.subheader("🚩 Paso 3: Generar Credenciales Google")
try:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(raw_creds, scopes=scopes)
    st.success("✅ Objeto de Credenciales creado. (¡Si llegaste acá, el PEM es válido!)")
except ValueError as ve:
    st.error(f"❌ Falló Paso 3 (PEM ERROR): {ve}")
    st.warning("Esto significa que la clave privada tiene un caracter inválido.")
    st.stop()
except Exception as e:
    st.error(f"❌ Falló Paso 3 (Otro Error): {e}")
    st.stop()

# --- BANDERÍN 4: AUTORIZAR CLIENTE ---
st.subheader("🚩 Paso 4: Autorizar Cliente GSpread")
try:
    gc = gspread.authorize(credentials)
    st.success("✅ Cliente autorizado exitosamente.")
except Exception as e:
    st.error(f"❌ Falló Paso 4: No se pudo autorizar. {e}")
    st.stop()

# --- BANDERÍN 5: CONECTAR A LA HOJA ---
st.subheader("🚩 Paso 5: Abrir Google Sheet")
try:
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    st.write(f"Intentando abrir: {url}")
    sh = gc.open_by_url(url)
    st.success(f"✅ ¡ÉXITO! Se abrió el archivo: **{sh.title}**")
except gspread.exceptions.APIError as api_err:
    st.error(f"❌ Falló Paso 5 (Permisos): Google rechazó la conexión.")
    st.write("Causa probable: El email del robot no está invitado como Editor.")
    st.write(f"Error técnico: {api_err}")
except Exception as e:
    st.error(f"❌ Falló Paso 5 (No encontrado): {e}")
    st.write("Verificá que el link sea correcto y la hoja exista.")
    st.stop()

# --- BANDERÍN 6: PRUEBA DE ESCRITURA ---
st.subheader("🚩 Paso 6: Prueba de Escritura")
try:
    # Intentamos leer la primera hoja
    worksheet = sh.get_worksheet(0)
    st.write(f"Leyendo hoja: `{worksheet.title}`")
    
    # Prueba de lectura
    val = worksheet.acell('A1').value
    st.info(f"Valor en celda A1: {val}")
    st.success("✅ Lectura OK. Sistema funcionando.")
    
except Exception as e:
    st.error(f"❌ Falló Paso 6: Error leyendo datos. {e}")

st.balloons()
