import streamlit as st
import pymongo
from datetime import datetime
import pytz
import time

# === CONFIG ===
st.set_page_config(page_title="⏱ Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
client = pymongo.MongoClient(st.secrets["mongo_uri"])
db = client["tiempo_personal"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]
col_tiempos = db["tiempos"]
zona_col = pytz.timezone("America/Bogota")

# === FUNCIONES ===
def ahora():
    return datetime.now(tz=zona_col)

def tiempo_transcurrido(inicio):
    delta = ahora() - inicio
    minutos, segundos = divmod(int(delta.total_seconds()), 60)
    return f"{minutos}m {segundos:02d}s"

def ya_tuvo_tiempo_personal_hoy(agente_id):
    hoy = ahora().date()
    registros = col_tiempos.find({
        "agente_id": agente_id,
        "estado": "Completado",
        "hora_fin": {"$gte": datetime(hoy.year, hoy.month, hoy.day, tzinfo=zona_col)}
    })
    return registros.count() > 0

# === UI PRINCIPAL ===
st.title("⏱ Registro de Tiempo Personal – personalito (Walmart DAS)")

secciones = {
    "📝 Registrar nuevo agente en cola": "registrar",
    "🕓 En cola (Pendiente)": "pendiente",
    "🟢 Autorizados (esperando que arranquen)": "autorizado",
    "⏳ Tiempo personal en curso": "curso"
}
seccion = st.selectbox("Selecciona una sección:", list(secciones.keys()))
st.divider()

# === REGISTRO ===
if secciones[seccion] == "registrar":
    st.subheader("📝 Registrar nuevo agente en cola")
    domain_aut = st.text_input("Domain ID del autorizador")
    if domain_aut:
        aut = col_autorizadores.find_one({"domain_id": domain_aut})
        if not aut:
            nombre_aut = st.text_input("Nombre del autorizador")
            if nombre_aut:
                col_autorizadores.insert_one({"domain_id": domain_aut, "nombre": nombre_aut})
                st.rerun()
        else:
            st.success(f"Bienvenido/a, {aut['nombre']}")
            domain_agente = st.text_input("Domain ID del agente")
            if domain_agente:
                if ya_tuvo_tiempo_personal_hoy(domain_agente):
                    st.warning("Este agente ya tuvo tiempo personal hoy.")
                else:
                    agente = col_agentes.find_one({"domain_id": domain_agente})
                    if not agente:
                        nombre_agente = st.text_input("Nombre del agente")
                        if nombre_agente:
                            col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                            st.rerun()
                    else:
                        if st.button("➕ Agregar a la cola (Pendiente)"):
                            ya_en_proceso = col_tiempos.find_one({
                                "agente_id": domain_agente,
                                "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                            })
                            if ya_en_proceso:
                                st.error("Este agente ya está en proceso.")
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

# === EN COLA (PENDIENTE) ===
elif secciones[seccion] == "pendiente":
    pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
    st.subheader("🕓 En cola (Pendiente)")
    st.info(f"Agentes en cola: {len(pendientes)}")

    if pendientes:
        opciones = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
        seleccion = st.selectbox("Selecciona agente a autorizar", opciones)
        idx = opciones.index(seleccion)
        agente = pendientes[idx]
        tiempo = tiempo_transcurrido(agente["hora_ingreso"])
        st.markdown(f"🕒 En cola: `{tiempo}`")
        if st.button("✅ Autorizar"):
            col_tiempos.update_one({"_id": agente["_id"]}, {
                "$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}
            })
            st.rerun()
        time.sleep(1)
        st.rerun()
    else:
        st.info("No hay agentes actualmente en cola.")

# === AUTORIZADOS ===
elif secciones[seccion] == "autorizado":
    autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
    st.subheader("🟢 Autorizados (esperando que arranquen)")
    st.info(f"Agentes autorizados: {len(autorizados)}")

    if autorizados:
        opciones = [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados]
        seleccion = st.selectbox("Selecciona agente para iniciar", opciones)
        idx = opciones.index(seleccion)
        agente = autorizados[idx]
        tiempo = tiempo_transcurrido(agente["hora_autorizacion"])
        st.markdown(f"🕒 Autorizado hace: `{tiempo}`")
        if st.button("▶️ Iniciar tiempo"):
            col_tiempos.update_one({"_id": agente["_id"]}, {
                "$set": {"estado": "En curso", "hora_inicio": ahora()}
            })
            st.rerun()
        time.sleep(1)
        st.rerun()
    else:
        st.info("No hay agentes autorizados aún.")

# === EN CURSO ===
elif secciones[seccion] == "curso":
    en_curso = list(col_tiempos.find({"estado": "En curso"}))
    st.subheader("⏳ Tiempo personal en curso")
    st.info(f"Agentes en curso: {len(en_curso)}")

    if en_curso:
        opciones = [f"{e['agente_nombre']} ({e['agente_id']})" for e in en_curso]
        seleccion = st.selectbox("Selecciona agente para finalizar", opciones)
        idx = opciones.index(seleccion)
        agente = en_curso[idx]
        tiempo = tiempo_transcurrido(agente["hora_inicio"])
        st.markdown(f"🕒 En curso desde hace: `{tiempo}`")
        if st.button("🛑 Finalizar tiempo"):
            fin = ahora()
            duracion = (fin - agente["hora_inicio"]).total_seconds() / 60
            col_tiempos.update_one({"_id": agente["_id"]}, {
                "$set": {
                    "estado": "Completado",
                    "hora_fin": fin,
                    "duracion_minutos": round(duracion, 2)
                }
            })
            st.success(f"Tiempo finalizado: {round(duracion, 2)} minutos")
            st.rerun()
        time.sleep(1)
        st.rerun()
    else:
        st.info("No hay agentes usando el tiempo personal ahora.")