import streamlit as st
import pandas as pd
from supabase import create_client

# --- CONFIGURACIÓN SIMPLE ---
st.set_page_config(page_title="Mi Cuenta - Villa Soñada", layout="centered")

# --- CONEXIÓN A SUPABASE ---
@st.cache_resource
def conectar_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["service_role_key"]
        return create_client(url, key)
    except Exception as e:
        st.error("⚠️ Error de conexión a la base de datos.")
        st.stop()

def cargar_datos():
    client = conectar_supabase()
    
    # Cargamos Movimientos
    resp_mov = client.table("movimientos").select("*").limit(100000).execute()
    df = pd.DataFrame(resp_mov.data)
    
    if not df.empty:
        df["Fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df["Monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
        df = df.rename(columns={
            "tipo": "Tipo", "categoria": "Categoria",
            "socio": "Socio", "concepto": "Concepto",
        })
        
    # Cargamos Socios (Para verificar nombres del enlace mágico)
    resp_soc = client.table("socios").select("nombre").execute()
    df_soc = pd.DataFrame(resp_soc.data)
    lista_socios = df_soc["nombre"].tolist() if not df_soc.empty else []
    
    return df, lista_socios

# --- INTERFAZ VISOR ---
st.title("🏡 Villa Soñada - Estado de Cuenta")

# 1. Recuperar datos
try:
    df, lista_socios = cargar_datos()
except Exception as e:
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
    # Asegurar tipos por si acaso
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
