import streamlit as st
import pymongo
from datetime import datetime
import pandas as pd
import pytz
import time

# === CONFIGURACIÓN ===
st.set_page_config(page_title="📋 Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
MONGO_URI = st.secrets["mongo_uri"]
client = pymongo.MongoClient(MONGO_URI)
db = client["tiempo_personal"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]
col_tiempos = db["tiempos"]
zona_col = pytz.timezone("America/Bogota")

# === FUNCIONES ===
def ahora():
    return datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(zona_col)

def tiempo_transcurrido(inicio):
    if not inicio:
        return "—"
    inicio = inicio.replace(tzinfo=pytz.UTC).astimezone(zona_col)
    delta = ahora() - inicio
    horas, resto = divmod(delta.total_seconds(), 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{int(horas):02d}:{int(minutos):02d}:{int(segundos):02d}"

def formatear_duracion(segundos_totales):
    horas, resto = divmod(int(segundos_totales), 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

# === INTERFAZ PRINCIPAL ===
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")

# === AUTORIZADOR ===
domain_aut = st.text_input("🔐 Domain ID del autorizador")
if not domain_aut:
    st.stop()

aut = col_autorizadores.find_one({"domain_id": domain_aut})
if not aut:
    nombre_aut = st.text_input("Nombre del autorizador")
    if nombre_aut:
        col_autorizadores.insert_one({"domain_id": domain_aut, "nombre": nombre_aut})
        st.success("Autorizador registrado exitosamente.")
        st.rerun()
else:
    st.caption(f"Autorizador: {aut['nombre']}")

# === DROPDOWN SECCIONES ===
opciones = {
    "📋 Registrar nuevo agente en cola": "registrar",
    "📤 En cola (Pendiente)": "pendientes",
    "🟢 Autorizados (esperando que arranquen)": "autorizados",
    "⏳ Tiempo personal en curso": "encurso",
    "📜 Historial": "historial"
}
conteos = {
    "pendientes": col_tiempos.count_documents({"estado": "Pendiente"}),
    "autorizados": col_tiempos.count_documents({"estado": "Autorizado"}),
    "encurso": col_tiempos.count_documents({"estado": "En curso"}),
}
st.markdown(f"""**En cola**: {conteos['pendientes']} 
**Autorizados**: {conteos['autorizados']} 
**En curso**: {conteos['encurso']}""")

seccion = st.selectbox("Selecciona una sección", list(opciones.keys()))
opcion = opciones[seccion]

# === 1. REGISTRO EN COLA ===
if opcion == "registrar":
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
            hoy = ahora().date()
            ya_tiene = col_tiempos.find_one({
                "agente_id": domain_agente,
                "estado": "Completado",
                "hora_inicio": {"$gte": datetime(hoy.year, hoy.month, hoy.day, tzinfo=zona_col)}
            })
            if ya_tiene:
                st.warning("Este agente ya usó su tiempo personal hoy.")
            else:
                if st.button("➕ Agregar a la cola (Pendiente)"):
                    existe = col_tiempos.find_one({
                        "agente_id": domain_agente,
                        "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                    })
                    if existe:
                        st.warning("Este agente ya tiene un proceso activo.")
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

# === 2. PENDIENTES ===
elif opcion == "pendientes":
    st.markdown(f"Agentes en cola: **{conteos['pendientes']}**")
    pendientes = list(col_tiempos.find({"estado": "Pendiente"}))
    if pendientes:
        seleccionado = st.selectbox("Selecciona un agente en cola", pendientes, format_func=lambda x: f"{x['agente_nombre']} ({x['agente_id']})")
        hora = seleccionado.get("hora_ingreso")
        st.markdown(f"⌛ Tiempo en cola: **{tiempo_transcurrido(hora)}**")
        time.sleep(1)
        st.rerun()
    else:
        st.info("No hay agentes en cola actualmente.")

# === 3. AUTORIZADOS ===
elif opcion == "autorizados":
    st.markdown(f"Agentes autorizados: **{conteos['autorizados']}**")
    autorizados = list(col_tiempos.find({"estado": "Autorizado"}))
    if autorizados:
        seleccionado = st.selectbox("Selecciona un agente autorizado", autorizados, format_func=lambda x: f"{x['agente_nombre']} ({x['agente_id']})")
        hora = seleccionado.get("hora_autorizacion")
        st.markdown(f"🕒 Tiempo desde autorización: **{tiempo_transcurrido(hora)}**")
        if st.button(f"▶️ Iniciar tiempo para {seleccionado['agente_nombre']}"):
            col_tiempos.update_one(
                {"_id": seleccionado["_id"]},
                {"$set": {"estado": "En curso", "hora_inicio": ahora()}}
            )
            st.rerun()
        time.sleep(1)
        st.rerun()
    else:
        st.info("No hay agentes autorizados.")

# === 4. EN CURSO ===
elif opcion == "encurso":
    st.markdown(f"Agentes en tiempo personal: **{conteos['encurso']}**")
    en_curso = list(col_tiempos.find({"estado": "En curso"}))
    if en_curso:
        seleccionado = st.selectbox("Selecciona un agente en curso", en_curso, format_func=lambda x: f"{x['agente_nombre']} ({x['agente_id']})")
        hora = seleccionado.get("hora_inicio")
        st.markdown(f"⏱ Tiempo en curso: **{tiempo_transcurrido(hora)}**")
        if st.button(f"🛑 Finalizar tiempo de {seleccionado['agente_nombre']}"):
            fin = ahora()
            duracion = (fin - hora).total_seconds()
            col_tiempos.update_one(
                {"_id": seleccionado["_id"]},
                {
                    "$set": {
                        "estado": "Completado",
                        "hora_fin": fin,
                        "duracion_segundos": duracion
                    }
                }
            )
            st.success(f"Tiempo finalizado: {formatear_duracion(duracion)}")
            st.rerun()
        time.sleep(1)
        st.rerun()
    else:
        st.info("No hay agentes con tiempo en curso.")

# === 5. HISTORIAL ===
elif opcion == "historial":
    st.header("📜 Historial de tiempos finalizados")
    finalizados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
    if finalizados:
        df = pd.DataFrame([{
            "N°": len(finalizados) - i,
            "Agente": f"{d['agente_nombre']}",
            "Domain ID": d["agente_id"],
            "Autorizador": d["autorizador_nombre"],
            "Duración (hh:mm:ss)": f"{int(d['duracion_segundos'] // 3600):02}:{int((d['duracion_segundos'] % 3600) // 60):02}:{int(d['duracion_segundos'] % 60):02}",
            "Inicio": d["hora_inicio"].astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S"),
            "Fin": d["hora_fin"].astimezone(zona_col).strftime("%Y-%m-%d %H:%M:%S")
        } for i, d in enumerate(finalizados)])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No hay registros completados.")