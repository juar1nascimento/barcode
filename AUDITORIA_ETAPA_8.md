# Auditoria — Etapa 8

## Base analisada

Foi analisada a cópia de trabalho `Tabela_Patrimonios_sem_origem_status_codigo_barras.xlsx`, usada como referência da estrutura histórica do inventário.

### Resultado estrutural

- 40 abas no total.
- 29 abas vazias.
- 11 abas com dados.
- 56 linhas físicas distribuídas nas abas com dados.
- Foram encontrados vários formatos históricos de cabeçalho, incluindo `Setor`, `Local / Setor`, colunas de patrimônio por tipo e o schema moderno de 5 colunas.
- Existem duas grafias históricas de abas para a mesma unidade: `URS Jacaraípe` / `URS Jacara_pe` e `UBS Bairro de Fátima` / `UBS Bairro de F_tima`.
- Nenhuma das linhas analisadas nessa cópia possuía valor preenchido em `Data Cadastro`.
- A cópia já não contém as colunas removidas `Código de Barras`, `Origem` e `Status` no schema moderno.

## Regra de integridade adotada

O identificador lido pelo scanner é armazenado em `Nº de Patrimônio`. Portanto, esse número é tratado como identificador único global do patrimônio: não pode ser cadastrado novamente em outro setor, tipo ou unidade.

A implementação não mantém a regra anterior que permitia o mesmo patrimônio em setores diferentes.

## Data e hora

O armazenamento de novos cadastros foi padronizado para:

`DD-MM-YYYY HH:MM:SS`

Exemplo: `09-09-2026 18:30:45`.

Também foi adicionada uma rotina de normalização que converte representações legadas conhecidas para esse formato ao carregar os dados e uma rotina específica para corrigir a coluna `Data Cadastro` das abas quando a migração for executada sobre a planilha real.

## Limite da auditoria

A análise estrutural acima é da cópia de trabalho disponível nesta conversa. O acesso direto aos dados atuais do Google Sheets não está exposto nesta execução; por isso, não foi afirmado que as 40 abas atuais da planilha online foram fisicamente alteradas. O código da Etapa 8 inclui a auditoria das abas reais via objeto `gspread` e a correção controlada da coluna `Data Cadastro`.
