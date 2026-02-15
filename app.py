import streamlit as st
import pandas as pd
import gspread
import json
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Sistema Villa Soñada 2.0", layout="wide")

# --- CONEXIÓN A GOOGLE SHEETS ---
def conectar_google_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["google_credentials"]["json_content"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    return gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])

# --- FUNCIONES DE BASE DE DATOS ---
def obtener_socios():
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Socios")
        datos = ws.get_all_records()
        df = pd.DataFrame(datos)
        # Convertimos a lista de diccionarios para usar fácil
        return df
    except:
        st.error("⚠️ Falta la hoja 'Socios' en el Excel.")
        return pd.DataFrame()

def cargar_movimientos():
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Movimientos")
        return pd.DataFrame(ws.get_all_records())
    except:
        return pd.DataFrame()

def guardar_lote_movimientos(lista_filas):
    # Esta función guarda MUCHAS filas de una sola vez (para el prorrateo)
    sh = conectar_google_sheet()
    ws = sh.worksheet("Movimientos")
    ws.append_rows(lista_filas)
    st.cache_data.clear()

def guardar_lectura_luz(datos_lectura):
    sh = conectar_google_sheet()
    ws = sh.worksheet("Lecturas")
    ws.append_row(datos_lectura)

# --- INTERFAZ ---
st.title("🏡 Administración Villa Soñada")

# Cargamos socios al inicio
df_socios = obtener_socios()
lista_nombres = df_socios["Nombre"].tolist() if not df_socios.empty else []

# Menú Principal
menu = st.sidebar.selectbox("Ir a:", [
    "1. 📝 Cargar Gastos/Ingresos", 
    "2. ⚡ Medidor de Luz", 
    "3. 📈 Aplicar Intereses/Inflación", 
    "4. 🔍 Cuentas Corrientes",
    "5. 📲 Enviar WhatsApp"
])

# ---------------------------------------------------------
# MÓDULO 1: CARGA DE GASTOS (CON PRORRATEO AUTOMÁTICO)
# ---------------------------------------------------------
if menu == "1. 📝 Cargar Gastos/Ingresos":
    st.header("Cargar Operación")
    
    col1, col2 = st.columns(2)
    with col1:
        fecha = st.date_input("Fecha", datetime.now())
        tipo = st.selectbox("Tipo", ["Gasto (Salida)", "Ingreso (Cobro)"])
    
    with col2:
        monto = st.number_input("Monto Total ($)", min_value=0.0, step=100.0)
    
    concepto = st.text_input("Concepto / Detalle")
    
    if tipo == "Ingreso (Cobro)":
        socio = st.selectbox("¿Quién pagó?", lista_nombres)
        afectacion = "Particular"
    else:
        # Es Gasto
        destino = st.radio("¿A quién corresponde el gasto?", ["General (Dividir entre TODOS)", "Particular (Asignar a UNO)"])
        if "General" in destino:
            socio = "TODOS" # Solo visual
            afectacion = "General"
            st.info(f"ℹ️ Se crearán {len(lista_nombres)} registros de ${monto/20:,.2f} cada uno.")
        else:
            socio = st.selectbox("¿A quién se le cobra?", lista_nombres)
            afectacion = "Particular"

    if st.button("💾 Guardar Operación"):
        with st.spinner("Procesando..."):
            filas_a_guardar = []
            fecha_str = fecha.strftime("%Y-%m-%d")
            
            if afectacion == "General":
                # MAGIA: Prorrateo Automático
                # Creamos 20 filas, una para cada socio
                monto_individual = monto / 20
                for vecino in lista_nombres:
                    # Orden: Fecha, Tipo, Categoria, Socio, Concepto, Monto
                    # Nota: Guardamos como "Egreso" para que sume deuda
                    filas_a_guardar.append([
                        fecha_str, "Egreso", "General Prorrateado", vecino, f"{concepto} (Cuota Parte)", monto_individual
                    ])
            else:
                # Gasto o Ingreso Particular
                tipo_guardar = "Ingreso" if "Ingreso" in tipo else "Egreso"
                filas_a_guardar.append([
                    fecha_str, tipo_guardar, "Particular", socio, concepto, monto
                ])
            
            guardar_lote_movimientos(filas_a_guardar)
            st.success("✅ Operación guardada correctamente.")

# ---------------------------------------------------------
# MÓDULO 2: LUZ
# ---------------------------------------------------------
elif menu == "2. ⚡ Medidor de Luz":
    st.header("Cálculo de Luz Individual")
    
    with st.form("form_luz"):
        col1, col2 = st.columns(2)
        socio_luz = col1.selectbox("Socio", lista_nombres)
        precio_kwh = col2.number_input("Precio por kWh ($)", value=100.0)
        
        lec_ant = col1.number_input("Lectura Anterior", min_value=0)
        lec_act = col2.number_input("Lectura Actual", min_value=0)
        
        consumo = lec_act - lec_ant
        total_luz = consumo * precio_kwh
        
        st.metric("Consumo Calculado", f"{consumo} kWh")
        st.metric("Monto a Cobrar", f"$ {total_luz:,.2f}")
        
        if st.form_submit_button("💾 Guardar y Cargar Deuda"):
            if consumo < 0:
                st.error("¡La lectura actual no puede ser menor a la anterior!")
            else:
                fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                
                # 1. Guardar en Hoja Lecturas (Histórico)
                guardar_lectura_luz([fecha_hoy, socio_luz, lec_ant, lec_act, consumo, precio_kwh, total_luz])
                
                # 2. Guardar en Movimientos (Como deuda/Egreso)
                fila_mov = [fecha_hoy, "Egreso", "Servicios", socio_luz, f"Luz (Consumo: {consumo}kw)", total_luz]
                guardar_lote_movimientos([fila_mov])
                
                st.success(f"✅ Se cargó una deuda de ${total_luz} a {socio_luz}")

# ---------------------------------------------------------
# MÓDULO 3: ACTUALIZACIÓN DEUDA (INTERÉS + INFLACIÓN)
# ---------------------------------------------------------
elif menu == "3. 📈 Aplicar Intereses/Inflación":
    st.header("Ajuste por Mora / Inflación")
    st.warning("⚠️ CUIDADO: Esto generará una nueva deuda a todos los que tengan saldo negativo.")
    
    inflacion = st.number_input("% Inflación Mensual", value=10.0)
    interes = st.number_input("% Interés Punitorio", value=5.0)
    
    factor_total = (inflacion + interes) / 100
    
    if st.button("🔍 Previsualizar Deudores"):
        df = cargar_movimientos()
        df["Monto"] = pd.to_numeric(df["Monto"])
        
        # Calcular saldos
        saldos = {}
        for socio in lista_nombres:
            movs = df[df["Socio"] == socio]
            pagos = movs[movs["Tipo"] == "Ingreso"]["Monto"].sum()
            deudas = movs[movs["Tipo"] == "Egreso"]["Monto"].sum()
            saldo = pagos - deudas
            if saldo < 0: # Solo si debe plata
                saldos[socio] = saldo

        if not saldos:
            st.success("¡Nadie debe nada! No hay nada que ajustar.")
        else:
            st.write("Se aplicarán los siguientes cargos:")
            filas_ajuste = []
            fecha_ajuste = datetime.now().strftime("%Y-%m-%d")
            
            for socio, deuda in saldos.items():
                monto_ajuste = abs(deuda) * factor_total
                st.write(f"- **{socio}**: Debe ${abs(deuda):,.2f} ➡️ Recargo: **${monto_ajuste:,.2f}**")
                
                filas_ajuste.append([
                    fecha_ajuste, "Egreso", "Financiero", socio, 
                    f"Ajuste {inflacion}% Inf + {interes}% Int s/deuda", 
                    round(monto_ajuste, 2)
                ])
            
            if st.button("🔥 APLICAR CARGOS AHORA"):
                guardar_lote_movimientos(filas_ajuste)
                st.balloons()
                st.success("✅ Cargos aplicados exitosamente.")

# ---------------------------------------------------------
# MÓDULO 4: CUENTAS CORRIENTES
# ---------------------------------------------------------
elif menu == "4. 🔍 Cuentas Corrientes":
    st.header("Estado de Cuentas")
    if st.button("🔄 Actualizar"): st.cache_data.clear()
    
    df = cargar_movimientos()
    if not df.empty:
        df["Monto"] = pd.to_numeric(df["Monto"])
        
        vecino = st.selectbox("Ver Vecino", lista_nombres)
        
        # Filtramos
        movs = df[df["Socio"] == vecino].sort_values(by="Fecha", ascending=False)
        
        # Calculamos saldo
        ingresos = movs[movs["Tipo"] == "Ingreso"]["Monto"].sum()
        egresos = movs[movs["Tipo"] == "Egreso"]["Monto"].sum()
        saldo = ingresos - egresos
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Pagado", f"${ingresos:,.0f}")
        col2.metric("Total Gastos/Deuda", f"${egresos:,.0f}")
        col3.metric("Saldo Final", f"${saldo:,.2f}", delta_color="normal" if saldo >= 0 else "inverse")
        
        st.dataframe(movs[["Fecha", "Concepto", "Tipo", "Monto"]], use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 5: WHATSAPP
# ---------------------------------------------------------
elif menu == "5. 📲 Enviar WhatsApp":
    st.header("Generar Mensajes de Cobro")
    
    df = cargar_movimientos()
    if not df.empty:
        df["Monto"] = pd.to_numeric(df["Monto"])
        
        for index, row in df_socios.iterrows():
            nombre = row["Nombre"]
            telefono = str(row["Telefono"]).replace("+", "").replace(" ", "")
            
            # Calculo saldo
            movs = df[df["Socio"] == nombre]
            saldo = movs[movs["Tipo"] == "Ingreso"]["Monto"].sum() - movs[movs["Tipo"] == "Egreso"]["Monto"].sum()
            
            with st.expander(f"{nombre} - Saldo: ${saldo:,.2f}"):
                if saldo < 0:
                    mensaje = f"Hola {nombre}, te paso el resumen de Villa Soñada. Tu saldo actual es de ${saldo:,.2f} (Deuda). Por favor regularizar."
                else:
                    mensaje = f"Hola {nombre}, tu estado de cuenta en Villa Soñada está al día. Saldo a favor: ${saldo:,.2f}."
                
                # Generar link
                link = f"https://wa.me/{telefono}?text={mensaje.replace(' ', '%20')}"
                st.markdown(f"[📲 Enviar WhatsApp a {nombre}]({link})")
                st.text_area("Texto del mensaje", value=mensaje, height=70)
