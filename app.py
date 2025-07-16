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

def formatear_duracion(delta):
    horas, rem = divmod(int(delta.total_seconds()), 3600)
    minutos, segundos = divmod(rem, 60)
    return f"{horas:02}:{minutos:02}:{segundos:02}"

def tiempo_transcurrido(doc):
    estado = doc.get("estado")
    if estado == "Pendiente":
        inicio = doc.get("hora_ingreso")
        return formatear_duracion(ahora() - inicio)
    elif estado == "Autorizado":
        inicio = doc.get("hora_autorizacion")
        return formatear_duracion(ahora() - inicio)
    elif estado == "En curso":
        inicio = doc.get("hora_inicio")
        return formatear_duracion(ahora() - inicio)
    elif estado == "Completado":
        inicio = doc.get("hora_inicio")
        fin = doc.get("hora_fin")
        return formatear_duracion(fin - inicio)
    return "--:--:--"

# === UI PRINCIPAL ===
st.title("⏱ Registro de Tiempo Personal – personalito (Walmart DAS)")

# === AUTORIZADOR ===
domain_aut = st.text_input("🔐 Domain ID del autorizador")
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

# === SECCIÓN ===
pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
en_curso = list(col_tiempos.find({"estado": "En curso"}))
completados = list(col_tiempos.find({"estado": "Completado"}))

secciones = {
    f"📤 En cola (Pendiente) [{len(pendientes)}]": pendientes,
    f"🟢 Autorizados [{len(autorizados)}]": autorizados,
    f"⏳ En curso [{len(en_curso)}]": en_curso,
    f"📜 Historial [{len(completados)}]": completados,
    "➕ Registrar nuevo agente": None,
}

opcion = st.selectbox("Seleccione una sección", list(secciones.keys()))

# === REGISTRO DE AGENTE ===
if opcion == "➕ Registrar nuevo agente":
    domain_agente = st.text_input("Domain ID del agente")
    if domain_agente:
        ya_completo = col_tiempos.find_one({
            "agente_id": domain_agente,
            "estado": "Completado",
            "hora_fin": {
                "$gte": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            }
        })
        if ya_completo:
            st.warning("Este agente ya completó su tiempo hoy.")
        else:
            agente = col_agentes.find_one({"domain_id": domain_agente})
            if not agente:
                nombre_agente = st.text_input("Nombre del agente")
                if nombre_agente:
                    col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                    st.success("Agente registrado.")
                    st.rerun()
            else:
                if st.button("Agregar a la cola"):
                    en_proceso = col_tiempos.find_one({
                        "agente_id": domain_agente,
                        "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                    })
                    if en_proceso:
                        st.warning("Este agente ya tiene un tiempo activo.")
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

# === MOSTRAR SECCIONES DINÁMICAS ===
else:
    datos = secciones[opcion]
    if not datos:
        st.info("No hay registros en esta sección.")
    else:
        opciones = [f"{d['agente_nombre']} ({d['agente_id']})" for d in datos]
        seleccionado = st.selectbox("Agente", opciones)
        doc = datos[opciones.index(seleccionado)]

        espacio = st.empty()
        for _ in range(300):
            espacio.markdown(f"⏱ Tiempo: **{tiempo_transcurrido(doc)}**")
            time.sleep(1)

        if doc["estado"] == "Pendiente":
            if st.button("✅ Autorizar"):
                col_tiempos.update_one({"_id": doc["_id"]}, {
                    "$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}
                })
                st.rerun()
        elif doc["estado"] == "Autorizado":
            if st.button("▶️ Iniciar"):
                col_tiempos.update_one({"_id": doc["_id"]}, {
                    "$set": {"estado": "En curso", "hora_inicio": ahora()}
                })
                st.rerun()
        elif doc["estado"] == "En curso":
            if st.button("🛑 Finalizar"):
                fin = ahora()
                duracion = fin - doc["hora_inicio"]
                col_tiempos.update_one({"_id": doc["_id"]}, {
                    "$set": {
                        "estado": "Completado",
                        "hora_fin": fin,
                        "duracion_segundos": int(duracion.total_seconds())
                    }
                })
                st.success("Tiempo finalizado.")
                st.rerun()
        elif doc["estado"] == "Completado":
            duracion = doc.get("duracion_segundos", 0)
            st.success(f"⏱ Duración: {formatear_duracion(pd.Timedelta(seconds=duracion))}")

# === HISTORIAL ===
if opcion == "📜 Historial":
    registros = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
    historial = []
    for i, h in enumerate(registros, 1):
        historial.append({
            "#": len(registros) - i + 1,
            "Agente": h["agente_nombre"],
            "Domain ID": h["agente_id"],
            "Autorizador": h["autorizador_nombre"],
            "Inicio": h["hora_inicio"].astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S"),
            "Fin": h["hora_fin"].astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S"),
            "Duración": formatear_duracion(h["hora_fin"] - h["hora_inicio"])
        })

    df = pd.DataFrame(historial)
    st.dataframe(df, use_container_width=True)