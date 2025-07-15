import streamlit as st
from datetime import datetime
from pymongo import MongoClient
import pytz
import pandas as pd

# === CONFIGURACIÓN ===
st.set_page_config(page_title="📋 Registro de Tiempo Personal – personalito (Walmart DAS)")
tz = pytz.timezone("America/Bogota")
client = MongoClient(st.secrets["mongo_uri"])
db = client["personalito"]
coleccion = db["tiempos"]

# === FUNCIONES ===
def ahora():
    return datetime.now(tz)

def tiempo_transcurrido(inicio):
    return ahora() - inicio

def formatear_tiempo(segundos):
    minutos, segundos = divmod(int(segundos), 60)
    return f"{minutos}m {segundos:02d}s"

# === IDENTIFICACIÓN DEL AUTORIZADOR ===
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")
st.subheader("🔐 Identificación del autorizador")
id_autorizador = st.text_input("Domain ID del autorizador", key="id_autorizador")
if not id_autorizador:
    st.stop()
st.success(f"Bienvenido/a, {id_autorizador}")

# === SELECCIÓN DE SECCIÓN ===
secciones = {
    "📋 Registrar nuevo agente en cola": "registro",
    "🧑‍🤝‍🧑 En cola (Pendiente)": "pendiente",
    "🟢 Autorizados (esperando que arranquen)": "autorizado",
    "⏳ Tiempo personal en curso": "en_curso",
    "📜 Historial de tiempos finalizados": "historial"
}
st.markdown("---")
st.markdown("###")
seccion = st.selectbox("Selecciona una sección:", list(secciones.keys()))
estado_actual = secciones[seccion]

# === CONTADORES ===
pendientes = list(coleccion.find({"estado": "pendiente"}))
autorizados = list(coleccion.find({"estado": "autorizado"}))
en_curso = list(coleccion.find({"estado": "en_curso"}))
st.markdown(
    f"🧑‍🤝‍🧑 En cola: {len(pendientes)} | 🟢 Autorizados: {len(autorizados)} | ⏳ En curso: {len(en_curso)}"
)

st.markdown("---")

# === SECCIÓN: REGISTRAR NUEVO ===
if estado_actual == "registro":
    st.subheader("📋 Registrar nuevo agente en cola")
    id_agente = st.text_input("Domain ID del agente")
    if id_agente:
        ya_tuvo = coleccion.find_one({
            "domain_id": id_agente,
            "estado": "finalizado",
            "fecha": {"$gte": ahora().replace(hour=0, minute=0, second=0, microsecond=0)}
        })
        if ya_tuvo:
            st.warning("Este agente ya tuvo tiempo personal hoy.")
        else:
            if st.button("➕ Registrar en cola"):
                coleccion.insert_one({
                    "domain_id": id_agente,
                    "estado": "pendiente",
                    "hora_ingreso": ahora(),
                    "fecha": ahora()
                })
                st.success("Agente registrado en cola.")
                st.rerun()

# === SECCIÓN: PENDIENTE ===
elif estado_actual == "pendiente":
    st.subheader("🧑‍🤝‍🧑 En cola (Pendiente)")
    if not pendientes:
        st.info("No hay agentes actualmente en cola.")
    else:
        nombres = [f"{a.get('nombre', a['domain_id'])} ({a['domain_id']})" for a in pendientes]
        seleccion = st.selectbox("Selecciona agente a autorizar", nombres)
        seleccionado = pendientes[nombres.index(seleccion)]
        segundos = tiempo_transcurrido(seleccionado["hora_ingreso"]).total_seconds()
        st.info(f"⏱ En cola hace: {formatear_tiempo(segundos)}")
        if st.button("✅ Autorizar"):
            coleccion.update_one({"_id": seleccionado["_id"]}, {
                "$set": {"estado": "autorizado", "hora_autorizado": ahora()}
            })
            st.success("Agente autorizado.")
            st.rerun()

# === SECCIÓN: AUTORIZADO ===
elif estado_actual == "autorizado":
    st.subheader("🟢 Autorizados (esperando que arranquen)")
    if not autorizados:
        st.info("No hay agentes autorizados.")
    else:
        nombres = [f"{a.get('nombre', a['domain_id'])} ({a['domain_id']})" for a in autorizados]
        seleccion = st.selectbox("Selecciona agente para iniciar", nombres)
        seleccionado = autorizados[nombres.index(seleccion)]
        segundos = tiempo_transcurrido(seleccionado["hora_autorizado"]).total_seconds()
        st.info(f"⏱ Autorizado hace: {formatear_tiempo(segundos)}")
        if st.button("▶️ Iniciar tiempo"):
            coleccion.update_one({"_id": seleccionado["_id"]}, {
                "$set": {"estado": "en_curso", "hora_inicio": ahora()}
            })
            st.success("Tiempo iniciado.")
            st.rerun()

# === SECCIÓN: EN CURSO ===
elif estado_actual == "en_curso":
    st.subheader("⏳ Tiempo personal en curso")
    if not en_curso:
        st.info("No hay agentes con tiempo personal en curso.")
    else:
        nombres = [f"{a.get('nombre', a['domain_id'])} ({a['domain_id']})" for a in en_curso]
        seleccion = st.selectbox("Selecciona agente para finalizar", nombres)
        seleccionado = en_curso[nombres.index(seleccion)]
        segundos = tiempo_transcurrido(seleccionado["hora_inicio"]).total_seconds()
        st.info(f"⏳ En curso hace: {formatear_tiempo(segundos)}")
        if st.button("⏹ Finalizar"):
            fin = ahora()
            duracion = (fin - seleccionado["hora_inicio"]).total_seconds()
            coleccion.update_one({"_id": seleccionado["_id"]}, {
                "$set": {
                    "estado": "finalizado",
                    "hora_fin": fin,
                    "duracion_segundos": duracion
                }
            })
            st.success("Tiempo finalizado.")
            st.rerun()

# === SECCIÓN: HISTORIAL ===
elif estado_actual == "historial":
    st.subheader("📜 Historial de tiempos finalizados")
    finalizados = list(coleccion.find({"estado": "finalizado"}).sort("hora_fin", -1))
    if not finalizados:
        st.info("No hay tiempos finalizados registrados.")
    else:
        filas = []
        for f in finalizados:
            filas.append({
                "Agente": f.get("nombre", f["domain_id"]),
                "Domain ID": f["domain_id"],
                "Fecha": f["fecha"].strftime("%Y-%m-%d"),
                "Duración": formatear_tiempo(f["duracion_segundos"])
            })
        df = pd.DataFrame(filas)
        df.insert(0, "#", range(len(df), 0, -1))
        st.dataframe(df)