import streamlit as st
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz
import pandas as pd
import time

# === CONFIGURACIÓN ===
st.set_page_config(page_title="⏱ Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")
tz = pytz.timezone("America/Bogota")

# === CONEXIÓN DB ===
client = MongoClient(st.secrets["mongo_uri"])
db = client["tiempo_personal"]
col_tiempos = db["tiempos"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]

def ahora():
    return datetime.now(tz)

def tiempo_transcurrido(inicio):
    if not inicio:
        return "—"
    delta = ahora() - inicio
    minutos, segundos = divmod(int(delta.total_seconds()), 60)
    return f"{minutos:02d}:{segundos:02d}"

# === AUTORIZADOR ===
st.text_input("Domain ID del autorizador", key="auth")
if st.session_state.auth:
    autorizador = col_autorizadores.find_one({"domain_id": st.session_state.auth})
    if not autorizador:
        nombre = st.text_input("Nombre del autorizador")
        if nombre:
            col_autorizadores.insert_one({"domain_id": st.session_state.auth, "nombre": nombre})
            st.rerun()
    else:
        st.success(f"Autorizador: {autorizador['nombre']}")

        # === CONTADORES ===
        pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
        autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
        en_curso = list(col_tiempos.find({"estado": "En curso"}))
        completados = list(col_tiempos.find({"estado": "Completado"}))

        st.markdown(f"**📤 En cola:** {len(pendientes)}  |  🟢 Autorizados: {len(autorizados)}  |  ⏳ En curso: {len(en_curso)}")

        # === SELECCIÓN ===
        secciones = [
            "📤 Registrar nuevo agente en cola",
            "📤 En cola (Pendiente)",
            "🟢 Autorizados (esperando que arranquen)",
            "⏳ Tiempo personal en curso",
            "📑 Historial"
        ]
        seleccion = st.selectbox("Selecciona una sección", secciones)

        # === REGISTRO DE NUEVO AGENTE ===
        if seleccion == "📤 Registrar nuevo agente en cola":
            domain = st.text_input("Domain ID del agente")
            if domain:
                agente = col_agentes.find_one({"domain_id": domain})
                if not agente:
                    nombre_agente = st.text_input("Nombre del agente")
                    if nombre_agente:
                        col_agentes.insert_one({"domain_id": domain, "nombre": nombre_agente})
                        st.success("Agente registrado. Continúa con la autorización.")
                        st.rerun()
                else:
                    ya_tiene_hoy = col_tiempos.find_one({
                        "agente_id": domain,
                        "hora_ingreso": {"$gte": datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)},
                        "estado": {"$in": ["Pendiente", "Autorizado", "En curso", "Completado"]}
                    })
                    if ya_tiene_hoy:
                        st.warning("Este agente ya ha tenido tiempo personal hoy.")
                    else:
                        if st.button("➕ Ingresar a la cola"):
                            col_tiempos.insert_one({
                                "agente_id": domain,
                                "agente_nombre": agente["nombre"],
                                "autorizador_id": autorizador["domain_id"],
                                "autorizador_nombre": autorizador["nombre"],
                                "hora_ingreso": ahora(),
                                "estado": "Pendiente"
                            })
                            st.success("Agente en cola.")
                            st.rerun()

        # === PENDIENTES ===
        elif seleccion == "📤 En cola (Pendiente)":
            if pendientes:
                opciones = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
                seleccion_pendiente = st.selectbox("Agente en cola:", opciones)
                if seleccion_pendiente:
                    seleccionado = pendientes[opciones.index(seleccion_pendiente)]
                    tiempo = tiempo_transcurrido(seleccionado["hora_ingreso"])
                    st.info(f"⏱ Tiempo en cola: {tiempo}")
                    if st.button("✅ Autorizar"):
                        col_tiempos.update_one(
                            {"_id": seleccionado["_id"]},
                            {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                        )
                        st.rerun()
            else:
                st.info("No hay agentes en cola.")

        # === AUTORIZADOS ===
        elif seleccion == "🟢 Autorizados (esperando que arranquen)":
            if autorizados:
                opciones = [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados]
                seleccion_aut = st.selectbox("Agente autorizado:", opciones)
                if seleccion_aut:
                    seleccionado = autorizados[opciones.index(seleccion_aut)]
                    tiempo = tiempo_transcurrido(seleccionado.get("hora_autorizacion"))
                    st.info(f"⏱ Esperando inicio hace: {tiempo}")
                    if st.button("▶️ Iniciar tiempo"):
                        col_tiempos.update_one(
                            {"_id": seleccionado["_id"]},
                            {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                        )
                        st.rerun()
            else:
                st.info("No hay agentes autorizados en espera.")

        # === EN CURSO ===
        elif seleccion == "⏳ Tiempo personal en curso":
            if en_curso:
                opciones = [f"{e['agente_nombre']} ({e['agente_id']})" for e in en_curso]
                seleccion_curso = st.selectbox("Agente en curso:", opciones)
                if seleccion_curso:
                    seleccionado = en_curso[opciones.index(seleccion_curso)]
                    cronometro = st.empty()
                    stop = st.button("🛑 Finalizar tiempo")
                    for _ in range(100000):
                        tiempo = tiempo_transcurrido(seleccionado.get("hora_inicio"))
                        cronometro.markdown(f"### 🕒 Tiempo transcurrido: {tiempo}")
                        time.sleep(1)
                        if stop:
                            fin = ahora()
                            duracion = (fin - seleccionado["hora_inicio"]).total_seconds() / 60
                            col_tiempos.update_one(
                                {"_id": seleccionado["_id"]},
                                {
                                    "$set": {
                                        "estado": "Completado",
                                        "hora_fin": fin,
                                        "duracion_minutos": round(duracion, 2)
                                    }
                                }
                            )
                            st.success(f"Tiempo finalizado: {round(duracion, 2)} minutos")
                            st.rerun()
            else:
                st.info("No hay tiempos personales en curso.")

        # === HISTORIAL ===
        elif seleccion == "📑 Historial":
            if completados:
                historial = []
                for h in completados:
                    inicio = h.get("hora_inicio")
                    fin = h.get("hora_fin")
                    duracion = h.get("duracion_minutos", 0)
                    minutos = int(duracion)
                    segundos = int((duracion - minutos) * 60)
                    historial.append({
                        "Agente": h["agente_nombre"],
                        "Domain ID": h["agente_id"],
                        "Autorizador": h["autorizador_nombre"],
                        "Inicio": inicio.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S") if inicio else "",
                        "Fin": fin.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S") if fin else "",
                        "Duración": f"{minutos:02d}:{segundos:02d}"
                    })
                df = pd.DataFrame(historial[::-1])
                df.index = list(range(len(df), 0, -1))
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No hay registros completados.")