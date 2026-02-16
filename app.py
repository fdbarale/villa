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

# --- 2. FUNCIONES DE BASE DE DATOS ---
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

# --- NUEVAS FUNCIONES DE CONFIGURACIÓN ---
def obtener_configuracion():
    """Lee el valor del kWh y la Inflación desde la hoja Configuracion"""
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Configuracion")
        data = ws.get_all_records()
        # Convertimos a diccionario simple: {'Precio_KWH': 100, 'Inflacion_Mensual': 10}
        config = {row['Parametro']: row['Valor'] for row in data}
        return config
    except:
        return {'Precio_KWH': 100.0, 'Inflacion_Mensual': 10.0}

def guardar_configuracion(precio_kwh, inflacion):
    """Actualiza la hoja de configuración"""
    sh = conectar_google_sheet()
    try:
        ws = sh.worksheet("Configuracion")
        # Sobreescribimos celda B2 y B3 (asumiendo estructura fija)
        ws.update_acell('B2', float(precio_kwh))
        ws.update_acell('B3', float(inflacion))
        st.cache_data.clear()
        st.toast("✅ Configuración guardada en la Nube")
    except Exception as e:
        st.error(f"Error guardando config: {e}")

# --- 3. CLASE PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Administración Villa Soñada', 0, 1, 'C')
        self.set_font('Arial', 'I', 9)
        self.cell(0, 10, 'Informe Mensual y Estado de Cuentas', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generar_pdf_caja(df, saldo_ini, mes, anio, lista_socios):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # CAJA GENERAL
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, f"1. MOVIMIENTOS REALES (CAJA) - {mes}/{anio}", 0, 1)
    pdf.set_font("Arial", size=9)
    pdf.cell(0, 8, f"Saldo Inicial: ${saldo_ini:,.2f}", 0, 1)
    
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
        # Filtro de Caja: Solo Ingresos reales y Gastos etiquetados como SOCIEDAD o Gasto Real
        es_gasto_caja = (row["Socio"] == "SOCIEDAD_GASTOS") or (row["Categoria"] == "Gasto Real")
        es_ingreso = (row["Tipo"] == "Ingreso")
        
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
    
    # DEUDORES
    pdf.ln(10)
    pdf.cell(0, 10, f"2. ESTADO DE DEUDAS (Financiero)", 0, 1)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(70, 8, "Vecino", 1, 0, 'C', 1)
    pdf.cell(40, 8, "Saldo a Favor", 1, 0, 'C', 1)
    pdf.cell(40, 8, "Deuda Total", 1, 1, 'C', 1)
    pdf.set_font("Arial", size=9)
    
    # Recalculamos deuda histórica total
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

# --- BARRA LATERAL: CONFIGURACIÓN PERSISTENTE ---
st.sidebar.title("⚙️ Configuración")

# 1. Selector de Fechas
st.sidebar.subheader("📅 Período")
mes_selec = st.sidebar.selectbox("Mes", range(1, 13), index=datetime.now().month - 1)
anio_selec = st.sidebar.number_input("Año", value=datetime.now().year)

f_ini = datetime(anio_selec, mes_selec, 1)
if mes_selec == 12: f_fin = datetime(anio_selec + 1, 1, 1)
else: f_fin = datetime(anio_selec, mes_selec + 1, 1)

# 2. Configuración de Valores (Lee y Guarda en Google Sheet)
st.sidebar.divider()
st.sidebar.subheader("💰 Valores del Mes")

# Leemos la config actual
config_actual = obtener_configuracion()
val_kwh_db = float(config_actual.get('Precio_KWH', 100.0))
val_inf_db = float(config_actual.get('Inflacion_Mensual', 10.0))

# Inputs en la sidebar
kwh_input = st.sidebar.number_input("Precio kWh ($)", value=val_kwh_db, step=0.5)
inf_input = st.sidebar.number_input("% Inflación", value=val_inf_db, step=0.1)
punitorio_fijo = 5.0 # Fijo según tu pedido

if st.sidebar.button("💾 Guardar Valores"):
    guardar_configuracion(kwh_input, inf_input)

st.sidebar.info(f"Interés por Mora Total: **{inf_input + punitorio_fijo}%**")

# --- MENÚ PRINCIPAL ---
menu = st.sidebar.radio("Ir a:", [
    "1. 📝 Cargar Op.", 
    "2. ⚡ Luz", 
    "3. 📈 Ajuste Deudas", 
    "4. 🚧 Crédito Alambrados", # NUEVO!
    "5. 🔍 Cuentas", 
    "6. 📲 WhatsApp", 
    "7. 📄 PDF"
])

# --- LÓGICA DE CADA MÓDULO ---

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
            # 1. Caja Real
            filas.append([hoy_str, "Egreso", "Gasto Real", "SOCIEDAD_GASTOS", concepto, monto])
            # 2. Deuda Vecinos
            cuota = monto / len(lista_nombres)
            for v in lista_nombres:
                filas.append([hoy_str, "Egreso", "Cuota Parte", v, f"Parte de: {concepto}", cuota])
            st.success("✅ Gasto General guardado y prorrateado.")
        else:
            tr = "Ingreso" if "Ingreso" in tipo_op else "Egreso"
            filas.append([hoy_str, tr, destino, socio, concepto, monto])
            st.success("✅ Operación guardada.")
            
        guardar_lote_movimientos(filas)

elif menu == "2. ⚡ Luz":
    st.header("Carga de Luz")
    socio = st.selectbox("Vecino", lista_nombres)
    
    # Botón de búsqueda de lectura anterior
    if 'luz_ant' not in st.session_state: st.session_state.luz_ant = 0
    if st.button("🔍 Buscar Anterior"):
        st.session_state.luz_ant = obtener_lectura_anterior(socio)
        st.rerun()

    ant = st.number_input("Anterior", value=st.session_state.luz_ant)
    act = st.number_input("Actual", min_value=st.session_state.luz_ant)
    # Toma el precio de la configuración global
    pr = st.number_input("Precio kWh (Config)", value=kwh_input, disabled=False) 
    
    cons = act - ant
    tot = cons * pr
    st.metric("A Pagar", f"${tot:,.2f}")
    
    if st.button("💾 Guardar Luz"):
        hoy = datetime.now().strftime("%Y-%m-%d")
        guardar_lectura_tecnica([hoy, socio, ant, act, cons, pr, tot])
        guardar_lote_movimientos([[hoy, "Egreso", "Luz", socio, f"Luz {cons}kw", tot]])
        st.success("✅ Cargado.")

elif menu == "3. 📈 Ajuste Deudas":
    st.header("Aplicar Intereses por Mora")
    st.info(f"Se aplicará: Inflación {inf_input}% + Punitorio {punitorio_fijo}%")
    
    factor = (inf_input + punitorio_fijo) / 100
    
    if st.button("🔍 Buscar Deudores y Calcular"):
        df = cargar_movimientos()
        filas = []
        hoy = datetime.now().strftime("%Y-%m-%d")
        hay = False
        st.write("---")
        
        for v in lista_nombres:
            m = df[df["Socio"] == v]
            s = m[m["Tipo"]=="Ingreso"]["Monto"].sum() - m[m["Tipo"]=="Egreso"]["Monto"].sum()
            
            if s < -100: # Tolerancia
                hay = True
                deuda = abs(s)
                recargo = deuda * factor
                st.error(f"{v}: Debe ${deuda:,.0f} -> Recargo ${recargo:,.0f}")
                
                # Asiento Contable: Aumenta la deuda del vecino
                # Nota: Esto se considera "Ahorro/Ganancia" para la Villa contablemente,
                # pero aquí solo impactamos la deuda del vecino.
                filas.append([
                    hoy, "Egreso", "Financiero", v, 
                    f"Ajuste Mora (Inf {inf_input}% + Pun {punitorio_fijo}%)", recargo
                ])
        
        if hay:
            if st.button("🔥 APLICAR RECARGOS"):
                guardar_lote_movimientos(filas)
                st.success("✅ Intereses aplicados.")
        else:
            st.success("Nadie tiene deuda vencida.")

elif menu == "4. 🚧 Crédito Alambrados":
    st.header("Actualización de Crédito Alambrados")
    st.markdown("""
    Esta herramienta hace 2 cosas:
    1. Genera un **Gasto General** por el monto total (lo pagan todos los socios).
    2. Le acredita ese dinero **solo a los vecinos seleccionados** (descuenta su deuda).
    """)
    
    vecinos_alambrado = st.multiselect("Vecinos que recuperan inversión:", lista_nombres)
    
    c1, c2 = st.columns(2)
    monto_base = c1.number_input("Monto Cuota Base ($)", min_value=0.0)
    # Toma la inflación de la config
    monto_ajustado = monto_base * (1 + (inf_input / 100))
    
    c2.metric("Monto Ajustado por Inflación", f"${monto_ajustado:,.2f}")
    
    if st.button("💾 Ejecutar Devolución"):
        if not vecinos_alambrado or monto_ajustado <= 0:
            st.error("Seleccioná vecinos y monto.")
        else:
            hoy = datetime.now().strftime("%Y-%m-%d")
            filas = []
            
            # Cantidad de beneficiarios
            cant_benef = len(vecinos_alambrado)
            total_a_pagar_sociedad = monto_ajustado * cant_benef
            
            # 1. GASTO GENERAL (Lo bancan los 20)
            # Primero a la Caja Real (Salida figurativa)
            filas.append([hoy, "Egreso", "Gasto Real", "SOCIEDAD_GASTOS", f"Pago Alambrados ({cant_benef} socios)", total_a_pagar_sociedad])
            
            # Prorrateo entre TODOS (Deuda para todos)
            cuota_individual = total_a_pagar_sociedad / len(lista_nombres)
            for v in lista_nombres:
                filas.append([hoy, "Egreso", "Cuota Parte", v, "Cuota Devolución Alambrado", cuota_individual])
            
            # 2. CRÉDITO A LOS 5 VECINOS (Ingreso para ellos)
            for benef in vecinos_alambrado:
                filas.append([hoy, "Ingreso", "Devolución", benef, f"Devolución Alambrado (Ajustado)", monto_ajustado])
            
            guardar_lote_movimientos(filas)
            st.balloons()
            st.success(f"✅ Operación Exitosa. Se acreditaron ${monto_ajustado:,.2f} a cada uno de los {cant_benef} vecinos seleccionados, y el costo se dividió entre todos.")

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

elif menu == "6. 📲 WhatsApp":
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
        st.markdown(f"### 👉 [ENVIAR WHATSAPP]({link})")

elif menu == "7. 📄 PDF":
    st.header(f"Informe Financiero: {mes_selec}/{anio_selec}")
    df = cargar_movimientos()
    if not df.empty:
        mask_caja = (df["Socio"] == "SOCIEDAD_GASTOS") | (df["Tipo"] == "Ingreso")
        df_caja = df[mask_caja]
        
        mask_ant = df_caja["Fecha"] < f_ini
        sal_ini = df_caja[mask_ant & (df_caja["Tipo"]=="Ingreso")]["Monto"].sum() - df_caja[mask_ant & (df_caja["Tipo"]=="Egreso")]["Monto"].sum()
        
        mask_mes = (df["Fecha"] >= f_ini) & (df["Fecha"] < f_fin)
        df_mes_completo = df[mask_mes].sort_values("Fecha")
        
        if st.button("🖨️ Generar PDF"):
            pdf_data = generar_pdf_caja(df_mes_completo, sal_ini, mes_selec, anio_selec, lista_nombres)
            b64 = base64.b64encode(pdf_data).decode()
            href = f'<a href="data:application/octet-stream;base64,{b64}" download="Informe_Villa_{mes_selec}_{anio_selec}.pdf">📥 DESCARGAR PDF</a>'
            st.markdown(href, unsafe_allow_html=True)
            st.success("Generado.")
