import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, timedelta
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
        df = df[df["Fecha"].astype(str).str.strip() != ""]
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
        df = df.dropna(subset=["Fecha"])
        df["Monto"] = pd.to_numeric(df["Monto"], errors="coerce").fillna(0)
        
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

def guardar_lectura_tecnica(fila):
    sh = conectar_google_sheet()
    sh.worksheet("Lecturas").append_row(fila)

def obtener_lectura_anterior(socio):
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Lecturas")
        df = pd.DataFrame(ws.get_all_records())
        if df.empty or "Socio" not in df.columns: return 0
        df_s = df[df["Socio"] == socio]
        if df_s.empty: return 0
        return int(df_s.iloc[-1]["Lectura_Act"])
    except: return 0

# --- CONFIGURACIÓN ---
def obtener_configuracion():
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Configuracion")
        data = ws.get_all_records()
        config = {row['Parametro']: row['Valor'] for row in data}
        return config
    except:
        return {'Precio_KWH': 100.0, 'Inflacion_Mensual': 10.0}

def guardar_configuracion(precio_kwh, inflacion):
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Configuracion")
        ws.update_acell('B2', float(precio_kwh))
        ws.update_acell('B3', float(inflacion))
        st.cache_data.clear()
        st.toast("✅ Configuración guardada correctamente")
    except Exception as e:
        st.error(f"Error guardando config: {e}")

# --- 3. CLASE PDF CON LOGO ---
class PDF(FPDF):
    def header(self):
        try:
            self.image('logo.png', 10, 8, 30)
        except:
            pass 

        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Administración Villa Soñada', 0, 1, 'C')
        self.set_font('Arial', 'I', 9)
        self.cell(0, 10, 'Informe Mensual y Estado de Cuentas', 0, 1, 'C')
        self.ln(15)
        
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generar_pdf_caja(df, saldo_ini, mes, anio, lista_socios):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # 1. CAJA REAL
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, f"1. MOVIMIENTOS REALES (CAJA) - {mes}/{anio}", 0, 1)
    pdf.set_font("Arial", size=9)
    pdf.cell(0, 8, f"Saldo Inicial de Caja: ${saldo_ini:,.2f}", 0, 1)
    
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(20, 8, "Fecha", 1, 0, 'C', 1)
    pdf.cell(90, 8, "Detalle", 1, 0, 'C', 1)
    pdf.cell(25, 8, "Ingreso", 1, 0, 'C', 1)
    pdf.cell(25, 8, "Egreso", 1, 0, 'C', 1)
    pdf.cell(25, 8, "Saldo", 1, 1, 'C', 1)
    
    saldo = saldo_ini
    tot_ing = 0
    tot_egr = 0
    
    for i, row in df.iterrows():
        # Filtro estricto para que la caja real no se contamine con los créditos figurativos
        es_gasto_caja = (row["Socio"] == "SOCIEDAD_GASTOS") and (row["Categoria"] == "Gasto Real")
        es_ingreso = (row["Tipo"] == "Ingreso") and (row["Categoria"] != "Crédito Especial")
        
        if es_gasto_caja or es_ingreso:
            m = row["Monto"]
            ent = m if es_ingreso else 0
            sal = m if es_gasto_caja else 0
            saldo += ent - sal
            tot_ing += ent
            tot_egr += sal
            
            det = str(row["Concepto"])[:45]
            if es_ingreso: det = f"Pago: {row['Socio']} ({det})"
            
            pdf.cell(20, 8, row["Fecha"].strftime("%d/%m"), 1)
            pdf.cell(90, 8, det, 1)
            pdf.cell(25, 8, f"{ent:,.0f}" if ent>0 else "-", 1, 0, 'R')
            pdf.cell(25, 8, f"{sal:,.0f}" if sal>0 else "-", 1, 0, 'R')
            pdf.cell(25, 8, f"{saldo:,.0f}", 1, 1, 'R')

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, f"TOTAL INGRESOS: ${tot_ing:,.2f} | TOTAL EGRESOS: ${tot_egr:,.2f}", 0, 1)
    pdf.cell(0, 8, f"SALDO CIERRE CAJA: ${saldo:,.2f}", 0, 1)
    
    # 2. GASTOS INTERNOS Y PRORRATEOS (Acá va el alambrado!)
    df_internos = df[(df["Socio"] == "SOCIEDAD_GASTOS") & (df["Categoria"] == "Gasto Interno")]
    if not df_internos.empty:
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 10, f"2. GASTOS INTERNOS Y PRORRATEOS (No afectan efectivo)", 0, 1)
        pdf.set_font("Arial", size=9)
        pdf.cell(0, 8, "Estos montos fueron divididos y cargados a las cuentas de los vecinos:", 0, 1)
        
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(25, 8, "Fecha", 1, 0, 'C', 1)
        pdf.cell(115, 8, "Detalle", 1, 0, 'C', 1)
        pdf.cell(50, 8, "Monto Total", 1, 1, 'C', 1)
        
        for i, row in df_internos.iterrows():
            pdf.cell(25, 8, row["Fecha"].strftime("%d/%m"), 1)
            det = str(row["Concepto"])[:60]
            pdf.cell(115, 8, det, 1)
            pdf.cell(50, 8, f"${row['Monto']:,.2f}", 1, 1, 'R')
            
    # 3. DEUDORES
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, f"ESTADO DE DEUDAS (Financiero)", 0, 1)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(70, 8, "Vecino", 1, 0, 'C', 1)
    pdf.cell(40, 8, "Saldo a Favor", 1, 0, 'C', 1)
    pdf.cell(40, 8, "Deuda Total", 1, 1, 'C', 1)
    pdf.set_font("Arial", size=9)
    
    df_full = cargar_movimientos()
    hay_deuda = False
    for vec in lista_socios:
        m = df_full[df_full["Socio"] == vec]
        s_neto = m[m["Tipo"]=="Ingreso"]["Monto"].sum() - m[m["Tipo"]=="Egreso"]["Monto"].sum()
        
        if s_neto < -100:
            hay_deuda = True
            pdf.set_text_color(180, 0, 0)
            pdf.cell(70, 8, vec, 1)
            pdf.cell(40, 8, "-", 1, 0, 'C')
            pdf.cell(40, 8, f"${abs(s_neto):,.2f}", 1, 1, 'R')
            pdf.set_text_color(0, 0, 0)
    
    if not hay_deuda: pdf.cell(150, 8, "Sin deudas registradas.", 1, 1, 'C')
    return pdf.output(dest='S').encode('latin-1')

# --- 4. INTERFAZ ---
st.title("🏡 Administración Villa Soñada")
lista_nombres, df_socios_completo = obtener_lista_socios()

# --- SELECTOR DE FECHA ---
st.sidebar.subheader("📅 Período de Trabajo")
mes_selec = st.sidebar.selectbox("Mes", range(1, 13), index=datetime.now().month - 1)
anio_selec = st.sidebar.number_input("Año", value=datetime.now().year)

f_ini = datetime(anio_selec, mes_selec, 1)
if mes_selec == 12: f_fin = datetime(anio_selec + 1, 1, 1)
else: f_fin = datetime(anio_selec, mes_selec + 1, 1)

# Configuración Inicial
config_actual = obtener_configuracion()
PRECIO_KWH = float(config_actual.get('Precio_KWH', 100.0))
INFLACION_MENSUAL = float(config_actual.get('Inflacion_Mensual', 10.0))

# --- MENÚ PRINCIPAL ---
menu = st.sidebar.radio("Menú:", [
    "1. 📝 Cargar Op.", 
    "2. ⚡ Luz", 
    "3. 📈 Cálculo Intereses", 
    "4. ⚖️ Movimientos Especiales", 
    "5. 🔍 Cuentas", 
    "6. 📲 WhatsApp", 
    "7. 📄 PDF",
    "8. ⚙️ Configuración"
])

# --- MÓDULO 1: CARGA ---
if menu == "1. 📝 Cargar Op.":
    st.header("Cargar Gastos o Ingresos")
    c1, c2 = st.columns(2)
    fecha_op = c1.date_input("Fecha", datetime.now())
    tipo_op = c2.selectbox("Tipo", ["Gasto (Salida)", "Ingreso (Cobro)"])
    
    socio = "TODOS"
    destino = "General"
    
    if tipo_op == "Ingreso (Cobro)":
        socio = st.selectbox("¿Quién paga?", lista_nombres)
        destino = "Particular"
    else:
        modo = st.radio("Destino", ["General (Sociedad)", "Particular (Vecino)"], horizontal=True)
        if "Particular" in modo:
            socio = st.selectbox("Vecino", lista_nombres)
            destino = "Particular"
        else:
            destino = "General"
            st.info(f"ℹ️ Se divide entre {len(lista_nombres)} socios.")

    c1, c2 = st.columns(2)
    monto = c1.number_input("Monto ($)", min_value=0.0, step=100.0)
    concepto = c2.text_input("Concepto")
    
    st.write("---")
    if st.button("💾 CONFIRMAR Y GUARDAR"):
        hoy_str = fecha_op.strftime("%Y-%m-%d")
        filas = []
        
        if destino == "General" and tipo_op == "Gasto (Salida)":
            filas.append([hoy_str, "Egreso", "Gasto Real", "SOCIEDAD_GASTOS", concepto, monto])
            cuota = monto / len(lista_nombres)
            for v in lista_nombres:
                filas.append([hoy_str, "Egreso", "Cuota Parte", v, f"Parte de: {concepto}", cuota])
            st.success("✅ Gasto General guardado y prorrateado.")
        else:
            tr = "Ingreso" if "Ingreso" in tipo_op else "Egreso"
            filas.append([hoy_str, tr, destino, socio, concepto, monto])
            st.success("✅ Operación guardada.")
            
        guardar_lote_movimientos(filas)

# --- MÓDULO 2: LUZ ---
elif menu == "2. ⚡ Luz":
    st.header("Carga de Luz")
    st.info(f"Precio del kWh actual: **${PRECIO_KWH}** (Configurado en Menú 8)")
    
    fecha_luz = st.date_input("Fecha de Registro", datetime.now())
    socio = st.selectbox("Vecino", lista_nombres)
    
    if 'luz_ant' not in st.session_state: st.session_state.luz_ant = 0
    if st.button("🔍 Buscar Anterior"):
        st.session_state.luz_ant = obtener_lectura_anterior(socio)
        st.rerun()

    ant = st.number_input("Anterior", value=st.session_state.luz_ant)
    act = st.number_input("Actual", min_value=st.session_state.luz_ant)
    pr = st.number_input("Precio kWh", value=PRECIO_KWH, disabled=True)
    
    cons = act - ant
    tot = cons * pr
    st.metric("A Pagar", f"${tot:,.2f}")
    
    if st.button("💾 Guardar Luz"):
        hoy = fecha_luz.strftime("%Y-%m-%d")
        guardar_lectura_tecnica([hoy, socio, ant, act, cons, pr, tot])
        guardar_lote_movimientos([[hoy, "Egreso", "Luz", socio, f"Luz {cons}kw", tot]])
        st.success(f"✅ Cargado con fecha {hoy}.")

# --- MÓDULO 3: INTERESES ---
elif menu == "3. 📈 Cálculo Intereses":
    st.header("Actualización de Deuda e Intereses")
    
    col1, col2 = st.columns(2)
    col1.metric("Inflación Mensual", f"{INFLACION_MENSUAL}%")
    col2.metric("Punitorio Fijo", "5.0%")
    
    if 'filas_intereses' not in st.session_state:
        st.session_state.filas_intereses = []
    
    st.markdown("""
    **Criterio de Cálculo Justo:**
    1. Se toma la **Deuda Histórica** (Gastos generados *antes* del mes seleccionado).
    2. Se le descuentan **TODOS los pagos o créditos** que el vecino haya hecho.
    3. *No se cobran intereses sobre los gastos nuevos de este mes*, porque aún no están vencidos.
    """)
    
    if st.button("🔍 1. Calcular sobre Saldos Vencidos"):
        df = cargar_movimientos()
        filas_temp = []
        hoy = datetime.now().strftime("%Y-%m-%d")
        
        st.session_state.filas_intereses = []
        
        st.write("---")
        st.subheader("Resultados del Cálculo:")
        hay_deuda = False
        
        for v in lista_nombres:
            m = df[df["Socio"] == v]
            ingresos_totales = m[m["Tipo"] == "Ingreso"]["Monto"].sum()
            egresos_viejos = m[(m["Tipo"] == "Egreso") & (m["Fecha"] < f_ini)]["Monto"].sum()
            saldo_base_interes = ingresos_totales - egresos_viejos
            
            if saldo_base_interes < -100: 
                hay_deuda = True
                deuda_vencida = abs(saldo_base_interes)
                
                monto_inf = deuda_vencida * (INFLACION_MENSUAL / 100)
                subtotal = deuda_vencida + monto_inf
                monto_pun = subtotal * 0.05
                total_recargo = monto_inf + monto_pun
                
                st.error(f"👤 **{v}**")
                st.write(f"- Deuda Vencida (ignorando mes actual): ${deuda_vencida:,.2f}")
                st.write(f"- Inflación ({INFLACION_MENSUAL}%): +${monto_inf:,.2f}")
                st.write(f"- Punitorio (5% s/actualizado): +${monto_pun:,.2f}")
                st.write(f"- **TOTAL A AGREGAR: ${total_recargo:,.2f}**")
                
                filas_temp.append([
                    hoy, "Egreso", "Financiero", v, 
                    f"Ajuste Mora (Inf {INFLACION_MENSUAL}% + Pun 5%)", total_recargo
                ])
                st.divider()

        if hay_deuda:
            st.session_state.filas_intereses = filas_temp
            st.success("✅ Cálculo realizado. Revisá arriba y confirmá abajo.")
        else:
            st.info("👏 Ningún vecino registra deuda vencida de meses anteriores.")

    if len(st.session_state.filas_intereses) > 0:
        st.write("---")
        st.warning(f"Se van a generar {len(st.session_state.filas_intereses)} movimientos de ajuste.")
        
        if st.button("🔥 2. CONFIRMAR Y GUARDAR INTERESES"):
            guardar_lote_movimientos(st.session_state.filas_intereses)
            st.balloons()
            st.success("✅ Intereses guardados correctamente en las Cuentas Corrientes.")
            st.session_state.filas_intereses = []

# --- MÓDULO 4: ESPECIALES ---
elif menu == "4. ⚖️ Movimientos Especiales":
    st.header("Operaciones Contables Avanzadas")
    tab1, tab2 = st.tabs(["Créditos (Socio presta)", "Gastos a Grupo (Sociedad paga)"])
    
    with tab1:
        st.subheader("Crédito a Socios")
        fecha_credito = st.date_input("Fecha del Crédito", datetime.now(), key="fc_cred")
        socios_acreedores = st.multiselect("¿A quiénes se acredita?", lista_nombres)
        monto_cred = st.number_input("Monto Crédito ($)", min_value=0.0, step=100.0)
        det_cred = st.text_input("Detalle Crédito")
        
        if st.button("Ejecutar Crédito"):
            hoy = fecha_credito.strftime("%Y-%m-%d")
            filas = []
            
            # ACÁ ESTÁ EL SECRETO: Le avisamos al sistema que hay un gasto general "interno", así sale en el PDF.
            filas.append([hoy, "Egreso", "Gasto Interno", "SOCIEDAD_GASTOS", f"Crédito Prorrateado: {det_cred}", monto_cred])
            
            cuota_todos = monto_cred / len(lista_nombres)
            for v in lista_nombres:
                filas.append([hoy, "Egreso", "Cuota Parte", v, f"Gasto: {det_cred}", cuota_todos])
            div_credito = monto_cred / len(socios_acreedores)
            for acreedor in socios_acreedores:
                filas.append([hoy, "Ingreso", "Crédito Especial", acreedor, f"Devolución: {det_cred}", div_credito])
            guardar_lote_movimientos(filas)
            st.success("✅ Crédito registrado correctamente.")

    with tab2:
        st.subheader("Gastos de Grupo")
        fecha_grupo = st.date_input("Fecha del Gasto", datetime.now(), key="fc_gasto")
        socios_deudores = st.multiselect("¿A quiénes se cobra?", lista_nombres)
        monto_gasto = st.number_input("Monto Gasto ($)", min_value=0.0, step=100.0)
        det_gasto = st.text_input("Detalle Gasto")
        
        if st.button("Ejecutar Cobro"):
            hoy = fecha_grupo.strftime("%Y-%m-%d")
            filas = []
            filas.append([hoy, "Egreso", "Gasto Real", "SOCIEDAD_GASTOS", f"Adelanto: {det_gasto}", monto_gasto])
            cuota_grupo = monto_gasto / len(socios_deudores)
            for deudor in socios_deudores:
                filas.append([hoy, "Egreso", "Particular", deudor, f"Cobro: {det_gasto}", cuota_grupo])
            guardar_lote_movimientos(filas)
            st.success("✅ Cobro registrado correctamente.")

# --- MÓDULO 5: CUENTAS ---
elif menu == "5. 🔍 Cuentas":
    st.subheader(f"Movimientos: {mes_selec}/{anio_selec}")
    df = cargar_movimientos()
    if not df.empty:
        vecino = st.selectbox("Vecino", lista_nombres)
        df_v = df[df["Socio"] == vecino]
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

# --- MÓDULO 6: WHATSAPP ---
elif menu == "6. 📲 WhatsApp":
    st.header("Enviar Resumen por WhatsApp")
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
            
            concepto_crudo = str(r['Concepto'])
            if ":" in concepto_crudo:
                concepto_limpio = concepto_crudo.split(":", 1)[1].strip()
            else:
                concepto_limpio = concepto_crudo.strip()
                
            concepto_corto = concepto_limpio[:18]
            txt += f"{r['Fecha'].strftime('%d/%m')} {concepto_corto}: {sig}${m:,.0f}\n"
        
        txt += f"----------------\n*SALDO FINAL: ${sal_temp:,.2f}*"
        
        tel_final = ""
        if not df_socios_completo.empty:
            s = df_socios_completo[df_socios_completo["Nombre"] == vecino]
            if not s.empty: 
                raw_tel = str(s.iloc[0]["Telefono"]).strip()
                clean_tel = raw_tel.replace("+", "").replace(" ", "").replace("-", "")
                if len(clean_tel) > 0:
                    if not clean_tel.startswith("54"):
                        tel_final = f"549{clean_tel}"
                    else:
                        tel_final = clean_tel
                else:
                    st.warning("⚠️ Este vecino no tiene teléfono cargado en la hoja Socios.")

        if tel_final:
            link = f"https://wa.me/{tel_final}?text={urllib.parse.quote(txt)}"
            st.success(f"Número detectado: {tel_final}")
            st.markdown(f"### 👉 [ENVIAR WHATSAPP AHORA]({link})")
        else:
            st.error("No se pudo generar el enlace porque falta el número.")

# --- MÓDULO 7: PDF ---
elif menu == "7. 📄 PDF":
    st.header(f"Informe Financiero: {mes_selec}/{anio_selec}")
    df = cargar_movimientos()
    if st.button("🖨️ Generar PDF"):
        # Filtro estricto para evitar que los Créditos Especiales simulen "plata falsa" en la caja inicial
        mask_caja = ((df["Socio"] == "SOCIEDAD_GASTOS") & (df["Categoria"] == "Gasto Real")) | ((df["Tipo"] == "Ingreso") & (df["Categoria"] != "Crédito Especial"))
        df_caja = df[mask_caja]
        mask_ant = df_caja["Fecha"] < f_ini
        sal_ini = df_caja[mask_ant & (df_caja["Tipo"]=="Ingreso")]["Monto"].sum() - df_caja[mask_ant & (df_caja["Tipo"]=="Egreso")]["Monto"].sum()
        
        mask_mes = (df["Fecha"] >= f_ini) & (df["Fecha"] < f_fin)
        df_mes_completo = df[mask_mes].sort_values("Fecha")
        
        pdf_data = generar_pdf_caja(df_mes_completo, sal_ini, mes_selec, anio_selec, lista_nombres)
        b64 = base64.b64encode(pdf_data).decode()
        href = f'<a href="data:application/octet-stream;base64,{b64}" download="Informe_Villa_{mes_selec}_{anio_selec}.pdf">📥 DESCARGAR PDF</a>'
        st.markdown(href, unsafe_allow_html=True)

# --- MÓDULO 8: CONFIGURACIÓN ---
elif menu == "8. ⚙️ Configuración":
    st.header("Configuración de Valores")
    st.info("Estos valores quedan guardados para todo el sistema.")
    
    c1, c2 = st.columns(2)
    new_kwh = c1.number_input("Precio del kWh ($)", value=PRECIO_KWH, step=0.5)
    new_inf = c2.number_input("Inflación Mensual (%)", value=INFLACION_MENSUAL, step=0.1)
    
    st.write("---")
    st.write(f"**Resumen de Intereses:**")
    st.write(f"- Inflación Base: {new_inf}%")
    st.write(f"- Punitorio Fijo: 5.0%")
    st.write(f"- **Total Aplicable:** Inflación + 5% sobre el total actualizado.")
    
    if st.button("💾 Guardar Nueva Configuración"):
        guardar_configuracion(new_kwh, new_inf)
        st.rerun()
