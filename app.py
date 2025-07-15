import streamlit as st
import pymongo
import pandas as pd
from datetime import datetime, timedelta
import pytz
import time

# === CONFIGURACIÓN ===
st.set_page_config(page_title="📋 Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")

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

def tiempo_transcurrido_segundos(inicio):
    return int((ahora() - inicio).total_seconds())

def formatear_mm_ss(segundos):
    minutos, segundos = divmod(segundos, 60)
    return f"{int(minutos):02d}:{int(segundos):02d}"

# === AUTORIZADOR ===
st.subheader("🔐 Identificación del autorizador")
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

        # === INDICADORES ===
        pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
        autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
        en_curso = list(col_tiempos.find({"estado": "En curso"}))
        st.markdown(f"#### 👥 En cola: **{len(pendientes)}** | 🟢 Autorizados: **{len(autorizados)}** | ⏳ En curso: **{len(en_curso)}**")

        # === SELECCIÓN DE SECCIÓN ===
        opciones = [
            "🆕 Registrar nuevo agente en cola",
            "🕓 En cola (Pendiente)",
            "🟢 Autorizados (esperando que arranquen)",
            "⏳ Tiempo personal en curso"
        ]
        seccion = st.selectbox("Selecciona una sección:", opciones)

        # === NUEVO REGISTRO ===
        if seccion == opciones[0]:
            st.subheader("🆕 Registrar nuevo agente en cola")
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
                    if st.button("➕ Agregar a la cola (Pendiente)"):
                        ya_en_cola = col_tiempos.find_one({
                            "agente_id": domain_agente,
                            "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]},
                            "hora_ingreso": {"$gte": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)}
                        })
                        if ya_en_cola:
                            st.warning("Este agente ya tiene un tiempo personal registrado hoy.")
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

        # === PENDIENTES ===
        elif seccion == opciones[1]:
            st.subheader("🕓 En cola (Pendiente)")
            ids = [f"{p['agente_nombre']} ({p['agente_id']})" for p in pendientes]
            seleccionado = st.selectbox("Selecciona un agente:", ids) if ids else None
            if seleccionado:
                agente_id = seleccionado.split("(")[-1].strip(")")
                agente = next(p for p in pendientes if p["agente_id"] == agente_id)
                cronometro = st.empty()
                if st.button(f"✅ Autorizar {agente_id}"):
                    col_tiempos.update_one(
                        {"_id": agente["_id"]},
                        {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                    )
                    st.rerun()
                for i in range(tiempo_transcurrido_segundos(agente["hora_ingreso"]), 100000):
                    cronometro.markdown(f"### ⏱ En cola: {formatear_mm_ss(i)}")
                    time.sleep(1)

        # === AUTORIZADOS ===
        elif seccion == opciones[2]:
            st.subheader("🟢 Autorizados")
            ids = [f"{a['agente_nombre']} ({a['agente_id']})" for a in autorizados]
            seleccionado = st.selectbox("Selecciona un agente:", ids) if ids else None
            if seleccionado:
                agente_id = seleccionado.split("(")[-1].strip(")")
                agente = next(a for a in autorizados if a["agente_id"] == agente_id)
                cronometro = st.empty()
                if st.button(f"▶️ Iniciar tiempo de {agente_id}"):
                    col_tiempos.update_one(
                        {"_id": agente["_id"]},
                        {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                    )
                    st.rerun()
                for i in range(tiempo_transcurrido_segundos(agente["hora_autorizacion"]), 100000):
                    cronometro.markdown(f"### ⏱ Esperando inicio: {formatear_mm_ss(i)}")
                    time.sleep(1)

        # === EN CURSO ===
        elif seccion == opciones[3]:
            st.subheader("⏳ Tiempo personal en curso")
            ids = [f"{e['agente_nombre']} ({e['agente_id']})" for e in en_curso]
            seleccionado = st.selectbox("Selecciona un agente:", ids) if ids else None
            if seleccionado:
                agente_id = seleccionado.split("(")[-1].strip(")")
                agente = next(e for e in en_curso if e["agente_id"] == agente_id)
                cronometro = st.empty()
                if st.button(f"🛑 Finalizar tiempo de {agente_id}"):
                    fin = ahora()
                    duracion = (fin - agente["hora_inicio"]).total_seconds() / 60
                    col_tiempos.update_one(
                        {"_id": agente["_id"]},
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
                for i in range(tiempo_transcurrido_segundos(agente["hora_inicio"]), 100000):
                    cronometro.markdown(f"### ⏱ Tiempo en curso: {formatear_mm_ss(i)}")
                    time.sleep(1)

        # === HISTORIAL ===
        st.subheader("📜 Historial de tiempos finalizados")
        finalizados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
        if finalizados:
            datos = []
            total = len(finalizados)
            for idx, f in enumerate(finalizados):
                minutos, segundos = divmod(int(f.get("duracion_minutos", 0) * 60), 60)
                datos.append({
                    "#": total - idx,
                    "Agente": f["agente_nombre"],
                    "Domain ID": f["agente_id"],
                    "Autorizador": f["autorizador_nombre"],
                    "Inicio": f["hora_inicio"].astimezone(zona_col).strftime("%H:%M:%S"),
                    "Fin": f["hora_fin"].astimezone(zona_col).strftime("%H:%M:%S"),
                    "Duración": f"{minutos:02d}:{segundos:02d}"
                })
            df = pd.DataFrame(datos)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No hay registros finalizados.")