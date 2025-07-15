import streamlit as st
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz
import time
import pandas as pd

# === CONFIGURACIÓN ===
st.set_page_config(page_title="📋 Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
MONGO_URI = st.secrets["mongo_uri"]
client = MongoClient(MONGO_URI)
db = client["tiempo_personal"]
col_tiempos = db["tiempos"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]
tz = pytz.timezone("America/Bogota")

# === UTILIDADES ===
def ahora():
    return datetime.now(tz)

def tiempo_transcurrido(inicio):
    if not inicio:
        return "Sin hora registrada"
    delta = ahora() - inicio
    minutos, segundos = divmod(int(delta.total_seconds()), 60)
    return f"{minutos:02d}:{segundos:02d}"

# === CONTADORES DE ESTADO ===
n_pendientes = col_tiempos.count_documents({"estado": "Pendiente"})
n_autorizados = col_tiempos.count_documents({"estado": "Autorizado"})
n_en_curso = col_tiempos.count_documents({"estado": "En curso"})

# === TÍTULO Y SELECCIÓN ===
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")

secciones = [
    "📋 Registrar nuevo agente en cola",
    f"📤 En cola (Pendiente) [{n_pendientes}]",
    f"🟢 Autorizadx [{n_autorizados}]",
    f"⏱️ En curso [{n_en_curso}]",
    "📜 Historial"
]
seleccion = st.selectbox("Selecciona una sección:", secciones)

# === REGISTRAR NUEVO AGENTE ===
if seleccion.startswith("📋"):
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
            domain_agente = st.text_input("Domain ID del agente")
            if domain_agente:
                agente = col_agentes.find_one({"domain_id": domain_agente})
                if not agente:
                    nombre_agente = st.text_input("Nombre del agente")
                    if nombre_agente:
                        col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                        st.success("Agente registrado. Continúe con la autorización.")
                        st.rerun()
                else:
                    hoy = ahora().date()
                    ya_tuvo = col_tiempos.find_one({
                        "agente_id": domain_agente,
                        "estado": "Completado",
                        "hora_fin": {"$gte": datetime.combine(hoy, datetime.min.time()).astimezone(tz)}
                    })
                    if ya_tuvo:
                        st.warning("Este agente ya tuvo tiempo personal hoy.")
                    elif st.button("➕ Agregar a la cola"):
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

# === EN COLA (PENDIENTE) ===
elif seleccion.startswith("📤"):
    pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
    if pendientes:
        opciones = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
        seleccion_p = st.selectbox("Agentes pendientes:", opciones)
        idx = opciones.index(seleccion_p)
        seleccionado = pendientes[idx]
        tiempo = tiempo_transcurrido(seleccionado.get("hora_ingreso"))
        st.success(f"⏱ Esperando hace: {tiempo}")
        if st.button("✅ Autorizar"):
            col_tiempos.update_one(
                {"_id": seleccionado["_id"]},
                {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
            )
            st.rerun()
    else:
        st.info("No hay agentes en cola.")

# === AUTORIZADOS ===
elif seleccion.startswith("🟢"):
    autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
    if autorizados:
        opciones = [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados]
        seleccion_a = st.selectbox("Agentes autorizados:", opciones)
        idx = opciones.index(seleccion_a)
        seleccionado = autorizados[idx]
        tiempo = tiempo_transcurrido(seleccionado.get("hora_autorizacion"))
        st.success(f"⏱ Autorizado hace: {tiempo}")
        if st.button("▶️ Iniciar tiempo"):
            col_tiempos.update_one(
                {"_id": seleccionado["_id"]},
                {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
            )
            st.rerun()
    else:
        st.info("No hay agentes autorizados.")

# === EN CURSO ===
elif seleccion.startswith("⏱️"):
    activos = list(col_tiempos.find({"estado": "En curso"}))
    if activos:
        opciones = [f"{e['agente_nombre']} ({e['agente_id']})" for e in activos]
        seleccion_e = st.selectbox("Agentes en curso:", opciones)
        idx = opciones.index(seleccion_e)
        seleccionado = activos[idx]
        cronometro = st.empty()
        stop = st.button("🛑 Finalizar")

        while True:
            tiempo = tiempo_transcurrido(seleccionado.get("hora_inicio"))
            cronometro.markdown(f"### 🕒 Tiempo en curso: {tiempo}")
            time.sleep(1)
            if stop:
                fin = ahora()
                duracion = (fin - seleccionado["hora_inicio"]).total_seconds()
                col_tiempos.update_one(
                    {"_id": seleccionado["_id"]},
                    {
                        "$set": {
                            "estado": "Completado",
                            "hora_fin": fin,
                            "duracion_segundos": int(duracion)
                        }
                    }
                )
                st.success("Tiempo finalizado.")
                st.rerun()
    else:
        st.info("No hay tiempos en curso.")

# === HISTORIAL ===
elif seleccion == "📜 Historial":
    completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
    if completados:
        data = []
        for i, reg in enumerate(completados, start=1):
            dur = reg.get("duracion_segundos", 0)
            minutos, segundos = divmod(dur, 60)
            data.append({
                "#": len(completados) - i + 1,
                "Agente": reg["agente_nombre"],
                "Domain ID": reg["agente_id"],
                "Autorizador": reg["autorizador_nombre"],
                "Inicio": reg.get("hora_inicio", "").astimezone(tz).strftime("%H:%M:%S"),
                "Fin": reg.get("hora_fin", "").astimezone(tz).strftime("%H:%M:%S"),
                "Duración": f"{int(minutos):02d}:{int(segundos):02d}"
            })
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Aún no hay tiempos completados.")