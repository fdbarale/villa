import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN SIMPLE ---
st.set_page_config(page_title="Mi Cuenta - Villa Soñada", layout="centered")

# --- CONEXIÓN (La misma que tu app admin) ---
def conectar():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        # Usamos los mismos secretos que ya tenés configurados
        creds_dict = dict(st.secrets["service_account"])
        if "\\n" in creds_dict["private_key"]:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(credentials)
        return gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
    except Exception as e:
        st.error("⚠️ Error de conexión o mantenimiento.")
        st.stop()

def cargar_datos():
    sh = conectar()
    # Cargamos Movimientos
    ws = sh.worksheet("Movimientos")
    df = pd.DataFrame(ws.get_all_records())
    
    # Cargamos Socios (Para verificar nombres)
    ws_soc = sh.worksheet("Socios")
    df_soc = pd.DataFrame(ws_soc.get_all_records())
    
    return df, df_soc["Nombre"].tolist()

# --- INTERFAZ VISOR ---
st.title("🏡 Villa Soñada - Estado de Cuenta")

# 1. Recuperar datos
try:
    df, lista_socios = cargar_datos()
except:
    st.error("Error cargando la base de datos.")
    st.stop()

# 2. Sistema de "Login" simple por URL o Selección
# Esto permite que mandes un link tipo: ...app?socio=Garcia
params = st.query_params
vecino_preseleccionado = params.get("socio", None)

if vecino_preseleccionado and vecino_preseleccionado in lista_socios:
    index_socio = lista_socios.index(vecino_preseleccionado)
else:
    index_socio = 0

# Selector (Por si quieren cambiar o entrar sin link)
vecino = st.selectbox("Seleccioná tu Lote/Nombre:", lista_socios, index=index_socio)

# 3. Mostrar la Información
if not df.empty and vecino:
    # Convertir números
    df["Monto"] = pd.to_numeric(df["Monto"])
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    
    # Filtrar solo lo de este vecino
    df_v = df[df["Socio"] == vecino].sort_values(by="Fecha", ascending=False)
    
    if df_v.empty:
        st.info("No tenés movimientos registrados aún.")
    else:
        # Cálculos
        ingresos = df_v[df_v["Tipo"] == "Ingreso"]["Monto"].sum()
        egresos = df_v[df_v["Tipo"] == "Egreso"]["Monto"].sum()
        saldo = ingresos - egresos
        
        # Tarjeta de Saldo
        st.divider()
        col1, col2 = st.columns([2, 1])
        with col1:
            st.caption("Tu saldo actual es:")
            if saldo < 0:
                st.metric("Deuda Pendiente", f"${abs(saldo):,.2f}", delta="- Deuda", delta_color="inverse")
                st.error("⚠️ Tenés saldo pendiente de pago.")
            else:
                st.metric("Saldo a Favor", f"${saldo:,.2f}", delta="Al día")
                st.success("✅ Tu cuenta está al día. ¡Gracias!")
        
        with col2:
            st.caption("Resumen Histórico")
            st.text(f"Pagaste: ${ingresos:,.0f}")
            st.text(f"Gastaste: ${egresos:,.0f}")

        # Tabla de Movimientos
        st.divider()
        st.subheader("📝 Últimos Movimientos")
        
        # Formateamos para que se vea lindo en celular
        df_mostrar = df_v[["Fecha", "Concepto", "Tipo", "Monto"]].copy()
        df_mostrar["Fecha"] = df_mostrar["Fecha"].dt.strftime("%d/%m/%Y")
        
        # Colorear montos (Truco visual)
        def color_monto(val):
            color = 'green' if val > 0 else 'red' # Esto es logica visual, pero mejor usar la columna tipo
            return f'color: {color}'

        st.dataframe(
            df_mostrar, 
            use_container_width=True,
            hide_index=True
        )

# Pie de página
st.markdown("---")
st.caption("Sistema de Transparencia Villa Soñada. Los datos se actualizan en vivo.")
