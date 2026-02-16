import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import urllib.parse
from fpdf import FPDF
import base64

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Villa Soñada", layout="wide")

# --- 1. CONEXIÓN ---
def conectar_google_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["service_account"])
        if "\\n" in creds_dict["private_key"]:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(credentials)
        return gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
    except Exception as e:
        st.error(f"❌ Error de Conexión: {e}")
        st.stop()

# --- 2. FUNCIONES DE DATOS ---
def cargar_movimientos():
    sh = conectar_google_sheet()
    ws = sh.worksheet("Movimientos")
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty:
        df["Fecha"] = pd.to_datetime(df["Fecha"])
        df["Monto"] = pd.to_numeric(df["Monto"])
    return df

def obtener_lista_socios():
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Socios")
        df = pd.DataFrame(ws.get_all_records())
        if not df.empty and "Nombre" in df.columns:
            return df["Nombre"].tolist(), df
        return [], pd.DataFrame()
    except:
        return ["A - Genérico"], pd.DataFrame()

def guardar_lote_movimientos(lista_filas):
    sh = conectar_google_sheet()
    ws = sh.worksheet("Movimientos")
    ws.append_rows(lista_filas)
    st.cache_data.clear()

def obtener_datos_luz_historicos(socio_seleccionado):
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Lecturas")
        df = pd.DataFrame(ws.get_all_records())
        if df.empty: return 0, 100.0
        
        # Precio
        ultimo_precio = float(df.iloc[-1]["Precio_kWh"]) if "Precio_kWh" in df.columns else 100.0
        
        # Lectura
        if "Socio" in df.columns:
            lec = df[df["Socio"] == socio_seleccionado]
            if not lec.empty:
                return int(lec.iloc[-1]["Lectura_Act"]), ultimo_precio
        return 0, ultimo_precio
    except: return 0, 100.0

def guardar_lectura_tecnica(fila):
    sh = conectar_google_sheet()
    sh.worksheet("Lecturas").append_row(fila)

# --- 3. CLASE PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Resumen de Caja - Villa Soñada', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generar_pdf_caja(df, saldo_ini, mes, anio):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, f"Período: {mes}/{anio} | Saldo Inicial: ${saldo_ini:,.2f}", 0, 1)
    
    # Encabezados
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(25, 10, "Fecha", 1, 0, 'C', 1)
    pdf.cell(25, 10, "Tipo", 1, 0, 'C', 1)
    pdf.cell(85, 10, "Concepto", 1, 0, 'C', 1)
    pdf.cell(30, 10, "Monto", 1, 0, 'C', 1)
    pdf.cell(30, 10, "Saldo", 1, 1, 'C', 1)
    
    saldo = saldo_ini
    ing = 0
    egr = 0
    
    for i, row in df.iterrows():
        m = row["Monto"]
        if row["Tipo"] == "Ingreso":
            saldo += m
            ing += m
        else:
            saldo -= m
            egr += m
            
        pdf.cell(25, 10, row["Fecha"].strftime("%d/%m"), 1)
        pdf.cell(25, 10, row["Tipo"], 1)
        pdf.cell(85, 10, str(row["Concepto"])[:45], 1)
        pdf.cell(30, 10, f"${m:,.0f}", 1, 0, 'R')
        pdf.cell(30, 10, f"${saldo:,.0f}", 1, 1, 'R')
        
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Ingresos: ${ing:,.2f} | Egresos: ${egr:,.2f}", 0, 1)
    pdf.cell(0, 10, f"SALDO CIERRE: ${saldo:,.2f}", 0, 1)
    return pdf.output(dest='S').encode('latin-1')

# --- 4. INTERFAZ ---
st.title("🏡 Administración Villa Soñada")
lista_nombres, df_socios_completo = obtener_lista_socios()

# Selector de Fechas (Global)
st.sidebar.header("📅 Filtro de Fecha")
mes_selec = st.sidebar.selectbox("Mes", range(1, 13), index=datetime.now().month - 1)
anio_selec = st.sidebar.number_input("Año", value=datetime.now().year)

# Fechas límite
f_ini = datetime(anio_selec, mes_selec, 1)
if mes_selec == 12: f_fin = datetime(anio_selec + 1, 1, 1)
else: f_fin = datetime(anio_selec, mes_selec + 1, 1)

menu = st.sidebar.radio("Menú:", ["1. 📝 Cargar", "2. ⚡ Luz", "3. 🔍 Cuentas", "4. 📲 WhatsApp", "5. 📄 PDF Caja"])

# --- LÓGICA DE CARGA CORREGIDA ---
if menu == "1. 📝 Cargar":
    st.header("Nueva Operación")
    
    # 1. PARTE INTERACTIVA (FUERA DEL FORMULARIO)
    # Esto permite que al cambiar "Particular", aparezca el socio AL INSTANTE.
    col1, col2 = st.columns(2)
    fecha_op = col1.date_input("Fecha", datetime.now())
    tipo_op = col2.selectbox("Tipo", ["Gasto (Salida)", "Ingreso (Cobro)"])
    
    socio_final = "TODOS" # Valor por defecto
    destino_final = "General"
    monto_prorrateado = 0
    
    if tipo_op == "Ingreso (Cobro)":
        socio_final = st.selectbox("¿Quién paga?", lista_nombres)
        destino_final = "Particular"
    else:
        # Es Gasto
        destino_select = st.radio("Destino del Gasto", ["General (Todos)", "Particular (Uno)"], horizontal=True)
        if "Particular" in destino_select:
            socio_final = st.selectbox("Seleccionar Vecino Afectado", lista_nombres)
            destino_final = "Particular"
        else:
            destino_final = "General"
            cant = len(lista_nombres)
            st.info(f"ℹ️ Se dividirá entre {cant} socios.")

    # 2. PARTE ESTÁTICA (DENTRO DEL FORMULARIO)
    # Aquí cargamos montos y conceptos sin que se recargue la página
    with st.form("form_carga"):
        c1, c2 = st.columns(2)
        monto = c1.number_input("Monto Total ($)", min_value=0.0, step=100.0)
        concepto = c2.text_input("Concepto / Detalle")
        
        submitted = st.form_submit_button("💾 Guardar Operación")
        
        if submitted:
            hoy_str = fecha_op.strftime("%Y-%m-%d")
            filas = []
            
            if destino_final == "General" and tipo_op == "Gasto (Salida)":
                # Prorrateo
                cant = len(lista_nombres)
                indiv = monto / cant if cant > 0 else 0
                for v in lista_nombres:
                    filas.append([hoy_str, "Egreso", "General Prorrateado", v, f"{concepto}", indiv])
            else:
                # Individual
                t_real = "Ingreso" if "Ingreso" in tipo_op else "Egreso"
                filas.append([hoy_str, t_real, destino_final, socio_final, concepto, monto])
            
            guardar_lote_movimientos(filas)
            st.success("✅ Guardado correctamente.")

elif menu == "2. ⚡ Luz":
    st.header("Carga de Luz")
    socio = st.selectbox("Vecino", lista_nombres)
    with st.spinner("Buscando historial..."):
        ant_sug, pr_sug = obtener_datos_luz_historicos(socio)
    st.info(f"Lectura anterior: {ant_sug}")
    
    with st.form("luz"):
        c1, c2 = st.columns(2)
        ant = c1.number_input("Anterior", value=int(ant_sug))
        act = c2.number_input("Actual", min_value=int(ant_sug))
        pr = st.number_input("Precio kWh", value=float(pr_sug))
        
        cons = act - ant
        tot = cons * pr
        st.metric("A Pagar", f"${tot:,.2f}")
        
        if st.form_submit_button("Guardar"):
            hoy = datetime.now().strftime("%Y-%m-%d")
            guardar_lectura_tecnica([hoy, socio, ant, act, cons, pr, tot])
            guardar_lote_movimientos([[hoy, "Egreso", "Luz", socio, f"Luz {cons}kw", tot]])
            st.success("✅ Cargado.")

elif menu == "3. 🔍 Cuentas":
    st.subheader(f"Movimientos: {mes_selec}/{anio_selec}")
    df = cargar_movimientos()
    if not df.empty:
        vecino = st.selectbox("Vecino", lista_nombres)
        df_v = df[df["Socio"] == vecino]
        
        # Saldo Anterior
        mask_ant = df_v["Fecha"] < f_ini
        df_ant = df_v[mask_ant]
        sal_ant = df_ant[df_ant["Tipo"]=="Ingreso"]["Monto"].sum() - df_ant[df_ant["Tipo"]=="Egreso"]["Monto"].sum()
        
        # Mes
        mask_mes = (df_v["Fecha"] >= f_ini) & (df_v["Fecha"] < f_fin)
        df_mes = df_v[mask_mes].sort_values("Fecha")
        
        ing = df_mes[df_mes["Tipo"]=="Ingreso"]["Monto"].sum()
        egr = df_mes[df_mes["Tipo"]=="Egreso"]["Monto"].sum()
        sal_fin = sal_ant + ing - egr
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Saldo Anterior", f"${sal_ant:,.2f}")
        c2.metric("Movimientos Mes", f"${ing - egr:,.2f}")
        c3.metric("Saldo Cierre", f"${sal_fin:,.2f}", delta_color="normal" if sal_fin>=0 else "inverse")
        
        st.dataframe(df_mes[["Fecha", "Concepto", "Tipo", "Monto"]], use_container_width=True)

elif menu == "4. 📲 WhatsApp":
    st.header("Enviar Resumen por WhatsApp")
    df = cargar_movimientos()
    if not df.empty:
        vecino = st.selectbox("Vecino", lista_nombres)
        
        # Calculo exacto igual a Cuentas
        df_v = df[df["Socio"] == vecino]
        mask_ant = df_v["Fecha"] < f_ini
        sal_ant = df_v[mask_ant & (df_v["Tipo"]=="Ingreso")]["Monto"].sum() - df_v[mask_ant & (df_v["Tipo"]=="Egreso")]["Monto"].sum()
        
        mask_mes = (df_v["Fecha"] >= f_ini) & (df_v["Fecha"] < f_fin)
        df_mes = df_v[mask_mes].sort_values("Fecha")
        
        # Armado de texto
        txt = f"*RESUMEN {mes_selec}/{anio_selec}*\nVecino: {vecino}\n"
        txt += f"Saldo Anterior: ${sal_ant:,.2f}\n----------------\n"
        sal_temp = sal_ant
        for i, r in df_mes.iterrows():
            sig = "+" if r["Tipo"]=="Ingreso" else "-"
            m = r["Monto"]
            if r["Tipo"]=="Ingreso": sal_temp+=m
            else: sal_temp-=m
            txt += f"{r['Fecha'].strftime('%d/%m')} {str(r['Concepto'])[:20]}: {sig}${m:,.0f}\n"
        txt += "----------------\n"
        txt += f"*SALDO FINAL: ${sal_temp:,.2f}*"
        
        # Link
        tel = ""
        if not df_socios_completo.empty:
            s = df_socios_completo[df_socios_completo["Nombre"] == vecino]
            if not s.empty: tel = str(s.iloc[0]["Telefono"]).replace("+", "").strip()
            
        link = f"https://wa.me/{tel}?text={urllib.parse.quote(txt)}"
        st.text_area("Vista previa:", txt, height=200)
        st.markdown(f"### 👉 [ENVIAR AHORA]({link})")

elif menu == "5. 📄 PDF Caja":
    st.header(f"Reporte Mensual: {mes_selec}/{anio_selec}")
    df = cargar_movimientos()
    if not df.empty:
        # Saldo Anterior General
        mask_ant = df["Fecha"] < f_ini
        sal_ini = df[mask_ant & (df["Tipo"]=="Ingreso")]["Monto"].sum() - df[mask_ant & (df["Tipo"]=="Egreso")]["Monto"].sum()
        
        mask_mes = (df["Fecha"] >= f_ini) & (df["Fecha"] < f_fin)
        df_mes = df[mask_mes].sort_values("Fecha")
        
        if st.button("Descargar PDF"):
            pdf_data = generar_pdf_caja(df_mes, sal_ini, mes_selec, anio_selec)
            b64 = base64.b64encode(pdf_data).decode()
            href = f'<a href="data:application/octet-stream;base64,{b64}" download="Resumen_{mes_selec}_{anio_selec}.pdf">📥 DESCARGAR PDF</a>'
            st.markdown(href, unsafe_allow_html=True)
            st.success("Generado.")
