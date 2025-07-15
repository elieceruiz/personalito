import streamlit as st
import pymongo
from datetime import datetime, timedelta
import pandas as pd
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

# === FUNCIONES ===
def ahora():
    return datetime.utcnow()

def hoy_col():
    return datetime.now(zona_col).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.UTC)

def cronometro_segundos(inicio):
    duracion = (datetime.utcnow() - inicio).total_seconds()
    mins = int(duracion // 60)
    segs = int(duracion % 60)
    return f"{mins}m {segs}s"

# === IDENTIFICACIÓN DE AUTORIZADOR ===
st.title("⏱ Registro de Tiempo Personal – personalito (Walmart DAS)")
st.subheader("🔐 Identificación del autorizador")
domain_aut = st.text_input("Domain ID del autorizador")

if domain_aut:
    aut = col_autorizadores.find_one({"domain_id": domain_aut})
    if not aut:
        nombre_aut = st.text_input("Nombre del autorizador")
        if nombre_aut:
            col_autorizadores.insert_one({"domain_id": domain_aut, "nombre": nombre_aut})
            st.success("Autorizador registrado exitosamente.")
            st.rerun()
    else:
        st.success(f"Bienvenido/a, {aut['nombre']}")

        # === REGISTRO DE SOLICITUD ===
        st.subheader("📝 Registrar nuevo agente en cola")
        domain_agente = st.text_input("Domain ID del agente")
        if domain_agente:
            agente = col_agentes.find_one({"domain_id": domain_agente})
            if not agente:
                nombre_agente = st.text_input("Nombre del agente")
                if nombre_agente:
                    col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                    st.success("Agente registrado.")
                    st.rerun()
            else:
                ya_hoy = col_tiempos.find_one({
                    "agente_id": domain_agente,
                    "hora_ingreso": {"$gte": hoy_col()}
                })
                if ya_hoy:
                    st.warning("⛔ Este agente ya tuvo tiempo personal hoy.")
                else:
                    if st.button("➕ Agregar a la cola (Pendiente)"):
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

        # === EN COLA (PENDIENTE) ===
        st.subheader("🕓 En cola (Pendiente)")
        pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
        for p in pendientes:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{p['agente_nombre']}** ({p['agente_id']}) – 🕒 {cronometro_segundos(p['hora_ingreso'])}")
            with col2:
                if st.button(f"✅ Autorizar {p['agente_id']}"):
                    col_tiempos.update_one(
                        {"_id": p["_id"]},
                        {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                    )
                    st.rerun()

        # === AUTORIZADOS ===
        st.subheader("🟢 Autorizados (esperando que arranquen)")
        autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
        for a in autorizados:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{a['agente_nombre']}** ({a['agente_id']}) – 🕒 {cronometro_segundos(a['hora_autorizacion'])}")
            with col2:
                if st.button(f"▶️ Iniciar tiempo de {a['agente_id']}"):
                    col_tiempos.update_one(
                        {"_id": a["_id"]},
                        {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                    )
                    st.rerun()

        # === EN CURSO ===
        st.subheader("⏳ Tiempos en curso")
        en_curso = list(col_tiempos.find({"estado": "En curso"}))
        for e in en_curso:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{e['agente_nombre']}** ({e['agente_id']}) – 🕒 {cronometro_segundos(e['hora_inicio'])}")
            with col2:
                if st.button(f"🛑 Finalizar tiempo de {e['agente_id']}"):
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

        # === HISTORIAL ===
        st.subheader("📜 Historial")
        completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
        historial = []
        for h in completados:
            ingreso = h.get("hora_ingreso")
            autorizacion = h.get("hora_autorizacion")
            inicio = h.get("hora_inicio")
            fin = h.get("hora_fin")
            historial.append({
                "Agente": h["agente_nombre"],
                "Domain ID": h["agente_id"],
                "Autorizador": h["autorizador_nombre"],
                "Ingreso": ingreso.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if ingreso else "",
                "Autorizado": autorizacion.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if autorizacion else "",
                "Inicio": inicio.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if inicio else "",
                "Fin": fin.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if fin else "",
                "Duración (min)": h.get("duracion_minutos", 0)
            })

        if historial:
            df = pd.DataFrame(historial)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Aún no hay registros completados.")