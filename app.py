import streamlit as st
import pymongo
from datetime import datetime, timedelta
import pytz
import time

# === CONFIGURACIÓN ===
st.set_page_config(page_title="⏱ Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
MONGO_URI = st.secrets["mongo_uri"]
client = pymongo.MongoClient(MONGO_URI)
db = client["tiempo_personal"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]
col_tiempos = db["tiempos"]
zona_col = pytz.timezone("America/Bogota")

def ahora():
    return datetime.now(zona_col)

def ya_tuvo_hoy(domain_id):
    hoy = ahora().date()
    return col_tiempos.find_one({
        "agente_id": domain_id,
        "estado": "Completado",
        "hora_fin": {"$gte": datetime.combine(hoy, datetime.min.time(), zona_col)}
    })

# === INICIO ===
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")

# === AUTORIZADOR ===
st.subheader("🔐 Identificación del autorizador")
domain_aut = st.text_input("Domain ID del autorizador")
if not domain_aut:
    st.stop()

aut = col_autorizadores.find_one({"domain_id": domain_aut})
if not aut:
    nombre_aut = st.text_input("Nombre del autorizador")
    if nombre_aut:
        col_autorizadores.insert_one({"domain_id": domain_aut, "nombre": nombre_aut})
        st.success("Autorizador registrado.")
        st.rerun()
else:
    st.success(f"Bienvenido/a, {aut['nombre']}")

# === REGISTRO DE AGENTE ===
st.subheader("📝 Registrar nuevo agente en cola")
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

# === PENDIENTES ===
st.subheader("🕓 En cola (Pendiente)")
pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
if pendientes:
    for p in pendientes:
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{p['agente_nombre']}** ({p['agente_id']})")
                marcador = st.empty()
            with col2:
                if st.button(f"✅ Autorizar {p['agente_id']}"):
                    col_tiempos.update_one(
                        {"_id": p["_id"]},
                        {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                    )
                    st.rerun()
            for i in range(100000):
                delta = ahora() - p['hora_ingreso']
                mins, secs = divmod(delta.total_seconds(), 60)
                marcador.markdown(f"⏱️ En cola: **{int(mins)}m {int(secs)}s**")
                time.sleep(1)

# === AUTORIZADOS ===
st.subheader("🟢 Autorizados (esperando que arranquen)")
autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
if autorizados:
    for a in autorizados:
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{a['agente_nombre']}** ({a['agente_id']})")
                marcador = st.empty()
            with col2:
                if st.button(f"▶️ Iniciar {a['agente_id']}"):
                    col_tiempos.update_one(
                        {"_id": a["_id"]},
                        {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                    )
                    st.rerun()
            for i in range(100000):
                delta = ahora() - a['hora_autorizacion']
                mins, secs = divmod(delta.total_seconds(), 60)
                marcador.markdown(f"🕒 Esperando inicio: **{int(mins)}m {int(secs)}s**")
                time.sleep(1)

# === EN CURSO ===
st.subheader("⏳ Tiempos en curso")
en_curso = list(col_tiempos.find({"estado": "En curso"}))
if en_curso:
    for e in en_curso:
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{e['agente_nombre']}** ({e['agente_id']})")
                marcador = st.empty()
            with col2:
                if st.button(f"🛑 Finalizar {e['agente_id']}"):
                    fin = ahora()
                    duracion = (fin - e['hora_inicio']).total_seconds() / 60
                    col_tiempos.update_one(
                        {"_id": e["_id"]},
                        {
                            "$set": {
                                "estado": "Completado",
                                "hora_fin": fin,
                                "duracion_minutos": round(duracion, 2)
                            }
                        }
                    )
                    st.success(f"Tiempo finalizado: {round(duracion, 2)} minutos")
                    st.rerun()
            for i in range(100000):
                delta = ahora() - e['hora_inicio']
                mins, secs = divmod(delta.total_seconds(), 60)
                marcador.markdown(f"🟢 En curso: **{int(mins)}m {int(secs)}s**")
                time.sleep(1)

# === HISTORIAL ===
st.subheader("📜 Historial")
completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
if completados:
    import pandas as pd
    data = []
    for h in completados:
        data.append({
            "Agente": h["agente_nombre"],
            "Domain ID": h["agente_id"],
            "Autorizador": h["autorizador_nombre"],
            "Ingreso": h["hora_ingreso"].astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if h.get("hora_ingreso") else "",
            "Autorizado": h.get("hora_autorizacion", "").astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if h.get("hora_autorizacion") else "",
            "Inicio": h.get("hora_inicio", "").astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if h.get("hora_inicio") else "",
            "Fin": h.get("hora_fin", "").astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if h.get("hora_fin") else "",
            "Duración (min)": h.get("duracion_minutos", 0)
        })
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)
else:
    st.info("No hay registros completados aún.")