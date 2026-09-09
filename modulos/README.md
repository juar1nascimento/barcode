# Módulos do Portal GTI-SESA

A aplicação é organizada em três módulos funcionais independentes, integrados pelo `app.py`:

- `sistema_inventarios/` — consulta, cadastro, leitura de códigos e gerenciamento do inventário.
- `entrada_equipamentos/` — recebimento e inclusão de equipamentos.
- `saida_equipamentos/` — saída, baixa, manutenção e transferência entre unidades.

## Camada compartilhada

Os módulos utilizam serviços compartilhados na raiz do projeto:

- `Tabela_de_dados_Inventario_7_2.py` — persistência, normalização e acesso aos dados.
- `inventario_regras.py` — regras oficiais de setores e tipos.
- `movimentacao_inventario.py` — operações de entrada, saída, transferência e exclusão exata.

## Portal

`app.py` é somente o orquestrador do Portal de Sistemas GTI-SESA. Ele apresenta os três cards e encaminha o usuário para o módulo selecionado.

Os arquivos `sistema_inventario.py`, `entrada_equipamentos.py` e `saida_equipamentos.py` permanecem como fachadas de compatibilidade para não quebrar imports existentes; o código funcional fica dentro de `modulos/`.
