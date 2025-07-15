import streamlit as st
import pymongo
from datetime import datetime, timedelta
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

def calcular_tiempo(inicio):
    delta = ahora() - inicio
    minutos, segundos = divmod(delta.total_seconds(), 60)
    return f"{int(minutos):02d}m {int(segundos):02d}s"

# === INICIO APP ===
st.title("⏱ Registro de Tiempo Personal – personalito (Walmart DAS)")

# === IDENTIFICACIÓN AUTORIZADOR ===
st.subheader("🔐 Identificación del autorizador")
domain_aut = st.text_input("Domain ID del autorizador")

if domain_aut:
    aut = col_autorizadores.find_one({"domain_id": domain_aut})
    if not aut:
        nombre_aut = st.text_input("Nombre del autorizador")
        if nombre_aut:
            col_autorizadores.insert_one({"domain_id": domain_aut, "nombre": nombre_aut})
            st.success("Autorizador registrado.")
            st.rerun()
    else:
        st.success(f"Bienvenido/a, {aut['nombre']}")

        # === CARGA DE ESTADOS ===
        pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
        autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
        en_curso = list(col_tiempos.find({"estado": "En curso"}))
        completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))

        # === MENSAJE CONTEO ===
        st.markdown(f"**🕓 En cola (Pendiente):** {len(pendientes)} | 🟢 **Autorizados:** {len(autorizados)} | ⏳ **En curso:** {len(en_curso)}")

        # === SECCIÓN SELECCIONABLE ===
        opcion = st.selectbox("Selecciona una sección:", [
            "📝 Registrar nuevo agente en cola",
            "🕓 En cola (Pendiente)",
            "🟢 Autorizados (esperando que arranquen)",
            "⏳ Tiempo personal en curso",
            "📜 Historial de tiempos completados"
        ])

        # === REGISTRAR NUEVO ===
        if opcion == "📝 Registrar nuevo agente en cola":
            st.subheader("➕ Registro de nuevo agente")
            domain_agente = st.text_input("Domain ID del agente")
            if domain_agente:
                agente = col_agentes.find_one({"domain_id": domain_agente})
                if not agente:
                    nombre_agente = st.text_input("Nombre del agente")
                    if nombre_agente:
                        col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                        st.success("Agente registrado.")
                        st.rerun()
                else:
                    ya_en_proceso = col_tiempos.find_one({
                        "agente_id": domain_agente,
                        "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                    })
                    if ya_en_proceso:
                        st.warning("Este agente ya tiene un proceso activo.")
                    else:
                        hoy = datetime.now(zona_col).date()
                        ya_tuvo = col_tiempos.find_one({
                            "agente_id": domain_agente,
                            "estado": "Completado",
                            "hora_fin": {"$gte": datetime.combine(hoy, datetime.min.time())}
                        })
                        if ya_tuvo:
                            st.error("Este agente ya tomó tiempo personal hoy.")
                        else:
                            if st.button("📥 Agregar a la cola"):
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

        # === PENDIENTES ===
        elif opcion == "🕓 En cola (Pendiente)":
            st.subheader("🕓 Agentes pendientes")
            ids = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
            if ids:
                seleccionado = st.selectbox("Selecciona un agente", ids)
                obj = pendientes[ids.index(seleccionado)]
                tiempo = calcular_tiempo(obj["hora_ingreso"])
                st.info(f"⏱ Tiempo en cola: {tiempo}")
                if st.button("✅ Autorizar"):
                    col_tiempos.update_one(
                        {"_id": obj["_id"]},
                        {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                    )
                    st.rerun()
            else:
                st.info("No hay agentes en cola.")

        # === AUTORIZADOS ===
        elif opcion == "🟢 Autorizados (esperando que arranquen)":
            st.subheader("🟢 Agentes autorizados")
            ids = [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados]
            if ids:
                seleccionado = st.selectbox("Selecciona un agente", ids)
                obj = autorizados[ids.index(seleccionado)]
                tiempo = calcular_tiempo(obj["hora_autorizacion"])
                st.info(f"⏱ Tiempo desde autorización: {tiempo}")
                if st.button("▶️ Iniciar tiempo"):
                    col_tiempos.update_one(
                        {"_id": obj["_id"]},
                        {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                    )
                    st.rerun()
            else:
                st.info("No hay agentes autorizados esperando.")

        # === EN CURSO ===
        elif opcion == "⏳ Tiempo personal en curso":
            st.subheader("⏳ Agentes en tiempo personal")
            ids = [f"{e['agente_nombre']} ({e['agente_id']})" for e in en_curso]
            if ids:
                seleccionado = st.selectbox("Selecciona un agente", ids)
                obj = en_curso[ids.index(seleccionado)]
                st.success(f"⏱ Tiempo corriendo desde {obj['hora_inicio'].astimezone(zona_col).strftime('%H:%M:%S')}")
                cronometro = st.empty()
                stop_button = st.button("🛑 Finalizar tiempo")
                for i in range(100000):
                    if stop_button:
                        fin = ahora()
                        duracion = (fin - obj['hora_inicio']).total_seconds() / 60
                        col_tiempos.update_one(
                            {"_id": obj["_id"]},
                            {
                                "$set": {
                                    "estado": "Completado",
                                    "hora_fin": fin,
                                    "duracion_minutos": round(duracion, 2)
                                }
                            }
                        )
                        st.success(f"Finalizado: {round(duracion, 2)} minutos")
                        st.rerun()
                    else:
                        cronometro.markdown(f"### 🕒 Duración: {calcular_tiempo(obj['hora_inicio'])}")
                        time.sleep(1)
            else:
                st.info("No hay tiempos personales activos.")

        # === HISTORIAL ===
        elif opcion == "📜 Historial de tiempos completados":
            st.subheader("📜 Historial")
            if completados:
                datos = []
                for c in completados:
                    datos.append({
                        "Agente": c["agente_nombre"],
                        "Domain ID": c["agente_id"],
                        "Autorizador": c["autorizador_nombre"],
                        "Inicio": c["hora_inicio"].astimezone(zona_col).strftime("%H:%M:%S"),
                        "Fin": c["hora_fin"].astimezone(zona_col).strftime("%H:%M:%S"),
                        "Duración (min)": c.get("duracion_minutos", 0)
                    })
                st.dataframe(datos, use_container_width=True)
            else:
                st.info("No hay tiempos finalizados.")