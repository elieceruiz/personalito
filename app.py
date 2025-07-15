import streamlit as st
from datetime import datetime
import pymongo
import pytz
import pandas as pd
import time

# === CONFIGURACIÓN GENERAL ===
st.set_page_config(page_title="📋 Registro de Tiempo Personal – personalito (Walmart DAS)", layout="centered")
MONGO_URI = st.secrets["mongo_uri"]
cliente = pymongo.MongoClient(MONGO_URI)
db = cliente["tiempo_personal"]
col_tiempos = db["tiempos"]
col_agentes = db["agentes"]
col_autorizadores = db["autorizadores"]
zona_col = pytz.timezone("America/Bogota")

# === FUNCIONES ===
def ahora():
    return datetime.now(tz=zona_col)

def formatear_duracion(delta):
    segundos = int(delta.total_seconds())
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segundos = segundos % 60
    return f"{horas:02}:{minutos:02}:{segundos:02}"

def tiempo_transcurrido(doc):
    estado = doc["estado"]
    inicio = None
    if estado == "Pendiente":
        inicio = doc.get("hora_ingreso")
    elif estado == "Autorizado":
        inicio = doc.get("hora_autorizacion")
    elif estado == "En curso":
        inicio = doc.get("hora_inicio")
    elif estado == "Completado":
        inicio = doc.get("hora_inicio")
        fin = doc.get("hora_fin")
        if inicio and fin:
            return formatear_duracion(fin - inicio)
        else:
            return "—"
    if not inicio:
        return "—"
    return formatear_duracion(ahora() - inicio)

def ya_completo_hoy(domain_id):
    hoy = ahora().date()
    doc = col_tiempos.find_one({
        "agente_id": domain_id,
        "estado": "Completado",
        "hora_fin": {
            "$gte": datetime(hoy.year, hoy.month, hoy.day, tzinfo=zona_col)
        }
    })
    return doc is not None

# === INTERFAZ ===
st.title("📋 Registro de Tiempo Personal – personalito (Walmart DAS)")
autorizador_id = st.text_input("Domain ID del autorizador", max_chars=50)
if autorizador_id:
    autorizado = col_autorizadores.find_one({"domain_id": autorizador_id})
    if not autorizado:
        nombre_aut = st.text_input("Nombre del autorizador")
        if nombre_aut:
            col_autorizadores.insert_one({"domain_id": autorizador_id, "nombre": nombre_aut})
            st.success("Autorizador registrado.")
            st.rerun()
    else:
        st.success(f"Bienvenido/a, {autorizado['nombre']}")

        # === DROPDOWN PRINCIPAL ===
        secciones = {
            "🆕 Registrar nuevo agente en cola": "registro",
            "📤 En cola (Pendiente)": "pendientes",
            "🟢 Autorizados": "autorizados",
            "⏳ Tiempo en curso": "encurso",
            "📜 Historial": "historial"
        }
        seleccion = st.selectbox("Seleccione sección", list(secciones.keys()))
        seleccion_clave = secciones[seleccion]

        st.markdown("---")

        if seleccion_clave == "registro":
            domain_id = st.text_input("Domain ID del agente", max_chars=50)
            if domain_id:
                if ya_completo_hoy(domain_id):
                    st.error("⛔ Este agente ya tuvo tiempo personal hoy.")
                else:
                    agente = col_agentes.find_one({"domain_id": domain_id})
                    if not agente:
                        nombre_ag = st.text_input("Nombre del agente")
                        if nombre_ag:
                            col_agentes.insert_one({"domain_id": domain_id, "nombre": nombre_ag})
                            st.success("Agente registrado.")
                            st.rerun()
                    else:
                        if st.button("➕ Agregar a la cola (Pendiente)"):
                            en_proceso = col_tiempos.find_one({
                                "agente_id": domain_id,
                                "estado": {"$in": ["Pendiente", "Autorizado", "En curso"]}
                            })
                            if en_proceso:
                                st.warning("Este agente ya tiene una solicitud en curso.")
                            else:
                                col_tiempos.insert_one({
                                    "agente_id": domain_id,
                                    "agente_nombre": agente["nombre"],
                                    "autorizador_id": autorizador_id,
                                    "autorizador_nombre": autorizado["nombre"],
                                    "hora_ingreso": ahora(),
                                    "estado": "Pendiente"
                                })
                                st.success("Agente agregado a la cola.")
                                st.rerun()

        elif seleccion_clave in ["pendientes", "autorizados", "encurso"]:
            estado_map = {
                "pendientes": "Pendiente",
                "autorizados": "Autorizado",
                "encurso": "En curso"
            }
            docs = list(col_tiempos.find({"estado": estado_map[seleccion_clave]}).sort("hora_ingreso", 1))
            cantidad = len(docs)
            st.markdown(f"**{cantidad} agente(s) en {estado_map[seleccion_clave]}**")

            if cantidad == 0:
                st.info("No hay agentes en esta sección.")
            else:
                opciones = [f"{d['agente_nombre']} ({d['agente_id']})" for d in docs]
                seleccion_opc = st.selectbox("Seleccionar agente", opciones)
                seleccionado = docs[opciones.index(seleccion_opc)]
                tiempo = tiempo_transcurrido(seleccionado)
                st.success(f"⏱ {tiempo}")

                if seleccion_clave == "pendientes":
                    if st.button("✅ Autorizar"):
                        col_tiempos.update_one({"_id": seleccionado["_id"]}, {
                            "$set": {
                                "estado": "Autorizado",
                                "hora_autorizacion": ahora()
                            }
                        })
                        st.rerun()
                elif seleccion_clave == "autorizados":
                    if st.button("▶️ Iniciar"):
                        col_tiempos.update_one({"_id": seleccionado["_id"]}, {
                            "$set": {
                                "estado": "En curso",
                                "hora_inicio": ahora()
                            }
                        })
                        st.rerun()
                elif seleccion_clave == "encurso":
                    if st.button("🛑 Finalizar"):
                        ahora_fin = ahora()
                        dur = ahora_fin - seleccionado["hora_inicio"]
                        col_tiempos.update_one({"_id": seleccionado["_id"]}, {
                            "$set": {
                                "estado": "Completado",
                                "hora_fin": ahora_fin,
                                "duracion_min": round(dur.total_seconds() / 60, 2)
                            }
                        })
                        st.success("Tiempo completado.")
                        st.rerun()

        elif seleccion_clave == "historial":
            completados = list(col_tiempos.find({"estado": "Completado"}).sort("hora_fin", -1))
            if not completados:
                st.info("No hay registros finalizados.")
            else:
                data = []
                for i, doc in enumerate(completados, 1):
                    data.append({
                        "#": len(completados) - i + 1,
                        "Agente": doc["agente_nombre"],
                        "Domain ID": doc["agente_id"],
                        "Autorizador": doc["autorizador_nombre"],
                        "Fecha": doc["hora_fin"].astimezone(zona_col).strftime("%Y-%m-%d"),
                        "Inicio": doc["hora_inicio"].astimezone(zona_col).strftime("%H:%M:%S"),
                        "Fin": doc["hora_fin"].astimezone(zona_col).strftime("%H:%M:%S"),
                        "Duración": formatear_duracion(doc["hora_fin"] - doc["hora_inicio"])
                    })
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True)
