import pandas as pd
from auditoria_integridade import auditar_dataframe
from Tabela_de_dados_Inventario_7_2 import COLUNAS_INVENTARIO
def test_auditoria_identifica_incompleto():
    df=pd.DataFrame([{'Setor':'Consultório','Tipo de Patrimônio':'CPU','Nº de Patrimônio':'1','Fabricante':'Dell','Data Cadastro':''},{'Setor':'Consultório','Tipo de Patrimônio':'','Nº de Patrimônio':'','Fabricante':'','Data Cadastro':''}])
    r=auditar_dataframe(df); assert r['linhas_validas']==1; assert r['linhas_descartadas_na_normalizacao']==1
def test_auditoria_detecta_duplicidade():
    df=pd.DataFrame([{'Setor':'Farmacia','Tipo de Patrimônio':'CPU','Nº de Patrimônio':'X','Fabricante':'Dell','Data Cadastro':''},{'Setor':'Recepção','Tipo de Patrimônio':'Monitores','Nº de Patrimônio':'X','Fabricante':'HP','Data Cadastro':''}],columns=COLUNAS_INVENTARIO)
    assert auditar_dataframe(df)['duplicidades_por_numero_patrimonio']==2
