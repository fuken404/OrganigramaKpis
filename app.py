import os
import re
import streamlit as st
import sqlite3  as sql
import pandas as pd
import time
from contextlib import closing
import json
from io import BytesIO
from collections import defaultdict

st.set_page_config(page_title="Calibración de KPIs", layout="wide", page_icon="⚙️")

try:
    from langchain_openai import ChatOpenAI
    from langchain.schema import SystemMessage, HumanMessage
except Exception:
    ChatOpenAI = None
    SystemMessage = HumanMessage = None

st.title("⚙️ Calibración de KPIs")
st.markdown(
    """
    <style>
    .block-container {
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        max-width: 100% !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Crear DB
DB_NAME = "organigrama_kpis.db"

OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY")
llm = None
if OPENAI_API_KEY and ChatOpenAI is not None:
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.15, openai_api_key=OPENAI_API_KEY)
    except Exception:
        llm = None

MARIA_SYSTEM_PROMPT = (
    "Eres MARIA, consultora senior en diseño de KPIs y gestión de desempeño. "
    "Tu estilo es ejecutivo, conciso y accionable. Cuando generes nuevas ideas de KPI, "
    "valida que estén alineadas con la estrategia dada, evita duplicar KPIs existentes "
    "y mantén pesos razonables (la suma no debe exceder 100% si se aplican todos). "
    "Siempre responde ÚNICAMENTE con un JSON que contenga dos claves: "
    "'mensaje' (texto breve con tu consejo) y 'kpis' (lista de objetos con "
    "'nombre', 'peso', 'indicador_estrategico' y 'formula', donde 'formula' describe "
    "cómo se calcula el KPI). No incluyas texto fuera del JSON."
)

def normalizar_texto(valor):
    """Devuelve un string sin espacios o vacío si el valor es nulo/NaN."""
    if valor is None:
        return ""
    try:
        if pd.isna(valor):  
            return ""
    except Exception:
        pass
    return str(valor).strip()

def buscar_columna_por_nombre(columnas, nombre_objetivo):
    """Devuelve el nombre real de la columna que coincide (ignorando mayúsculas/espacios)."""
    objetivo = nombre_objetivo.strip().lower()
    for col in columnas:
        if col.strip().lower() == objetivo:
            return col
    return None

def reset_database_file():
    """Elimina la base de datos y archivos auxiliares para reiniciar el flujo."""
    for suffix in ("", "-wal", "-shm"):
        path = f"{DB_NAME}{suffix}"
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

def reiniciar_estado_por_upload():
    """Reinicia la BD y los indicadores de sesión al cargar un nuevo archivo."""
    reset_database_file()
    init_database()
    # Limpiar banderas principales para volver a correr el flujo desde cero
    for key in [
        "df_fuente",
        "archivo_procesado",
        "niveles_guardados",
        "asignaciones_niveles",
        "guardar_niveles_clicked",
        "jefes_guardados",
        "asignaciones_jefes",
        "guardar_jefes_clicked",
        "indicadores_asignados",
        "nodo_seleccionado",
        "filtro_cargo",
        "selectbox_key_counter",
    ]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.df_fuente = None
    st.session_state.archivo_procesado = False

def obtener_contexto_cargo_por_nombre(nombre_cargo: str) -> dict:
    """Extrae datos descriptivos del cargo desde el archivo cargado."""
    df_fuente = st.session_state.get("df_fuente")
    if df_fuente is None or not nombre_cargo:
        return {}
    columnas = list(df_fuente.columns)
    col_cargo = buscar_columna_por_nombre(columnas, "Cargo")
    if not col_cargo:
        return {}
    clean_target = normalizar_texto(nombre_cargo).lower()
    subset = df_fuente[df_fuente[col_cargo].astype(str).str.strip().str.lower() == clean_target]
    if subset.empty:
        return {}

    contexto = {}
    for etiqueta in ["Área", "Departamento", "Responde al Cargo", "Nivel Jerárquico"]:
        col = buscar_columna_por_nombre(columnas, etiqueta)
        if col and col in subset:
            valores = subset[col].dropna().astype(str).str.strip()
            if not valores.empty:
                contexto[etiqueta] = valores.iloc[0]
    return contexto

def _extraer_json_de_respuesta(texto: str):
    """Intenta extraer un bloque JSON de la respuesta del modelo."""
    if not texto:
        return None
    cleaned = texto.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9]*", "", cleaned)
        cleaned = cleaned.rsplit("```", 1)[0]
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        cleaned = match.group(0)
    try:
        return json.loads(cleaned)
    except Exception:
        return None

def generar_kpis_con_maria(nombre_cargo, prompt_usuario, kpis_actuales, indicadores_disponibles, max_kpis=3):
    """Invoca al agente MARIA para sugerir KPIs."""
    if llm is None or SystemMessage is None or HumanMessage is None:
        return ("Configura tu OPENAI_API_KEY en st.secrets para habilitar a MARIA.", None)

    contexto_cargo = obtener_contexto_cargo_por_nombre(nombre_cargo)
    area = contexto_cargo.get("Área", "Área no especificada")
    depto = contexto_cargo.get("Departamento", "Departamento no especificado")
    nivel = contexto_cargo.get("Nivel Jerárquico", "Nivel no especificado")
    jefe = contexto_cargo.get("Responde al Cargo", "No registrado")

    if kpis_actuales:
        resumen_kpis = "\n".join(
            f"- {k['nombre']} (peso {k.get('peso') or 's/d'} / indicador: {k.get('indicador') or 'Sin indicador'})"
            for k in kpis_actuales
        )
    else:
        resumen_kpis = "- El cargo aún no tiene KPIs guardados."

    indicadores_texto = ", ".join(indicadores_disponibles) if indicadores_disponibles else "Sin indicadores definidos"

    user_payload = (
        f"Cargo: {nombre_cargo}\n"
        f"Área: {area}\n"
        f"Departamento: {depto}\n"
        f"Nivel: {nivel}\n"
        f"Responde a: {jefe}\n\n"
        f"KPIs actuales:\n{resumen_kpis}\n\n"
        f"Indicadores estratégicos disponibles: {indicadores_texto}\n\n"
        f"Solicitud del usuario: {prompt_usuario}\n\n"
        f"Genera hasta {max_kpis} KPI(s) nuevos o refinados alineados al contexto, "
        "con nombre claro, un peso sugerido, la fórmula con la que se calcularía y "
        "el indicador estratégico al que se conectan. "
        "Siempre responde en JSON conforme a las instrucciones del sistema."
    )

    respuesta = llm([SystemMessage(content=MARIA_SYSTEM_PROMPT), HumanMessage(content=user_payload)])
    contenido = getattr(respuesta, "content", str(respuesta))

    data = _extraer_json_de_respuesta(contenido)
    mensaje = contenido.strip()
    tabla = None

    if isinstance(data, dict):
        mensaje = data.get("mensaje", mensaje)
        filas = data.get("kpis", [])
        if isinstance(filas, list) and filas:
            tabla = pd.DataFrame(filas)
            if not tabla.empty:
                tabla = tabla.rename(
                    columns={
                        "nombre": "Nombre KPI",
                        "peso": "Peso sugerido",
                        "indicador_estrategico": "Indicador estratégico",
                        "formula": "Fórmula",
                    }
                )
                for columna in ["Nombre KPI", "Fórmula", "Peso sugerido", "Indicador estratégico"]:
                    if columna not in tabla.columns:
                        tabla[columna] = ""
                tabla = tabla[["Nombre KPI", "Fórmula", "Peso sugerido", "Indicador estratégico"]]
    return mensaje, tabla

def init_database():
    """Inicializa la base de datos SOLO si no existe"""
    with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        
        cursor = conn.cursor()
        
        # Verificar si las tablas ya existen
        cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='Cargos'
        """)
        
        if cursor.fetchone() is None:
            # Las tablas NO existen, crearlas
            st.info("🔧 Creando estructura de base de datos...")
            
            cursor.executescript("""
            DROP TABLE IF EXISTS CargosKpis;
            DROP TABLE IF EXISTS Kpis;
            DROP TABLE IF EXISTS IndicadoresEstrategicos;
            DROP TABLE IF EXISTS Cargos;

            CREATE TABLE IF NOT EXISTS Cargos (
                id_cargo INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_cargo TEXT UNIQUE NOT NULL,
                nivel_cargo TEXT,
                fk_jefe INTEGER,
                CONSTRAINT fk_jefe_fk FOREIGN KEY (fk_jefe)
                    REFERENCES Cargos(id_cargo)
                    ON UPDATE CASCADE
                    ON DELETE SET NULL,
                CONSTRAINT no_self_ref CHECK (fk_jefe IS NULL OR fk_jefe <> id_cargo)
            );

            CREATE TABLE IF NOT EXISTS IndicadoresEstrategicos (
                id_kpiEs INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_kpiEs TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS Kpis (
                id_kpi INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_kpi TEXT UNIQUE NOT NULL,
                formula_kpi TEXT,
                fk_kpiEs INTEGER,
                CONSTRAINT fk_kpiEs FOREIGN KEY (fk_kpiEs)
                    REFERENCES IndicadoresEstrategicos(id_kpiEs)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS CargosKpis (
                id_cargoKpi INTEGER PRIMARY KEY AUTOINCREMENT,
                fk_cargo INTEGER,
                fk_kpi INTEGER,
                peso_kpi INTEGER,
                CONSTRAINT fk_cargo FOREIGN KEY (fk_cargo)
                    REFERENCES Cargos(id_cargo)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE,
                CONSTRAINT fk_kpi FOREIGN KEY (fk_kpi)
                    REFERENCES Kpis(id_kpi)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE,
                UNIQUE(fk_cargo, fk_kpi)
            );
            """)
            conn.commit()
            return True  # Base de datos recién creada
        else:
            # Las tablas ya existen
            return False  # Base de datos ya existía

def insert_data(df):
    """Inserta los datos desde el DataFrame SOLO si es necesario"""
    with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        
        # Verificar si ya hay datos
        cursor.execute("SELECT COUNT(*) FROM Cargos")
        count = cursor.fetchone()[0]
        
        if count > 0:
            st.info(f"ℹ️ La base de datos ya contiene {count} cargos. Omitiendo inserción de datos.")
            return
        
        st.info("📥 Insertando datos en la base de datos...")
        
        # Preparar DataFrames
        df_cargos = pd.DataFrame({
            "Cargo": pd.concat([df["Cargo"], df["Responde al Cargo"]]).unique(),
        })
        
        tmp = df[["Cargo", "Nivel Jerárquico"]].drop_duplicates(subset="Cargo", keep="first")
        df_cargos = df_cargos.merge(tmp, on="Cargo", how="left")
        df_cargos["Nivel Jerárquico"] = df_cargos["Nivel Jerárquico"].fillna("N/A").astype(str)
        
        df_kpis = pd.DataFrame({
            "Kpis": df["Indicador"],
            "Fórmula": df["Fórmula"]
        })
        
        df_kpisEs = pd.DataFrame({
            "IndicadoresEstrategicos": df["Alineado (archivo)"].unique()
        })
        
        # Insertar datos base
        for _, row in df_cargos.iterrows():
            cursor.execute("""
            INSERT OR IGNORE INTO Cargos (nombre_cargo, nivel_cargo)
            VALUES (?, ?);
            """, (row["Cargo"], row["Nivel Jerárquico"]))
        
        for _, row in df_kpisEs.iterrows():
            cursor.execute("""
            INSERT OR IGNORE INTO IndicadoresEstrategicos (nombre_kpiEs)
            VALUES (?);
            """, (row["IndicadoresEstrategicos"],))
        
        for _, row in df_kpis.iterrows():
            cursor.execute("""
            INSERT OR IGNORE INTO Kpis (nombre_kpi, formula_kpi)
            VALUES (?, ?);
            """, (row["Kpis"], row["Fórmula"]))
        
        conn.commit()
        
        #Insertar fks
        # Actualizar FK
        for _, row in df.iterrows():
            if pd.notna(row["Responde al Cargo"]) and row["Cargo"] != row["Responde al Cargo"]:
                try:
                    cursor.execute("""
                    UPDATE Cargos
                    SET fk_jefe = (SELECT id_cargo FROM Cargos WHERE nombre_cargo = ?)
                    WHERE nombre_cargo = ?;
                    """, (row["Responde al Cargo"], row["Cargo"]))
                except sql.IntegrityError:
                    pass
        
        conn.commit()
        
        for _, row in df.iterrows():
            if pd.notna(row["Alineado (archivo)"]) and pd.notna(row["Indicador"]):
                cursor.execute("""
                UPDATE Kpis
                SET fk_kpiEs = (SELECT id_kpiEs FROM IndicadoresEstrategicos WHERE nombre_kpiEs = ?)
                WHERE nombre_kpi = ?;
                """, (row["Alineado (archivo)"], row["Indicador"]))
        conn.commit()
        
        for _, row in df.iterrows():
            if pd.notna(row["Cargo"]) and pd.notna(row["Indicador"]):
            # Obtener peso si existe en tu Excel
                peso = row.get("Peso", None)  # Ajusta el nombre de columna según tu Excel

                cursor.execute("""
                INSERT OR IGNORE INTO CargosKpis (fk_cargo, fk_kpi, peso_kpi)
                SELECT 
                    (SELECT id_cargo FROM Cargos WHERE nombre_cargo = ?),
                    (SELECT id_kpi FROM Kpis WHERE nombre_kpi = ?),
                    ?;
                """, (row["Cargo"], row["Indicador"], peso))
        conn.commit()
        st.success("✅ Datos insertados correctamente")

def construir_arbol_organizacional():
    """Construye el árbol jerárquico de la organización desde la BD"""
    with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
        cursor = conn.cursor()
        
        # Obtener todos los cargos con sus jefes
        cursor.execute("""
        SELECT id_cargo, nombre_cargo, fk_jefe, nivel_cargo
        FROM Cargos
        ORDER BY id_cargo
        """)
        cargos = cursor.fetchall()
    
    # Crear diccionario de cargos por ID
    cargo_map = {}
    for id_cargo, nombre_cargo, fk_jefe, nivel_cargo in cargos:
        cargo_map[id_cargo] = {
            "name": nombre_cargo,
            "id": id_cargo,
            "fk_jefe": fk_jefe,
            "nivel": nivel_cargo,
            "children": []
        }
    
    # Encontrar la raíz (CEO) y construir el árbol
    root = None
    orfanos = []  # Cargos sin jefe que no son CEO
    
    for id_cargo, node in cargo_map.items():
        if node["fk_jefe"] is None:
            # Si no tiene jefe
            if root is None:
                root = node  # El primero sin jefe es la raíz
            else:
                orfanos.append(node)  # Los demás son huérfanos
        else:
            # Agregar como hijo al jefe
            if node["fk_jefe"] in cargo_map:
                cargo_map[node["fk_jefe"]]["children"].append(node)
            else:
                # Si el jefe no existe, agregar como huérfano
                orfanos.append(node)
    
    # Si hay huérfanos, agregarlos como hijos de la raíz
    if root and orfanos:
        root["children"].extend(orfanos)
    
    return root if root else {"name": "Organización", "children": list(cargo_map.values())}

def renderizar_organigrama():
    """Renderiza el organigrama interactivo con streamlit-agraph y permite editar KPIs"""
    
    # Inicializar session state para nodo seleccionado
    if 'nodo_seleccionado' not in st.session_state:
        st.session_state.nodo_seleccionado = None
    
    if 'filtro_cargo' not in st.session_state:
        st.session_state.filtro_cargo = None
    
    # AGREGAR ESTA LÍNEA: Key para forzar reset del selectbox
    if 'selectbox_key_counter' not in st.session_state:
        st.session_state.selectbox_key_counter = 0
    
    try:
        from streamlit_agraph import agraph, Node, Edge, Config
        
        # Construir árbol completo
        arbol_completo = construir_arbol_organizacional()
        
        # Filtro de búsqueda
        st.write("## 🔍 Filtrar Organigrama")
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Obtener todos los cargos que tienen hijos
            with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT DISTINCT c1.id_cargo, c1.nombre_cargo
                FROM Cargos c1
                WHERE EXISTS (
                    SELECT 1 FROM Cargos c2 WHERE c2.fk_jefe = c1.id_cargo
                )
                ORDER BY c1.nombre_cargo
                """)
                cargos_con_hijos = cursor.fetchall()
            
            opciones = ["📊 Ver Todo"] + [f"{nombre}" for _, nombre in cargos_con_hijos]
            
            # CAMBIO AQUÍ: Usar index en lugar de depender solo del key
            index_default = 0  # Siempre empieza en "Ver Todo"
            if st.session_state.filtro_cargo is not None:
                # Buscar el índice del cargo filtrado
                for i, (id_cargo, nombre) in enumerate(cargos_con_hijos, 1):
                    if id_cargo == st.session_state.filtro_cargo:
                        index_default = i
                        break
            
            opcion_seleccionada = st.selectbox(
                "Selecciona un cargo para ver su árbol:",
                opciones,
                index=index_default,  # AGREGAR ESTO
                key=f"filtro_organigrama_{st.session_state.selectbox_key_counter}"  # MODIFICAR ESTO
            )
            
            if opcion_seleccionada == "📊 Ver Todo":
                st.session_state.filtro_cargo = None
                arbol = arbol_completo
            else:
                # Buscar el ID del cargo seleccionado
                cargo_id_filtro = next(
                    (id_cargo for id_cargo, nombre in cargos_con_hijos 
                     if nombre == opcion_seleccionada),
                    None
                )
                if cargo_id_filtro:
                    st.session_state.filtro_cargo = cargo_id_filtro
                    # Buscar ese nodo en el árbol
                    def buscar_subtarbol(nodo, nodo_id_buscar):
                        if nodo["id"] == nodo_id_buscar:
                            return nodo
                        for hijo in nodo.get("children", []):
                            resultado = buscar_subtarbol(hijo, nodo_id_buscar)
                            if resultado:
                                return resultado
                        return None
                    
                    arbol = buscar_subtarbol(arbol_completo, cargo_id_filtro)
                    if not arbol:
                        arbol = arbol_completo
        
        with col2:
            # CAMBIO AQUÍ: Incrementar el counter para forzar recreación del selectbox
            if st.button("🔄 Limpiar", use_container_width=True):
                st.session_state.filtro_cargo = None
                st.session_state.selectbox_key_counter += 1  # AGREGAR ESTO
                st.rerun()
        
        st.divider()
        
        # Cargar KPIs por cargo para mostrarlos como nodos independientes
        kpis_por_cargo = defaultdict(list)
        with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ck.id_cargoKpi,
                       ck.fk_cargo,
                       k.nombre_kpi,
                       ck.peso_kpi,
                       COALESCE(k.formula_kpi, ''),
                       COALESCE(ies.nombre_kpiEs, '')
                FROM CargosKpis ck
                JOIN Kpis k ON ck.fk_kpi = k.id_kpi
                LEFT JOIN IndicadoresEstrategicos ies ON k.fk_kpiEs = ies.id_kpiEs
                ORDER BY ck.fk_cargo, k.nombre_kpi
                """
            )
            for kpi_id, fk_cargo, nombre, peso, formula, indicador in cursor.fetchall():
                descripcion = normalizar_texto(formula) or normalizar_texto(indicador) or "Sin descripción"
                try:
                    peso_val = int(peso) if peso is not None else 0
                except (TypeError, ValueError):
                    peso_val = 0
                kpis_por_cargo[fk_cargo].append(
                    {
                        "id": kpi_id,
                        "nombre": normalizar_texto(nombre),
                        "peso": peso_val,
                        "descripcion": descripcion,
                    }
                )

        # Calcular posiciones manuales para lograr una distribución uniforme
        H_SPACING = 280
        LEVEL_HEIGHT = 220
        SUMMARY_OFFSET = 110

        posiciones = {}
        contador_hojas = {"value": 0}

        def obtener_id_nodo(nodo_obj):
            return nodo_obj.get("id") if nodo_obj.get("id") is not None else nodo_obj["name"]

        def asignar_posiciones(nodo, depth=0):
            hijos = nodo.get("children", [])
            if not hijos:
                contador_hojas["value"] += 1
                centro = contador_hojas["value"]
            else:
                centros_hijos = [asignar_posiciones(hijo, depth + 1) for hijo in hijos]
                centro = sum(centros_hijos) / len(centros_hijos)

            nodo_key = obtener_id_nodo(nodo)
            cargo_node_id = f"cargo_{nodo_key}"
            x_pos = centro * H_SPACING
            posiciones[cargo_node_id] = (x_pos, depth * LEVEL_HEIGHT)

            summary_id = f"{cargo_node_id}_kpis"
            posiciones[summary_id] = (x_pos, depth * LEVEL_HEIGHT + SUMMARY_OFFSET)

            return centro

        asignar_posiciones(arbol)

        # Ajustar para centrar el organigrama en pantalla
        min_x = min(pos[0] for pos in posiciones.values())
        shift = -(min_x - H_SPACING)
        for key in list(posiciones.keys()):
            x, y = posiciones[key]
            posiciones[key] = (x + shift, y)
        max_x = max(pos[0] for pos in posiciones.values())
        canvas_width = int(max_x + H_SPACING)

        # Crear nodos y edges desde el árbol filtrado
        nodos = []
        edges = []

        def agregar_nodos_y_edges(nodo):
            cargo_id_real = obtener_id_nodo(nodo)
            nodo_id = f"cargo_{cargo_id_real}"
            x_cargo, y_cargo = posiciones.get(nodo_id, (0, 0))
            nodos.append(
                Node(
                    id=nodo_id,
                    label=nodo["name"],
                    size=40,
                    title=nodo["name"],
                    shape="box",
                    color="#d7e3fc",
                    x=x_cargo,
                    y=y_cargo,
                    fixed=True,
                    physics=False,
                )
            )

            kpis_del_cargo = kpis_por_cargo.get(nodo.get("id"), [])
            summary_id = f"{nodo_id}_kpis"
            x_summary, y_summary = posiciones.get(summary_id, (x_cargo, y_cargo + SUMMARY_OFFSET))
            if kpis_del_cargo:
                resumen_html = "\n".join(
                    f"- {kpi['nombre']}: {kpi['peso']}%" for kpi in kpis_del_cargo
                )
                resumen_title = "\n".join(
                    f"{kpi['nombre']} · Peso: {kpi['peso']}% · {kpi['descripcion']}"
                    for kpi in kpis_del_cargo
                )
            else:
                resumen_html = "Sin KPIs registrados"
                resumen_title = "Aún no hay KPIs asignados a este cargo."

            nodos.append(
                Node(
                    id=summary_id,
                    label=resumen_html,
                    size=45,
                    shape="box",
                    color="#b5e48c",
                    title=resumen_title,
                    font={"multi": "html", "size": 14},
                    x=x_summary,
                    y=y_summary,
                    fixed=True,
                    physics=False,
                )
            )
            edges.append(Edge(source=nodo_id, target=summary_id))

            hijos = nodo.get("children", [])
            for idx, hijo in enumerate(hijos):
                child_node_id = f"cargo_{obtener_id_nodo(hijo)}"
                child_x, _ = posiciones.get(child_node_id, (x_summary, y_summary + LEVEL_HEIGHT))
                connector_id = f"{summary_id}_connector_{idx}"
                nodos.append(
                    Node(
                        id=connector_id,
                        label="",
                        size=5,
                        shape="dot",
                        color="rgba(0,0,0,0)",
                        x=child_x,
                        y=y_summary,
                        fixed=True,
                        physics=False,
                    )
                )
                edges.append(Edge(source=summary_id, target=connector_id))
                edges.append(Edge(source=connector_id, target=child_node_id))
                agregar_nodos_y_edges(hijo)

        agregar_nodos_y_edges(arbol)
        
        # Configuración del grafo
        config = Config(
            width=canvas_width,
            height=650,
            directed=True,
            physics=False,
            hierarchical=False,
            edges={"smooth": {"type": "straightCross", "roundness": 0}},
            fit=True,
            suppress_toolbar=True,
        )
        
        # Renderizar grafo y capturar click
        selected_node = agraph(
            nodes=nodos,
            edges=edges,
            config=config
        )
        
        # Si se hace clic en un nodo, guardar en session state
        if selected_node and selected_node.startswith("cargo_"):
            try:
                cargo_id = int(selected_node.replace("cargo_", ""))

                with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT nombre_cargo FROM Cargos WHERE id_cargo = ?
                        """,
                        (cargo_id,),
                    )
                    resultado = cursor.fetchone()

                    if resultado:
                        nombre_cargo = resultado[0]
                        st.session_state.nodo_seleccionado = {
                            "cargo_id": cargo_id,
                            "nombre_cargo": nombre_cargo,
                        }
            except Exception as e:
                st.error(f"❌ Error al seleccionar nodo: {str(e)}")
    
    except ImportError:
        st.warning("⚠️ Para visualizar el organigrama, instala: pip install streamlit-agraph")
    
    # Mostrar panel si hay nodo seleccionado
    if st.session_state.nodo_seleccionado:
        cargo_id = st.session_state.nodo_seleccionado["cargo_id"]
        nombre_cargo = st.session_state.nodo_seleccionado["nombre_cargo"]
        mostrar_panel_kpis(cargo_id, nombre_cargo)

def mostrar_panel_kpis(cargo_id, nombre_cargo):
    """Muestra panel editable de KPIs para un cargo en el sidebar"""
    
    with st.sidebar:
        st.markdown(f"### 📊 KPIs de {nombre_cargo}")
        
        # Botón cerrar panel
        if st.button("✕ Cerrar Panel", key=f"close_panel_{cargo_id}"):
            st.session_state.nodo_seleccionado = None
            st.rerun()
        
        st.divider()
        
        with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
            cursor = conn.cursor()
            
            # Obtener KPIs asignados al cargo
            cursor.execute("""
            SELECT ck.id_cargoKpi,
                   k.nombre_kpi,
                   k.formula_kpi,
                   ck.peso_kpi,
                   k.id_kpi,
                   ies.nombre_kpiEs,
                   k.fk_kpiEs
            FROM CargosKpis ck
            JOIN Kpis k ON ck.fk_kpi = k.id_kpi
            LEFT JOIN IndicadoresEstrategicos ies ON k.fk_kpiEs = ies.id_kpiEs
            WHERE ck.fk_cargo = ?
            ORDER BY k.nombre_kpi
            """, (cargo_id,))
            kpis_cargo = cursor.fetchall()
            kpis_para_contexto = [
                {
                    "id_cargoKpi": id_cargoKpi,
                    "nombre": nombre_kpi,
                    "formula": formula_kpi,
                    "peso": peso_kpi,
                    "id_kpi": id_kpi,
                    "indicador": indicador_nombre,
                    "fk_kpiEs": fk_indicador
                }
                for id_cargoKpi, nombre_kpi, formula_kpi, peso_kpi, id_kpi, indicador_nombre, fk_indicador in kpis_cargo
            ]
            
            # Obtener indicadores estrategicos disponibles
            cursor.execute("""
            SELECT id_kpiEs, nombre_kpiEs
            FROM IndicadoresEstrategicos
            ORDER BY nombre_kpiEs
            """)
            indicadores_estrategicos = cursor.fetchall()
        
        indicadores_opciones = ["-- Sin indicador --"] + [nombre for _, nombre in indicadores_estrategicos]
        indicadores_dict = {"-- Sin indicador --": None}
        indicadores_dict.update({nombre: id_kpiEs for id_kpiEs, nombre in indicadores_estrategicos})

        # Crear DataFrame editable con opcion de eliminar
        if kpis_para_contexto:
            datos = []
            for item in kpis_para_contexto:
                indicador_display = item["indicador"] if item["indicador"] else "-- Sin indicador --"
                datos.append({
                    "KPI": item["nombre"],
                    "Alineado a": indicador_display,
                    "Fórmula": normalizar_texto(item.get("formula")),
                    "Peso (%)": int(item["peso"]) if item["peso"] else 0,
                    "Eliminar": False,
                    "id_cargoKpi": item["id_cargoKpi"],
                    "id_kpi": item["id_kpi"],
                    "fk_kpiEs": item["fk_kpiEs"],
                    "es_total": False,
                })

            df_kpis = pd.DataFrame(datos)

            st.markdown("**KPIs Asignados:**")
            st.caption(f"KPIs cargados: {len(df_kpis)}")

            df_editado = st.data_editor(
                df_kpis,
                use_container_width=True,
                height=min(400, 35 * (len(df_kpis) + 1)),
                key=f"editor_kpis_{cargo_id}",
                hide_index=True,
                column_order=[
                    "KPI",
                    "Fórmula",
                    "Alineado a",
                    "Peso (%)",
                    "Eliminar",
                ],
                column_config={
                    "Alineado a": st.column_config.SelectboxColumn(
                        "Alineado a",
                        options=indicadores_opciones,
                        default="-- Sin indicador --"
                    ),
                    "Fórmula": st.column_config.TextColumn(
                        "Fórmula",
                        width="medium",
                        help="Describe cómo se calcula este KPI."
                    ),
                    # Ocultar columnas de control que no deben ser visibles
                    "id_cargoKpi": None,
                    "id_kpi": None,
                    "fk_kpiEs": None,
                    "es_total": None,
                },
            )

            # Crear y mostrar la fila de total por separado (no editable)
            pesos = pd.to_numeric(df_editado["Peso (%)"], errors="coerce").fillna(0)
            total_peso = float(pesos.sum())
            
            # Usar st.columns para crear una fila de total sin encabezados
            # Esto es más robusto que usar CSS.
            st.markdown(
                """<hr style="margin-top: -0.5rem; margin-bottom: 0.5rem;">""",
                unsafe_allow_html=True,
            )
            total_cols = st.columns([0.28, 0.23, 0.23, 0.16, 0.1])
            with total_cols[0]:
                st.markdown("**Total de los Pesos**")
            with total_cols[3]:
                st.markdown(f"**{total_peso:.0f}%**")
            

            # La validación y el botón de guardar ahora usan el df_editado directamente
            df_editable = df_editado
            pesos_validos = abs(total_peso - 100.0) < 1e-6

            st.caption(f"Total de pesos asignados: {total_peso:.0f}% (debe sumar 100%)")
            if not pesos_validos:
                st.warning("Ajusta los pesos hasta alcanzar exactamente el 100% para poder guardar.")

            # Boton para guardar cambios
            if st.button(
                "Guardar Cambios",
                key=f"save_kpis_{cargo_id}",
                use_container_width=True,
                disabled=not pesos_validos,
            ):
                try:
                    cambios = 0

                    with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
                        conn.execute("PRAGMA foreign_keys = ON")
                        cursor = conn.cursor()

                        base_por_id = {
                            int(row["id_cargoKpi"]): row
                            for _, row in df_kpis.iterrows()
                            if row["id_cargoKpi"] is not None
                        }

                        # Recorrer cada fila del DataFrame editado
                        for _, row in df_editable.iterrows():
                            id_cargoKpi = int(row["id_cargoKpi"])
                            nuevo_peso = int(row["Peso (%)"])
                            marcar_eliminar = bool(row["Eliminar"])
                            indicador_seleccionado = row["Alineado a"]
                            nuevo_fk = indicadores_dict.get(indicador_seleccionado)
                            formula_actualizada = normalizar_texto(row["Fórmula"])

                            base_row = base_por_id.get(id_cargoKpi, {})
                            peso_original = int(base_row.get("Peso (%)", 0))
                            indicador_original_fk = base_row.get("fk_kpiEs")
                            formula_original = normalizar_texto(base_row.get("Fórmula"))

                            if marcar_eliminar:
                                cursor.execute("""
                                DELETE FROM CargosKpis
                                WHERE id_cargoKpi = ?
                                """, (id_cargoKpi,))
                                cambios += cursor.rowcount
                            elif nuevo_peso != peso_original:
                                cursor.execute("""
                                UPDATE CargosKpis
                                SET peso_kpi = ?
                                WHERE id_cargoKpi = ?
                                """, (nuevo_peso, id_cargoKpi))
                                cambios += cursor.rowcount

                            if nuevo_fk != indicador_original_fk:
                                cursor.execute("""
                                UPDATE Kpis
                                SET fk_kpiEs = ?
                                WHERE id_kpi = ?
                                """, (nuevo_fk, int(base_row.get("id_kpi"))))
                                cambios += cursor.rowcount

                            if formula_actualizada != formula_original:
                                cursor.execute("""
                                UPDATE Kpis
                                SET formula_kpi = ?
                                WHERE id_kpi = ?
                                """, (formula_actualizada or None, int(base_row.get("id_kpi"))))
                                cambios += cursor.rowcount

                        conn.commit()

                    st.success(f"{cambios} cambio(s) guardado(s)")
                    time.sleep(1)
                    st.rerun()

                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())

        else:
            st.info("Este cargo aún no tiene KPIs asignados. Puedes crearlos a continuación.")

        st.divider()
        st.markdown("### 🤖 MARIA · Agente IA de KPIs")

        history_key = f"maria_history_{cargo_id}"
        if history_key not in st.session_state:
            st.session_state[history_key] = [
                {
                    "role": "assistant",
                    "content": f"Hola, soy MARIA. Dime qué KPIs necesitas para {nombre_cargo} y te sugeriré opciones alineadas a la estrategia.",
                }
            ]

        for msg in st.session_state[history_key]:
            with st.chat_message("assistant" if msg["role"] == "assistant" else "user"):
                st.markdown(msg["content"])
                if msg.get("table"):
                    st.table(pd.DataFrame(msg["table"]))

        if llm is None:
            st.info("Configura tu `OPENAI_API_KEY` en `st.secrets` e instala `langchain-openai` para habilitar a MARIA.")
        else:
            prompt_key = f"maria_prompt_{cargo_id}"
            clear_flag_key = f"{prompt_key}_clear"
            if prompt_key not in st.session_state:
                st.session_state[prompt_key] = ""
            if st.session_state.get(clear_flag_key):
                st.session_state[prompt_key] = ""
                st.session_state[clear_flag_key] = False
            user_prompt = st.text_area(
                "Descríbele a MARIA qué necesitas (contexto adicional, metas, dudas, etc.)",
                key=prompt_key,
                height=100,
            )
            cantidad_key = f"maria_kpi_count_{cargo_id}"
            num_kpis = st.slider(
                "Cantidad de KPIs que deseas que MARIA sugiera",
                min_value=1,
                max_value=10,
                value=3,
                key=cantidad_key,
                help="MARIA intentará no superar este número, manteniendo coherencia estratégica."
            )
            if st.button("Preguntar a MARIA", key=f"maria_ask_{cargo_id}", use_container_width=True):
                if not user_prompt.strip():
                    st.warning("Escribe una solicitud para MARIA.")
                else:
                    st.session_state[history_key].append({"role": "user", "content": user_prompt})
                    mensaje, tabla = generar_kpis_con_maria(
                        nombre_cargo,
                        user_prompt,
                        [
                            {
                                "nombre": item["nombre"],
                                "peso": item["peso"],
                                "indicador": item["indicador"],
                            }
                            for item in kpis_para_contexto
                        ],
                        [nombre for _, nombre in indicadores_estrategicos],
                        max_kpis=num_kpis,
                    )
                    registro = {"role": "assistant", "content": mensaje}
                    if tabla is not None and not tabla.empty:
                        registro["table"] = tabla.to_dict("records")
                    st.session_state[history_key].append(registro)
                    st.session_state[clear_flag_key] = True
                    st.rerun()
        nuevo_nombre = st.text_input(
            "Nombre o Descripcion",
            placeholder="Ej: Tasa de conversion",
            key=f"nuevo_kpi_nombre_{cargo_id}"
        )
        
        nuevo_peso = st.number_input(
            "Peso (%)",
            min_value=0,
            max_value=100,
            value=0,
            key=f"nuevo_kpi_peso_{cargo_id}"
        )
        nuevo_formula = st.text_area(
            "Fórmula (opcional)",
            placeholder="Ej: (Ventas nuevas / Ventas totales)",
            key=f"nuevo_kpi_formula_{cargo_id}",
            height=80,
        )
        
        opciones_indicadores = ["-- Seleccionar --"] + [nombre for _, nombre in indicadores_estrategicos]
        indicador_seleccionado = st.selectbox(
            "Alineado a (Indicador Estrategico)",
            options=opciones_indicadores,
            key=f"indicador_kpi_{cargo_id}"
        )
        
        if st.button("[+] Crear KPI", key=f"add_kpi_{cargo_id}", use_container_width=True):
            nombre_limpio = nuevo_nombre.strip()
            formula_limpia = nuevo_formula.strip()
            if not nombre_limpio:
                st.error("Ingresa un nombre para el KPI")
            elif indicador_seleccionado == "-- Seleccionar --":
                st.error("Selecciona el indicador estrategico al que se alinea")
            else:
                try:
                    with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
                        conn.execute("PRAGMA foreign_keys = ON")
                        cursor = conn.cursor()
                        
                        id_indicador = next(
                            (id_kpiEs for id_kpiEs, nombre in indicadores_estrategicos if nombre == indicador_seleccionado),
                            None
                        )
                        
                        if id_indicador is None:
                            st.error("No se encontro el indicador seleccionado")
                        else:
                            try:
                                cursor.execute("""
                                INSERT INTO Kpis (nombre_kpi, formula_kpi, fk_kpiEs)
                                VALUES (?, ?, ?)
                                """, (nombre_limpio, formula_limpia or None, id_indicador))
                                id_kpi = cursor.lastrowid
                            except sql.IntegrityError:
                                cursor.execute("""
                                SELECT id_kpi FROM Kpis WHERE nombre_kpi = ?
                                """, (nombre_limpio,))
                                registro = cursor.fetchone()
                                if not registro:
                                    raise
                                id_kpi = registro[0]
                                if formula_limpia:
                                    cursor.execute("""
                                    UPDATE Kpis
                                    SET formula_kpi = ?
                                    WHERE id_kpi = ?
                                    """, (formula_limpia, id_kpi))
                            
                            cursor.execute("""
                            INSERT INTO CargosKpis (fk_cargo, fk_kpi, peso_kpi)
                            VALUES (?, ?, ?)
                            """, (cargo_id, id_kpi, int(nuevo_peso)))
                            
                            conn.commit()
                    
                    st.success("KPI creado y asignado!")
                    time.sleep(1)
                    st.rerun()
                
                except Exception as e:
                    st.error(f"Error al crear KPI: {str(e)}")

def sincronizar_nuevos_kpis(df):
    """Inserta en la BD los KPIs del archivo que aún no existen."""
    columnas_fuente = list(df.columns)
    col_indicador = buscar_columna_por_nombre(columnas_fuente, "Indicador")

    if not col_indicador:
        st.warning("No se encontró la columna 'Indicador' en el archivo. No se sincronizaron KPIs.")
        return

    col_formula = buscar_columna_por_nombre(columnas_fuente, "Fórmula")
    col_alineado_archivo = buscar_columna_por_nombre(columnas_fuente, "Alineado (archivo)")

    with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nombre_kpi FROM Kpis")
        existentes = {normalizar_texto(row[0]).lower() for row in cursor.fetchall() if row[0]}
        nuevos = 0

        for _, row in df.iterrows():
            indicador = normalizar_texto(row.get(col_indicador, "")) if col_indicador else ""
            if not indicador or indicador.lower() in existentes:
                continue

            formula_val = normalizar_texto(row.get(col_formula, "")) if col_formula else ""
            formula_db = formula_val or None

            fk_kpiEs = None
            if col_alineado_archivo:
                alineado = normalizar_texto(row.get(col_alineado_archivo, ""))
                if alineado:
                    cursor.execute(
                        "INSERT OR IGNORE INTO IndicadoresEstrategicos (nombre_kpiEs) VALUES (?)",
                        (alineado,),
                    )
                    cursor.execute(
                        "SELECT id_kpiEs FROM IndicadoresEstrategicos WHERE nombre_kpiEs = ?",
                        (alineado,),
                    )
                    resultado = cursor.fetchone()
                    if resultado:
                        fk_kpiEs = resultado[0]

            cursor.execute(
                """
                INSERT INTO Kpis (nombre_kpi, formula_kpi, fk_kpiEs)
                VALUES (?, ?, ?)
                """,
                (indicador, formula_db, fk_kpiEs),
            )
            existentes.add(indicador.lower())
            nuevos += 1

        conn.commit()

    if nuevos:
        st.success(f"Se sincronizaron {nuevos} KPI(s) nuevos desde el archivo.")


def generar_df_hoja3(df_fuente=None):
    """Genera el DataFrame requerido para la Archivo Actualizado a partir de la base de datos."""

    columnas = [
        "Indicador",
        "Fórmula",
        "Frecuencia",
        "Fuente",
        "Responsable",
        "Meta",
        "Sentido",
        "Área",
        "Departamento",
        "Cargo",
        "Responde al Cargo",
        "Nivel Jerárquico",
        "Alineado a",
        "Observaciones",
        "Alineado (archivo)",
        "Peso",
    ]

    extra_campos = [
        "Frecuencia",
        "Fuente",
        "Responsable",
        "Meta",
        "Sentido",
        "Área",
        "Departamento",
        "Alineado a",
        "Observaciones",
    ]

    extra_map = {}
    if df_fuente is not None and not df_fuente.empty:
        columnas_fuente = list(df_fuente.columns)
        col_indicador = buscar_columna_por_nombre(columnas_fuente, "Indicador")
        col_cargo = buscar_columna_por_nombre(columnas_fuente, "Cargo")
        columnas_extra_renombradas = {
            campo: buscar_columna_por_nombre(columnas_fuente, campo) for campo in extra_campos
        }

        if col_indicador:
            for _, row in df_fuente.iterrows():
                indicador_val = normalizar_texto(row.get(col_indicador, "")) if col_indicador else ""
                if not indicador_val:
                    continue

                cargo_val = normalizar_texto(row.get(col_cargo, "")) if col_cargo else ""
                key = (indicador_val, cargo_val)

                if key not in extra_map:
                    valores_extra = {}
                    for campo, col_real in columnas_extra_renombradas.items():
                        valor = ""
                        if col_real:
                            valor = normalizar_texto(row.get(col_real, ""))
                        valores_extra[campo] = valor
                    extra_map[key] = valores_extra

                # Guardar versión sin cargo para fallback
                key_simple = (indicador_val, "")
                if key_simple not in extra_map:
                    extra_map[key_simple] = extra_map[key].copy()

    with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                k.nombre_kpi,
                k.formula_kpi,
                ck.peso_kpi,
                c.nombre_cargo,
                jefe.nombre_cargo,
                c.nivel_cargo,
                ies.nombre_kpiEs
            FROM Kpis k
            LEFT JOIN CargosKpis ck ON ck.fk_kpi = k.id_kpi
            LEFT JOIN Cargos c ON ck.fk_cargo = c.id_cargo
            LEFT JOIN Cargos jefe ON c.fk_jefe = jefe.id_cargo
            LEFT JOIN IndicadoresEstrategicos ies ON k.fk_kpiEs = ies.id_kpiEs
            ORDER BY k.nombre_kpi, c.nombre_cargo
            """
        )
        registros = cursor.fetchall()

    data = []
    for (
        indicador,
        formula,
        peso,
        cargo,
        responde,
        nivel,
        alineado_archivo,
    ) in registros:
        indicador_norm = normalizar_texto(indicador)
        cargo_norm = normalizar_texto(cargo)
        extra_valores = extra_map.get((indicador_norm, cargo_norm)) or extra_map.get(
            (indicador_norm, "")
        ) or {}

        fila = {
            "Indicador": indicador_norm,
            "Fórmula": normalizar_texto(formula),
            "Frecuencia": extra_valores.get("Frecuencia", ""),
            "Fuente": extra_valores.get("Fuente", ""),
            "Responsable": extra_valores.get("Responsable", ""),
            "Meta": extra_valores.get("Meta", ""),
            "Sentido": extra_valores.get("Sentido", ""),
            "Área": extra_valores.get("Área", ""),
            "Departamento": extra_valores.get("Departamento", ""),
            "Cargo": cargo_norm,
            "Responde al Cargo": normalizar_texto(responde),
            "Nivel Jerárquico": normalizar_texto(nivel),
            "Alineado a": extra_valores.get("Alineado a", ""),
            "Observaciones": extra_valores.get("Observaciones", ""),
            "Alineado (archivo)": normalizar_texto(alineado_archivo),
            "Peso": peso if peso is not None else "",
        }
        data.append(fila)

    if not data:
        return pd.DataFrame(columns=columnas)

    return pd.DataFrame(data, columns=columnas)


def asignar_indicadores_estrategicos_a_ceo():
    """Asigna los indicadores estratégicos como KPIs al CEO con peso distribuido equitativamente"""
    with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
        cursor = conn.cursor()
        
        # Obtener el ID del CEO
        cursor.execute("""
        SELECT id_cargo FROM Cargos
        WHERE UPPER(nombre_cargo) LIKE '%CEO%'
           OR UPPER(nivel_cargo) = 'PRESIDENCIA'
        LIMIT 1
        """)
        resultado_ceo = cursor.fetchone()
        
        if not resultado_ceo:
            st.error("❌ No se encontró el CEO en la BD")
            return False
        
        id_ceo = resultado_ceo[0]
        
        # Obtener todos los indicadores estratégicos
        cursor.execute("""
        SELECT id_kpiEs, nombre_kpiEs
        FROM IndicadoresEstrategicos
        ORDER BY nombre_kpiEs
        """)
        indicadores = cursor.fetchall()
        
        if not indicadores:
            st.info("ℹ️ No hay indicadores estratégicos para asignar")
            return True
        
        # Calcular peso equitativo
        peso_unitario = 100 // len(indicadores)
        peso_sobrante = 100 % len(indicadores)
        
        # Obtener KPIs asignados al CEO
        cursor.execute("""
        SELECT fk_kpi FROM CargosKpis
        WHERE fk_cargo = ?
        """, (id_ceo,))
        kpis_actuales = {row[0] for row in cursor.fetchall()}
        
        # Para cada indicador estratégico, crear un KPI que lo represente
        asignados = 0
        for idx, (id_kpiEs, nombre_indicador) in enumerate(indicadores):
            # Buscar si ya existe un KPI con este nombre
            cursor.execute("""
            SELECT id_kpi FROM Kpis
            WHERE nombre_kpi = ?
            """, (nombre_indicador,))
            resultado = cursor.fetchone()
            
            if resultado:
                id_kpi = resultado[0]
            else:
                # Crear un KPI nuevo con el nombre del indicador estratégico
                cursor.execute("""
                INSERT INTO Kpis (nombre_kpi, fk_kpiEs)
                VALUES (?, ?)
                """, (nombre_indicador, id_kpiEs))
                id_kpi = cursor.lastrowid
            
            # Calcular peso
            peso = peso_unitario
            if idx < peso_sobrante:
                peso += 1
            
            # Insertar en CargosKpis si no existe
            try:
                cursor.execute("""
                INSERT OR IGNORE INTO CargosKpis (fk_cargo, fk_kpi, peso_kpi)
                VALUES (?, ?, ?)
                """, (id_ceo, id_kpi, peso))
                asignados += cursor.rowcount
            except:
                pass
        
        conn.commit()
        return asignados > 0

def asignar_niveles_jerarquicos():
    """Permite al usuario asignar niveles jerárquicos a los cargos usando niveles existentes en la BD"""
    
    # Inicializar flag
    if 'niveles_guardados' not in st.session_state:
        st.session_state.niveles_guardados = False
    
    with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
        cursor = conn.cursor()
        
        # Identificar y asignar nivel al CEO automáticamente
        cursor.execute("""
        SELECT id_cargo, nombre_cargo 
        FROM Cargos 
        WHERE UPPER(nombre_cargo) LIKE '%CEO%'
        LIMIT 1
        """)
        ceo = cursor.fetchone()
        
        if ceo:
            cursor.execute("""
            SELECT nivel_cargo FROM Cargos WHERE id_cargo = ?
            """, (ceo[0],))
            nivel_actual = cursor.fetchone()[0]
            
            if nivel_actual != 'Presidencia':
                cursor.execute("""
                UPDATE Cargos 
                SET nivel_cargo = 'Presidencia'
                WHERE id_cargo = ?
                """, (ceo[0],))
                conn.commit()
        
        # Obtener niveles existentes
        cursor.execute("""
        SELECT DISTINCT nivel_cargo 
        FROM Cargos 
        WHERE nivel_cargo IS NOT NULL 
          AND nivel_cargo != 'NULL' 
          AND nivel_cargo != 'N/A'
          AND TRIM(nivel_cargo) != ''
        ORDER BY nivel_cargo
        """)
        niveles_existentes = [row[0] for row in cursor.fetchall()]
        
        if not niveles_existentes:
            st.error("❌ No hay niveles jerárquicos definidos en la base de datos.")
            return False
        
        # Obtener cargos sin nivel (EXCLUYENDO al CEO)
        cursor.execute("""
        SELECT id_cargo, nombre_cargo, nivel_cargo 
        FROM Cargos 
        WHERE (nivel_cargo IS NULL 
           OR nivel_cargo = 'NULL' 
           OR nivel_cargo = 'N/A'
           OR TRIM(nivel_cargo) = '')
          AND id_cargo != ?
        ORDER BY nombre_cargo
        """, (ceo[0] if ceo else -1,))
        cargos_sin_nivel = cursor.fetchall()
        
        if not cargos_sin_nivel:
            st.success("✅ Todos los cargos tienen un nivel jerárquico asignado")
            st.session_state.niveles_guardados = True
            return True
    
    st.warning(f"⚠️ Hay {len(cargos_sin_nivel)} cargo(s) sin nivel jerárquico (excluyendo CEO)")
    
    # Mostrar niveles disponibles
    with st.expander("📋 Niveles disponibles en la base de datos"):
        cols = st.columns(3)
        for idx, nivel in enumerate(niveles_existentes):
            with cols[idx % 3]:
                st.write(f"• {nivel}")
    
    st.write("### 🎯 Asigna un nivel jerárquico a cada cargo:")
    
    # Preparar opciones
    niveles_disponibles = ["-- Seleccionar --"] + niveles_existentes
    
    # Inicializar session_state para asignaciones
    if 'asignaciones_niveles' not in st.session_state:
        st.session_state.asignaciones_niveles = {}
    
    # Crear selectbox para CADA cargo
    for idx, cargo in enumerate(cargos_sin_nivel, 1):
        id_cargo, nombre_cargo, nivel_actual = cargo
        
        st.divider()
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown(f"**{idx}. {nombre_cargo}**")
            nivel_display = nivel_actual if nivel_actual and nivel_actual not in ['NULL', 'N/A', ''] else 'Sin nivel'
            st.caption(f"Nivel actual: {nivel_display}")
        
        with col2:
            nivel_seleccionado = st.selectbox(
                "Selecciona el nivel jerárquico:",
                options=niveles_disponibles,
                key=f"nivel_{id_cargo}",
                label_visibility="collapsed"
            )
            
            # Guardar como INTEGER
            if nivel_seleccionado != "-- Seleccionar --":
                st.session_state.asignaciones_niveles[int(id_cargo)] = nivel_seleccionado
            elif int(id_cargo) in st.session_state.asignaciones_niveles:
                del st.session_state.asignaciones_niveles[int(id_cargo)]
    
    st.divider()
    
    # Controles
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("🔄 Limpiar", use_container_width=True, key="clear_niveles"):
            st.session_state.asignaciones_niveles = {}
            st.rerun()
    
    with col2:
        st.metric("Progreso", f"{len(st.session_state.asignaciones_niveles)}/{len(cargos_sin_nivel)}")
    
    with col3:
        if st.button("💾 Guardar Niveles", 
                     use_container_width=True, 
                     type="primary",
                     disabled=(len(st.session_state.asignaciones_niveles) < len(cargos_sin_nivel)),
                     key="save_niveles"):
            st.session_state.guardar_niveles_clicked = True
    
    # Procesar guardado SI el botón fue clickeado
    if st.session_state.get('guardar_niveles_clicked', False):
        
        if len(st.session_state.asignaciones_niveles) >= len(cargos_sin_nivel):
            with st.spinner("Guardando niveles..."):
                try:
                    # Usar una nueva conexión FUERA del context manager anterior
                    conn_save = sql.connect(DB_NAME, timeout=30.0)
                    cursor_save = conn_save.cursor()
                    
                    actualizados = 0
                    for id_cargo, nivel in st.session_state.asignaciones_niveles.items():
                        cursor_save.execute("""
                        UPDATE Cargos 
                        SET nivel_cargo = ?
                        WHERE id_cargo = ?
                        """, (nivel, int(id_cargo)))
                        
                        actualizados += cursor_save.rowcount
                    
                    conn_save.commit()
                    conn_save.close()
                    
                    st.success(f"✅ ¡{actualizados} nivel(es) guardado(s) correctamente!")
                    
                    # Esperar antes de limpiar
                    time.sleep(3)
                    
                    # Limpiar flags y asignaciones
                    st.session_state.asignaciones_niveles = {}
                    st.session_state.guardar_niveles_clicked = False
                    st.session_state.niveles_guardados = True
                    
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error al guardar: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
                    st.session_state.guardar_niveles_clicked = False
                    if 'conn_save' in locals():
                        conn_save.close()
        else:
            st.error("❌ Completa todas las asignaciones antes de guardar")
            st.session_state.guardar_niveles_clicked = False
    
    if len(st.session_state.asignaciones_niveles) < len(cargos_sin_nivel):
        st.info(f"⏸️ Asigna niveles a todos los cargos para continuar ({len(cargos_sin_nivel) - len(st.session_state.asignaciones_niveles)} pendientes)")
    
    return False

def asignar_jefes_faltantes():
    """Permite al usuario asignar jefes a cargos que no los tienen"""
    
    # Inicializar flag
    if 'jefes_guardados' not in st.session_state:
        st.session_state.jefes_guardados = False
    
    with closing(sql.connect(DB_NAME, timeout=30.0)) as conn:
        cursor = conn.cursor()
        
        # Identificar al CEO
        cursor.execute("""
        SELECT id_cargo, nombre_cargo 
        FROM Cargos 
        WHERE UPPER(nombre_cargo) LIKE '%CEO%'
           OR UPPER(nivel_cargo) = 'PRESIDENCIA'
        LIMIT 1
        """)
        ceo = cursor.fetchone()
        
        if ceo:
            cursor.execute("""
            UPDATE Cargos 
            SET fk_jefe = NULL
            WHERE id_cargo = ?
            """, (ceo[0],))
            conn.commit()
        
        # Obtener cargos sin jefe (EXCLUYENDO el CEO)
        cursor.execute("""
        SELECT id_cargo, nombre_cargo, nivel_cargo 
        FROM Cargos 
        WHERE fk_jefe IS NULL 
          AND (
            NOT (UPPER(nombre_cargo) LIKE '%CEO%' 
              OR UPPER(nivel_cargo) = 'PRESIDENCIA')
          )
        ORDER BY nombre_cargo
        """)
        cargos_sin_jefe = cursor.fetchall()
        
        if not cargos_sin_jefe:
            st.success("✅ Todos los cargos tienen un jefe asignado")
            st.session_state.jefes_guardados = True
            return True
        
        # Obtener todos los cargos disponibles
        cursor.execute("""
        SELECT id_cargo, nombre_cargo, nivel_cargo 
        FROM Cargos
        ORDER BY 
            CASE WHEN nivel_cargo = 'Presidencia' THEN 0 ELSE 1 END,
            nombre_cargo
        """)
        todos_cargos = cursor.fetchall()
    
    st.warning(f"⚠️ Hay {len(cargos_sin_jefe)} cargo(s) sin jefe asignado (excluyendo CEO)")
    st.write("### 📝 Asigna un jefe a cada cargo:")
    
    # Inicializar session_state
    if 'asignaciones_jefes' not in st.session_state:
        st.session_state.asignaciones_jefes = {}
    
    # Crear selectbox para CADA cargo
    for idx, cargo in enumerate(cargos_sin_jefe, 1):
        id_cargo, nombre_cargo, nivel_cargo = cargo
        
        st.divider()
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown(f"**{idx}. {nombre_cargo}**")
            nivel_display = nivel_cargo if nivel_cargo and nivel_cargo != 'NULL' else 'Sin nivel'
            st.caption(f"Nivel: {nivel_display}")
        
        with col2:
            opciones = ["-- Seleccionar --"]
            opciones_map = {}
            
            for cargo_disponible in todos_cargos:
                id_disp, nombre_disp, nivel_disp = cargo_disponible
                
                if id_disp != id_cargo:
                    nivel_text = nivel_disp if nivel_disp and nivel_disp != 'NULL' else 'Sin nivel'
                    etiqueta = f"{nombre_disp} ({nivel_text})"
                    opciones.append(etiqueta)
                    opciones_map[etiqueta] = id_disp
            
            seleccion = st.selectbox(
                "Selecciona el jefe:",
                options=opciones,
                key=f"jefe_{id_cargo}",
                label_visibility="collapsed"
            )
            
            if seleccion != "-- Seleccionar --":
                st.session_state.asignaciones_jefes[int(id_cargo)] = opciones_map[seleccion]
            elif int(id_cargo) in st.session_state.asignaciones_jefes:
                del st.session_state.asignaciones_jefes[int(id_cargo)]
    
    st.divider()
    
    # Controles
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("🔄 Limpiar", use_container_width=True, key="clear_jefes"):
            st.session_state.asignaciones_jefes = {}
            st.rerun()
    
    with col2:
        st.metric("Progreso", f"{len(st.session_state.asignaciones_jefes)}/{len(cargos_sin_jefe)}")
    
    with col3:
        if st.button("💾 Guardar Cambios", 
                     use_container_width=True, 
                     type="primary",
                     disabled=(len(st.session_state.asignaciones_jefes) < len(cargos_sin_jefe)),
                     key="save_jefes"):
            st.session_state.guardar_jefes_clicked = True
    
    # Procesar guardado
    if st.session_state.get('guardar_jefes_clicked', False):
        
        if len(st.session_state.asignaciones_jefes) >= len(cargos_sin_jefe):
            with st.spinner("Guardando asignaciones..."):
                try:
                    conn_save = sql.connect(DB_NAME, timeout=30.0)
                    conn_save.execute("PRAGMA foreign_keys = ON")
                    cursor_save = conn_save.cursor()
                    
                    actualizados = 0
                    for id_cargo, id_jefe in st.session_state.asignaciones_jefes.items():
                        cursor_save.execute("""
                        UPDATE Cargos 
                        SET fk_jefe = ?
                        WHERE id_cargo = ?
                        """, (id_jefe, int(id_cargo)))
                        
                        actualizados += cursor_save.rowcount
                    
                    conn_save.commit()
                    conn_save.close()
                    
                    st.success(f"✅ ¡{actualizados} asignación(es) guardada(s) correctamente!")
                    
                    time.sleep(3)
                    
                    # Limpiar
                    st.session_state.asignaciones_jefes = {}
                    st.session_state.guardar_jefes_clicked = False
                    st.session_state.jefes_guardados = True
                    
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
                    st.session_state.guardar_jefes_clicked = False
                    if 'conn_save' in locals():
                        conn_save.rollback()
                        conn_save.close()
        else:
            st.error("❌ Completa todas las asignaciones")
            st.session_state.guardar_jefes_clicked = False
    
    if len(st.session_state.asignaciones_jefes) < len(cargos_sin_jefe):
        st.info(f"⏸️ Completa todas las asignaciones para continuar ({len(cargos_sin_jefe) - len(st.session_state.asignaciones_jefes)} pendientes)")
    
    return False


# Ejecutar (con pestañas)
# Inicializar base de datos (solo si no existe)
init_database()

# Carga de archivo origen (CSV/XLSX)
st.write("### Carga de archivo origen")
uploaded_file = st.file_uploader(
    "Sube tu archivo base (CSV o XLSX)",
    type=["csv", "xlsx"],
    accept_multiple_files=False,
    key="archivo_fuente_uploader",
    on_change=reiniciar_estado_por_upload,
)

if 'df_fuente' not in st.session_state:
    st.session_state.df_fuente = None
if 'archivo_procesado' not in st.session_state:
    st.session_state.archivo_procesado = False

if uploaded_file is not None:
    if not st.session_state.archivo_procesado:
        try:
            reset_database_file()
            init_database()
            nombre = uploaded_file.name.lower()
            if nombre.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                try:
                    df = pd.read_excel(uploaded_file)
                except Exception as e:
                    st.error("Error al leer XLSX. Asegurate de tener 'openpyxl' instalado.")
                    raise
            st.session_state.df_fuente = df
            msg_block = st.empty()
            with msg_block.container():
                insert_data(df)
                sincronizar_nuevos_kpis(df)
                st.success("Archivo cargado y datos insertados (si aplicaba)")
            time.sleep(3)
            msg_block.empty()
            st.session_state.archivo_procesado = True
        except Exception as e:
            st.error(f"No se pudo procesar el archivo: {e}")
else:
    # Si antes habia archivo cargado y ahora no, reiniciar todo
    if st.session_state.df_fuente is not None:
        reset_database_file()
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    else:
        st.info("Sube un archivo CSV/XLSX para continuar con el ajuste de datos")

# Pestañas principales
tab_ajuste, tab_organigrama, tab_hoja3 = st.tabs(["Ajuste de datos", "Organigrama", "Archivo Actualizado"])

with tab_ajuste:
    if st.session_state.df_fuente is None:
        st.warning("Sube un archivo en la parte superior para comenzar.")
    else:
        # Paso 1
        st.write("## Paso 1: Asignación de Niveles Jerárquicos")
        if not st.session_state.get('niveles_guardados', False):
            asignar_niveles_jerarquicos()
        else:
            st.success("Niveles jerárquicos ya asignados")

        st.write("---")

        # Paso 2
        st.write("## Paso 2: Asignación de Jefes")
        if st.session_state.get('niveles_guardados', False):
            if not st.session_state.get('jefes_guardados', False):
                asignar_jefes_faltantes()
            else:
                st.success("Jefes ya asignados")
        else:
            st.info("Completa el Paso 1 antes de asignar jefes")

        st.write("---")

        # Paso 3
        st.write("## Paso 3: Asignación de Indicadores Estratégicos al CEO")
        if st.session_state.get('niveles_guardados', False) and st.session_state.get('jefes_guardados', False):
            if not st.session_state.get('indicadores_asignados', False):
                with st.spinner("Asignando indicadores estratégicos..."):
                    asignados = asignar_indicadores_estrategicos_a_ceo()
                    if asignados:
                        st.success("Indicadores estratégicos asignados al CEO")
                    else:
                        st.info("Los indicadores estratégicos ya estaban asignados")
                    st.session_state.indicadores_asignados = True
            else:
                st.success("Indicadores estratégicos ya asignados")
        else:
            st.info("Completa los Pasos 1 y 2 antes de asignar indicadores")

with tab_organigrama:
    if (
        st.session_state.get('niveles_guardados', False)
        and st.session_state.get('jefes_guardados', False)
        and st.session_state.get('indicadores_asignados', False)
    ):
        renderizar_organigrama()
    else:
        st.warning("Termina el ajuste de datos en la pestaña 'Ajuste de datos' para ver el organigrama")

with tab_hoja3:
    st.write("## Archivo Actualizado")
    if st.session_state.df_fuente is None:
        st.info("Sube un archivo en la parte superior para ver el detalle de KPIs.")
    else:
        df_hoja3 = generar_df_hoja3(st.session_state.df_fuente)
        if df_hoja3.empty:
            st.warning("No hay KPIs registrados en la base de datos.")
        else:
            st.dataframe(df_hoja3, use_container_width=True, height=400)
            st.caption("Este resumen se actualiza automáticamente al modificar los KPIs en el organigrama.")

            # Build Excel payload so the download button serves an .xlsx file
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_hoja3.to_excel(writer, index=False, sheet_name="KPIs")
            output.seek(0)
            st.download_button(
                "Descargar archivo actualizado (.xlsx)",
                data=output.getvalue(),
                file_name="archivo_actualizado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
