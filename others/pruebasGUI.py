import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

# 1. FUNCIÓN DE DEFINICIÓN DE DATOS DEL MAPA
def define_mapa_conceptual():
    nodes = []
    edges = []

    # Nodos principales
    nodes.append(Node(id="Concepto Principal", label="CARACTERÍSTICAS DEL MAPA CONCEPTUAL", size=40, color="#1E90FF", shape="box"))
    
    # Nodos de primer nivel (siguiendo el esquema de la imagen)
    nodes.append(Node(id="Jerarquía", label="1. Jerarquía", size=30, color="#3CB371", shape="box"))
    nodes.append(Node(id="Síntesis", label="2. Síntesis", size=30, color="#3CB371", shape="box"))
    nodes.append(Node(id="Relación", label="3. Relación", size=30, color="#3CB371", shape="box"))

    # Nodos de segundo nivel (ejemplo de desglose)
    nodes.append(Node(id="Estructura", label="Estructura Secuencial", size=25, color="#FFD700", shape="box"))
    nodes.append(Node(id="Conexión", label="Conexiones Cruzadas", size=25, color="#FFD700", shape="box"))

    # Aristas
    edges.append(Edge(source="Concepto Principal", target="Jerarquía", label="se basa en", color="#1E90FF"))
    edges.append(Edge(source="Concepto Principal", target="Síntesis", label="permite la", color="#1E90FF"))
    edges.append(Edge(source="Concepto Principal", target="Relación", label="contiene", color="#1E90FF"))
    
    edges.append(Edge(source="Jerarquía", target="Estructura", label="define la", color="#3CB371"))
    edges.append(Edge(source="Relación", target="Conexión", label="incluye", color="#3CB371"))
    edges.append(Edge(source="Estructura", target="Conexión", label="requiere", color="#FFD700"))
    
    return nodes, edges

# 2. FUNCIÓN DE RENDERIZACIÓN DE DETALLES EN EL SIDEBAR
def display_node_details(node_id):
    """Muestra información detallada sobre el nodo seleccionado en el sidebar."""
    
    # Datos de ejemplo para demostración
    DETALLES_NODO = {
        "Concepto Principal": "Este es el tema central del mapa, representando las características fundamentales de un mapa conceptual.",
        "Jerarquía": "La información más general se coloca en la cima, y los conceptos específicos se ordenan hacia abajo.",
        "Síntesis": "Un mapa conceptual resume la información clave de manera visual y eficiente.",
        "Relación": "Señala cómo los conceptos se conectan, usando palabras de enlace en las aristas.",
        "Estructura": "Implica un orden de lectura definido, usualmente de lo general a lo particular.",
        "Conexión": "Muestra las interrelaciones complejas entre diferentes ramas del conocimiento."
    }

    st.subheader(f"Detalle: {node_id}")
    st.markdown(DETALLES_NODO.get(node_id, "Detalles no disponibles para este nodo."))
    
    # Acción de Streamlit dentro del sidebar:
    st.write("---")
    if st.button(f"Ejecutar Acción para {node_id}"):
        st.success(f"¡Acción ejecutada para el nodo '{node_id}'!")
        # Aquí se podría incluir lógica para llamar a una API, cargar un DataFrame, etc.


# --- APLICACIÓN PRINCIPAL DE STREAMLIT ---
st.set_page_config(layout="wide")

# Inicialización de estado para el nodo cliqueado 
if 'clicked_node' not in st.session_state:
    st.session_state['clicked_node'] = None

st.title("Mapa Conceptual Interactivo (Streamlit + Agraph)")
st.caption("Haga clic en un nodo del mapa para ver sus detalles en el sidebar.")

# 3. DEFINICIÓN DE DATOS Y CONFIGURACIÓN DEL GRAFO
nodes, edges = define_mapa_conceptual()

# Configuración del Layout Jerárquico 
config = Config(
    width=700,
    height=600,
    directed=True,
    physics=False,  # Desactiva la física para un layout estable
    hierarchical=True, # Activa el layout de árbol
    layout={"hierarchical": {"direction": "UD", "sortMethod": "directed"}},
    fit=True
)

# 4. RENDERIZADO DEL GRAFO Y CAPTURA DEL VALOR
clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

# 5. LÓGICA DE GESTIÓN DE ESTADO (POST-RERUN)
# Si el componente devolvió un nuevo ID (hubo un clic), actualizamos el estado persistente.
if clicked_node_id:
    # Solo actualizamos si el ID es diferente para evitar reruns innecesarios si se hace clic en el mismo nodo
    if clicked_node_id!= st.session_state['clicked_node']:
        st.session_state['clicked_node'] = clicked_node_id
        # Si se desea que el cambio sea visible inmediatamente sin esperar más código, se puede usar st.rerun()
        # st.rerun() # Opcional, ya que el componente ya causa un rerun al enviar el valor.

# --- LÓGICA DE RENDERIZACIÓN DEL SIDEBAR ---
with st.sidebar:
    st.header("Información Contextual del Nodo")

    # B. Renderización Condicional basada en st.session_state 
    if st.session_state.clicked_node:
        node_id = st.session_state.clicked_node
        display_node_details(node_id)
        
        # Botón para deseleccionar el nodo y limpiar el sidebar
        st.write("---")
        if st.button("Limpiar Selección"):
            st.session_state['clicked_node'] = None
            st.rerun() # Forzar un rerun para limpiar el contenido del sidebar
    else:
        st.warning("El sidebar se actualizará al seleccionar un nodo.")