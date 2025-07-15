import streamlit as st
import pymongo
from datetime import datetime
import pandas as pd
import pytz

# === CONFIGURACIÓN ===
st.set_page_config(page_title="Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
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
    if not isinstance(inicio, datetime):
        return "⛔ Sin dato"
    delta = ahora() - inicio
    minutos, segundos = divmod(int(delta.total_seconds()), 60)
    return f"{minutos}m {segundos:02d}s"

# === INTERFAZ ===
st.title("Registro de Tiempo Personal – personalito (Walmart DAS)")

# === CONTADORES ===
total_pendientes = col_tiempos.count_documents({"estado": "Pendiente"})
total_autorizados = col_tiempos.count_documents({"estado": "Autorizado"})
total_curso = col_tiempos.count_documents({"estado": "En curso"})

st.markdown(f"""
### Agentes por estado:
- 🕓 Pendientes: **{total_pendientes}**
- 🟢 Autorizados: **{total_autorizados}**
- ⏳ En curso: **{total_curso}**
""")

# === SELECCIÓN DE SECCIÓN ===
secciones = {
    "📝 Registrar nuevo agente en cola": "registro",
    "🕓 En cola (Pendiente)": "pendientes",
    "🟢 Autorizados (esperando que arranquen)": "autorizados",
    "⏳ Tiempo personal en curso": "en_curso"
}
seccion = st.selectbox("Selecciona una sección:", list(secciones.keys()))
seccion_activa = secciones[seccion]

# === SECCIÓN: REGISTRO ===
if seccion_activa == "registro":
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
                hoy = datetime.now(zona_col).date()
                ya_tuvo = col_tiempos.find_one({
                    "agente_id": domain_agente,
                    "estado": "Completado",
                    "hora_fin": {
                        "$gte": datetime.combine(hoy, datetime.min.time()),
                        "$lt": datetime.combine(hoy, datetime.max.time())
                    }
                })
                if ya_tuvo:
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
                            en_proceso = col_tiempos.find_one({
                                "agente_id": domain_agente,
                                "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                            })
                            if en_proceso:
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

# === SECCIÓN: PENDIENTES ===
elif seccion_activa == "pendientes":
    pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
    st.subheader(f"🕓 En cola (Pendiente)")
    if pendientes:
        opciones = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
        seleccion = st.selectbox("Selecciona agente a autorizar", opciones)
        agente_sel = pendientes[opciones.index(seleccion)]
        tiempo = tiempo_transcurrido(agente_sel.get("hora_ingreso"))
        st.write(f"🕓 En cola: {tiempo}")
        if st.button("✅ Autorizar"):
            col_tiempos.update_one(
                {"_id": agente_sel["_id"]},
                {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
            )
            st.success("Agente autorizado.")
            st.rerun()
    else:
        st.info("No hay agentes actualmente en cola.")

# === SECCIÓN: AUTORIZADOS ===
elif seccion_activa == "autorizados":
    autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
    st.subheader(f"🟢 Autorizados (esperando que arranquen)")
    if autorizados:
        opciones = [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados]
        seleccion = st.selectbox("Selecciona agente para iniciar", opciones)
        agente_sel = autorizados[opciones.index(seleccion)]
        tiempo = tiempo_transcurrido(agente_sel.get("hora_autorizacion"))
        st.write(f"🕰️ Autorizado hace: {tiempo}")
        if st.button("▶️ Iniciar tiempo"):
            col_tiempos.update_one(
                {"_id": agente_sel["_id"]},
                {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
            )
            st.success("Tiempo iniciado.")
            st.rerun()
    else:
        st.info("No hay agentes actualmente autorizados.")

# === SECCIÓN: EN CURSO ===
elif seccion_activa == "en_curso":
    en_curso = list(col_tiempos.find({"estado": "En curso"}))
    st.subheader("⏳ Tiempo personal en curso")
    if en_curso:
        opciones = [f"{e['agente_nombre']} ({e['agente_id']})" for e in en_curso]
        seleccion = st.selectbox("Selecciona agente para finalizar", opciones)
        agente_sel = en_curso[opciones.index(seleccion)]
        tiempo = tiempo_transcurrido(agente_sel.get("hora_inicio"))
        st.write(f"⏱️ Tiempo en curso: {tiempo}")
        if st.button("🛑 Finalizar"):
            fin = ahora()
            duracion = (fin - agente_sel["hora_inicio"]).total_seconds() / 60
            col_tiempos.update_one(
                {"_id": agente_sel["_id"]},
                {
                    "$set": {
                        "estado": "Completado",
                        "hora_fin": fin,
                        "duracion_minutos": round(duracion, 2)
                    }
                }
            )
            st.success(f"Tiempo finalizado: {round(duracion, 2)} minutos.")
            st.rerun()
    else:
        st.info("No hay agentes actualmente en curso.")

# === HISTORIAL FINAL ===
st.subheader("📜 Historial de tiempos finalizados")
finalizados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
if finalizados:
    filas = []
    for item in finalizados:
        filas.append({
            "Agente": item["agente_nombre"],
            "Domain ID": item["agente_id"],
            "Autorizador": item["autorizador_nombre"],
            "Ingreso": item.get("hora_ingreso", "").astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if item.get("hora_ingreso") else "",
            "Autorizado": item.get("hora_autorizacion", "").astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if item.get("hora_autorizacion") else "",
            "Inicio": item.get("hora_inicio", "").astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if item.get("hora_inicio") else "",
            "Fin": item.get("hora_fin", "").astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if item.get("hora_fin") else "",
            "Duración (min)": item.get("duracion_minutos", 0)
        })
    df = pd.DataFrame(filas)
    st.dataframe(df, use_container_width=True)
else:
    st.info("No hay registros finalizados todavía.")