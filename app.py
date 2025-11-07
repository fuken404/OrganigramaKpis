"""Carga de un archivo .xlsx para conversión a .csv y así manipular datos con los que al final con se crea el organigrama"""
import streamlit as st
import pandas as pd
import time




#PTE RENDERIZAR CON Streamlit_Flows




#Inicialización de variables de sesión
if 'df' not in st.session_state:
    st.session_state['df'] = None
if 'file_id' not in st.session_state:
    st.session_state['file_id'] = None

#Inicialización del GUI
st.title("Generador de Organigramas")
st.write("Cargar archivo .xlsx para generar el organigrama")
fileXlsx = st.file_uploader("Elige un archivo de Excel", type="xlsx")

#Función para dejar solo los datos necesarios para la creación del organigrama
def limpiarDatosNecesatrios(dfr):
  #Paso 1: Crear DataFrame de únicamente cargos sin duplicados
  df = pd.DataFrame({
    "Cargo": pd.concat([dfr["Cargo"], dfr["Responde al Cargo"]]).unique()
    })
  
  #Paso 2: Incluir columna de jefes
  df_jefes = dfr[["Cargo", "Responde al Cargo"]].drop_duplicates(subset="Cargo", keep="first")
  df = df.merge(
      df_jefes,
      on = "Cargo",
      how = "left"
  )
  df["Responde al Cargo"] = df["Responde al Cargo"].fillna("N/A").astype(str)

  #Paso 3: Obtener niveles jerárquicos únicos por cargo y rellenar los faltantes con "N/A"
  df_nivel = dfr[["Cargo", "Nivel Jerárquico"]].drop_duplicates(subset="Cargo", keep="first")
  df = df.merge(
      df_nivel,
      on="Cargo",
      how="left"
  )
  df["Nivel Jerárquico"] = df["Nivel Jerárquico"].fillna("N/A").astype(str)
  
  #Paso 4: Incluir columna para KPI's
  tmp = dfr[["Cargo", "Indicador"]].copy()
  tmp["Indicador"] = (
      tmp["Indicador"]
        .astype(str)
        .str.strip()
  )
  tmp = tmp[
      tmp["Indicador"].notna()
      & (tmp["Indicador"] != "")
      & (tmp["Indicador"].str.lower() != "n/a")
  ]
  df_kpi = (
      tmp.groupby("Cargo", as_index=False)["Indicador"]
         .agg(lambda s: list(dict.fromkeys(s)))
         .rename(columns={"Indicador": "KPIs"})
  )
  df = df.merge(df_kpi, on="Cargo", how="left")
  df["KPIs"] = df["KPIs"].apply(lambda v: v if isinstance(v, list) and len(v) > 0 else ["N/A"])
  
  return df

#Función para validar y asignar jefes faltantes
def validarJefe(dfr):
  jefe_na = dfr.loc[dfr["Responde al Cargo"].isin(["N/A", "nan", "", "None"]), "Cargo"].drop_duplicates().tolist()
  if not jefe_na:
    return dfr
  else:
    alerta = st.empty()
    alerta.warning(f"Hay {len(jefe_na)} cargos sin jefe asignado. Por favor asignar.")
    form_container = st.empty()
    with form_container.form(key = "form_asignar_jefes"):
        st.subheader("Selecciona jefe por cada cargo sin asignar")
        asignaciones = {}
        cargos_disponibles = dfr["Cargo"].tolist()
        for cargo in jefe_na:
          default_idx = None
          opciones_jefe = [c for c in cargos_disponibles if c != cargo]
          sel = st.selectbox(
              f"Jefe para: {cargo}",
              options=["-- Seleccionar --"] + opciones_jefe,
              index=default_idx if default_idx is not None else 0,
              key=f"sel_jefe_{cargo}"
          )
          # Evitar guardar placeholder
          asignaciones[cargo] = sel if sel != "-- Seleccionar --" else None
        submit = st.form_submit_button("Guardar Cambios")
    if submit:
      dfr["Responde al Cargo"] = dfr.apply(
          lambda r: asignaciones.get(r["Cargo"])
                    if (str(r["Responde al Cargo"]) in ["N/A", "nan", "", "None"] and asignaciones.get(r["Cargo"]))
                    else r["Responde al Cargo"],
          axis=1
      )
      form_container.empty()
      alerta.empty()
      msg = st.empty()
      msg.success("Jefes aplicados.")
      time.sleep(5)
      msg.empty()
  return dfr

#Función para validar y asignar niveles jerárquicos faltantes
def validarNivel(dfr):
  nivelesJerarquia = {
    "CEO": 1,
    "Vicepresidente": 2,
    "Gerente": 3,
    "Director": 4,
    "Jefe / Coordinador": 5,
    "Profesional / Analista": 6,
    "Asistente / Auxiliar": 7,
    "Operativo": 8
  }

  cargos_na = dfr.loc[dfr["Nivel Jerárquico"].isin(["N/A", "nan", "", "None"]), "Cargo"].drop_duplicates().tolist()

  ya_existe_ceo = (
    dfr["Nivel Jerárquico"].astype(str).str.strip().str.lower().eq("1").any()
    or dfr["Nivel Jerárquico"].astype(str).str.strip().str.lower().eq("ceo").any()
  )

  if not cargos_na:
      return dfr
  else:
    alerta = st.empty()
    alerta.warning(f"Hay {len(cargos_na)} cargos sin nivel. Por favor asignar.")

    form_container = st.empty()
    with form_container.form(key = "form_asignar_niveles"):
        st.subheader("Selecciona nivel por cada cargo sin asignar")
        asignaciones = {}
        etiquetas = list(nivelesJerarquia.keys())
        default_idx = None
        if ya_existe_ceo:
          etiquetas = [opt for opt in etiquetas if opt != "CEO"]
        for cargo in cargos_na:
            sel = st.selectbox(
                f"Nivel para: {cargo}",
                options=["-- Seleccionar --"] + etiquetas,
                index=default_idx if default_idx is not None else 0,
                key=f"sel_{cargo}"
            )
            # Evitar guardar placeholder; guarda etiqueta válida
            asignaciones[cargo] = sel if sel != "-- Seleccionar --" else None
        submit = st.form_submit_button("Guardar Cambios")
    if submit:
        dfr["Nivel Jerárquico"] = dfr.apply(
            lambda r: asignaciones.get(r["Cargo"])
                      if (str(r["Nivel Jerárquico"]) in ["N/A", "nan", "", "None"] and asignaciones.get(r["Cargo"]))
                      else r["Nivel Jerárquico"],
            axis=1
        )
        form_container.empty()
        alerta.empty()
        msg = st.empty()
        msg.success("Niveles aplicados.")
        time.sleep(5)
        msg.empty()
  return dfr

#Procesar archivo si se ha cargado uno
if fileXlsx is not None:
  with st.spinner('Actualizando datos...'):
    dfExcel = pd.read_excel(fileXlsx)
    try:
      # Solo reconstruir df si el archivo cambió o no hay df en sesión
      if (st.session_state['df'] is None) or (st.session_state['file_id'] != fileXlsx.name):
        st.session_state['file_id'] = fileXlsx.name
        st.session_state['df'] = limpiarDatosNecesatrios(dfExcel)

      # Trabajar siempre sobre el df persistente
      df = st.session_state['df']

      # Aplicar validaciones y persistir si hubo cambios
      updated = validarNivel(df)
      if updated is not None:
        st.session_state['df'] = updated

      updated = validarJefe(st.session_state['df'])
      if updated is not None:
        st.session_state['df'] = updated

      st.dataframe(st.session_state['df'], use_container_width=True)
    except Exception as e:
      st.error("Ha ocurrido un error por favor verifica que el archivo tenga las columnas necesarias: 'Cargo', 'Responde al Cargo', 'Nivel Jerárquico' y 'KPI's'.")