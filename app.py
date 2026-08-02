import streamlit as st
import pandas as pd
from datetime import datetime
import urllib.parse
from fpdf import FPDF
import base64
import os
from supabase import create_client

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Villa Soñada", layout="wide")


# ---------------------------------------------------------------------------
# 0. ACCESO CON CONTRASEÑA
# ---------------------------------------------------------------------------

def verificar_acceso():
    """Pide una contraseña única (definida en st.secrets['auth']['password'])
    antes de mostrar cualquier dato financiero. No es un sistema de usuarios
    múltiples, es un candado simple para que no cualquiera con el link vea
    o cargue movimientos."""
    if st.session_state.get("autenticado", False):
        return True

    st.title("🔒 Administración Villa Soñada")
    clave_ingresada = st.text_input("Ingresá la contraseña de acceso", type="password")
    if st.button("Entrar"):
        try:
            clave_correcta = st.secrets["auth"]["password"]
        except Exception:
            st.error("❌ No hay contraseña configurada en Secrets (auth.password). Avisá al administrador del sistema.")
            return False
        if clave_ingresada == clave_correcta:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("❌ Contraseña incorrecta.")
    return False


if not verificar_acceso():
    st.stop()

# --- Fuente unicode para los PDF (evita que rompan con caracteres raros) ---
# Descargá DejaVuSans.ttf y DejaVuSans-Bold.ttf (son gratis y de uso libre) y
# ponelos en la misma carpeta que este archivo. Si no están, la app sigue
# funcionando con la fuente estándar (menos robusta con algunos caracteres).
FUENTE_TTF = "DejaVuSans.ttf"
FUENTE_TTF_BOLD = "DejaVuSans-Bold.ttf"
HAY_FUENTE_UNICODE = os.path.exists(FUENTE_TTF)


# ---------------------------------------------------------------------------
# 1. CONEXIÓN A SUPABASE
# ---------------------------------------------------------------------------

@st.cache_resource
def conectar_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["service_role_key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Error de Conexión a Supabase: {e}")
        st.stop()


# ---------------------------------------------------------------------------
# 2. FUNCIONES DE DATOS
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def cargar_movimientos():
    client = conectar_supabase()
    try:
        resp = client.table("movimientos").select("*").execute()
        df = pd.DataFrame(resp.data)
        if df.empty:
            return df
        df["Fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df = df.dropna(subset=["Fecha"])
        df["Monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
        df = df.rename(columns={
            "tipo": "Tipo", "categoria": "Categoria",
            "socio": "Socio", "concepto": "Concepto",
        })
        return df
    except Exception as e:
        st.error(f"❌ Error cargando movimientos: {e}")
        return pd.DataFrame()


def obtener_lista_socios():
    client = conectar_supabase()
    try:
        resp = client.table("socios").select("*").execute()
        df = pd.DataFrame(resp.data)
        if df.empty or "nombre" not in df.columns:
            st.warning("⚠️ No hay socios cargados en la tabla 'socios'.")
            return ["A - Genérico"], pd.DataFrame()
        df = df.rename(columns={"nombre": "Nombre", "telefono": "Telefono"})
        return df["Nombre"].tolist(), df
    except Exception as e:
        st.error(f"❌ Error cargando socios: {e}")
        return ["A - Genérico"], pd.DataFrame()


def guardar_lote_movimientos(lista_filas):
    """lista_filas: lista de [fecha, tipo, categoria, socio, concepto, monto].
    Se inserta como un único statement -> o entran todas las filas, o ninguna
    (a diferencia de la versión con Google Sheets, acá no quedan cargas
    parciales si algo falla a mitad de camino)."""
    client = conectar_supabase()
    filas_dict = [
        {
            "fecha": fecha,
            "tipo": tipo,
            "categoria": categoria,
            "socio": socio,
            "concepto": concepto,
            "monto": float(monto),
        }
        for fecha, tipo, categoria, socio, concepto, monto in lista_filas
    ]
    try:
        client.table("movimientos").insert(filas_dict).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ Error guardando movimientos: {e}. No se guardó nada de este lote.")
        return False


def anular_movimiento(fila_original):
    """Registra el reverso de un movimiento (signo contrario, mismo monto),
    dejando rastro de cuál fue el original. No borra nada -> mantiene la
    trazabilidad contable."""
    tipo_contrario = "Egreso" if fila_original["Tipo"] == "Ingreso" else "Ingreso"
    concepto_reverso = f"ANULACIÓN de mov. #{fila_original['id']}: {fila_original['Concepto']}"
    hoy = datetime.now().strftime("%Y-%m-%d")
    fila = [[
        hoy, tipo_contrario, fila_original["Categoria"], fila_original["Socio"],
        concepto_reverso, fila_original["Monto"],
    ]]
    return guardar_lote_movimientos(fila)


def eliminar_movimiento_definitivo(id_movimiento):
    """Borrado real y permanente. Usar sólo cuando el movimiento fue una
    prueba o un error de tipeo evidente, nunca para 'corregir' un monto ya
    comunicado a un vecino (para eso, usar anular_movimiento)."""
    client = conectar_supabase()
    try:
        client.table("movimientos").delete().eq("id", id_movimiento).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ Error borrando el movimiento: {e}")
        return False


def guardar_lectura_tecnica(fila):
    client = conectar_supabase()
    hoy, socio, ant, act, cons, pr, tot = fila
    try:
        client.table("lecturas").insert({
            "fecha": hoy, "socio": socio,
            "lectura_ant": ant, "lectura_act": act,
            "consumo": cons, "precio_kwh": pr, "total": tot,
        }).execute()
        return True
    except Exception as e:
        st.error(f"❌ Error guardando lectura: {e}")
        return False


def obtener_lectura_anterior(socio):
    client = conectar_supabase()
    try:
        resp = (
            client.table("lecturas")
            .select("lectura_act")
            .eq("socio", socio)
            .order("fecha", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            return int(resp.data[0]["lectura_act"])
        return 0
    except Exception as e:
        st.warning(f"⚠️ No pude traer la lectura anterior de {socio}: {e}")
        return 0


# --- CONFIGURACIÓN ---
def obtener_configuracion():
    client = conectar_supabase()
    try:
        resp = client.table("configuracion").select("*").execute()
        if not resp.data:
            st.warning("⚠️ No hay configuración guardada todavía, uso valores por defecto.")
            return {"Precio_KWH": 100.0, "Inflacion_Mensual": 10.0}
        return {row["parametro"]: row["valor"] for row in resp.data}
    except Exception as e:
        st.warning(f"⚠️ No pude leer la configuración, uso valores por defecto: {e}")
        return {"Precio_KWH": 100.0, "Inflacion_Mensual": 10.0}


def guardar_configuracion(precio_kwh, inflacion):
    client = conectar_supabase()
    try:
        client.table("configuracion").upsert([
            {"parametro": "Precio_KWH", "valor": str(precio_kwh)},
            {"parametro": "Inflacion_Mensual", "valor": str(inflacion)},
        ]).execute()
        st.cache_data.clear()
        st.toast("✅ Configuración guardada correctamente")
    except Exception as e:
        st.error(f"❌ Error guardando config: {e}")


# ---------------------------------------------------------------------------
# 3. CLASES PDF (REPORTE Y RECIBO) — fpdf2, con fuente unicode si está disponible
# ---------------------------------------------------------------------------

class PDFBase(FPDF):
    def _preparar_fuente(self):
        if HAY_FUENTE_UNICODE:
            self.add_font("DejaVu", "", FUENTE_TTF)
            if os.path.exists(FUENTE_TTF_BOLD):
                self.add_font("DejaVu", "B", FUENTE_TTF_BOLD)
            else:
                self.add_font("DejaVu", "B", FUENTE_TTF)
            return "DejaVu"
        return "Helvetica"


class PDF(PDFBase):
    def header(self):
        try:
            self.image('logo.png', 10, 8, 30)
        except Exception:
            pass
        fuente = self._preparar_fuente()
        self.set_font(fuente, 'B', 15)
        self.cell(0, 10, 'Administración Villa Soñada', 0, 1, 'C')
        self.set_font(fuente, '', 9)
        self.cell(0, 10, 'Informe Mensual y Estado de Cuentas', 0, 1, 'C')
        self.ln(15)

    def footer(self):
        self.set_y(-15)
        fuente = self._preparar_fuente()
        self.set_font(fuente, '', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')


class ReciboPDF(PDFBase):
    def header(self):
        try:
            self.image('logo.png', 10, 8, 25)
        except Exception:
            pass
        fuente = self._preparar_fuente()
        self.set_font(fuente, 'B', 14)
        self.cell(0, 10, 'Administración Villa Soñada', 0, 1, 'R')
        self.set_font(fuente, 'B', 12)
        self.cell(0, 10, 'RECIBO OFICIAL', 0, 1, 'R')
        self.ln(10)


def generar_recibo_pdf(fecha, socio, monto, concepto):
    pdf = ReciboPDF()
    pdf.add_page()
    fuente = pdf._preparar_fuente()
    pdf.set_font(fuente, size=12)

    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, f" Fecha: {fecha}", 1, 1, 'L', 1)
    pdf.cell(0, 10, f" Recibimos de: {socio}", 1, 1, 'L')
    pdf.cell(0, 10, f" La cantidad de: ${monto:,.2f}", 1, 1, 'L')
    pdf.cell(0, 10, f" En concepto de: {concepto}", 1, 1, 'L')

    pdf.ln(25)
    pdf.set_font(fuente, size=10)
    pdf.cell(80, 10, "______________________________", 0, 0, 'C')
    pdf.cell(0, 10, "", 0, 1)
    pdf.cell(80, 5, "Firma de la Administración", 0, 1, 'C')

    return bytes(pdf.output())


def generar_pdf_caja(df, saldo_ini, mes, anio, lista_socios, f_fin):
    pdf = PDF()
    pdf.add_page()
    fuente = pdf._preparar_fuente()
    pdf.set_font(fuente, size=10)

    # 1. CAJA REAL
    pdf.set_font(fuente, 'B', 11)
    pdf.cell(0, 10, f"1. MOVIMIENTOS REALES (CAJA) - {mes}/{anio}", 0, 1)
    pdf.set_font(fuente, size=9)
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
            if es_ingreso:
                det = f"Pago: {row['Socio']} ({det})"

            pdf.cell(20, 8, row["Fecha"].strftime("%d/%m"), 1)
            pdf.cell(90, 8, det, 1)
            pdf.cell(25, 8, f"{ent:,.0f}" if ent > 0 else "-", 1, 0, 'R')
            pdf.cell(25, 8, f"{sal:,.0f}" if sal > 0 else "-", 1, 0, 'R')
            pdf.cell(25, 8, f"{saldo:,.0f}", 1, 1, 'R')

    pdf.ln(5)
    pdf.set_font(fuente, 'B', 10)
    pdf.cell(0, 8, f"TOTAL INGRESOS: ${tot_ing:,.2f} | TOTAL EGRESOS: ${tot_egr:,.2f}", 0, 1)
    pdf.cell(0, 8, f"SALDO CIERRE CAJA: ${saldo:,.2f}", 0, 1)

    # 2. GASTOS INTERNOS Y PRORRATEOS
    df_internos = df[(df["Socio"] == "SOCIEDAD_GASTOS") & (df["Categoria"] == "Gasto Interno")]
    if not df_internos.empty:
        pdf.ln(10)
        pdf.set_font(fuente, 'B', 11)
        pdf.cell(0, 10, "2. GASTOS INTERNOS Y PRORRATEOS (No afectan efectivo)", 0, 1)
        pdf.set_font(fuente, size=9)
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
    pdf.set_font(fuente, 'B', 11)
    pdf.cell(0, 10, f"ESTADO DE DEUDAS (Al cierre del mes {mes}/{anio})", 0, 1)
    pdf.set_font(fuente, 'B', 9)
    pdf.cell(70, 8, "Vecino", 1, 0, 'C', 1)
    pdf.cell(40, 8, "Saldo a Favor", 1, 0, 'C', 1)
    pdf.cell(40, 8, "Deuda Total", 1, 1, 'C', 1)
    pdf.set_font(fuente, size=9)

    df_full = cargar_movimientos()
    df_foto_fija = df_full[df_full["Fecha"] < f_fin]

    hay_deuda = False
    for vec in lista_socios:
        m = df_foto_fija[df_foto_fija["Socio"] == vec]
        s_neto = m[m["Tipo"] == "Ingreso"]["Monto"].sum() - m[m["Tipo"] == "Egreso"]["Monto"].sum()

        if s_neto < -100:
            hay_deuda = True
            pdf.set_text_color(180, 0, 0)
            pdf.cell(70, 8, vec, 1)
            pdf.cell(40, 8, "-", 1, 0, 'C')
            pdf.cell(40, 8, f"${abs(s_neto):,.2f}", 1, 1, 'R')
            pdf.set_text_color(0, 0, 0)

    if not hay_deuda:
        pdf.cell(150, 8, "Sin deudas registradas a esa fecha.", 1, 1, 'C')
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# 4. INTERFAZ
# ---------------------------------------------------------------------------

st.title("🏡 Administración Villa Soñada")
lista_nombres, df_socios_completo = obtener_lista_socios()

# --- SELECTOR DE FECHA ---
st.sidebar.subheader("📅 Período de Trabajo")
mes_selec = st.sidebar.selectbox("Mes", range(1, 13), index=datetime.now().month - 1)
anio_selec = st.sidebar.number_input("Año", value=datetime.now().year)

f_ini = datetime(anio_selec, mes_selec, 1)
if mes_selec == 12:
    f_fin = datetime(anio_selec + 1, 1, 1)
else:
    f_fin = datetime(anio_selec, mes_selec + 1, 1)

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
    "8. ⚙️ Configuración",
    "9. 🛠️ Corregir/Anular"
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
    concepto = c2.text_input("Concepto (Si es cobro físico, incluí la palabra 'efectivo')")

    tope_cpe = 0
    if destino == "General" and tipo_op == "Gasto (Salida)" and "cpe" in concepto.lower():
        st.warning("⚡ Detectado gasto de luz CPE. Se aplicará tope de cobro a vecinos.")
        tope_cpe = st.number_input("Tope a cobrar por vecino ($)", value=30000.0, step=1000.0)

    st.write("---")
    if st.button("💾 CONFIRMAR Y GUARDAR"):
        hoy_str = fecha_op.strftime("%Y-%m-%d")
        filas = []

        if destino == "General" and tipo_op == "Gasto (Salida)":
            filas.append([hoy_str, "Egreso", "Gasto Real", "SOCIEDAD_GASTOS", concepto, monto])

            if "cpe" in concepto.lower() and tope_cpe > 0:
                cuota = tope_cpe
                concepto_cuota = "Fondo obras/emergencia"
            else:
                cuota = monto / len(lista_nombres)
                concepto_cuota = f"Parte de: {concepto}"

            for v in lista_nombres:
                filas.append([hoy_str, "Egreso", "Cuota Parte", v, concepto_cuota, cuota])

            if guardar_lote_movimientos(filas):
                if "cpe" in concepto.lower() and tope_cpe > 0:
                    st.success(f"✅ Gasto General guardado. A cada vecino se le cargaron ${cuota:,.2f} como Fondo de obras.")
                else:
                    st.success("✅ Gasto General guardado y prorrateado linealmente.")

        else:
            tr = "Ingreso" if "Ingreso" in tipo_op else "Egreso"
            filas.append([hoy_str, tr, destino, socio, concepto, monto])
            if guardar_lote_movimientos(filas):
                st.success("✅ Operación guardada.")

                if tr == "Ingreso" and "efectivo" in concepto.lower():
                    pdf_recibo = generar_recibo_pdf(hoy_str, socio, monto, concepto)
                    b64 = base64.b64encode(pdf_recibo).decode()
                    href = f'<a href="data:application/octet-stream;base64,{b64}" download="Recibo_{socio}_{hoy_str}.pdf" target="_blank" style="display: inline-block; padding: 12px 24px; background-color: #28a745; color: white; font-weight: bold; text-align: center; text-decoration: none; border-radius: 8px;">🧾 DESCARGAR RECIBO PDF</a>'
                    st.info(f"¡Se detectó un pago en efectivo de {socio}! Hacé clic abajo para obtener su recibo.")
                    st.markdown(href, unsafe_allow_html=True)

# --- MÓDULO 2: LUZ ---
elif menu == "2. ⚡ Luz":
    st.header("Carga de Luz")
    st.info(f"Precio del kWh actual: **${PRECIO_KWH}** (Configurado en Menú 8)")

    fecha_luz = st.date_input("Fecha de Registro", datetime.now())
    socio = st.selectbox("Vecino", lista_nombres)

    if 'luz_ant' not in st.session_state:
        st.session_state.luz_ant = 0
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
        if guardar_lectura_tecnica([hoy, socio, ant, act, cons, pr, tot]):
            if guardar_lote_movimientos([[hoy, "Egreso", "Luz", socio, f"Luz {cons}kw", tot]]):
                st.success(f"✅ Cargado con fecha {hoy}.")

# --- MÓDULO 3: INTERESES ---
elif menu == "3. 📈 Cálculo Intereses":
    st.header("Actualización de Deuda e Intereses")

    col1, col2 = st.columns(2)
    col1.metric("Inflación Mensual", f"{INFLACION_MENSUAL}%")
    col2.metric("Punitorio Fijo", "5.0%")

    st.markdown("---")
    st.subheader("⚙️ Parámetros del Cálculo")
    st.info("Elegí hasta qué fecha un gasto se considera 'Viejo' (vencido). Para un cierre normal, suele ser el 1ro del mes que estás cobrando.")

    fecha_corte_interes = st.date_input("Fecha de corte para considerar deuda:", datetime(datetime.now().year, datetime.now().month, 1))

    if 'filas_intereses' not in st.session_state:
        st.session_state.filas_intereses = []

    st.markdown(f"""
    **Criterio de Cálculo Justo:**
    1. Se suma la deuda de todos los gastos generados **ANTES del {fecha_corte_interes.strftime('%d/%m/%Y')}**.
    2. Se le descuentan **TODOS los pagos o créditos** que el vecino haya hecho hasta hoy.
    3. *No se cobran intereses sobre los gastos posteriores* a la fecha de corte.
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

            egresos_viejos = m[(m["Tipo"] == "Egreso") & (m["Fecha"] < pd.to_datetime(fecha_corte_interes))]["Monto"].sum()

            saldo_base_interes = ingresos_totales - egresos_viejos

            if saldo_base_interes < -100:
                hay_deuda = True
                deuda_vencida = abs(saldo_base_interes)

                monto_inf = deuda_vencida * (INFLACION_MENSUAL / 100)
                subtotal = deuda_vencida + monto_inf
                monto_pun = subtotal * 0.05
                total_recargo = monto_inf + monto_pun

                st.error(f"👤 **{v}**")
                st.write(f"- Deuda Vencida a penalizar: ${deuda_vencida:,.2f}")
                st.write(f"- Inflación ({INFLACION_MENSUAL}%): +${monto_inf:,.2f}")
                st.write(f"- Punitorio (5% s/actualizado): +${monto_pun:,.2f}")
                st.write(f"- **TOTAL A AGREGAR: ${total_recargo:,.2f}**")

                filas_temp.append([
                    hoy, "Egreso", "Financiero", v,
                    f"Ajuste Mora (Inflación {INFLACION_MENSUAL}% + Punitorio 5%)", total_recargo
                ])
                st.divider()

        if hay_deuda:
            st.session_state.filas_intereses = filas_temp
            st.success("✅ Cálculo realizado. Revisá arriba y confirmá abajo.")
        else:
            st.info("👏 Ningún vecino registra deuda vencida según la fecha de corte.")

    if len(st.session_state.filas_intereses) > 0:
        st.write("---")
        st.warning(f"Se van a generar {len(st.session_state.filas_intereses)} movimientos de ajuste.")

        if st.button("🔥 2. CONFIRMAR Y GUARDAR INTERESES"):
            if guardar_lote_movimientos(st.session_state.filas_intereses):
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
            if not socios_acreedores:
                st.error("❌ Elegí al menos un acreedor.")
            else:
                hoy = fecha_credito.strftime("%Y-%m-%d")
                filas = []

                filas.append([hoy, "Egreso", "Gasto Interno", "SOCIEDAD_GASTOS", f"Crédito Prorrateado: {det_cred}", monto_cred])

                cuota_todos = monto_cred / len(lista_nombres)
                for v in lista_nombres:
                    filas.append([hoy, "Egreso", "Cuota Parte", v, f"Gasto: {det_cred}", cuota_todos])
                div_credito = monto_cred / len(socios_acreedores)
                for acreedor in socios_acreedores:
                    filas.append([hoy, "Ingreso", "Crédito Especial", acreedor, f"Devolución: {det_cred}", div_credito])
                if guardar_lote_movimientos(filas):
                    st.success("✅ Crédito registrado correctamente.")

    with tab2:
        st.subheader("Gastos de Grupo")
        fecha_grupo = st.date_input("Fecha del Gasto", datetime.now(), key="fc_gasto")
        socios_deudores = st.multiselect("¿A quiénes se cobra?", lista_nombres)
        monto_gasto = st.number_input("Monto Gasto ($)", min_value=0.0, step=100.0)
        det_gasto = st.text_input("Detalle Gasto")

        if st.button("Ejecutar Cobro"):
            if not socios_deudores:
                st.error("❌ Elegí al menos un deudor.")
            else:
                hoy = fecha_grupo.strftime("%Y-%m-%d")
                filas = []
                filas.append([hoy, "Egreso", "Gasto Real", "SOCIEDAD_GASTOS", f"Adelanto: {det_gasto}", monto_gasto])
                cuota_grupo = monto_gasto / len(socios_deudores)
                for deudor in socios_deudores:
                    filas.append([hoy, "Egreso", "Particular", deudor, f"Cobro: {det_gasto}", cuota_grupo])
                if guardar_lote_movimientos(filas):
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
        sal_ant = df_ant[df_ant["Tipo"] == "Ingreso"]["Monto"].sum() - df_ant[df_ant["Tipo"] == "Egreso"]["Monto"].sum()
        mask_mes = (df_v["Fecha"] >= f_ini) & (df_v["Fecha"] < f_fin)
        df_mes = df_v[mask_mes].sort_values("Fecha")
        ing = df_mes[df_mes["Tipo"] == "Ingreso"]["Monto"].sum()
        egr = df_mes[df_mes["Tipo"] == "Egreso"]["Monto"].sum()
        sal_fin = sal_ant + ing - egr
        c1, c2, c3 = st.columns(3)
        c1.metric("Saldo Anterior", f"${sal_ant:,.2f}")
        c2.metric("Movimientos Mes", f"${ing - egr:,.2f}")
        c3.metric("Saldo Cierre", f"${sal_fin:,.2f}", delta_color="normal" if sal_fin >= 0 else "inverse")
        st.dataframe(df_mes[["Fecha", "Concepto", "Tipo", "Monto"]], use_container_width=True)
    else:
        st.info("Todavía no hay movimientos cargados.")

# --- MÓDULO 6: WHATSAPP ---
elif menu == "6. 📲 WhatsApp":
    st.header("Enviar Resumen por WhatsApp")
    df = cargar_movimientos()

    if not df.empty:
        vecino = st.selectbox("Vecino", lista_nombres)
        df_v = df[df["Socio"] == vecino]
        mask_ant = df_v["Fecha"] < f_ini
        sal_ant = df_v[mask_ant & (df_v["Tipo"] == "Ingreso")]["Monto"].sum() - df_v[mask_ant & (df_v["Tipo"] == "Egreso")]["Monto"].sum()
        mask_mes = (df_v["Fecha"] >= f_ini) & (df_v["Fecha"] < f_fin)
        df_mes = df_v[mask_mes].sort_values("Fecha")

        txt = f"*RESUMEN {mes_selec}/{anio_selec}*\nVecino: {vecino}\n"
        txt += f"Saldo Anterior: ${sal_ant:,.2f}\n----------------\n"

        sal_temp = sal_ant
        for i, r in df_mes.iterrows():
            sig = "+" if r["Tipo"] == "Ingreso" else "-"
            m = r["Monto"]
            if r["Tipo"] == "Ingreso":
                sal_temp += m
            else:
                sal_temp -= m

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
                    st.warning("⚠️ Este vecino no tiene teléfono cargado en la tabla Socios.")

        if tel_final:
            link = f"https://wa.me/{tel_final}?text={urllib.parse.quote(txt)}"
            st.success(f"Número detectado: {tel_final}")
            st.markdown(f"### 👉 [ENVIAR WHATSAPP AHORA]({link})")
        else:
            st.error("No se pudo generar el enlace porque falta el número.")
    else:
        st.info("Todavía no hay movimientos cargados.")

# --- MÓDULO 7: PDF ---
elif menu == "7. 📄 PDF":
    st.header(f"Informe Financiero: {mes_selec}/{anio_selec}")
    df = cargar_movimientos()
    if df.empty:
        st.info("Todavía no hay movimientos cargados.")
    elif st.button("🖨️ Generar PDF"):
        mask_caja = ((df["Socio"] == "SOCIEDAD_GASTOS") & (df["Categoria"] == "Gasto Real")) | ((df["Tipo"] == "Ingreso") & (df["Categoria"] != "Crédito Especial"))
        df_caja = df[mask_caja]
        mask_ant = df_caja["Fecha"] < f_ini
        sal_ini = df_caja[mask_ant & (df_caja["Tipo"] == "Ingreso")]["Monto"].sum() - df_caja[mask_ant & (df_caja["Tipo"] == "Egreso")]["Monto"].sum()

        mask_mes = (df["Fecha"] >= f_ini) & (df["Fecha"] < f_fin)
        df_mes_completo = df[mask_mes].sort_values("Fecha")

        pdf_data = generar_pdf_caja(df_mes_completo, sal_ini, mes_selec, anio_selec, lista_nombres, f_fin)

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
    st.write("**Resumen de Intereses:**")
    st.write(f"- Inflación Base: {new_inf}%")
    st.write("- Punitorio Fijo: 5.0%")
    st.write("- **Total Aplicable:** Inflación + 5% sobre el total actualizado.")

    if st.button("💾 Guardar Nueva Configuración"):
        guardar_configuracion(new_kwh, new_inf)
        st.rerun()

# --- MÓDULO 9: CORREGIR / ANULAR ---
elif menu == "9. 🛠️ Corregir/Anular":
    st.header("Corregir o Anular un Movimiento")
    st.info(
        "Por regla general usá **'Anular'**: genera un movimiento contrario "
        "(mismo monto, signo opuesto) y deja rastro del original — así el "
        "historial nunca queda incompleto. Usá **'Borrar definitivo'** sólo "
        "para cargas de prueba o errores obvios que nadie más vio todavía."
    )

    df = cargar_movimientos()
    if df.empty:
        st.info("Todavía no hay movimientos cargados.")
    else:
        vecino_corr = st.selectbox("Filtrar por vecino/categoría", ["TODOS"] + lista_nombres + ["SOCIEDAD_GASTOS"])
        df_filtrado = df if vecino_corr == "TODOS" else df[df["Socio"] == vecino_corr]
        df_filtrado = df_filtrado.sort_values("Fecha", ascending=False).head(50)

        if df_filtrado.empty:
            st.warning("No hay movimientos para ese filtro.")
        else:
            opciones = {
                f"#{r['id']} | {r['Fecha'].strftime('%d/%m/%Y')} | {r['Socio']} | {r['Concepto']} | ${r['Monto']:,.2f} ({r['Tipo']})": r
                for _, r in df_filtrado.iterrows()
            }
            seleccion = st.selectbox("Elegí el movimiento", list(opciones.keys()))
            fila_sel = opciones[seleccion]

            st.write("---")
            st.write(f"**Fecha:** {fila_sel['Fecha'].strftime('%d/%m/%Y')}")
            st.write(f"**Socio:** {fila_sel['Socio']}")
            st.write(f"**Categoría:** {fila_sel['Categoria']}")
            st.write(f"**Concepto:** {fila_sel['Concepto']}")
            st.write(f"**Monto:** ${fila_sel['Monto']:,.2f} ({fila_sel['Tipo']})")

            c1, c2 = st.columns(2)
            with c1:
                st.subheader("↩️ Anular (recomendado)")
                if st.button("Generar reverso de este movimiento"):
                    if anular_movimiento(fila_sel):
                        st.success("✅ Se generó el movimiento contrario. El original queda en el historial para referencia.")

            with c2:
                st.subheader("🗑️ Borrado definitivo")
                confirmacion = st.text_input("Escribí BORRAR para confirmar", key="confirmar_borrado")
                if st.button("Borrar definitivamente", type="secondary"):
                    if confirmacion.strip().upper() != "BORRAR":
                        st.error("❌ Tenés que escribir BORRAR para confirmar.")
                    else:
                        if eliminar_movimiento_definitivo(int(fila_sel["id"])):
                            st.success("✅ Movimiento borrado definitivamente.")
                            st.rerun()
