import streamlit as st
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz
import pandas as pd
import time

# === CONFIGURACIÓN INICIAL ===
st.set_page_config("⏱ Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")

# === CONEXIÓN A MONGODB ===
client = MongoClient(st.secrets["mongo_uri"])
db = client["tiempo_personal"]
col_tiempos = db["tiempos"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]
zona = pytz.timezone("America/Bogota")

# === FUNCIONES AUXILIARES ===
def ahora():
    return datetime.now(tz=zona)

def tiempo_transcurrido(dt):
    delta = ahora() - dt
    minutos, segundos = divmod(int(delta.total_seconds()), 60)
    return f"{minutos:02d}:{segundos:02d}"

def hay_registro_hoy(domain_id):
    hoy = ahora().date()
    registro = col_tiempos.find_one({
        "agente_id": domain_id,
        "estado": "Completado",
        "hora_fin": {
            "$gte": datetime.combine(hoy, datetime.min.time()).astimezone(zona),
            "$lt": datetime.combine(hoy + timedelta(days=1), datetime.min.time()).astimezone(zona)
        }
    })
    return registro is not None

# === SECCIÓN DE AUTORIZADOR ===
domain_aut = st.text_input("🔐 Domain ID del autorizador")
if not domain_aut:
    st.stop()

autorizador = col_autorizadores.find_one({"domain_id": domain_aut})
if not autorizador:
    nombre_aut = st.text_input("🧑‍💼 Tu nombre (autorizador)")
    if nombre_aut:
        col_autorizadores.insert_one({"domain_id": domain_aut, "nombre": nombre_aut})
        st.success("✅ Autorizador registrado.")
        st.rerun()
    else:
        st.stop()
else:
    st.success(f"Bienvenido/a, **{autorizador['nombre']}**")

# === DROPDOWN DE SECCIONES ===
st.subheader("📂 Selecciona una sección")
seccion = st.selectbox(
    "¿Qué deseas hacer?",
    [
        "📋 Registrar nuevo agente en cola",
        "En cola (Pendiente)",
        "🟢 Autorizados (esperando que arranquen)",
        "⏳ Tiempo personal en curso",
        "📜 Historial de tiempos finalizados"
    ]
)

# === CONTADORES POR ESTADO ===
st.markdown("---")
pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
en_curso = list(col_tiempos.find({"estado": "En curso"}))

st.markdown(f"🔄 **Agentes en espera:** {len(pendientes)} &nbsp;&nbsp;&nbsp; ✅ **Autorizados:** {len(autorizados)} &nbsp;&nbsp;&nbsp; ⏳ **En curso:** {len(en_curso)}")
st.markdown("---")

# === REGISTRAR NUEVO AGENTE EN COLA ===
if seccion == "📋 Registrar nuevo agente en cola":
    domain_agente = st.text_input("🆔 Domain ID del agente a registrar")
    if domain_agente:
        if hay_registro_hoy(domain_agente):
            st.warning("⛔ Este agente ya tuvo tiempo personal hoy.")
            st.stop()

        agente = col_agentes.find_one({"domain_id": domain_agente})
        if not agente:
            nombre_agente = st.text_input("👤 Nombre del agente")
            if nombre_agente:
                col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                st.success("✅ Agente registrado.")
                st.rerun()
        else:
            ya_tiene = col_tiempos.find_one({
                "agente_id": domain_agente,
                "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
            })
            if ya_tiene:
                st.warning("⏳ Este agente ya tiene un tiempo activo o en cola.")
            elif st.button("➕ Agregar a la cola (Pendiente)"):
                col_tiempos.insert_one({
                    "agente_id": domain_agente,
                    "agente_nombre": agente["nombre"],
                    "autorizador_id": domain_aut,
                    "autorizador_nombre": autorizador["nombre"],
                    "hora_ingreso": ahora(),
                    "estado": "Pendiente"
                })
                st.success("📝 Agente agregado a la cola.")
                st.rerun()

# === PENDIENTES ===
elif seccion == "En cola (Pendiente)":
    if not pendientes:
        st.info("🕓 No hay agentes en cola.")
    else:
        opciones = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
        seleccion = st.selectbox("Selecciona un agente pendiente", opciones)
        agente = pendientes[opciones.index(seleccion)]
        tiempo = tiempo_transcurrido(agente["hora_ingreso"])
        st.success(f"⏳ Tiempo en cola: {tiempo}")
        if st.button("✅ Autorizar"):
            col_tiempos.update_one(
                {"_id": agente["_id"]},
                {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
            )
            st.success("Agente autorizado.")
            st.rerun()

# === AUTORIZADOS ===
elif seccion == "🟢 Autorizados (esperando que arranquen)":
    if not autorizados:
        st.info("✅ No hay agentes autorizados en espera.")
    else:
        opciones = [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados]
        seleccion = st.selectbox("Selecciona un agente autorizado", opciones)
        agente = autorizados[opciones.index(seleccion)]
        tiempo = tiempo_transcurrido(agente["hora_autorizacion"])
        st.success(f"⏱ Tiempo desde autorización: {tiempo}")
        if st.button("▶️ Iniciar tiempo personal"):
            col_tiempos.update_one(
                {"_id": agente["_id"]},
                {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
            )
            st.rerun()

# === EN CURSO ===
elif seccion == "⏳ Tiempo personal en curso":
    if not en_curso:
        st.info("⏳ No hay tiempos personales en curso.")
    else:
        opciones = [f"{e['agente_nombre']} ({e['agente_id']})" for e in en_curso]
        seleccion = st.selectbox("Selecciona un agente en curso", opciones)
        agente = en_curso[opciones.index(seleccion)]
        tiempo = tiempo_transcurrido(agente["hora_inicio"])
        st.success(f"🕒 Tiempo transcurrido: {tiempo}")
        if st.button("🛑 Finalizar tiempo"):
            fin = ahora()
            duracion = int((fin - agente["hora_inicio"]).total_seconds())
            col_tiempos.update_one(
                {"_id": agente["_id"]},
                {
                    "$set": {
                        "estado": "Completado",
                        "hora_fin": fin,
                        "duracion_segundos": duracion
                    }
                }
            )
            st.success(f"Tiempo finalizado: {duracion // 60}m {duracion % 60}s")
            st.rerun()

# === HISTORIAL ===
elif seccion == "📜 Historial de tiempos finalizados":
    completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
    if not completados:
        st.info("📭 Aún no hay registros completados.")
    else:
        data = []
        for i, h in enumerate(completados, start=1):
            dur = h.get("duracion_segundos", 0)
            data.append({
                "#": len(completados) - i + 1,
                "Agente": h["agente_nombre"],
                "Domain ID": h["agente_id"],
                "Autorizador": h["autorizador_nombre"],
                "Ingreso": h["hora_ingreso"].astimezone(zona).strftime("%H:%M:%S"),
                "Autorizado": h["hora_autorizacion"].astimezone(zona).strftime("%H:%M:%S"),
                "Inicio": h["hora_inicio"].astimezone(zona).strftime("%H:%M:%S"),
                "Fin": h["hora_fin"].astimezone(zona).strftime("%H:%M:%S"),
                "Duración": f"{dur // 60:02d}:{dur % 60:02d}"
            })
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)