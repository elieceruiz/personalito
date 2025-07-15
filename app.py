import streamlit as st
from pymongo import MongoClient
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import pytz

# === CONFIG ===
st.set_page_config(page_title="⏱ Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
colombia = pytz.timezone("America/Bogota")

def ahora():
    return datetime.now(colombia)

# === CONEXIÓN BASE DE DATOS ===
client = MongoClient(st.secrets["mongo_uri"])
db = client["tiempo_personal"]
col_tiempos = db["tiempos"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]

# === CONTADORES POR ESTADO ===
n_pendientes = col_tiempos.count_documents({"estado": "Pendiente"})
n_autorizados = col_tiempos.count_documents({"estado": "Autorizado"})
n_en_curso = col_tiempos.count_documents({"estado": "En curso"})

# === INTERFAZ PRINCIPAL ===
st.title("⏱ Registro de Tiempo Personal – personalito (Walmart DAS)")

secciones = [
    f"📋 Registrar nuevo agente en cola",
    f"📤 En cola (Pendiente) [{n_pendientes}]",
    f"🟢 Autorizados (esperando que arranquen) [{n_autorizados}]",
    f"⏳ Tiempo personal en curso [{n_en_curso}]",
    "📜 Historial"
]

seleccion = st.selectbox("Selecciona una sección:", secciones)

# === FUNCIÓN TIEMPO TRANSCURRIDO ===
def tiempo_transcurrido(inicio):
    if not inicio:
        return "00:00"
    delta = ahora() - inicio
    minutos, segundos = divmod(int(delta.total_seconds()), 60)
    return f"{minutos:02d}:{segundos:02d}"

# === REGISTRAR AGENTE EN COLA ===
if seleccion.startswith("📋"):
    st.subheader("🔐 Identificación del autorizador")
    domain_aut = st.text_input("Domain ID del autorizador")
    
    if domain_aut:
        aut = col_autorizadores.find_one({"domain_id": domain_aut})
        if not aut:
            nombre_aut = st.text_input("Nombre del autorizador")
            if nombre_aut:
                col_autorizadores.insert_one({
                    "domain_id": domain_aut,
                    "nombre": nombre_aut
                })
                st.success("Autorizador registrado.")
        else:
            st.success(f"Bienvenido/a, {aut['nombre']}")
            st.subheader("👤 Registro de agente")
            agente_id = st.text_input("Domain ID del agente")
            agente_nombre = st.text_input("Nombre del agente")
            if st.button("Poner en cola"):
                if not col_tiempos.find_one({"agente_id": agente_id, "estado": {"$ne": "Completado"}}):
                    col_agentes.update_one(
                        {"domain_id": agente_id},
                        {"$set": {"nombre": agente_nombre}},
                        upsert=True
                    )
                    col_tiempos.insert_one({
                        "agente_id": agente_id,
                        "agente_nombre": agente_nombre,
                        "autorizador_id": domain_aut,
                        "autorizador_nombre": aut["nombre"],
                        "hora_ingreso": ahora(),
                        "estado": "Pendiente"
                    })
                    st.success("Agente registrado y en cola.")
                else:
                    st.warning("Ese agente ya tiene un registro activo.")

# === AUTORIZAR AGENTE PENDIENTE ===
elif seleccion.startswith("📤"):
    pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
    if pendientes:
        opciones = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
        seleccionado = st.selectbox("Selecciona un agente pendiente:", opciones)
        agente = pendientes[opciones.index(seleccionado)]
        hora = agente.get("hora_ingreso")
        tiempo = tiempo_transcurrido(hora)
        st.write(f"🕒 Tiempo en espera: **{tiempo}**")
        if st.button("Autorizar"):
            col_tiempos.update_one(
                {"_id": agente["_id"]},
                {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
            )
            st.success("Agente autorizado.")

# === INICIAR TIEMPO AUTORIZADO ===
elif seleccion.startswith("🟢"):
    autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
    if autorizados:
        opciones = [f"{p['agente_nombre']} ({p['agente_id']})" for p in autorizados]
        seleccionado = st.selectbox("Selecciona un agente autorizado:", opciones)
        agente = autorizados[opciones.index(seleccionado)]
        hora = agente.get("hora_autorizacion")
        tiempo = tiempo_transcurrido(hora)
        st.write(f"🕒 Tiempo desde autorización: **{tiempo}**")
        if st.button("Iniciar tiempo personal"):
            col_tiempos.update_one(
                {"_id": agente["_id"]},
                {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
            )
            st.success("Tiempo iniciado.")

# === FINALIZAR TIEMPO PERSONAL EN CURSO ===
elif seleccion.startswith("⏳"):
    en_curso = list(col_tiempos.find({"estado": "En curso"}))
    if en_curso:
        opciones = [f"{p['agente_nombre']} ({p['agente_id']})" for p in en_curso]
        seleccionado = st.selectbox("Agente en curso:", opciones)
        agente = en_curso[opciones.index(seleccionado)]
        hora = agente.get("hora_inicio")
        tiempo = tiempo_transcurrido(hora)
        st.write(f"🕒 Tiempo en curso: **{tiempo}**")
        if st.button("Finalizar tiempo"):
            hora_fin = ahora()
            duracion = (hora_fin - hora).total_seconds() / 60
            col_tiempos.update_one(
                {"_id": agente["_id"]},
                {"$set": {
                    "estado": "Completado",
                    "hora_fin": hora_fin,
                    "duracion_minutos": round(duracion, 2)
                }}
            )
            st.success("Tiempo finalizado.")

# === HISTORIAL DE TIEMPOS ===
elif seleccion == "📜 Historial":
    historial = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
    if historial:
        df = pd.DataFrame(historial)
        df["Duración"] = df["duracion_minutos"].apply(lambda x: f"{int(x):02d}:{int((x%1)*60):02d}")
        df["Autorizador"] = df["autorizador_nombre"]
        df["Agente"] = df["agente_nombre"]
        df = df[["Agente", "Autorizador", "Duración", "hora_fin"]]
        df = df.rename(columns={"hora_fin": "Finalizó"})
        df["N°"] = range(len(df), 0, -1)
        df = df[["N°"] + [col for col in df.columns if col != "N°"]]
        st.dataframe(df, use_container_width=True)