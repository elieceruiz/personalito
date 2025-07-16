import streamlit as st
from datetime import datetime
from pymongo import MongoClient
import pandas as pd
import pytz
from streamlit_autorefresh import st_autorefresh

# === CONFIGURACIÓN ===
st.set_page_config(page_title="📋 Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
client = MongoClient(st.secrets["mongo_uri"])
db = client["tiempo_personal"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]
col_tiempos = db["tiempos"]
zona_col = pytz.timezone("America/Bogota")

# === FUNCIONES ===
def ahora():
    return datetime.utcnow()

def formatear_duracion(delta):
    total_seg = int(delta.total_seconds())
    h, m = divmod(total_seg, 3600)
    m, s = divmod(m, 60)
    return f"{h:02}:{m:02}:{s:02}"

def tiempo_transcurrido(inicio):
    return formatear_duracion(ahora() - inicio)

def ya_solicito_hoy(domain_id):
    ahora_col = datetime.now(zona_col)
    inicio_dia = ahora_col.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc)
    fin_dia = ahora_col.replace(hour=23, minute=59, second=59, microsecond=999999).astimezone(pytz.utc)
    registro = col_tiempos.find_one({
        "agente_id": domain_id,
        "estado": "Completado",
        "hora_fin": {"$gte": inicio_dia, "$lte": fin_dia}
    })
    return bool(registro)

# === INTERFAZ ===
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")
domain_aut = st.text_input("🧑‍💼 Domain ID del autorizador")

if domain_aut:
    autorizador = col_autorizadores.find_one({"domain_id": domain_aut})
    if not autorizador:
        nombre_aut = st.text_input("Nombre del autorizador")
        if nombre_aut:
            col_autorizadores.insert_one({"domain_id": domain_aut, "nombre": nombre_aut})
            st.rerun()
    else:
        st.success(f"Autorizador: {autorizador['nombre']}")

        opciones = [
            "📤 Registrar nuevo agente en cola",
            "📤 En cola (Pendiente)",
            "🟢 Autorizados (esperando que arranquen)",
            "⏳ Tiempo personal en curso",
            "📑 Historial"
        ]
        seleccion = st.selectbox("Selecciona una sección", opciones)

        if seleccion == "📤 Registrar nuevo agente en cola":
            domain_agente = st.text_input("🆔 Domain ID del agente")
            if domain_agente:
                if ya_solicito_hoy(domain_agente):
                    registro = col_tiempos.find_one({
                        "agente_id": domain_agente,
                        "estado": "Completado"
                    }, sort=[("hora_fin", -1)])
                    if registro:
                        hora_fin_col = registro["hora_fin"].astimezone(zona_col).strftime("%H:%M:%S")
                        st.info(f"⛔ Este agente ya completó su tiempo personal hoy a las {hora_fin_col}.")
                    else:
                        st.warning("⛔ Este agente ya ha solicitado tiempo personal hoy.")
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
                            existente = col_tiempos.find_one({
                                "agente_id": domain_agente,
                                "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                            })
                            if existente:
                                st.warning("Este agente ya tiene un tiempo en proceso.")
                            else:
                                col_tiempos.insert_one({
                                    "agente_id": domain_agente,
                                    "agente_nombre": agente["nombre"],
                                    "autorizador_id": domain_aut,
                                    "autorizador_nombre": autorizador["nombre"],
                                    "hora_ingreso": ahora(),
                                    "estado": "Pendiente"
                                })
                                st.success("Agente agregado a la cola.")
                                st.rerun()

        elif seleccion == "📤 En cola (Pendiente)":
            st_autorefresh(interval=1000, key="pendiente_refresh")
            pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
            if not pendientes:
                st.info("No hay agentes en cola.")
            else:
                seleccionado = st.selectbox("Selecciona un agente", [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes])
                agente_id = seleccionado.split("(")[-1].replace(")", "")
                agente_data = next(p for p in pendientes if p["agente_id"] == agente_id)
                tiempo = tiempo_transcurrido(agente_data["hora_ingreso"])
                st.write(f"⏳ Esperando hace: {tiempo}")
                if st.button("✅ Autorizar"):
                    col_tiempos.update_one(
                        {"_id": agente_data["_id"]},
                        {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                    )
                    st.rerun()

        elif seleccion == "🟢 Autorizados (esperando que arranquen)":
            st_autorefresh(interval=1000, key="autorizado_refresh")
            autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
            if not autorizados:
                st.info("No hay agentes autorizados.")
            else:
                seleccionado = st.selectbox("Selecciona un agente", [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados])
                agente_id = seleccionado.split("(")[-1].replace(")", "")
                agente_data = next(a for a in autorizados if a["agente_id"] == agente_id)
                tiempo = tiempo_transcurrido(agente_data["hora_autorizacion"])
                st.write(f"⏳ Autorizado hace: {tiempo}")
                if st.button("▶️ Iniciar tiempo"):
                    col_tiempos.update_one(
                        {"_id": agente_data["_id"]},
                        {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                    )
                    st.rerun()

        elif seleccion == "⏳ Tiempo personal en curso":
            st_autorefresh(interval=1000, key="curso_refresh")
            en_curso = list(col_tiempos.find({"estado": "En curso"}))
            if not en_curso:
                st.info("No hay agentes en tiempo personal.")
            else:
                seleccionado = st.selectbox("Selecciona un agente", [f"{e['agente_nombre']} ({e['agente_id']})" for e in en_curso])
                agente_id = seleccionado.split("(")[-1].replace(")", "")
                agente_data = next(e for e in en_curso if e["agente_id"] == agente_id)
                tiempo = tiempo_transcurrido(agente_data["hora_inicio"])
                st.write(f"⏳ En curso desde: {tiempo}")
                if st.button("🛑 Finalizar tiempo"):
                    fin = ahora()
                    duracion = fin - agente_data["hora_inicio"]
                    col_tiempos.update_one(
                        {"_id": agente_data["_id"]},
                        {"$set": {
                            "estado": "Completado",
                            "hora_fin": fin,
                            "duracion_segundos": int(duracion.total_seconds())
                        }}
                    )
                    st.success(f"Tiempo finalizado: {formatear_duracion(duracion)}")
                    st.rerun()

        elif seleccion == "📑 Historial":
            completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
            if not completados:
                st.info("No hay registros completados.")
            else:
                historial = []
                for i, c in enumerate(completados, 1):
                    historial.append({
                        "#": len(completados) - i + 1,
                        "Agente": c["agente_nombre"],
                        "Domain ID": c["agente_id"],
                        "Autorizador": c["autorizador_nombre"],
                        "Fecha": c["hora_inicio"].astimezone(zona_col).strftime("%Y-%m-%d"),
                        "Duración": formatear_duracion(c["hora_fin"] - c["hora_inicio"]) if "hora_fin" in c else "-"
                    })
                df = pd.DataFrame(historial)
                st.dataframe(df, use_container_width=True)