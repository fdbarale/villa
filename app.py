import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestión Villa Soñada", layout="centered")

# Lista de Socios
SOCIOS = [
    "A - Garcia Berberena", "B - Sierra Analisa", "C - Fernandez Natalia", 
    "D - Novaretto Emiliano", "E - Calderon José Luis", "F - Rodriguez Matias", 
    "G - Diser Javier", "H - Piñero Silvana", "I - Civale Florencia", 
    "J - Molina Angel", "K - Barale Fernando", "L - Biscayart Bernardo", 
    "M - Garcia Wild Anahi", "N - Mendez Pamela", "O - Guillermo Saul", 
    "P - Justet Luis", "Q - RUIZ DIEGO", "R - Root Silvana", 
    "S - Pathauer Carina", "S - Buss Valeria"
]

# --- CONEXIÓN CON GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos():
    # Lee la hoja "Movimientos" y evita caché viejo
    return conn.read(worksheet="Movimientos", ttl=0)

def guardar_movimiento(fecha, tipo, categoria, socio, concepto, monto):
    # 1. Traemos los datos actuales
    df_actual = cargar_datos()
    
    # 2. Creamos la nueva fila
    nueva_fila = pd.DataFrame([{
        "Fecha": fecha.strftime("%Y-%m-%d"),
        "Tipo": tipo,
        "Categoria": categoria,
        "Socio": socio,
        "Concepto": concepto,
        "Monto": float(monto)
    }])
    
    # 3. Unimos (Append)
    df_actualizado = pd.concat([df_actual, nueva_fila], ignore_index=True)
    
    # 4. Subimos todo a Google Sheets
    conn.update(worksheet="Movimientos", data=df_actualizado)
    st.cache_data.clear() # Limpiamos memoria para ver el cambio ya
    return True

# --- INTERFAZ GRÁFICA ---
st.title("🏡 Villa Soñada - Nube")

menu = st.sidebar.radio("Ir a:", ["Cargar Movimiento", "Ver Cuentas", "Resumen Caja"])

if menu == "Cargar Movimiento":
    st.header("📝 Nuevo Movimiento")
    tipo = st.selectbox("Operación", ["Gasto (Salida)", "Ingreso (Cobro)"])
    
    with st.form("form_carga"):
        fecha = st.date_input("Fecha", datetime.now())
        
        if "Ingreso" in tipo:
            socio = st.selectbox("Vecino", SOCIOS)
            categoria = "Particular"
            concepto = st.text_input("Detalle", "Expensas")
            monto = st.number_input("Monto $", min_value=0.0, step=100.0)
        else:
            tipo_gasto = st.radio("Destino", ["General (Todos)", "Particular (Uno)"])
            socio = st.selectbox("Vecino", SOCIOS) if "Particular" in tipo_gasto else "TODOS"
            categoria = "Particular" if "Particular" in tipo_gasto else "General"
            concepto = st.text_input("Detalle", "")
            monto = st.number_input("Monto $", min_value=0.0, step=100.0)

        if st.form_submit_button("💾 Guardar en Drive"):
            with st.spinner("Guardando en la nube..."):
                guardar_movimiento(fecha, "Ingreso" if "Ingreso" in tipo else "Egreso", categoria, socio, concepto, monto)
            st.success("¡Guardado! Revisá tu Google Sheet.")

elif menu == "Ver Cuentas":
    st.header("🔎 Cuenta Corriente")
    vecino = st.selectbox("Vecino", SOCIOS)
    
    df = cargar_datos()
    if not df.empty:
        # Lógica de prorrateo
        df["Monto"] = pd.to_numeric(df["Monto"])
        movs_socio = df[df["Socio"] == vecino].copy()
        movs_gral = df[df["Socio"] == "TODOS"].copy()
        
        if not movs_gral.empty:
            movs_gral["Monto"] = movs_gral["Monto"] / 20
            movs_gral["Concepto"] += " (Prorrateo)"
        
        final = pd.concat([movs_socio, movs_gral]).sort_values("Fecha")
        st.dataframe(final)
        
        pagos = final[final["Tipo"] == "Ingreso"]["Monto"].sum()
        gastos = final[final["Tipo"] == "Egreso"]["Monto"].sum()
        st.metric("Saldo (Negativo = Deuda)", f"$ {pagos - gastos:,.2f}")

elif menu == "Resumen Caja":
    st.header("📊 Estado del Consorcio")
    df = cargar_datos()
    if not df.empty:
        ingresos = df[df["Tipo"] == "Ingreso"]["Monto"].sum()
        egresos = df[df["Tipo"] == "Egreso"]["Monto"].sum()
        st.metric("Caja Real", f"$ {ingresos - egresos:,.2f}")
        st.dataframe(df)
