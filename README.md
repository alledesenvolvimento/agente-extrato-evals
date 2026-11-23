# Agente de Extração de Extratos Bancários — Evals

Mini projeto de estudo voltado à aplicação de Python e Engenharia de IA, com foco em extração estruturada de movimentações bancárias utilizando LLMs e avaliação automatizada da qualidade das respostas.

O projeto demonstra como estruturar a saída de um modelo de linguagem, validar os dados extraídos e medir a qualidade da extração por meio de um Golden Set e um Quality Gate.

## Objetivos

- Integrar uma aplicação Python à API da OpenAI.
- Utilizar Pydantic para definir e validar estruturas de dados.
- Realizar extração estruturada de movimentações bancárias a partir de textos.
- Construir um Golden Set com casos de referência.
- Comparar resultados extraídos com resultados esperados.
- Automatizar a avaliação de qualidade.
- Aplicar um Quality Gate para controlar a aprovação das avaliações.
- Registrar os resultados em relatórios JSON.
- Desenvolver testes automatizados.

## Tecnologias

| Tecnologia | Aplicação |
|---|---|
| Python 3.12+ | Linguagem principal |
| OpenAI SDK | Integração com modelos de linguagem |
| Pydantic 2 | Modelagem e validação de dados |
| python-dotenv | Variáveis de ambiente |
| Pytest | Testes automatizados |
| Ruff | Análise estática e qualidade do código |
| MyPy | Verificação estática de tipos |


## Estrutura do projeto

```text
agente-extrato-evals/
├── evals/
│   └── casos_ouro.jsonl
├── resultados/
│   └── avaliacao_golden_set.json
├── src/
│   └── agente/
│       ├── __init__.py
│       ├── modelos.py
│       ├── provedor_openai.py
│       └── avaliador.py
├── tests/
│   ├── test_avaliador.py
│   ├── test_golden_set.py
│   └── test_quality_gate.py
├── .gitignore
├── pyproject.toml
└── README.md
```

## Componentes principais

### modelos.py

Define as estruturas de dados utilizando Pydantic:

- `Fonte`: identificação do documento e página de origem.
- `ItemExtrato`: representação de uma movimentação bancária.
- `ResultadoExtracao`: estrutura do resultado da extração.

### provedor_openai.py

Responsável pela integração com a API da OpenAI.

Utiliza `responses.parse()` para solicitar a extração estruturada e validar a resposta conforme o modelo Pydantic `ResultadoExtracao`.

### avaliador.py

Responsável pela avaliação do Golden Set:

- Carregamento dos casos de referência.
- Execução das extrações.
- Comparação determinística dos resultados.
- Cálculo da taxa de aprovação.
- Aplicação do Quality Gate.
- Geração e persistência do relatório JSON.

### casos_ouro.jsonl

Contém os casos fictícios utilizados como referência para avaliar as extrações.

## Fluxo de funcionamento

```text
       Golden Set
            |
            v
    Carregar os casos
            |
            v
     Provedor OpenAI
            |
            v
   Extração estruturada
            |
            v
    Validação Pydantic
            |
            v
 Comparação determinística
            |
            v
   Relatório de avaliação
            |
            v
      Quality Gate
        (90%)
       /      \
      v        v
  Aprovado  Reprovado
     |         |
  Código 0  Código 1
```


## Instalação e configuração

### Requisitos

- Python 3.12 ou superior.
- Uma chave de API da OpenAI.
- Git.

### 1. Obter o código do projeto

Depois que o repositório estiver publicado, utilize a URL real fornecida pelo GitHub:

`powershell
git clone <URL_REAL_DO_REPOSITORIO>
cd agente-extrato-evals
`

Se você já recebeu uma cópia do código, abra o terminal na pasta do projeto e continue a partir da criação do ambiente virtual.

### 2. Criar o ambiente virtual

```powershell
py -3.12 -m venv .venv
```

### 3. Instalar as dependências

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 4. Configurar a variável de ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
OPENAI_API_KEY=sua_chave_api
```

A chave é carregada pelo `python-dotenv` e utilizada pelo cliente oficial da OpenAI.

**Importante:** o arquivo `.env` está configurado no `.gitignore` e não deve ser enviado ao repositório.


## Execução

Para executar a avaliação completa do Golden Set:

```powershell
.\.venv\Scripts\python.exe -m agente.avaliador
```

A execução realiza chamadas reais à API da OpenAI para cada caso do Golden Set. Portanto, pode gerar custos de utilização.

Ao final, o sistema:
1. Exibe o resumo da avaliação.
2. Salva os resultados em `resultados/avaliacao_golden_set.json`.
3. Aplica o Quality Gate.
4. Retorna código de saída `0` quando aprovado ou `1` quando reprovado.

O relatório é salvo antes da decisão do Quality Gate, inclusive quando a avaliação é reprovada.

## Golden Set

O conjunto atual contém 20 casos fictícios, com 27 movimentações esperadas, armazenados em `evals/casos_ouro.jsonl`.

A comparação determinística considera:
- Descrição normalizada, ignorando diferenças de maiúsculas/minúsculas e espaços.
- Valor monetário com duas casas decimais.
- Data.
- Documento de origem.
- Página de origem.

A comparação não depende da ordem das movimentações. Casos com erro de extração ou resultado diferente do esperado são contabilizados como reprovados.

## Quality Gate

O limite inicial de aprovação está definido em `LIMITE_APROVACAO`, no arquivo `src/agente/avaliador.py`.

| Condição | Resultado |
|---|---|
| Taxa igual ou superior a 90% | Aprovado |
| Taxa inferior a 90% | Reprovado |
| Nenhum caso avaliado | Reprovado |

O código de saída permite que ferramentas externas identifiquem se a avaliação passou ou falhou:
- `0`: Quality Gate aprovado.
- `1`: Quality Gate reprovado.

## Testes e qualidade do código

Os testes automatizados não precisam chamar a API da OpenAI:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Verificação com Ruff:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

Verificação de tipos com MyPy:

```powershell
.\.venv\Scripts\python.exe -m mypy src tests
```

### Validação registrada durante o desenvolvimento

- 18 testes automatizados aprovados.
- Ruff: `All checks passed!`.
- MyPy: sem problemas em 8 arquivos verificados em src e tests.

## Resultado de referência

O arquivo `resultados/avaliacao_golden_set.json` registra uma avaliação real realizada em 23/11/2026, antes da implementação do Quality Gate.

| Indicador | Resultado |
|---|---:|
| Casos avaliados | 20 |
| Casos aprovados | 20 |
| Casos reprovados | 0 |
| Taxa de aprovação | 100% |
| Movimentações esperadas | 27 |
| Movimentações extraídas | 27 |

Esse resultado representa a linha de base dos 20 casos fictícios atuais. Não é garantia de desempenho em extratos reais e não representa uma execução aprovada pelo Quality Gate, pois foi obtido antes de sua implementação.

O relatório JSON é sobrescrito a cada nova execução; o projeto ainda não mantém histórico acumulado de avaliações.

## Limitações atuais

- A entrada do provedor é texto; a leitura direta de arquivos PDF ainda não está implementada.
- O Golden Set utiliza dados fictícios e ainda possui escopo limitado.
- A avaliação completa depende de chamadas à API da OpenAI.
- O relatório registra somente a última execução.
- A demonstração controlada de regressão do prompt ainda não foi implementada.

## Próximas evoluções

- Demonstrar regressão de qualidade por meio de uma alteração controlada do prompt.
- Expandir o Golden Set com novos cenários.
- Implementar histórico de avaliações.
- Evoluir os critérios de avaliação e a cobertura de testes.

---

Projeto desenvolvido como parte dos estudos para a área de Desenvolvimento Python e Engenharia de IA.
