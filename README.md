# Organigrama KPIs

Aplicación Streamlit para construir organigramas interactivos y administrar KPIs por cargo. Lee archivos Excel/CSV de estructura organizacional, persiste la información en SQLite y ofrece un panel para editar pesos, alinear indicadores estratégicos y obtener sugerencias automáticas con el agente MARIA (LangChain + OpenAI).

## Características principales
- **Ingesta guiada de datos**: normaliza columnas típicas (`Cargo`, `Responde al Cargo`, `Nivel Jerárquico`, `Indicador`, etc.), crea las tablas (`Cargos`, `Kpis`, `IndicadoresEstrategicos`, `CargosKpis`) y evita duplicados.
- **Organigrama interactivo**: visualización jerárquica con `streamlit-agraph`, filtros por cargo y sincronización inmediata con la base de datos `organigrama_kpis.db`.
- **Panel lateral de KPIs**: edición en línea de pesos, alineación, eliminación o creación de nuevos KPIs, todo con validaciones y escritura directa sobre SQLite.
- **Agente MARIA**: sugerencias de KPIs alineados a la estrategia usando `langchain-openai` y claves almacenadas en `.streamlit/secrets.toml`.
- **Exportación y sincronización**: generación de dataframes consolidados para volver a Excel, así como sincronización incremental de indicadores nuevos desde los archivos cargados.

## Requisitos previos
- Python **3.11**.
- Una clave de OpenAI válida si deseas habilitar a MARIA: añádela a `.streamlit/secrets.toml` como `OPENAI_API_KEY = "tu_clave"`.
- Archivo de entrada con las columnas mínimas (`Cargo`, `Responde al Cargo`, `Nivel Jerárquico`, `Indicador`, `Fórmula`, `Alineado (archivo)`, etc.). Puedes usar `data/tst.xlsx` como referencia.

## Instalación con pip
```bash
git clone <url-del-repo> #Clonar repositorio
cd Organigrama\ KPIs #Ingresar a la carpeta
py -3.11 -m venv venv #Crear entorno virtual con versión 3.11 de python (necesaria para correcta ejecución)
venv\Scripts\activate #Activar venv en Windows
source venv\Scripts\activate #Activar venv en Linux/macOS
python.exe -m pip install --upgrade pip #Actualizar pip (opcional)
pip install -r requirements.txt #Instalar dependecias necesarias
```

## Ejecución
1. Activa tu entorno (`.venv\Scripts\activate` en Windows).
2. Lanza la app:
   ```bash
   streamlit run app.py
   ```
3. Desde la interfaz:
   - Carga tu archivo base (Excel/CSV). El script inicializa/actualiza `organigrama_kpis.db` usando WAL y llaves foráneas.
   - Explora o filtra el organigrama desde el canvas interactivo.
   - Selecciona un cargo y usa el panel lateral para editar pesos, alinear indicadores o crear nuevos KPIs.
   - Si configuraste `OPENAI_API_KEY`, chatea con MARIA y convierte sus propuestas en KPIs con un clic.

## Estructura relevante
- `app.py`: lógica completa de Streamlit, conexión SQLite, renderizado del organigrama, panel de KPIs y agente MARIA.
- `data/`, `docs_iniciales/`: archivos de ejemplo que sirven como base para pruebas o referencias.
- `organigrama_kpis.db`: base de datos SQLite generada automáticamente (se puede borrar para reiniciar el flujo).
- `.streamlit/secrets.toml`: credenciales y configuración sensible.
- `others/`: prototipos y pruebas (p.ej. `pruebasGUI.py` para experimentar con grafos).

## Resolución de problemas
- **Faltan dependencias**: vuelve a ejecutar `pip install -r requirements.txt`.
- **Errores de base de datos**: usa la opción "reset" de la interfaz (botón que llama a `reset_database_file`) o elimina manualmente `organigrama_kpis.db`, `organigrama_kpis.db-wal` y `organigrama_kpis.db-shm`.
- **MARIA no responde**: verifica que `langchain-openai` esté instalado y que `OPENAI_API_KEY` sea válido en `.streamlit/secrets.toml`.
- **Organigrama vacío**: revisa que las columnas `Cargo` y `Responde al Cargo` del archivo fuente estén bien escritas; la app es case-insensitive pero requiere coincidencias exactas en valores.

¡Listo! Con esto podrás replicar el entorno, cargar tus archivos organizacionales y gestionar KPIs de forma interactiva.
