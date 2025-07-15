import streamlit as st
from datetime import datetime, timezone
from pymongo import MongoClient
import pandas as pd

# === CONFIGURACIÓN ===
st.set_page_config(page_title="personalito", layout="centered")

# === CONEXIÓN A MONGO ===
client = MongoClient(st.secrets["mongo_uri"])
db = client["tiempo_personal"]
col_tiempos = db["tiempos"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]

# === FUNCIONES ===
def ahora():
    return datetime.now(timezone.utc)

def tiempo_transcurrido(inicio):
    if not inicio:
        return "00:00"
    delta = ahora() - inicio
    minutos = int(delta.total_seconds() // 60)
    segundos = int(delta.total_seconds() % 60)
    return f"{minutos:02d}:{segundos:02d}"

def formatear_duracion(segundos):
    if segundos is None:
        return ""
    minutos = int(segundos)
    segundos = int((segundos - minutos) * 60)
    return f"{minutos:02d}:{segundos:02d}"

# === CONTADORES POR ESTADO ===
n_pendientes = col_tiempos.count_documents({"estado": "Pendiente"})
n_autorizados = col_tiempos.count_documents({"estado": "Autorizado"})
n_en_curso = col_tiempos.count_documents({"estado": "En curso"})

# === UI PRINCIPAL ===
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")

secciones = [
    f"📋 Registrar nuevo agente en cola",
    f"📤 En cola (Pendiente) [{n_pendientes}]",
    f"🟢 Autorizados (esperando que arranquen) [{n_autorizados}]",
    f"⏱ Tiempo personal en curso [{n_en_curso}]",
    "📜 Historial"
]

seleccion = st.selectbox("Selecciona una sección:", secciones)

# === REGISTRAR AGENTE ===
if seleccion.startswith("📋"):
    st.subheader("🔐 Identificación del autorizador")
    domain_aut = st.text_input("Domain ID del autorizador")

    if domain_aut:
        aut = col_autorizadores.find_one({"domain_id": domain_aut})
        if not aut:
            nombre_aut = st.text_input("Nombre del autorizador")
            if st.button("Guardar autorizador"):
                col_autorizadores.insert_one({
                    "domain_id": domain_aut,
                    "nombre": nombre_aut
                })
                st.success("Autorizador guardado.")
        else:
            st.success(f"Bienvenido/a, {aut['nombre']}")
            agentes = list(col_agentes.find())
            agente_opciones = [f"{a['nombre']} ({a['domain_id']})" for a in agentes]
            seleccionado = st.selectbox("Selecciona un agente:", agente_opciones)

            if st.button("Poner en cola"):
                domain_agente = seleccionado.split("(")[-1][:-1]
                agente = col_agentes.find_one({"domain_id": domain_agente})
                ya = ahora()
                col_tiempos.insert_one({
                    "agente_id": agente["domain_id"],
                    "agente_nombre": agente["nombre"],
                    "autorizador_id": aut["domain_id"],
                    "autorizador_nombre": aut["nombre"],
                    "hora_ingreso": ya,
                    "estado": "Pendiente"
                })
                st.success("Agente en cola.")

# === PENDIENTES / AUTORIZADOS / EN CURSO ===
elif "Pendiente" in seleccion or "Autorizados" in seleccion or "curso" in seleccion:
    estado = "Pendiente" if "Pendiente" in seleccion else "Autorizado" if "Autorizados" in seleccion else "En curso"
    agentes_estado = list(col_tiempos.find({"estado": estado}))
    
    st.subheader(seleccion.split("[")[0].strip())
    
    if not agentes_estado:
        st.info(f"No hay agentes actualmente en estado '{estado}'.")
    else:
        opciones = [f"{a['agente_nombre']} ({a['agente_id']})" for a in agentes_estado]
        seleccionado = st.selectbox("Agente:", opciones)
        agente = next(a for a in agentes_estado if f"{a['agente_nombre']} ({a['agente_id']})" == seleccionado)

        # CRONÓMETRO
        hora = agente.get("hora_ingreso") if estado == "Pendiente" else agente.get("hora_autorizacion") if estado == "Autorizado" else agente.get("hora_inicio")
        tiempo = tiempo_transcurrido(hora)
        st.success(f"⏱ Tiempo en estado '{estado}': {tiempo}")

# === HISTORIAL ===
elif "Historial" in seleccion:
    st.subheader("📜 Historial de tiempos finalizados")
    finalizados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))

    if not finalizados:
        st.info("No hay tiempos completados.")
    else:
        df = pd.DataFrame(finalizados)
        df["Duración"] = df["duracion_minutos"].apply(formatear_duracion)
        df["Fecha Fin"] = pd.to_datetime(df["hora_fin"]).dt.strftime("%Y-%m-%d %H:%M")
        df = df[["agente_nombre", "autorizador_nombre", "Duración", "Fecha Fin"]]
        df.columns = ["Agente", "Autorizador", "Duración", "Fecha"]

        df.insert(0, "N°", range(len(df), 0, -1))  # numeración descendente
        st.dataframe(df, use_container_width=True)