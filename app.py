import streamlit as st
import pymongo
from datetime import datetime
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

def tiempo_transcurrido(inicio):
    delta = ahora() - inicio
    minutos, segundos = divmod(delta.total_seconds(), 60)
    return f"{int(minutos)}m {int(segundos)}s"

def ya_tuvo_hoy(agente_id):
    hoy = datetime.now(zona_col).date()
    return col_tiempos.find_one({
        "agente_id": agente_id,
        "estado": "Completado",
        "hora_inicio": {"$gte": datetime.combine(hoy, datetime.min.time())}
    })

# === TÍTULO ===
st.title("⏱ Registro de Tiempo Personal – personalito (Walmart DAS)")

# === NAVEGACIÓN ===
secciones = [
    "📝 Registrar nuevo agente en cola",
    "🕓 En cola (Pendiente)",
    "🟢 Autorizados (esperando que arranquen)",
    "⏳ Tiempo personal en curso",
    "📜 Historial de tiempos finalizados"
]
seccion = st.selectbox("Selecciona una sección:", secciones)

# === SECCIÓN 1: Registrar nuevo agente ===
if seccion == secciones[0]:
    st.subheader("📝 Registrar nuevo agente en cola")
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
            domain_agente = st.text_input("Domain ID del agente")
            if domain_agente:
                if ya_tuvo_hoy(domain_agente):
                    st.warning("⚠️ Este agente ya tuvo tiempo personal hoy.")
                else:
                    agente = col_agentes.find_one({"domain_id": domain_agente})
                    if not agente:
                        nombre_agente = st.text_input("Nombre del agente")
                        if nombre_agente:
                            col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                            st.success("Agente registrado. Continúe con la autorización.")
                            st.rerun()
                    else:
                        if st.button("➕ Agregar a la cola (Pendiente)"):
                            ya_en_cola = col_tiempos.find_one({
                                "agente_id": domain_agente,
                                "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                            })
                            if ya_en_cola:
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

# === SECCIÓN 2: Pendientes ===
elif seccion == secciones[1]:
    st.subheader("🕓 En cola (Pendiente)")
    pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
    if pendientes:
        agentes = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
        seleccion = st.selectbox("Selecciona agente a autorizar", agentes)
        if seleccion:
            seleccionado = pendientes[agentes.index(seleccion)]
            st.info("🔁 Refresca la página para ver cuánto lleva en cola.")
            if st.button("✅ Autorizar"):
                col_tiempos.update_one(
                    {"_id": seleccionado["_id"]},
                    {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                )
                st.success("Agente autorizado.")
                st.rerun()
    else:
        st.info("📭 No hay agentes en cola actualmente.")

# === SECCIÓN 3: Autorizados ===
elif seccion == secciones[2]:
    st.subheader("🟢 Autorizados (esperando que arranquen)")
    autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
    if autorizados:
        agentes = [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados]
        seleccion = st.selectbox("Selecciona agente para iniciar", agentes)
        if seleccion:
            seleccionado = autorizados[agentes.index(seleccion)]
            st.info("🔁 Refresca la página para ver hace cuánto fue autorizado.")
            if st.button("▶️ Iniciar tiempo personal"):
                col_tiempos.update_one(
                    {"_id": seleccionado["_id"]},
                    {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                )
                st.success("Tiempo personal iniciado.")
                st.rerun()
    else:
        st.info("📭 No hay agentes autorizados aún.")

# === SECCIÓN 4: En curso ===
elif seccion == secciones[3]:
    st.subheader("⏳ Tiempo personal en curso")
    en_curso = list(col_tiempos.find({"estado": "En curso"}))
    if en_curso:
        for e in en_curso:
            st.write(f"👤 {e['agente_nombre']} ({e['agente_id']})")
            cronometro = st.empty()
            stop = st.button(f"🛑 Finalizar tiempo de {e['agente_id']}")
            tiempo_inicio = e['hora_inicio']
            while True:
                if stop:
                    fin = ahora()
                    duracion = (fin - tiempo_inicio).total_seconds() / 60
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
                    st.success(f"✅ Tiempo finalizado: {round(duracion, 2)} minutos")
                    st.rerun()
                duracion = ahora() - tiempo_inicio
                minutos, segundos = divmod(duracion.total_seconds(), 60)
                cronometro.markdown(f"### 🕒 Tiempo actual: {int(minutos)}m {int(segundos)}s")
                time.sleep(1)
    else:
        st.info("📭 No hay agentes en tiempo personal actualmente.")

# === SECCIÓN 5: Historial ===
elif seccion == secciones[4]:
    st.subheader("📜 Historial de tiempos finalizados")
    historial = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
    if historial:
        datos = []
        for h in historial:
            datos.append({
                "Agente": h["agente_nombre"],
                "Domain ID": h["agente_id"],
                "Autorizador": h["autorizador_nombre"],
                "Inicio": h.get("hora_inicio", "").astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S"),
                "Fin": h.get("hora_fin", "").astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S"),
                "Duración (min)": h.get("duracion_minutos", 0)
            })
        df = pd.DataFrame(datos)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("📭 No hay registros finalizados aún.")