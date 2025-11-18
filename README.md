# Organigrama KPIs

Aplicación Streamlit para construir organigramas interactivos y administrar KPIs por cargo. Lee archivos Excel/CSV de estructura organizacional, persiste la información en SQLite y ofrece un panel para editar pesos, alinear indicadores estratégicos y obtener sugerencias automáticas con el agente MARIA (LangChain + OpenAI).

## Características principales
- **Ingesta guiada de datos**: normaliza columnas típicas (`Cargo`, `Responde al Cargo`, `Nivel Jerárquico`, `Indicador`, etc.), crea las tablas (`Cargos`, `Kpis`, `IndicadoresEstrategicos`, `CargosKpis`) y evita duplicados.
- **Organigrama interactivo**: visualización jerárquica con `streamlit-agraph`, filtros por cargo y sincronización inmediata con la base de datos `organigrama_kpis.db`.
- **Panel lateral de KPIs**: edición en línea de pesos, alineación, eliminación o creación de nuevos KPIs, todo con validaciones y escritura directa sobre SQLite.
- **Agente MARIA**: sugerencias de KPIs alineados a la estrategia usando `langchain-openai` y claves almacenadas en `.streamlit/secrets.toml`.
- **Exportación y sincronización**: generación de dataframes consolidados para volver a Excel, así como sincronización incremental de indicadores nuevos desde los archivos cargados.

## Requisitos previos
- Python **3.11** (la app se declara en `pyproject.toml` como `>=3.11,<3.12`).
- [uv](https://github.com/astral-sh/uv) para gestionar dependencias mediante `pyproject.toml`/`uv.lock`.
- Una clave de OpenAI válida si deseas habilitar a MARIA: añádela a `.streamlit/secrets.toml` como `OPENAI_API_KEY = "tu_clave"`.
- Archivo de entrada con las columnas mínimas (`Cargo`, `Responde al Cargo`, `Nivel Jerárquico`, `Indicador`, `Fórmula`, `Alineado (archivo)`, etc.). Puedes usar `data/tst.xlsx` como referencia.

## Instalación con uv
```bash
git clone <url-del-repo>
cd Organigrama\ KPIs
uv sync        # crea .venv/ y resuelve pyproject.toml + uv.lock
```

uv crea el entorno virtual automáticamente (por defecto en `.venv`). Para activarlo manualmente en Windows:
```bash
.venv\Scripts\activate
```
En macOS/Linux:
```bash
source .venv/bin/activate
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

Para una verificación rápida del entorno puedes ejecutar:
```bash
python main.py
```

## Estructura relevante
- `app.py`: lógica completa de Streamlit, conexión SQLite, renderizado del organigrama, panel de KPIs y agente MARIA.
- `data/`, `docs_iniciales/`: archivos de ejemplo que sirven como base para pruebas o referencias.
- `organigrama_kpis.db`: base de datos SQLite generada automáticamente (se puede borrar para reiniciar el flujo).
- `.streamlit/secrets.toml`: credenciales y configuración sensible.
- `others/`: prototipos y pruebas (p.ej. `pruebasGUI.py` para experimentar con grafos).

## Despliegue y empaquetado
- **Streamlit Cloud u otros PaaS**: configura el build step para que ejecute `uv sync` antes de `streamlit run app.py`. No olvides definir los `secrets`.
- **Contenedores**: copia `pyproject.toml`, `uv.lock` y ejecuta `uv sync` en la imagen base (por ejemplo, `python:3.11`). Lanza la app con `streamlit run app.py --server.port $PORT`.
- **Binarios locales**: el proyecto incluye `pyinstaller` en dependencias; puedes generar un ejecutable ejecutando `pyinstaller app.py --onefile` y distribuyendo la carpeta `docs_iniciales`/`data` según necesites.

## Resolución de problemas
- **Faltan dependencias**: vuelve a ejecutar `uv sync` (lo puedes forzar con `uv sync --reinstall`).
- **Errores de base de datos**: usa la opción "reset" de la interfaz (botón que llama a `reset_database_file`) o elimina manualmente `organigrama_kpis.db`, `organigrama_kpis.db-wal` y `organigrama_kpis.db-shm`.
- **MARIA no responde**: verifica que `langchain-openai` esté instalado y que `OPENAI_API_KEY` sea válido en `.streamlit/secrets.toml`.
- **Organigrama vacío**: revisa que las columnas `Cargo` y `Responde al Cargo` del archivo fuente estén bien escritas; la app es case-insensitive pero requiere coincidencias exactas en valores.

¡Listo! Con esto podrás replicar el entorno, cargar tus archivos organizacionales y gestionar KPIs de forma interactiva.
