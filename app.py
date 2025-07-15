import streamlit as st
import pymongo
from datetime import datetime, timedelta
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

def formatear(fecha):
    return fecha.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S")

# === INGRESO DE AUTORIZADOR ===
st.title("⏱ Registro de Tiempo Personal – personalito (Walmart DAS)")
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

        # === REGISTRO DE SOLICITUD ===
        st.subheader("📝 Registrar nuevo agente en cola")
        domain_agente = st.text_input("Domain ID del agente")
        if domain_agente:
            agente = col_agentes.find_one({"domain_id": domain_agente})
            hoy = datetime.now(zona_col).date()
            ya_solicito = col_tiempos.find_one({
                "agente_id": domain_agente,
                "hora_ingreso": {"$gte": datetime.combine(hoy, datetime.min.time()).astimezone(pytz.UTC)}
            })

            if ya_solicito:
                st.warning("Este agente ya ha solicitado tiempo personal hoy.")
            elif not agente:
                nombre_agente = st.text_input("Nombre del agente")
                if nombre_agente:
                    col_agentes.insert_one({"domain_id": domain_agente, "nombre": nombre_agente})
                    st.success("Agente registrado. Continúe con la autorización.")
                    st.rerun()
            else:
                if st.button("➕ Agregar a la cola (Pendiente)"):
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
        st.subheader("🕓 En cola (Pendiente)")
        pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
        for p in pendientes:
            st.write(f"🟡 {p['agente_nombre']} ({p['agente_id']}) – Lleva {tiempo_transcurrido(p['hora_ingreso'])} en cola")
            st.caption("🔁 Refresque la página para ver el tiempo actualizado.")
            if st.button(f"✅ Autorizar {p['agente_id']}"):
                col_tiempos.update_one(
                    {"_id": p["_id"]},
                    {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                )
                st.rerun()

        # === AUTORIZADOS ===
        st.subheader("🟢 Autorizados (esperando que arranquen)")
        autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
        for a in autorizados:
            st.write(f"🟢 {a['agente_nombre']} ({a['agente_id']}) – Autorizado hace {tiempo_transcurrido(a['hora_autorizacion'])}")
            st.caption("🔁 Refresque la página para ver el tiempo actualizado.")
            if st.button(f"▶️ Iniciar tiempo de {a['agente_id']}"):
                col_tiempos.update_one(
                    {"_id": a["_id"]},
                    {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                )
                st.rerun()

        # === EN CURSO ===
        st.subheader("⏳ Tiempo personal en curso")
        en_curso = list(col_tiempos.find({"estado": "En curso"}))
        for e in en_curso:
            st.write(f"⏳ {e['agente_nombre']} ({e['agente_id']}) – Tiempo corriendo desde:")
            reloj = st.empty()
            detener = st.button(f"🛑 Finalizar tiempo de {e['agente_id']}")
            inicio = e['hora_inicio']
            segundos_iniciales = int((ahora() - inicio).total_seconds())

            for i in range(segundos_iniciales, 6 * 60 + 1):
                if detener:
                    fin = ahora()
                    duracion = (fin - inicio).total_seconds() / 60
                    col_tiempos.update_one(
                        {"_id": e["_id"]},
                        {"$set": {
                            "estado": "Completado",
                            "hora_fin": fin,
                            "duracion_minutos": round(duracion, 2)
                        }}
                    )
                    st.success(f"Tiempo finalizado: {round(duracion, 2)} minutos")
                    st.rerun()

                reloj.markdown(f"### 🕒 {i // 60}m {i % 60}s")
                time.sleep(1)

        # === HISTORIAL ===
        st.subheader("📜 Historial de tiempos completados")
        completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
        if completados:
            filas = []
            for c in completados:
                filas.append({
                    "Agente": c["agente_nombre"],
                    "Domain ID": c["agente_id"],
                    "Autorizador": c["autorizador_nombre"],
                    "Ingreso": formatear(c["hora_ingreso"]),
                    "Autorizado": formatear(c["hora_autorizacion"]),
                    "Inicio": formatear(c["hora_inicio"]),
                    "Fin": formatear(c["hora_fin"]),
                    "Duración (min)": c.get("duracion_minutos", 0)
                })
            st.dataframe(pd.DataFrame(filas), use_container_width=True)
        else:
            st.info("Aún no hay tiempos completados.")