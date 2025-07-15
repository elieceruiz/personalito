import streamlit as st
import pymongo
from datetime import datetime
import pandas as pd
import pytz

# === CONFIG ===
st.set_page_config(page_title="⏱ Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
MONGO_URI = st.secrets["mongo_uri"]
client = pymongo.MongoClient(MONGO_URI)
db = client["tiempo_personal"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]
col_tiempos = db["tiempos"]
zona_col = pytz.timezone("America/Bogota")

# === FUNCIONES ===
def ahora():
    return datetime.utcnow()

def tiempo_transcurrido(inicio):
    delta = ahora() - inicio
    minutos, segundos = divmod(delta.total_seconds(), 60)
    return f"{int(minutos)}m {int(segundos)}s"

def ya_tuvo_hoy(domain_id):
    hoy = datetime.now(zona_col).date()
    inicio = datetime.combine(hoy, datetime.min.time()).astimezone(zona_col).astimezone(pytz.utc)
    fin = datetime.combine(hoy, datetime.max.time()).astimezone(zona_col).astimezone(pytz.utc)
    return col_tiempos.find_one({
        "agente_id": domain_id,
        "hora_ingreso": {"$gte": inicio, "$lte": fin}
    })

# === UI PRINCIPAL ===
st.title("⏱ Registro de Tiempo Personal – personalito (Walmart DAS)")

seccion = st.selectbox(
    "Selecciona una sección:",
    ["📝 Registrar nuevo agente en cola", "🕓 En cola (Pendiente)", "🟢 Autorizados (esperando que arranquen)", "⏳ Tiempo personal en curso"]
)

# === 1. REGISTRAR NUEVO ===
if seccion == "📝 Registrar nuevo agente en cola":
    domain_aut = st.text_input("Domain ID del autorizador")
    if domain_aut:
        aut = col_autorizadores.find_one({"domain_id": domain_aut})
        if not aut:
            nombre_aut = st.text_input("Nombre del autorizador")
            if nombre_aut:
                col_autorizadores.insert_one({"domain_id": domain_aut, "nombre": nombre_aut})
                st.success("Autorizador registrado.")
                st.rerun()
        else:
            st.success(f"Bienvenido/a, {aut['nombre']}")
            domain_agente = st.text_input("Domain ID del agente")
            if domain_agente:
                if ya_tuvo_hoy(domain_agente):
                    st.warning("Este agente ya tuvo tiempo personal hoy.")
                else:
                    agente = col_agentes.find_one({"domain_id": domain_agente})
                    if not agente:
                        nombre_agente = st.text_input("Nombre del agente")
                        if nombre_agente:
                            col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                            st.success("Agente registrado.")
                            st.rerun()
                    else:
                        if st.button("➕ Agregar a la cola (Pendiente)"):
                            ya_en_proceso = col_tiempos.find_one({
                                "agente_id": domain_agente,
                                "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                            })
                            if ya_en_proceso:
                                st.warning("Este agente ya tiene un tiempo en proceso.")
                            else:
                                col_tiempos.insert_one({
                                    "agente_id": domain_agente,
                                    "agente_nombre": agente["nombre"],
                                    "autorizador_id": domain_aut,
                                    "autorizador_nombre": aut["nombre"],
                                    "hora_ingreso": ahora(),
                                    "estado": "Pendiente"
                                })
                                st.success("Agente agregado a la cola.")
                                st.rerun()

# === 2. EN COLA (PENDIENTE) ===
elif seccion == "🕓 En cola (Pendiente)":
    pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
    st.info(f"Agentes en cola: {len(pendientes)}")
    opciones = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
    seleccion = st.selectbox("Selecciona agente a autorizar", opciones) if opciones else None
    if seleccion:
        domain_id = seleccion.split("(")[-1].strip(")")
        agente = next((p for p in pendientes if p["agente_id"] == domain_id), None)
        if agente:
            st.write(f"⏱ En cola: {tiempo_transcurrido(agente['hora_ingreso'])}")
            if st.button("✅ Autorizar"):
                col_tiempos.update_one({"_id": agente["_id"]}, {
                    "$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}
                })
                st.rerun()
    else:
        st.info("No hay agentes actualmente en cola.")

# === 3. AUTORIZADOS (esperando arranque) ===
elif seccion == "🟢 Autorizados (esperando que arranquen)":
    autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
    st.info(f"Agentes autorizados: {len(autorizados)}")
    opciones = [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados]
    seleccion = st.selectbox("Selecciona agente para iniciar", opciones) if opciones else None
    if seleccion:
        domain_id = seleccion.split("(")[-1].strip(")")
        agente = next((a for a in autorizados if a["agente_id"] == domain_id), None)
        if agente:
            st.write(f"⏱ Autorizado hace: {tiempo_transcurrido(agente['hora_autorizacion'])}")
            if st.button("▶️ Iniciar tiempo"):
                col_tiempos.update_one({"_id": agente["_id"]}, {
                    "$set": {"estado": "En curso", "hora_inicio": ahora()}
                })
                st.rerun()
    else:
        st.info("No hay agentes autorizados.")

# === 4. EN CURSO ===
elif seccion == "⏳ Tiempo personal en curso":
    en_curso = list(col_tiempos.find({"estado": "En curso"}))
    st.info(f"Tiempos personales activos: {len(en_curso)}")
    opciones = [f"{e['agente_nombre']} ({e['agente_id']})" for e in en_curso]
    seleccion = st.selectbox("Selecciona agente en curso", opciones) if opciones else None
    if seleccion:
        domain_id = seleccion.split("(")[-1].strip(")")
        agente = next((e for e in en_curso if e["agente_id"] == domain_id), None)
        if agente:
            st.write(f"⏱ En curso: {tiempo_transcurrido(agente['hora_inicio'])}")
            if st.button("🛑 Finalizar tiempo"):
                fin = ahora()
                duracion = (fin - agente['hora_inicio']).total_seconds() / 60
                col_tiempos.update_one({"_id": agente["_id"]}, {
                    "$set": {
                        "estado": "Completado",
                        "hora_fin": fin,
                        "duracion_minutos": round(duracion, 2)
                    }
                })
                st.success(f"Tiempo finalizado: {round(duracion, 2)} minutos")
                st.rerun()
    else:
        st.info("No hay tiempos personales activos.")