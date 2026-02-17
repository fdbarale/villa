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

# 2. LÓGICA DE SEGURIDAD "CANDADO" 🔒
# Verificamos si alguien entró con el enlace mágico
param_socio = st.query_params.get("socio", None)

vecino = None

if param_socio and param_socio in lista_socios:
    # CASO A: Entró con enlace mágico -> BLOQUEAMOS LA VISTA
    vecino = param_socio
    st.success(f"👋 Hola **{vecino}**. Estás viendo tu cuenta exclusiva.")
    # No mostramos el selectbox, así no puede cambiar de vecino
else:
    # CASO B: Entró sin enlace (o nombre incorrecto) -> VISTA ABIERTA (Para el admin)
    st.info("Modo Administrador: Seleccioná un vecino para ver.")
    vecino = st.selectbox("Seleccioná Lote/Nombre:", lista_socios)

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
            st.caption("Estado actual:")
            if saldo < -100: # Tolerancia pequeña
                st.metric("Saldo Pendiente", f"${abs(saldo):,.2f}", delta="- Deuda", delta_color="inverse")
                st.error("⚠️ Tenés saldo pendiente de pago.")
            else:
                st.metric("Saldo a Favor / Al día", f"${saldo:,.2f}", delta="OK")
                st.success("✅ Tu cuenta está al día.")
        
        with col2:
            st.caption("Histórico Total")
            st.text(f"Pagado: ${ingresos:,.0f}")
            st.text(f"Cargado: ${egresos:,.0f}")

        # Tabla de Movimientos
        st.divider()
        st.subheader("📝 Últimos Movimientos")
        
        # Formateamos para que se vea lindo en celular
        df_mostrar = df_v[["Fecha", "Concepto", "Tipo", "Monto"]].copy()
        df_mostrar["Fecha"] = df_mostrar["Fecha"].dt.strftime("%d/%m/%Y")
        
        st.dataframe(
            df_mostrar, 
            use_container_width=True,
            hide_index=True
        )

# Pie de página
st.markdown("---")
st.caption("Sistema de Transparencia Villa Soñada. Datos actualizados en vivo.")
