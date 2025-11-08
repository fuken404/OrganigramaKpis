"""Carga de un archivo .xlsx para conversión a .csv y así manipular datos con los que al final con se crea el organigrama"""
#Librerías para manipulación de datos
import pandas as pd
import time

#Librerías para renderizar organigrama
import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge 
from streamlit_flow.state import StreamlitFlowState
from streamlit_flow.layouts import TreeLayout

# Usar página ancha para aprovechar más espacio horizontal
st.set_page_config(layout="wide")

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
  # Cargos sin jefe declarado
  cargos_sin_jefe = dfr.loc[dfr["Responde al Cargo"].isin(["N/A", "nan", "", "None"]), "Cargo"].drop_duplicates().tolist()

  # Identificar cargos con nivel CEO (etiqueta "CEO" o nivel "1") para no pedir jefe
  try:
    ceo_mask = dfr["Nivel Jerárquico"].astype(str).str.strip().str.lower().isin(["1", "CEO"])
    cargos_ceo = dfr.loc[ceo_mask, "Cargo"].drop_duplicates().tolist()
  except Exception:
    cargos_ceo = []

  # Excluir CEO(s) de la lista a solicitar
  jefe_na = [c for c in cargos_sin_jefe if c not in cargos_ceo]

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

# Utilidad para localizar la columna de nivel jerárquico pese a acentos/variantes
def _find_nivel_col(columns):
  def norm(s):
    return ''.join(ch for ch in str(s).lower() if ch.isalpha())
  for col in columns:
    n = norm(col)
    if 'nivel' in n and 'jer' in n:
      return col
  return None

# Versión robusta: no pide jefe para CEO (nivel "1" o "CEO")
def validarJefe_v2(dfr):
  placeholders = {"N/A", "nan", "", "None"}
  cargos_sin_jefe = (
    dfr.loc[dfr["Responde al Cargo"].astype(str).str.strip().isin(placeholders), "Cargo"]
      .drop_duplicates().tolist()
  )

  nivel_col = _find_nivel_col(dfr.columns)
  cargos_ceo = []
  if nivel_col is not None:
    s = dfr[nivel_col].astype(str).str.strip().str.lower()
    ceo_mask = s.eq("1") | s.str.startswith("1") | s.str.contains("ceo")
    cargos_ceo = dfr.loc[ceo_mask, "Cargo"].drop_duplicates().tolist()
  # Fallback adicional: detectar por nombre del cargo si no se encontró por nivel
  if not cargos_ceo:
    cargos_ceo = dfr.loc[dfr["Cargo"].astype(str).str.strip().str.lower().str.contains("ceo"), "Cargo"].drop_duplicates().tolist()

  jefe_na = [c for c in cargos_sin_jefe if c not in cargos_ceo]

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
          asignaciones[cargo] = sel if sel != "-- Seleccionar --" else None
        submit = st.form_submit_button("Guardar Cambios")
    if submit:
      dfr["Responde al Cargo"] = dfr.apply(
          lambda r: asignaciones.get(r["Cargo"])
                    if (str(r["Responde al Cargo"]).strip() in placeholders and asignaciones.get(r["Cargo"]))
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

#Función para renderizar el organigrama
def renderizarOrganigrama(df):
  columnas = {"Cargo", "Responde al Cargo", "KPIs"}
  if not columnas.issubset(set(df.columns)):
      st.warning("El DataFrame no contiene las columnas requeridas: 'Cargo', 'Responde al Cargo', 'KPIs'.")
      return
  base = df[["Cargo", "Responde al Cargo", "KPIs"]].drop_duplicates(subset="Cargo", keep="first").copy()
  base["Cargo"] = base["Cargo"].astype(str).str.strip()
  base["Responde al Cargo"] = base["Responde al Cargo"].astype(str).str.strip()
  cargos = base["Cargo"].tolist()
  cargo_set = set(cargos)
  kpis_map = dict(zip(base["Cargo"], base["KPIs"]))
  jefe_map = dict(zip(base["Cargo"], base["Responde al Cargo"]))
  children_by_jefe = {}
  for cargo in cargos:
      jefe = jefe_map.get(cargo)
      if jefe and jefe not in ["N/A", "nan", "None", ""] and jefe in cargo_set and jefe != cargo:
          children_by_jefe.setdefault(jefe, []).append(cargo)
  nodes = []
  edges = []
  for cargo in cargos:
      jefe = jefe_map.get(cargo)
      is_root = (not jefe) or (jefe in ["N/A", "nan", "None", ""]) or (jefe not in cargo_set) or (jefe == cargo)
      is_leaf = cargo not in children_by_jefe
      kpis = kpis_map.get(cargo)
      if not isinstance(kpis, list):
          kpis = [str(kpis)] if pd.notna(kpis) else ["N/A"]
      kpis = [str(k).strip() for k in kpis if str(k).strip()]
      if not kpis:
          kpis = ["N/A"]
      content = cargo + "\n" + "\n".join([f"• {k}" for k in kpis])
      if is_root and is_leaf:
          node = StreamlitFlowNode(
              id=cargo,
              pos=(0, 0),
              data={"content": content},
              node_type='input',
              source_position='bottom',
              draggable=False,
          )
      elif is_root:
          node = StreamlitFlowNode(
              id=cargo,
              pos=(0, 0),
              data={"content": content},
              node_type='input',
              source_position='bottom',
              draggable=False,
          )
      elif is_leaf:
          node = StreamlitFlowNode(
              id=cargo,
              pos=(0, 0),
              data={"content": content},
              node_type='output',
              target_position='top',
              draggable=False,
          )
      else:
          node = StreamlitFlowNode(
              id=cargo,
              pos=(0, 0),
              data={"content": content},
              node_type='default',
              source_position='bottom',
              target_position='top',
              draggable=False,
          )
      nodes.append(node)
  for cargo in cargos:
      jefe = jefe_map.get(cargo)
      if jefe and jefe not in ["N/A", "nan", "None", ""] and jefe in cargo_set and jefe != cargo:
          edges.append(StreamlitFlowEdge(f"{jefe}->{cargo}", jefe, cargo, animated=False))
  if 'flow_state' not in st.session_state:
      st.session_state['flow_state'] = StreamlitFlowState(nodes, edges)
  else:
      st.session_state['flow_state'].nodes = nodes
      st.session_state['flow_state'].edges = edges
  streamlit_flow(
      'org_chart',
      st.session_state['flow_state'],
      layout=TreeLayout(direction='down'),
      fit_view=True,
  )

def renderizarOrganigramaV2(dfr):
  columnas = {"Cargo", "Responde al Cargo", "KPIs"}
  if not columnas.issubset(set(dfr.columns)):
      st.warning("El DataFrame no contiene las columnas requeridas: 'Cargo', 'Responde al Cargo', 'KPIs'.")
      return

  base = dfr[["Cargo", "Responde al Cargo", "KPIs"]].drop_duplicates(subset="Cargo", keep="first").copy()
  base["Cargo"] = base["Cargo"].astype(str).str.strip()
  base["Responde al Cargo"] = base["Responde al Cargo"].astype(str).str.strip()

  cargos = base["Cargo"].tolist()
  cargo_set = set(cargos)
  kpis_map = dict(zip(base["Cargo"], base["KPIs"]))
  jefe_map = dict(zip(base["Cargo"], base["Responde al Cargo"]))

  # hijos por jefe
  children_by_jefe = {}
  for cargo in cargos:
    jefe = jefe_map.get(cargo)
    if jefe and jefe not in ["N/A", "nan", "None", ""] and jefe in cargo_set and jefe != cargo:
      children_by_jefe.setdefault(jefe, []).append(cargo)

  nodes = []
  edges = []

  def kpi_node_id(c):
    return f"{c}__KPIs"

  for cargo in cargos:
    jefe = jefe_map.get(cargo)
    is_root = (not jefe) or (jefe in ["N/A", "nan", "None", ""]) or (jefe not in cargo_set) or (jefe == cargo)
    has_children = cargo in children_by_jefe

    # Normalizar KPIs
    kpis = kpis_map.get(cargo)
    if not isinstance(kpis, list):
      kpis = [str(kpis)] if pd.notna(kpis) else ["N/A"]
    kpis = [str(k).strip() for k in kpis if str(k).strip()]
    if not kpis:
      kpis = ["N/A"]

    # Nodo del cargo
    if is_root:
      cargo_node = StreamlitFlowNode(
        id=cargo,
        pos=(0, 0),
        data={"content": cargo},
        node_type='input',
        source_position='bottom',
        draggable=False,
      )
    else:
      cargo_node = StreamlitFlowNode(
        id=cargo,
        pos=(0, 0),
        data={"content": cargo},
        node_type='default',
        source_position='bottom',
        target_position='top',
        draggable=False,
      )
    nodes.append(cargo_node)

    # Nodo de KPIs (intermedio)
    kpi_content = "\n".join([f"- {k}" for k in kpis])
    if has_children:
      kpi_node = StreamlitFlowNode(
        id=kpi_node_id(cargo),
        pos=(0, 0),
        data={"content": kpi_content},
        node_type='default',
        source_position='bottom',
        target_position='top',
        draggable=False,
      )
    else:
      kpi_node = StreamlitFlowNode(
        id=kpi_node_id(cargo),
        pos=(0, 0),
        data={"content": kpi_content},
        node_type='output',
        target_position='top',
        draggable=False,
      )
    nodes.append(kpi_node)

    # Conexión cargo -> KPIs
    edges.append(StreamlitFlowEdge(f"{cargo}=>{kpi_node_id(cargo)}", cargo, kpi_node_id(cargo), animated=False))

  # Conexiones KPIs del jefe -> cargo subordinado
  for jefe, hijos in children_by_jefe.items():
    for sub in hijos:
      edges.append(StreamlitFlowEdge(f"{kpi_node_id(jefe)}=>{sub}", kpi_node_id(jefe), sub, animated=False))

  if 'flow_state' not in st.session_state:
    st.session_state['flow_state'] = StreamlitFlowState(nodes, edges)
  else:
    st.session_state['flow_state'].nodes = nodes
    st.session_state['flow_state'].edges = edges

  # Render centrado ocupando ~90% del ancho
  _left, _center, _right = st.columns([0.05, 0.9, 0.05])
  with _center:
    streamlit_flow('org_chart', st.session_state['flow_state'], layout=TreeLayout(direction='down'), fit_view=True)

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

      updated = validarJefe_v2(st.session_state['df'])
      if updated is not None:
        st.session_state['df'] = updated
        
      
      st.dataframe(st.session_state['df'], use_container_width=True)
      # Render solo cuando no haya cargos sin nivel ni sin jefe (excluye CEO)
      placeholders = {"N/A", "nan", "", "None"}
      # detectar nombre real de columna de nivel jerárquico
      def _find_nivel_col(cols):
        def norm(s):
          return ''.join(ch for ch in str(s).lower() if ch.isalpha())
        for c in cols:
          n = norm(c)
          if 'nivel' in n and 'jer' in n:
            return c
        return None
      nivel_col = _find_nivel_col(st.session_state['df'].columns)
      cargos_sin_nivel = []
      if nivel_col is not None:
        cargos_sin_nivel = (
          st.session_state['df']
            .loc[st.session_state['df'][nivel_col].astype(str).str.strip().isin(placeholders), 'Cargo']
            .drop_duplicates().tolist()
        )
      cargos_sin_jefe = (
        st.session_state['df']
          .loc[st.session_state['df']["Responde al Cargo"].astype(str).str.strip().isin(placeholders), 'Cargo']
          .drop_duplicates().tolist()
      )
      ceo_cargos = []
      if nivel_col is not None:
        s = st.session_state['df'][nivel_col].astype(str).str.strip().str.lower()
        ceo_mask = s.eq("1") | s.str.startswith("1") | s.str.contains("ceo")
        ceo_cargos = st.session_state['df'].loc[ceo_mask, 'Cargo'].drop_duplicates().tolist()
      if not ceo_cargos:
        ceo_cargos = (
          st.session_state['df']
            .loc[st.session_state['df']["Cargo"].astype(str).str.strip().str.lower().str.contains("ceo"), 'Cargo']
            .drop_duplicates().tolist()
        )
      cargos_sin_jefe = [c for c in cargos_sin_jefe if c not in ceo_cargos]

      if (len(cargos_sin_nivel) == 0) and (len(cargos_sin_jefe) == 0):
        st.subheader("Organigrama")
        renderizarOrganigramaV2(st.session_state['df'])
      else:
        pendientes = []
        if len(cargos_sin_nivel) > 0:
          pendientes.append(f"{len(cargos_sin_nivel)} cargos sin nivel")
        if len(cargos_sin_jefe) > 0:
          pendientes.append(f"{len(cargos_sin_jefe)} cargos sin jefe")
        if pendientes:
          st.info("Organigrama pendiente: " + ", ".join(pendientes))
    except Exception as e:
      st.error("Ha ocurrido un error por favor verifica que el archivo tenga las columnas necesarias: 'Cargo', 'Responde al Cargo', 'Nivel Jerárquico' y 'KPI's'.")
