import streamlit as st
import json

st.set_page_config(page_title="Reparador de Llaves 🔧", layout="centered")

st.title("🔧 Reparador de Credenciales")
st.markdown("""
El problema es que al copiar y pegar el JSON en los Secretos, se rompe el formato.
**Esta herramienta lo va a arreglar por vos.**
""")

# 1. Cajita para pegar el JSON sucio
st.subheader("1. Abrí tu archivo JSON (el nuevo), copiá TODO y pegalo acá:")
json_input = st.text_area("Pegá aquí el contenido de tu archivo .json", height=300)

if json_input:
    try:
        # Intentamos leerlo y limpiar errores comunes
        creds = json.loads(json_input)
        
        st.success("✅ ¡JSON Leído correctamente! La llave es válida.")
        
        # 2. Generamos el formato TOML perfecto
        st.subheader("2. Copiá este bloque EXACTO:")
        st.markdown("Borrá todo lo que tengas en **Secrets** y pegá esto tal cual:")
        
        # Construimos el TOML limpio
        toml_output = f"""[connections.gsheets]
spreadsheet = "https://docs.google.com/spreadsheets/d/1omHPz_dphetEu-udxuu_Io_XlE1Nz-CPLPYF4wUWnZE/edit"

[service_account]
type = "{creds['type']}"
project_id = "{creds['project_id']}"
private_key_id = "{creds['private_key_id']}"
private_key = \"\"\"{creds['private_key']}\"\"\"
client_email = "{creds['client_email']}"
client_id = "{creds['client_id']}"
auth_uri = "{creds['auth_uri']}"
token_uri = "{creds['token_uri']}"
auth_provider_x509_cert_url = "{creds['auth_provider_x509_cert_url']}"
client_x509_cert_url = "{creds['client_x509_cert_url']}"
"""
        st.code(toml_output, language="toml")
        
        st.info("👆 Fijate que la 'private_key' ahora tiene triple comilla. Eso es lo que nos faltaba.")

    except json.JSONDecodeError as e:
        st.error(f"❌ El texto que pegaste no es un JSON válido. Asegurate de copiar desde la primera {{ hasta la última }}. Error: {e}")
    except Exception as e:
        st.error(f"❌ Ocurrió un error inesperado: {e}")
