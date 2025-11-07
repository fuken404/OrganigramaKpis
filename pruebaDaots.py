import streamlit as st
import pandas as pd

"""nivelesJerarquia = {
  "CEO": 1,
  "Vicepresidente": 2,
  "Gerente": 3,
  "Director": 4,
  "Jefe / Coordinador": 5,
  "Profesional / Analista": 6,
  "Asistente / Auxiliar": 7,
  "Operativo": 8
}"""

df = pd.read_excel('data/tst.xlsx')
dfCargos = pd.DataFrame({
  "Cargo": pd.concat([df["Cargo"], df["Responde al Cargo"]]).unique()
  })

df_unique = df[["Cargo", "Nivel Jerárquico"]].drop_duplicates(subset="Cargo", keep="first")

dfCargos = dfCargos.merge(
    df_unique,    # columnas originales
    on="Cargo",
    how="left"
)

dfCargos["Nivel Jerárquico"] = dfCargos["Nivel Jerárquico"].fillna("N/A")


""""

st.set_page_config(page_title="Asignar niveles jerárquicos", layout="wide")

# --- Supone que ya tienes df y dfCargos creados ---
# df = pd.read_excel("tst.xlsx")
# dfCargos = ...  # como lo construimos antes
# Asegura tipo texto para comparar:
dfCargos["Nivel Jerárquico"] = dfCargos["Nivel Jerárquico"].astype(str)

# --- Catálogo de niveles (etiqueta -> número) ---
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

st.title("Asignar niveles jerárquicos faltantes")

# Filtra cargos sin nivel (N/A)
cargos_na = dfCargos.loc[dfCargos["Nivel Jerárquico"].isin(["N/A", "nan", "", "None"]), "Cargo"].drop_duplicates().tolist()

if not cargos_na:
    st.success("✅ No hay cargos con Nivel Jerárquico = N/A.")
else:
    st.warning(f"Hay {len(cargos_na)} cargos sin nivel. Asígname un nivel, por favor.")

    # Usamos una form para asignar todos en un solo submit
    with st.form("form_asignar_niveles"):
        st.subheader("Selecciona nivel por cada cargo sin asignar")
        # mostramos un select por cargo
        asignaciones = {}
        etiquetas = list(nivelesJerarquia.keys())
        default_idx = None  # sin valor por defecto

        for cargo in cargos_na:
            sel = st.selectbox(
                f"Nivel para: {cargo}",
                options=["-- Seleccionar --"] + etiquetas,
                index=default_idx if default_idx is not None else 0,
                key=f"sel_{cargo}"
            )
            asignaciones[cargo] = sel  # guardamos la etiqueta (ej. "Director")

        submit = st.form_submit_button("💾 Aplicar niveles seleccionados")

    if submit:
        # Convertimos etiqueta -> número según el catálogo
        etiqueta_a_num = nivelesJerarquia  # alias

        # Mapeo cargo -> número
        cargo_a_nivel_num = {cargo: etiqueta_a_num[etiqueta] for cargo, etiqueta in asignaciones.items()}

        # Actualizamos dfCargos:
        dfCargos["Nivel Jerárquico"] = dfCargos.apply(
            lambda r: asignaciones.get(r["Cargo"]) 
                      if str(r["Nivel Jerárquico"]) in ["N/A", "nan", "", "None"] else r["Nivel Jerárquico"],
            axis=1
        )

        st.success("✅ Niveles aplicados.")
        st.dataframe(dfCargos, use_container_width=True)

        # # Descarga opcional
        # st.download_button(
        #     "⬇️ Descargar cargos_con_nivel.xlsx",
        #     data=dfCargos.to_excel(index=False, engine="openpyxl"),
        #     file_name="cargos_con_nivel.xlsx",
        #     mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        # )
    else:
        # Vista previa antes de aplicar
        st.caption("Vista previa actual (aún sin aplicar):")
        st.dataframe(dfCargos, use_container_width=True)"""
