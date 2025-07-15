import streamlit as st
import pymongo
import pandas as pd
from datetime import datetime
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
    if not inicio:
        return "—"
    delta = ahora() - inicio
    minutos, segundos = divmod(delta.total_seconds(), 60)
    return f"{int(minutos)}m {int(segundos)}s"

def formatear_duracion_mmss(segundos_totales):
    minutos, segundos = divmod(int(segundos_totales), 60)
    return f"{minutos:02d}:{segundos:02d}"

# === UI PRINCIPAL ===
st.markdown("## 📋 Registro de Tiempo Personal – personalito (Walmart DAS)")
st.markdown("#### 🔐 Identificación del autorizador")
domain_aut = st.text_input("Domain ID del autorizador")

if domain_aut:
    autorizador = col_autorizadores.find_one({"domain_id": domain_aut})
    if not autorizador:
        nombre_aut = st.text_input("Nombre del autorizador")
        if nombre_aut:
            col_autorizadores.insert_one({"domain_id": domain_aut, "nombre": nombre_aut})
            st.success("Autorizador registrado exitosamente.")
            st.rerun()
        st.stop()
    else:
        st.success(f"Bienvenido/a, {autorizador['nombre']}")

    st.markdown("### 🧾 Secciones")
    seccion = st.selectbox(
        "Selecciona una sección",
        ["📝 Registrar nuevo agente en cola", "📤 En cola (Pendiente)", "🟢 Autorizados", "⏳ Tiempo personal en curso", "📜 Historial"],
        index=0
    )

    # === CONTADORES ===
    pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
    autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
    en_curso = list(col_tiempos.find({"estado": "En curso"}))

    # === SECCIÓN: Registrar nuevo agente ===
    if seccion == "📝 Registrar nuevo agente en cola":
        domain_agente = st.text_input("Domain ID del agente")
        if domain_agente:
            agente = col_agentes.find_one({"domain_id": domain_agente})
            if not agente:
                nombre_agente = st.text_input("Nombre del agente")
                if nombre_agente:
                    col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                    st.success("Agente registrado correctamente.")
                    st.rerun()
            else:
                ya_tiene = col_tiempos.find_one({
                    "agente_id": domain_agente,
                    "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]},
                    "hora_ingreso": {"$gte": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)}
                })
                if ya_tiene:
                    st.warning("Este agente ya tiene un tiempo activo hoy.")
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

    # === SECCIÓN: En cola (Pendiente) ===
    elif seccion == "📤 En cola (Pendiente)":
        st.markdown(f"Agentes en cola: **{len(pendientes)}**")
        if not pendientes:
            st.info("No hay agentes en cola.")
        else:
            opciones = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
            seleccion = st.selectbox("Selecciona un agente", opciones)
            seleccionado = pendientes[opciones.index(seleccion)]
            tiempo = tiempo_transcurrido(seleccionado.get("hora_ingreso"))
            st.markdown(f"⏳ Esperando desde hace: **{tiempo}**")
            if st.button("✅ Autorizar"):
                col_tiempos.update_one(
                    {"_id": seleccionado["_id"]},
                    {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                )
                st.rerun()
            time.sleep(1)
            st.rerun()

    # === SECCIÓN: Autorizados ===
    elif seccion == "🟢 Autorizados":
        st.markdown(f"Agentes autorizados: **{len(autorizados)}**")
        if not autorizados:
            st.info("No hay agentes autorizados.")
        else:
            opciones = [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados]
            seleccion = st.selectbox("Selecciona un agente autorizado", opciones)
            seleccionado = autorizados[opciones.index(seleccion)]
            tiempo = tiempo_transcurrido(seleccionado.get("hora_autorizacion"))
            st.markdown(f"🕒 Autorizado desde hace: **{tiempo}**")
            if st.button("▶️ Iniciar tiempo"):
                col_tiempos.update_one(
                    {"_id": seleccionado["_id"]},
                    {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                )
                st.rerun()
            time.sleep(1)
            st.rerun()

    # === SECCIÓN: En curso ===
    elif seccion == "⏳ Tiempo personal en curso":
        st.markdown(f"Agentes en tiempo personal: **{len(en_curso)}**")
        if not en_curso:
            st.info("No hay tiempos en curso.")
        else:
            opciones = [f"{e['agente_nombre']} ({e['agente_id']})" for e in en_curso]
            seleccion = st.selectbox("Selecciona un agente en curso", opciones)
            seleccionado = en_curso[opciones.index(seleccion)]
            tiempo = tiempo_transcurrido(seleccionado.get("hora_inicio"))
            st.markdown(f"⏳ Tiempo en curso: **{tiempo}**")
            if st.button("🛑 Finalizar tiempo"):
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
                st.success(f"Tiempo finalizado: {formatear_duracion_mmss(duracion)}")
                st.rerun()
            time.sleep(1)
            st.rerun()

    # === SECCIÓN: Historial ===
    elif seccion == "📜 Historial":
        completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
        if not completados:
            st.info("No hay registros finalizados.")
        else:
            historial = []
            for h in completados:
                historial.append({
                    "#": None,  # Se rellena luego
                    "Agente": h["agente_nombre"],
                    "Domain ID": h["agente_id"],
                    "Autorizador": h["autorizador_nombre"],
                    "Duración (mm:ss)": formatear_duracion_mmss(h.get("duracion_segundos", 0)),
                    "Inicio": h.get("hora_inicio", "").astimezone(zona_col).strftime("%H:%M:%S") if h.get("hora_inicio") else "",
                    "Fin": h.get("hora_fin", "").astimezone(zona_col).strftime("%H:%M:%S") if h.get("hora_fin") else "",
                })
            df = pd.DataFrame(historial)
            df.index = range(len(df), 0, -1)
            df["#"] = df.index
            st.dataframe(df[["#", "Agente", "Domain ID", "Autorizador", "Duración (mm:ss)", "Inicio", "Fin"]], use_container_width=True)