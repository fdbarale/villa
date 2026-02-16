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
        
        ultimo_precio = float(df.iloc[-1]["Precio_kWh"]) if "Precio_kWh" in df.columns else 100.0
        
        if "Socio" in df.columns:
            lec = df[df["Socio"] == socio_seleccionado]
            if not lec.empty:
                return int(lec.iloc[-1]["Lectura_Act"]), ultimo_precio
        return 0, ultimo_precio
    except: return 0, 100.0

def guardar_lectura_tecnica(fila):
    sh = conectar_google_sheet()
    sh.worksheet("Lecturas").append_row(fila)

# --- 3. CLASE PDF AVANZADA ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Administración Villa Soñada', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, 'Informe de Caja y Estado Financiero', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generar_pdf_caja(df, saldo_ini, mes, anio, lista_socios):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # 1. ENCABEZADO CAJA
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"1. MOVIMIENTOS DE CAJA (REAL) - {mes}/{anio}", 0, 1)
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, f"Saldo Inicial al comenzar el mes: ${saldo_ini:,.2f}", 0, 1)
    
    # Tabla Caja
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(25, 8, "Fecha", 1, 0, 'C', 1)
    pdf.cell(85, 8, "Detalle", 1, 0, 'C', 1)
    pdf.cell(25, 8, "Entrada", 1, 0, 'C', 1)
    pdf.cell(25, 8, "Salida", 1, 0, 'C', 1)
    pdf.cell(30, 8, "Saldo Parcial", 1, 1, 'C', 1)
    
    saldo = saldo_ini
    tot_ing = 0
    tot_egr = 0
    
    # Filtramos: Solo Ingresos reales y Gastos Globales (SOCIEDAD_GASTOS)
    # Excluimos las cuotas partes individuales para no ensuciar la caja
    for i, row in df.iterrows():
        # Lógica de Caja: Entra todo cobro, sale todo gasto marcado como SOCIEDAD
        es_gasto_real = (row["Socio"] == "SOCIEDAD_GASTOS") or (row["Categoria"] == "Gasto Real")
        es_ingreso_real = (row["Tipo"] == "Ingreso")
        
        if es_gasto_real or es_ingreso_real:
            m = row["Monto"]
            entrada = m if es_ingreso_real else 0
            salida = m if es_gasto_real else 0
            
            saldo += entrada - salida
            tot_ing += entrada
            tot_egr += salida
            
            concepto = str(row["Concepto"])[:40]
            if es_ingreso_real: concepto = f"Pago: {row['Socio']} ({concepto})"
            
            pdf.cell(25, 8, row["Fecha"].strftime("%d/%m"), 1)
            pdf.cell(85, 8, concepto, 1)
            pdf.cell(25, 8, f"${entrada:,.0f}" if entrada > 0 else "-", 1, 0, 'R')
            pdf.cell(25, 8, f"${salida:,.0f}" if salida > 0 else "-", 1, 0, 'R')
            pdf.cell(30, 8, f"${saldo:,.0f}", 1, 1, 'R')

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, f"TOTAL INGRESOS: ${tot_ing:,.2f} | TOTAL GASTOS: ${tot_egr:,.2f}", 0, 1)
    pdf.cell(0, 10, f"SALDO CIERRE DE CAJA: ${saldo:,.2f}", 0, 1)
    pdf.ln(10)

    # 2. LISTADO DE DEUDORES
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"2. ESTADO DE DEUDAS (Al cierre del reporte)", 0, 1)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(80, 8, "Socio / Vecino", 1, 0, 'C', 1)
    pdf.cell(40, 8, "Saldo a Favor", 1, 0, 'C', 1)
    pdf.cell(40, 8, "Deuda Total", 1, 1, 'C', 1)
    
    pdf.set_font("Arial", size=10)
    
    # Recalculamos saldos históricos totales de TODOS los movimientos para ver deuda actual
    df_full = cargar_movimientos() # Cargamos todo sin filtro de fecha para ver la deuda real
    
    hay_deuda = False
    for vecino in lista_socios:
        movs = df_full[df_full["Socio"] == vecino]
        ing = movs[movs["Tipo"] == "Ingreso"]["Monto"].sum()
        egr = movs[movs["Tipo"] == "Egreso"]["Monto"].sum()
        saldo_vecino = ing - egr
        
        if saldo_vecino < -100: # Tolerancia $100
            hay_deuda = True
            pdf.set_text_color(180, 0, 0) # Rojo
            pdf.cell(80, 8, vecino, 1)
            pdf.cell(40, 8, "-", 1, 0, 'C')
            pdf.cell(40, 8, f"${abs(saldo_vecino):,.2f}", 1, 1, 'R')
            pdf.set_text_color(0, 0, 0)
    
    if not hay_deuda:
        pdf.cell(160, 8, "¡Felicitaciones! No hay deudas registradas.", 1, 1, 'C')
        
    return pdf.output(dest='S').encode('latin-1')

# --- 4. INTERFAZ ---
st.title("🏡 Administración Villa Soñada")
lista_nombres, df_socios_completo = obtener_lista_socios()

# Selector de Fechas (Global)
st.sidebar.header("📅 Filtro de Fecha")
mes_selec = st.sidebar.selectbox("Mes", range(1, 13), index=datetime.now().month - 1)
anio_selec = st.sidebar.number_input("Año", value=datetime.now().year)

f_ini = datetime(anio_selec, mes_selec, 1)
if mes_selec == 12: f_fin = datetime(anio_selec + 1, 1, 1)
else: f_fin = datetime(anio_selec, mes_selec + 1, 1)

menu = st.sidebar.radio("Menú:", ["1. 📝 Cargar", "2. ⚡ Luz", "3. 🔍 Cuentas", "4. 📲 WhatsApp", "5. 📄 PDF Mensual"])

# --- MÓDULO 1: CARGA (SIN FORMULARIO / SIN ENTER AUTOMÁTICO) ---
if menu == "1. 📝 Cargar":
    st.header("Nueva Operación")
    
    # Inputs directos (No st.form, para evitar que Enter envíe)
    col1, col2 = st.columns(2)
    fecha_op = col1.date_input("Fecha", datetime.now())
    tipo_op = col2.selectbox("Tipo", ["Gasto (Salida)", "Ingreso (Cobro)"])
    
    socio_final = "TODOS"
    destino_final = "General"
    
    # Lógica de selectores condicionales
    if tipo_op == "Ingreso (Cobro)":
        socio_final = st.selectbox("¿Quién paga?", lista_nombres)
        destino_final = "Particular"
    else:
        # Gasto
        modo_gasto = st.radio("Destino", ["General (Sociedad)", "Particular (Vecino)"], horizontal=True)
        if "Particular" in modo_gasto:
            socio_final = st.selectbox("Vecino Afectado", lista_nombres)
            destino_final = "Particular"
        else:
            destino_final = "General"
            st.info(f"ℹ️ Esto generará:\n1. Un egreso en la Caja de la Sociedad.\n2. Una deuda dividida entre {len(lista_nombres)} vecinos.")

    c1, c2 = st.columns(2)
    monto = c1.number_input("Monto Total ($)", min_value=0.0, step=100.0)
    concepto = c2.text_input("Concepto / Detalle")
    
    st.write("---")
    
    # Botón único de guardado
    if st.button("💾 CONFIRMAR Y GUARDAR"):
        if monto <= 0:
            st.error("El monto debe ser mayor a 0")
        else:
            hoy_str = fecha_op.strftime("%Y-%m-%d")
            filas = []
            
            # --- LÓGICA DE DOBLE IMPUTACIÓN ---
            if destino_final == "General" and tipo_op == "Gasto (Salida)":
                # 1. Asiento en la CAJA (Para el PDF de la Sociedad)
                # Usamos un socio ficticio "SOCIEDAD_GASTOS" para identificar salida de caja real
                filas.append([hoy_str, "Egreso", "Gasto Real", "SOCIEDAD_GASTOS", concepto, monto])
                
                # 2. Asiento en los VECINOS (Generación de Deuda)
                cant = len(lista_nombres)
                indiv = monto / cant if cant > 0 else 0
                for v in lista_nombres:
                    filas.append([hoy_str, "Egreso", "Cuota Parte", v, f"Parte de: {concepto}", indiv])
                    
                st.success(f"✅ Se registró el gasto de ${monto} en la caja y se dividió en cuotas de ${indiv:,.2f}")

            else:
                # Carga Simple (Ingreso o Gasto Particular)
                t_real = "Ingreso" if "Ingreso" in tipo_op else "Egreso"
                filas.append([hoy_str, t_real, destino_final, socio_final, concepto, monto])
                st.success("✅ Operación particular guardada.")
            
            guardar_lote_movimientos(filas)

# --- MÓDULO 2: LUZ (SIN FORMULARIO) ---
elif menu == "2. ⚡ Luz":
    st.header("Carga de Luz")
    socio = st.selectbox("Vecino", lista_nombres)
    
    # Botón para buscar (para que no busque en cada recarga)
    if 'luz_sug' not in st.session_state: st.session_state.luz_sug = 0
    
    if st.button("🔍 Buscar Lectura Anterior"):
        ant, pr = obtener_datos_luz_historicos(socio)
        st.session_state.luz_ant_val = int(ant)
        st.session_state.luz_pr_val = float(pr)
        st.rerun()

    c1, c2 = st.columns(2)
    # Usamos valores de session_state si existen, sino 0
    val_ant = st.session_state.get('luz_ant_val', 0)
    val_pr = st.session_state.get('luz_pr_val', 100.0)
    
    ant = c1.number_input("Anterior", value=val_ant)
    act = c2.number_input("Actual", min_value=val_ant)
    pr = st.number_input("Precio kWh", value=val_pr)
    
    cons = act - ant
    tot = cons * pr
    st.metric("A Pagar", f"${tot:,.2f}")
    
    if st.button("💾 Guardar Luz"):
        hoy = datetime.now().strftime("%Y-%m-%d")
        guardar_lectura_tecnica([hoy, socio, ant, act, cons, pr, tot])
        guardar_lote_movimientos([[hoy, "Egreso", "Luz", socio, f"Luz {cons}kw", tot]])
        st.success("✅ Cargado.")

# --- MÓDULO 3: CUENTAS ---
elif menu == "3. 🔍 Cuentas":
    st.subheader(f"Movimientos: {mes_selec}/{anio_selec}")
    df = cargar_movimientos()
    if not df.empty:
        vecino = st.selectbox("Vecino", lista_nombres)
        df_v = df[df["Socio"] == vecino]
        
        # Filtros de fecha
        mask_ant = df_v["Fecha"] < f_ini
        df_ant = df_v[mask_ant]
        sal_ant = df_ant[df_ant["Tipo"]=="Ingreso"]["Monto"].sum() - df_ant[df_ant["Tipo"]=="Egreso"]["Monto"].sum()
        
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

# --- MÓDULO 4: WHATSAPP ---
elif menu == "4. 📲 WhatsApp":
    st.header("Enviar Resumen")
    df = cargar_movimientos()
    if not df.empty:
        vecino = st.selectbox("Vecino", lista_nombres)
        df_v = df[df["Socio"] == vecino]
        
        mask_ant = df_v["Fecha"] < f_ini
        sal_ant = df_v[mask_ant & (df_v["Tipo"]=="Ingreso")]["Monto"].sum() - df_v[mask_ant & (df_v["Tipo"]=="Egreso")]["Monto"].sum()
        
        mask_mes = (df_v["Fecha"] >= f_ini) & (df_v["Fecha"] < f_fin)
        df_mes = df_v[mask_mes].sort_values("Fecha")
        
        txt = f"*RESUMEN {mes_selec}/{anio_selec}*\nVecino: {vecino}\n"
        txt += f"Saldo Anterior: ${sal_ant:,.2f}\n----------------\n"
        sal_temp = sal_ant
        for i, r in df_mes.iterrows():
            sig = "+" if r["Tipo"]=="Ingreso" else "-"
            m = r["Monto"]
            if r["Tipo"]=="Ingreso": sal_temp+=m
            else: sal_temp-=m
            txt += f"{r['Fecha'].strftime('%d/%m')} {str(r['Concepto'])[:15]}: {sig}${m:,.0f}\n"
        txt += "----------------\n"
        txt += f"*SALDO FINAL: ${sal_temp:,.2f}*"
        
        tel = ""
        if not df_socios_completo.empty:
            s = df_socios_completo[df_socios_completo["Nombre"] == vecino]
            if not s.empty: tel = str(s.iloc[0]["Telefono"]).replace("+", "").strip()
            
        link = f"https://wa.me/{tel}?text={urllib.parse.quote(txt)}"
        st.text_area("Mensaje:", txt, height=200)
        st.markdown(f"### 👉 [ENVIAR AHORA]({link})")

# --- MÓDULO 5: PDF CAJA ---
elif menu == "5. 📄 PDF Mensual":
    st.header(f"Informe Financiero: {mes_selec}/{anio_selec}")
    st.info("Este informe contiene: 1. Movimientos reales de la Caja de la Sociedad. 2. Lista de vecinos con Deuda.")
    
    df = cargar_movimientos()
    if not df.empty:
        # Calcular Saldo de CAJA (No de vecinos)
        # Filtramos solo movimientos reales: SOCIEDAD_GASTOS o INGRESOS
        mask_caja = (df["Socio"] == "SOCIEDAD_GASTOS") | (df["Tipo"] == "Ingreso")
        df_caja = df[mask_caja]
        
        # Saldo Anterior de Caja
        mask_ant = df_caja["Fecha"] < f_ini
        ing_ant = df_caja[mask_ant & (df_caja["Tipo"]=="Ingreso")]["Monto"].sum()
        egr_ant = df_caja[mask_ant & (df_caja["Tipo"]=="Egreso")]["Monto"].sum()
        sal_ini_caja = ing_ant - egr_ant
        
        # Movimientos del mes para el PDF
        mask_mes = (df["Fecha"] >= f_ini) & (df["Fecha"] < f_fin)
        df_mes_completo = df[mask_mes].sort_values("Fecha") 
        
        if st.button("🖨️ Generar Informe PDF"):
            # Le pasamos el DF completo del mes, la función del PDF se encarga de filtrar
            # qué mostrar en la tabla y qué mostrar en la lista de deudores
            pdf_data = generar_pdf_caja(df_mes_completo, sal_ini_caja, mes_selec, anio_selec, lista_nombres)
            
            b64 = base64.b64encode(pdf_data).decode()
            href = f'<a href="data:application/octet-stream;base64,{b64}" download="Informe_Villa_{mes_selec}_{anio_selec}.pdf">📥 DESCARGAR PDF</a>'
            st.markdown(href, unsafe_allow_html=True)
            st.success("Informe generado exitosamente.")
