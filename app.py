import streamlit as st
import pymongo
from datetime import datetime, timedelta
import pandas as pd
import pytz
import time

# === CONFIGURACIÓN ===
st.set_page_config(page_title="🕘 Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
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

def hoy_inicio():
    now = datetime.now(zona_col)
    return datetime(now.year, now.month, now.day, tzinfo=zona_col).astimezone(pytz.UTC)

def cronometro_segundos(inicio):
    tiempo = int((datetime.utcnow() - inicio).total_seconds())
    return f"{tiempo // 60}m {tiempo % 60}s"

def cronometro_en_vivo(inicio, label):
    placeholder = st.empty()
    for i in range(100000):
        transcurrido = datetime.utcnow() - inicio
        minutos, segundos = divmod(transcurrido.total_seconds(), 60)
        placeholder.markdown(f"**{label}**: {int(minutos)}m {int(segundos)}s")
        time.sleep(1)

# === INTERFAZ ===
st.title("🕘 Registro de Tiempo Personal – personalito (Walmart DAS)")
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

        # === REGISTRO DE NUEVO AGENTE ===
        st.subheader("📝 Registrar nuevo agente en cola")
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
                hoy = hoy_inicio()
                ya_tuvo = col_tiempos.find_one({
                    "agente_id": domain_agente,
                    "hora_ingreso": {"$gte": hoy}
                })
                if ya_tuvo:
                    st.warning("Este agente ya tuvo tiempo personal hoy.")
                elif st.button("➕ Agregar a la cola (Pendiente)"):
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
        if pendientes:
            mapa = {f"{p['agente_nombre']} ({p['agente_id']})": p for p in pendientes}
            elegido = st.selectbox("Selecciona agente a autorizar", list(mapa.keys()), key="pendiente")
            cronometro_en_vivo(mapa[elegido]['hora_ingreso'], "En cola")
            if st.button("✅ Autorizar"):
                col_tiempos.update_one(
                    {"_id": mapa[elegido]["_id"]},
                    {"$set": {"estado": "Autorizado", "hora_autorizacion": ahora()}}
                )
                st.rerun()
        else:
            st.info("Sin agentes pendientes.")

        # === AUTORIZADOS ===
        st.subheader("🟢 Autorizados (esperando inicio)")
        autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
        if autorizados:
            mapa = {f"{a['agente_nombre']} ({a['agente_id']})": a for a in autorizados}
            elegido = st.selectbox("Selecciona agente a iniciar", list(mapa.keys()), key="autorizado")
            cronometro_en_vivo(mapa[elegido]['hora_autorizacion'], "Autorizado")
            if st.button("▶️ Iniciar tiempo"):
                col_tiempos.update_one(
                    {"_id": mapa[elegido]["_id"]},
                    {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
                )
                st.rerun()
        else:
            st.info("Sin agentes autorizados aún.")

        # === EN CURSO ===
        st.subheader("⏳ En curso")
        activos = list(col_tiempos.find({"estado": "En curso"}))
        if activos:
            mapa = {f"{e['agente_nombre']} ({e['agente_id']})": e for e in activos}
            elegido = st.selectbox("Selecciona agente a finalizar", list(mapa.keys()), key="encurso")
            cronometro_en_vivo(mapa[elegido]['hora_inicio'], "Tiempo en curso")
            if st.button("🛑 Finalizar"):
                fin = ahora()
                duracion = (fin - mapa[elegido]["hora_inicio"]).total_seconds() / 60
                col_tiempos.update_one(
                    {"_id": mapa[elegido]["_id"]},
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
            st.info("No hay tiempos activos en curso.")

        # === HISTORIAL ===
        st.subheader("📜 Historial de Tiempos Completados")
        completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
        historial = []
        for h in completados:
            ingreso = h.get("hora_ingreso")
            autorizacion = h.get("hora_autorizacion")
            inicio = h.get("hora_inicio")
            fin = h.get("hora_fin")
            historial.append({
                "Agente": h["agente_nombre"],
                "Autorizador": h["autorizador_nombre"],
                "Ingreso": ingreso.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if ingreso else "",
                "Autorizado": autorizacion.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if autorizacion else "",
                "Inicio": inicio.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if inicio else "",
                "Fin": fin.astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S") if fin else "",
                "Duración (min)": h.get("duracion_minutos", 0)
            })

        if historial:
            df = pd.DataFrame(historial)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Sin registros completados todavía.")