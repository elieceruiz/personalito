import streamlit as st
from datetime import datetime
from pymongo import MongoClient
import pytz
import pandas as pd
import time

# === CONFIG ===
st.set_page_config(page_title="⏱ Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
colombia = pytz.timezone("America/Bogota")

def ahora():
    return datetime.now(colombia)

# === DATABASE CONNECTION ===
client = MongoClient(st.secrets["mongo_uri"])
db = client["tiempo_personal"]
coleccion_tiempos = db["tiempos"]
coleccion_agentes = db["agentes"]
coleccion_autorizadores = db["autorizadores"]

# === FUNCIONES ===
def tiempo_transcurrido(inicio):
    if not inicio:
        return "--:--:--"
    delta = ahora() - inicio
    return str(delta).split(".")[0]

def hay_solicitud_activa_para(agente_id):
    hoy = ahora().date()
    inicio_hoy = datetime.combine(hoy, datetime.min.time(), tzinfo=colombia)
    return coleccion_tiempos.find_one({
        "agente_id": agente_id,
        "hora_ingreso": {"$gte": inicio_hoy}
    })

# === UI ===
st.title("\u23f1 Registro de Tiempo Personal – personalito (Walmart DAS)")

seccion = st.selectbox("Selecciona una sección:", [
    "📄 Registrar nuevo agente en cola",
    "🔐 Identificación del autorizador",
    "⏰ Tiempo personal en curso",
    "📜 Historial de tiempos finalizados",
])

# === SECCION 1: Registrar nuevo agente en cola ===
if seccion == "📄 Registrar nuevo agente en cola":
    agente_id = st.text_input("Domain ID del agente", key="agente_id")
    agente_nombre = st.text_input("Nombre del agente", key="agente_nombre")
    autorizador_id = st.text_input("Domain ID del autorizador")
    autorizador_nombre = st.text_input("Nombre del autorizador")

    if st.button("Poner en cola"):
        if not hay_solicitud_activa_para(agente_id):
            coleccion_tiempos.insert_one({
                "agente_id": agente_id,
                "agente_nombre": agente_nombre,
                "autorizador_id": autorizador_id,
                "autorizador_nombre": autorizador_nombre,
                "hora_ingreso": ahora(),
                "estado": "Pendiente",
            })
            st.success("Agente registrado en cola correctamente.")
        else:
            st.warning("Este agente ya tiene una solicitud registrada para hoy.")

# === SECCION 2: Identificación del autorizador ===
el_autorizador = None
if seccion == "🔐 Identificación del autorizador":
    autorizador_id = st.text_input("Domain ID del autorizador", key="auth_id")
    autorizador_nombre = st.text_input("Nombre del autorizador", key="auth_nombre")
    st.success(f"Bienvenido/a, {autorizador_nombre}")

    en_cola = list(coleccion_tiempos.find({"estado": "Pendiente"}))
    opciones = [f"{doc['agente_nombre']} ({doc['agente_id']})" for doc in en_cola]
    seleccion = st.selectbox("Selecciona un agente:", opciones) if opciones else None

    if seleccion and st.button("Autorizar"):
        agente_id = seleccion.split("(")[-1].strip(")")
        coleccion_tiempos.update_one(
            {"agente_id": agente_id, "estado": "Pendiente"},
            {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
        )
        st.success("Agente autorizado correctamente.")

# === SECCION 3: Tiempo personal en curso ===
if seccion == "⏰ Tiempo personal en curso":
    en_curso = list(coleccion_tiempos.find({"estado": {"$in": ["Autorizado", "En curso"]}}))
    seleccion = st.selectbox("Agente en curso:", [f"{doc['agente_nombre']} ({doc['agente_id']})" for doc in en_curso]) if en_curso else None

    if seleccion:
        agente_id = seleccion.split("(")[-1].strip(")")
        seleccionado = coleccion_tiempos.find_one({"agente_id": agente_id, "estado": {"$in": ["Autorizado", "En curso"]}})

        if seleccionado["estado"] == "Autorizado":
            coleccion_tiempos.update_one({"_id": seleccionado["_id"]}, {"$set": {"estado": "En curso", "hora_inicio": ahora()}})
            seleccionado = coleccion_tiempos.find_one({"_id": seleccionado["_id"]})

        hora = seleccionado.get("hora_inicio") or seleccionado.get("hora_autorizacion") or seleccionado.get("hora_ingreso")
        tiempo = tiempo_transcurrido(hora)
        st.metric("Duración", tiempo)

        if st.button("⛔ Finalizar tiempo"):
            coleccion_tiempos.update_one({"_id": seleccionado["_id"]}, {
                "$set": {
                    "estado": "Completado",
                    "hora_fin": ahora()
                }
            })
            st.success("Tiempo personal finalizado.")
            st.rerun()

# === SECCION 4: Historial ===
if seccion == "📜 Historial de tiempos finalizados":
    tiempos_finalizados = list(coleccion_tiempos.find({"estado": "Completado"}))
    tiempos_finalizados.sort(key=lambda x: x.get("hora_fin", datetime.min), reverse=True)

    if tiempos_finalizados:
        filas = []
        for doc in tiempos_finalizados:
            duracion = doc.get("hora_fin") - doc.get("hora_inicio")
            filas.append({
                "Agente": doc.get("agente_nombre", ""),
                "Domain ID": doc.get("agente_id", ""),
                "Autorizador": doc.get("autorizador_nombre", ""),
                "Duración (hh:mm:ss)": str(duracion).split(".")[0],
                "Inicio": doc.get("hora_inicio").astimezone(colombia).strftime("%H:%M:%S"),
                "Fin": doc.get("hora_fin").astimezone(colombia).strftime("%H:%M:%S"),
                "Fecha": doc.get("hora_fin").astimezone(colombia).strftime("%Y-%m-%d"),
            })

        df = pd.DataFrame(filas)
        df["Nº"] = range(len(df), 0, -1)
        cols = ["Nº"] + [col for col in df.columns if col != "Nº"]
        df = df[cols]
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No hay registros finalizados.")
