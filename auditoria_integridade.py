import pandas as pd
from Tabela_de_dados_Inventario_7_2 import COLUNAS_INVENTARIO, TIPOS_PATRIMONIO, _chave_texto, _normalizar_legacy_dataframe
def auditar_dataframe(df: pd.DataFrame) -> dict:
    original=0 if df is None else len(df); n=_normalizar_legacy_dataframe(df)
    return {'linhas_originais':original,'linhas_validas':len(n),'linhas_descartadas_na_normalizacao':original-len(n),'duplicidades_por_numero_patrimonio':int(n.duplicated(subset=['Nº de Patrimônio'],keep=False).sum()),'tipos_invalidos':int((~n['Tipo de Patrimônio'].isin(TIPOS_PATRIMONIO)).sum()) if not n.empty else 0,'numeros_vazios':int(n['Nº de Patrimônio'].map(lambda v:not _chave_texto(v)).sum()) if not n.empty else 0,'colunas_canonicas':list(n.columns)==COLUNAS_INVENTARIO}
