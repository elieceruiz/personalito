import streamlit as st
from datetime import datetime, timedelta
import pymongo
import pytz
import pandas as pd

# CONFIGURACIÓN
st.set_page_config(page_title="📋 Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
MONGO_URI = st.secrets["mongo_uri"]
cliente = pymongo.MongoClient(MONGO_URI)
db = cliente["tiempo_personal"]
col_tiempos = db["tiempos"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]
zona_col = pytz.timezone("America/Bogota")

# FUNCIONES
def ahora():
    return datetime.now(tz=zona_col)

def formatear_duracion(delta):
    total_segundos = int(delta.total_seconds())
    horas = total_segundos // 3600
    minutos = (total_segundos % 3600) // 60
    segundos = total_segundos % 60
    return f"{horas:02}:{minutos:02}:{segundos:02}"

def tiempo_transcurrido(doc):
    estado = doc["estado"]
    if estado == "Pendiente":
        inicio = doc.get("hora_ingreso")
    elif estado == "Autorizado":
        inicio = doc.get("hora_autorizacion")
    elif estado == "En curso":
        inicio = doc.get("hora_inicio")
    elif estado == "Completado":
        inicio = doc.get("hora_inicio")
        fin = doc.get("hora_fin")
        if inicio and fin:
            return formatear_duracion(fin - inicio)
        return "—"
    else:
        return "—"
    
    if inicio:
        return formatear_duracion(ahora() - inicio)
    return "—"

# UI
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")

# CONTADORES
pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
en_curso = list(col_tiempos.find({"estado": "En curso"}))
completados = list(col_tiempos.find({"estado": "Completado"}))

# MENÚ
opcion = st.selectbox(
    "Selecciona una sección:",
    [
        f"📥 Registrar nuevo agente en cola",
        f"📤 En cola (Pendiente) ({len(pendientes)})",
        f"🟢 Autorizados (esperando que arranquen) ({len(autorizados)})",
        f"⏳ Tiempo personal en curso ({len(en_curso)})",
        f"📜 Historial ({len(completados)})"
    ]
)

# INGRESAR AUTORIZADOR
st.subheader("🔐 Identificación del autorizador")
domain_aut = st.text_input("Domain ID del autorizador")

if domain_aut:
    autorizador = col_autorizadores.find_one({"domain_id": domain_aut})
    if not autorizador:
        nombre_aut = st.text_input("Nombre del autorizador")
        if nombre_aut:
            col_autorizadores.insert_one({"domain_id": domain_aut, "nombre": nombre_aut})
            st.success("Autorizador registrado.")
            st.rerun()
    else:
        st.success(f"Bienvenido/a, {autorizador['nombre']}")

        # REGISTRAR NUEVO AGENTE
        if opcion.startswith("📥"):
            st.subheader("Registrar nuevo agente en cola")
            domain_agente = st.text_input("Domain ID del agente")
            if domain_agente:
                existe = col_tiempos.find_one({
                    "agente_id": domain_agente,
                    "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                })
                if existe:
                    st.warning("Este agente ya tiene un tiempo personal en curso.")
                else:
                    nombre_agente = st.text_input("Nombre del agente")
                    if nombre_agente:
                        # Validar o insertar en colección de agentes
                        if not col_agentes.find_one({"domain_id": domain_agente}):
                            col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                        col_tiempos.insert_one({
                            "agente_id": domain_agente,
                            "agente_nombre": nombre_agente,
                            "autorizador_id": domain_aut,
                            "autorizador_nombre": autorizador["nombre"],
                            "hora_ingreso": ahora(),
                            "estado": "Pendiente"
                        })
                        st.success("Agente registrado y en cola.")
                        st.rerun()

        # PENDIENTES
        elif opcion.startswith("📤"):
            st.subheader("Agentes en cola (Pendiente)")
            if pendientes:
                seleccion = st.selectbox("Selecciona un agente", pendientes, format_func=lambda d: d["agente_nombre"])
                tiempo = tiempo_transcurrido(seleccion)
                st.info(f"⏳ Esperando desde hace: {tiempo}")
                if st.button("✅ Autorizar"):
                    col_tiempos.update_one({"_id": seleccion["_id"]}, {
                        "$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}
                    })
                    st.rerun()
            else:
                st.info("No hay agentes en cola.")

        # AUTORIZADOS
        elif opcion.startswith("🟢"):
            st.subheader("Agentes autorizados")
            if autorizados:
                seleccion = st.selectbox("Selecciona un agente", autorizados, format_func=lambda d: d["agente_nombre"])
                tiempo = tiempo_transcurrido(seleccion)
                st.info(f"⏳ Autorizado hace: {tiempo}")
                if st.button("▶️ Iniciar tiempo"):
                    col_tiempos.update_one({"_id": seleccion["_id"]}, {
                        "$set": {"estado": "En curso", "hora_inicio": ahora()}
                    })
                    st.rerun()
            else:
                st.info("No hay agentes autorizados.")

        # EN CURSO
        elif opcion.startswith("⏳"):
            st.subheader("Agentes con tiempo personal en curso")
            if en_curso:
                seleccion = st.selectbox("Selecciona un agente", en_curso, format_func=lambda d: d["agente_nombre"])
                tiempo = tiempo_transcurrido(seleccion)
                st.info(f"⏳ En curso desde hace: {tiempo}")
                if st.button("🛑 Finalizar tiempo"):
                    ahora_ = ahora()
                    inicio = seleccion.get("hora_inicio")
                    duracion = (ahora_ - inicio).total_seconds() / 60
                    col_tiempos.update_one({"_id": seleccion["_id"]}, {
                        "$set": {
                            "estado": "Completado",
                            "hora_fin": ahora_,
                            "duracion_minutos": round(duracion, 2)
                        }
                    })
                    st.success(f"Tiempo finalizado: {round(duracion, 2)} minutos.")
                    st.rerun()
            else:
                st.info("No hay tiempos en curso.")

        # HISTORIAL
        elif opcion.startswith("📜"):
            st.subheader("Historial de tiempos finalizados")
            if completados:
                completados = sorted(completados, key=lambda d: d["hora_fin"], reverse=True)
                data = []
                for i, item in enumerate(completados, 1):
                    duracion = tiempo_transcurrido(item)
                    fecha = item["hora_fin"].astimezone(zona_col).strftime("%Y-%m-%d")
                    data.append({
                        "N°": len(completados) - i + 1,
                        "Agente": item["agente_nombre"],
                        "Duración": duracion,
                        "Fecha": fecha
                    })
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Aún no hay registros completados.")
