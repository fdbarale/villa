import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Gestión Villa Soñada", layout="centered")

# --- LISTA DE SOCIOS (Recuperada de tus archivos) ---
SOCIOS = [
    "A - Garcia Berberena", "B - Sierra Analisa", "C - Fernandez Natalia", 
    "D - Novaretto Emiliano", "E - Calderon José Luis", "F - Rodriguez Matias", 
    "G - Diser Javier", "H - Piñero Silvana", "I - Civale Florencia", 
    "J - Molina Angel", "K - Barale Fernando", "L - Biscayart Bernardo", 
    "M - Garcia Wild Anahi", "N - Mendez Pamela", "O - Guillermo Saul", 
    "P - Justet Luis", "Q - RUIZ DIEGO", "R - Root Silvana", 
    "S - Pathauer Carina", "S - Buss Valeria"
]

# --- FUNCIONES DE BASE DE DATOS (Simulada en CSV) ---
FILE_MOVIMIENTOS = "movimientos_villa_sonada.csv"

def cargar_datos():
    if not os.path.exists(FILE_MOVIMIENTOS):
        # Crear estructura si no existe
        df = pd.DataFrame(columns=["Fecha", "Tipo", "Categoria", "Socio", "Concepto", "Monto"])
        return df
    return pd.read_csv(FILE_MOVIMIENTOS)

def guardar_movimiento(fecha, tipo, categoria, socio, concepto, monto):
    df = cargar_datos()
    nuevo_registro = pd.DataFrame([{
        "Fecha": fecha,
        "Tipo": tipo, # Ingreso / Gasto
        "Categoria": categoria, # General / Particular
        "Socio": socio,
        "Concepto": concepto,
        "Monto": float(monto)
    }])
    df = pd.concat([df, nuevo_registro], ignore_index=True)
    df.to_csv(FILE_MOVIMIENTOS, index=False)
    return True

# --- INTERFAZ GRÁFICA ---
st.title("🏡 Villa Soñada - Gestión")

# Menú lateral
menu = st.sidebar.radio("Ir a:", ["Cargar Movimiento", "Ver Cuentas Corrientes", "Resumen Global"])

# ---------------- PANTALLA 1: CARGA ----------------
if menu == "Cargar Movimiento":
    st.header("📝 Nuevo Movimiento")
    
    tipo = st.selectbox("¿Qué vas a cargar?", ["Gasto (Salida de dinero)", "Ingreso (Cobro a Vecino)"])
    
    with st.form("form_carga"):
        fecha = st.date_input("Fecha", datetime.now())
        
        if tipo == "Ingreso (Cobro a Vecino)":
            socio = st.selectbox("Seleccionar Vecino", SOCIOS)
            categoria = "Particular"
            concepto = st.text_input("Concepto (Ej: Expensas Febrero)", "Expensas Mes Actual")
            monto = st.number_input("Monto Cobrado ($)", min_value=0.0, step=100.0)
            
        else: # Es Gasto
            tipo_gasto = st.radio("Tipo de Gasto", ["General (Se divide entre todos)", "Particular (Se cobra a uno solo)"])
            if tipo_gasto == "Particular (Se cobra a uno solo)":
                socio = st.selectbox("¿A quién se le carga?", SOCIOS)
                categoria = "Particular"
            else:
                socio = "TODOS"
                categoria = "General"
            
            concepto = st.text_input("Concepto (Ej: Luz, Corte pasto)", "")
            monto = st.number_input("Monto Gasto ($)", min_value=0.0, step=100.0)

        # Botón de Guardar
        submitted = st.form_submit_button("💾 Guardar Movimiento")
        
        if submitted:
            guardar_movimiento(fecha, "Ingreso" if "Ingreso" in tipo else "Egreso", categoria, socio, concepto, monto)
            st.success("✅ ¡Guardado correctamente!")

# ---------------- PANTALLA 2: CUENTAS CORRIENTES ----------------
elif menu == "Ver Cuentas Corrientes":
    st.header("🔎 Estado de Cuenta por Vecino")
    
    vecino_seleccionado = st.selectbox("Ver cuenta de:", SOCIOS)
    
    df = cargar_datos()
    
    if not df.empty:
        # Lógica de cálculo
        # 1. Filtramos movimientos directos del socio
        movs_socio = df[df["Socio"] == vecino_seleccionado].copy()
        
        # 2. Buscamos gastos generales y calculamos su parte (1/20)
        movs_generales = df[df["Socio"] == "TODOS"].copy()
        if not movs_generales.empty:
            movs_generales["Monto"] = movs_generales["Monto"] / 20 # Prorrateo
            movs_generales["Concepto"] = movs_generales["Concepto"] + " (Prorrateo General)"
            
        # 3. Unimos todo
        cuenta_final = pd.concat([movs_socio, movs_generales]).sort_values(by="Fecha")
        
        # 4. Signos: Si es Ingreso resta deuda (verde), si es Gasto suma deuda (rojo)
        # Para visualizar: Saldo negativo es a favor del consorcio (debe pagar)
        
        st.write(f"Movimientos de **{vecino_seleccionado}**:")
        st.dataframe(cuenta_final[["Fecha", "Tipo", "Concepto", "Monto"]])
        
        # Cálculo de saldo simple
        pagos = cuenta_final[cuenta_final["Tipo"] == "Ingreso"]["Monto"].sum()
        cargos = cuenta_final[cuenta_final["Tipo"] == "Egreso"]["Monto"].sum()
        saldo = pagos - cargos
        
        st.metric("Saldo Actual (Negativo es Deuda)", f"$ {saldo:,.2f}")
        
    else:
        st.info("Aún no hay movimientos cargados.")

# ---------------- PANTALLA 3: RESUMEN ----------------
elif menu == "Resumen Global":
    st.header("📊 Caja del Consorcio")
    df = cargar_datos()
    if not df.empty:
        total_ingresos = df[df["Tipo"] == "Ingreso"]["Monto"].sum()
        total_gastos = df[df["Tipo"] == "Egreso"]["Monto"].sum() # Gastos totales reales, no prorrateados
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Ingresos", f"$ {total_ingresos:,.0f}")
        col2.metric("Total Gastos", f"$ {total_gastos:,.0f}")
        col3.metric("Caja Actual", f"$ {total_ingresos - total_gastos:,.0f}")
        
        st.subheader("Últimos movimientos")
        st.dataframe(df.tail(10))
