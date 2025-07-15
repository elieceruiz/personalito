import streamlit as st
import pymongo
from datetime import datetime
import pytz
import pandas as pd
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

def hoy_colombia():
    return datetime.now(zona_col).date()

def tiempo_transcurrido(inicio):
    if not inicio:
        return "00:00:00"
    if inicio.tzinfo is None:
        inicio = inicio.replace(tzinfo=pytz.UTC)
    delta = ahora() - inicio
    horas, rem = divmod(int(delta.total_seconds()), 3600)
    minutos, segundos = divmod(rem, 60)
    return f"{horas:02}:{minutos:02}:{segundos:02}"

# === INTERFAZ ===
st.title("⏱ Registro de Tiempo Personal – personalito (Walmart DAS)")
autorizador_id = st.text_input("Domain ID del autorizador", max_chars=50)

if autorizador_id:
    autorizador = col_autorizadores.find_one({"domain_id": autorizador_id})
    if not autorizador:
        nombre_aut = st.text_input("Nombre del autorizador")
        if nombre_aut:
            col_autorizadores.insert_one({"domain_id": autorizador_id, "nombre": nombre_aut})
            st.success("Autorizador registrado exitosamente.")
            st.rerun()
    else:
        st.markdown(f"**👤 Bienvenido/a:** {autorizador['nombre']}")
        seccion = st.selectbox(
            "Selecciona una sección:",
            [
                "📋 Registrar nuevo agente en cola",
                "📤 En cola (Pendiente)",
                "🟢 Autorizados (esperando que arranquen)",
                "⏳ Tiempo personal en curso",
                "📜 Historial"
            ]
        )

        if seccion == "📋 Registrar nuevo agente en cola":
            st.subheader("Registrar nuevo agente")
            domain_agente = st.text_input("Domain ID del agente", max_chars=50)
            if domain_agente:
                agente = col_agentes.find_one({"domain_id": domain_agente})
                if not agente:
                    nombre_agente = st.text_input("Nombre del agente")
                    if nombre_agente:
                        col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                        st.success("Agente registrado exitosamente.")
                        st.rerun()
                else:
                    # Restricción: ¿ya tiene uno completado hoy?
                    completado_hoy = col_tiempos.find_one({
                        "agente_id": domain_agente,
                        "estado": "Completado",
                        "hora_fin": {"$gte": datetime.combine(hoy_colombia(), datetime.min.time()).astimezone(pytz.UTC)}
                    })
                    if completado_hoy:
                        st.warning("Este agente ya utilizó su tiempo personal hoy.")
                    else:
                        if st.button("➕ Agregar a la cola (Pendiente)"):
                            ya_en_proceso = col_tiempos.find_one({
                                "agente_id": domain_agente,
                                "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                            })
                            if ya_en_proceso:
                                st.warning("Este agente ya tiene un tiempo activo o pendiente.")
                            else:
                                col_tiempos.insert_one({
                                    "agente_id": domain_agente,
                                    "agente_nombre": agente["nombre"],
                                    "autorizador_id": autorizador_id,
                                    "autorizador_nombre": autorizador["nombre"],
                                    "hora_ingreso": ahora(),
                                    "estado": "Pendiente"
                                })
                                st.success("Agente agregado a la cola.")
                                st.rerun()

        elif seccion == "📤 En cola (Pendiente)":
            pendientes = list(col_tiempos.find({"estado": "Pendiente"}).sort("hora_ingreso", 1))
            st.subheader("Agentes en cola")
            st.caption(f"Total en cola: {len(pendientes)}")
            if pendientes:
                seleccion = st.selectbox("Selecciona un agente", pendientes, format_func=lambda x: x["agente_nombre"])
                if seleccion:
                    tiempo = tiempo_transcurrido(seleccion["hora_ingreso"])
                    st.info(f"{seleccion['agente_nombre']} lleva {tiempo} esperando")
                    if st.button("✅ Autorizar"):
                        col_tiempos.update_one(
                            {"_id": seleccion["_id"]},
                            {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                        )
                        st.success("Agente autorizado.")
                        st.rerun()
            else:
                st.info("No hay agentes en cola.")

        elif seccion == "🟢 Autorizados (esperando que arranquen)":
            autorizados = list(col_tiempos.find({"estado": "Autorizado"}).sort("hora_autorizacion", 1))
            st.subheader("Agentes autorizados")
            st.caption(f"Total autorizados: {len(autorizados)}")
            if autorizados:
                seleccion = st.selectbox("Selecciona un agente", autorizados, format_func=lambda x: x["agente_nombre"])
                if seleccion:
                    tiempo = tiempo_transcurrido(seleccion["hora_autorizacion"])
                    st.info(f"{seleccion['agente_nombre']} fue autorizado hace {tiempo}")
                    if st.button("▶️ Iniciar tiempo"):
                        col_tiempos.update_one(
                            {"_id": seleccion["_id"]},
                            {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                        )
                        st.success("Tiempo iniciado.")
                        st.rerun()
            else:
                st.info("No hay agentes autorizados.")

        elif seccion == "⏳ Tiempo personal en curso":
            en_curso = list(col_tiempos.find({"estado": "En curso"}).sort("hora_inicio", 1))
            st.subheader("Tiempo en curso")
            st.caption(f"Total en curso: {len(en_curso)}")
            if en_curso:
                seleccion = st.selectbox("Selecciona un agente", en_curso, format_func=lambda x: x["agente_nombre"])
                if seleccion:
                    tiempo = tiempo_transcurrido(seleccion["hora_inicio"])
                    st.info(f"{seleccion['agente_nombre']} lleva {tiempo} en tiempo personal")
                    if st.button("🛑 Finalizar tiempo"):
                        fin = ahora()
                        duracion = (fin - seleccion["hora_inicio"]).total_seconds()
                        col_tiempos.update_one(
                            {"_id": seleccion["_id"]},
                            {"$set": {
                                "estado": "Completado",
                                "hora_fin": fin,
                                "duracion_segundos": int(duracion)
                            }}
                        )
                        st.success(f"Tiempo finalizado: {int(duracion)} segundos")
                        st.rerun()
            else:
                st.info("No hay tiempos personales activos.")

        elif seccion == "📜 Historial":
            completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
            if completados:
                historial = []
                for i, r in enumerate(completados, 1):
                    inicio = r.get("hora_inicio", None)
                    fin = r.get("hora_fin", None)
                    duracion = r.get("duracion_segundos", 0)
                    historial.append({
                        "#": len(completados) - i + 1,
                        "Agente": r["agente_nombre"],
                        "Autorizador": r["autorizador_nombre"],
                        "Inicio": inicio.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if inicio else "",
                        "Fin": fin.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if fin else "",
                        "Duración": time.strftime('%H:%M:%S', time.gmtime(duracion))
                    })
                df = pd.DataFrame(historial)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No hay registros completados aún.")
