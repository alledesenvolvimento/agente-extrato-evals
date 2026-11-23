# Agente de Extração de Extratos Bancários — Evals

Projeto de Engenharia de IA e Python focado na extração estruturada de movimentações financeiras a partir de extratos bancários em texto, com validação tipada via Pydantic, suporte multi-provedor (OpenAI e AWS Bedrock), observabilidade opcional via Langfuse, avaliação determinística contra um Golden Set, diagnóstico de divergências, testes de regressão controlada, Quality Gate automatizado e pipeline de CI.

---

## Problema resolvido

Modelos de linguagem (LLMs) podem variar na formatação de datas, sinais monetários (crédito vs. débito), descrições ou omitir lançamentos ao extrair dados de extratos bancários. Sem avaliação automatizada e determinística, alterações de prompt, modelo ou provedor introduzem regressões silenciosas.

Este projeto resolve esse problema estruturando a saída em contratos tipados e submetendo qualquer alteração a um ciclo reproduzível de avaliação com **Golden Set** e **Quality Gate**.

## Objetivo do projeto

- Extrair movimentações financeiras com saída estruturada e rastreável até documento e página de origem.
- Validar rigorosamente os dados extraídos com Pydantic v2.
- Desacoplar a lógica de avaliação determinística dos provedores de LLM (`ProvedorExtracao`).
- Permitir alternância entre provedores (**OpenAI** e **AWS Bedrock**) sem alterar o avaliador.
- Registrar telemetria operacional opcional com **Langfuse** (tokens, latência, custo real/estimado, versão do prompt e erros).
- Detectar regressões de prompt com diagnóstico granular de divergências.
- Bloquear degradações de qualidade via **Quality Gate** (limite de 90%) e **CI no GitHub Actions**.

---

## Arquitetura

```text
                    +------------------------+
                    |   Golden Set (JSONL)   |
                    +-----------+------------+
                                |
                                v
+------------------+   +--------+---------+   +-------------------------+
| Seleção Provedor |-->|    avaliador.py  |-->| ObservadorExecucao      |
| (openai|bedrock) |   | (Orquestração)   |   | (Langfuse ou No-op)     |
+------------------+   +--------+---------+   +-------------------------+
                                |
                                v
                    +-----------+------------+
                    |  Validação Pydantic    |
                    |  (ResultadoExtracao)   |
                    +-----------+------------+
                                |
                                v
                    +-----------+------------+
                    | Comparação Determiníst.|
                    | + Diagnóstico Diverg.  |
                    +-----------+------------+
                                |
                +---------------+---------------+
                v                               v
     +----------+-----------+       +-----------+----------+
     | Relatório JSON       |       | Quality Gate (90%)   |
     | resultados/*.json    |       | Exit 0 (OK) / 1 (NOK)|
     +----------------------+       +----------------------+
```

### Princípios arquiteturais

- **Desacoplamento por protocolo (`ProvedorExtracao`)**: `avaliador.py` depende apenas da interface comum definida em `src/agente/provedores.py`, permitindo alternar entre OpenAI e AWS Bedrock sem reescrever a avaliação.
- **Avaliador determinístico puro**: `comparar_resultados`, `diagnosticar_divergencias` e `verificar_quality_gate` não dependem de SDKs externos nem de telemetria.
- **Observabilidade não intrusiva**: `ObservadorLangfuse` é opcional; quando `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` não estão configurados, `ObservadorNulo` atua sem impacto e sem chamadas de rede.

---

## Tecnologias utilizadas

| Tecnologia | Aplicação |
|---|---|
| Python 3.12+ | Linguagem principal |
| Pydantic 2 | Modelagem e validação estrita de dados |
| OpenAI SDK (`responses.parse`) | Extração estruturada com modelos OpenAI |
| AWS `boto3` (`bedrock-runtime`) | Extração estruturada via Bedrock Converse API (tool use) |
| Langfuse SDK v5+ | Observabilidade, tracing, tokens, latência e custos |
| python-dotenv | Carregamento de variáveis de ambiente |
| Pytest | Testes unitários, integração com mocks e validação do Golden Set |
| Ruff | Lint e padronização de código |
| MyPy (`strict = true`) | Verificação estática de tipos |
| GitHub Actions | Pipeline de CI (Ruff, MyPy, Pytest e Quality Gate controlado) |

---

## Estrutura de diretórios

```text
agente-extrato-evals/
├── .github/
│   └── workflows/
│       └── ci.yml                       # Pipeline de CI no GitHub Actions
├── evals/
│   └── casos_ouro.jsonl                 # Golden Set com 20 casos fictícios (27 movimentações)
├── resultados/
│   ├── avaliacao_golden_set.json        # Relatório de referência (baseline OpenAI)
│   └── avaliacao_regressao.json         # Relatório preservado da regressão controlada
├── src/
│   └── agente/
│       ├── __init__.py
│       ├── modelos.py                   # Fonte, ItemExtrato, ResultadoExtracao
│       ├── provedores.py                # Protocolo ProvedorExtracao, MetadadosExtracao e fábrica
│       ├── provedor_openai.py           # Provedor OpenAI (responses.parse)
│       ├── provedor_bedrock.py          # Provedor AWS Bedrock (Converse API + toolConfig)
│       ├── observabilidade.py           # ObservadorLangfuse e ObservadorNulo
│       ├── avaliador.py                 # Avaliador determinístico, diagnóstico e Quality Gate
│       ├── avaliacao_regressao.py       # Experimento controlado de regressão de prompt
│       └── validacao_ci.py              # Validação controlada do Quality Gate para CI
├── tests/
│   ├── test_avaliacao_regressao.py
│   ├── test_avaliador.py
│   ├── test_golden_set.py
│   ├── test_main.py
│   ├── test_observabilidade.py
│   ├── test_provedor_bedrock.py
│   ├── test_provedor_openai.py
│   └── test_quality_gate.py
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

---

## Como configurar o ambiente

### Pré-requisitos

- Python 3.12+
- Git
- Credenciais apenas se for executar chamadas reais a provedores externos (os testes automatizados e a CI usam mocks/simulações e não exigem chaves).

### Instalação (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Copie `.env.example` para `.env` e preencha apenas as variáveis necessárias para o seu ambiente:

```powershell
Copy-Item .env.example .env
```

> **Segurança:** O arquivo `.env` está listado no `.gitignore` e nunca deve ser versionado.

---

## Como executar os testes e verificações estáticas

Os testes automatizados utilizam mocks e não realizam chamadas pagas à OpenAI, AWS ou Langfuse:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src tests
```

---

## Como executar as avaliações

> **Atenção:** Os comandos abaixo realizam chamadas reais ao provedor configurado e podem gerar custos.

### Avaliação padrão (OpenAI)

```powershell
.\.venv\Scripts\python.exe -m agente.avaliador
```

### Alternando provedores e modelo via CLI ou variável de ambiente

Via CLI:

```powershell
# Usando AWS Bedrock
.\.venv\Scripts\python.exe -m agente.avaliador --provedor bedrock

# Especificando modelo e arquivo de saída alternativo
.\.venv\Scripts\python.exe -m agente.avaliador --provedor bedrock --modelo anthropic.claude-3-5-haiku-20241022-v1:0 --saida resultados/avaliacao_bedrock.json
```

Ou via variável de ambiente (`AGENTE_PROVEDOR=bedrock` ou `AGENTE_PROVEDOR=openai`):

```powershell
$env:AGENTE_PROVEDOR = "bedrock"
.\.venv\Scripts\python.exe -m agente.avaliador
```

### Avaliação de regressão controlada

Executa uma variante degradada do prompt (`regressao-v1`) e salva separadamente em `resultados/avaliacao_regressao.json` sem sobrescrever o relatório principal:

```powershell
.\.venv\Scripts\python.exe -m agente.avaliacao_regressao
```

---

## Como interpretar os relatórios

Os relatórios JSON gerados em `resultados/` seguem esta estrutura:

- `data_execucao`: timestamp ISO 8601 com fuso horário.
- `modelo`: identificador do modelo executado.
- `variante_prompt`: identificador da variante de prompt (`null` na execução padrão, `"regressao-v1"` na regressão).
- `resumo`:
  - `total_casos`, `aprovados`, `reprovados`
  - `taxa_aprovacao_percentual`
  - `movimentacoes_esperadas`, `movimentacoes_extraidas`
- `casos`: lista com `id`, `status` (`"aprovado"` ou `"reprovado"`), contagens, `erro` e `divergencias` contendo:
  - `campo_divergente` (`descricao`, `valor`, `data`, `fonte.documento`, `fonte.pagina`)
  - `movimentacao_ausente`
  - `movimentacao_extra`

### Resultados registrados no repositório

| Execução | Arquivo | Casos | Aprovados | Reprovados | Taxa |
|---|---|---:|---:|---:|---:|
| Baseline OpenAI (`gpt-6.2-sol`) | `resultados/avaliacao_golden_set.json` | 20 | 20 | 0 | 100.0% |
| Regressão controlada (`regressao-v1`) | `resultados/avaliacao_regressao.json` | 20 | 9 | 11 | 45.0% |

---

## Como funciona o Quality Gate

Definido em `LIMITE_APROVACAO = 90.0` (`src/agente/avaliador.py`):

| Condição | Resultado | Código de saída |
|---|---|---:|
| Taxa de aprovação ≥ 90% | Aprovado | `0` |
| Taxa de aprovação < 90% | Reprovado | `1` |
| Lista de resultados vazia | Reprovado | `1` |

O relatório JSON é sempre persistido antes da verificação do Quality Gate, permitindo auditar falhas.

---

## Como configurar o AWS Bedrock

1. Configure suas credenciais AWS pelos mecanismos padrão do `boto3` (AWS CLI `aws configure`, perfil IAM, SSO ou variáveis de ambiente):

```env
AGENTE_PROVEDOR=bedrock
AWS_REGION=us-east-1
AWS_BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

2. Certifique-se de que o modelo Claude desejado está habilitado na região configurada do Amazon Bedrock.
3. Permissão IAM mínima necessária para a identidade executora:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
    }
  ]
}
```

> Caso utilize *cross-region inference profiles* (ex.: `us.anthropic.claude-...`), inclua também `arn:aws:bedrock:*:*:inference-profile/*` no `Resource`.

---

## Como configurar o Langfuse

Defina as variáveis no `.env` (ou no ambiente de execução):

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

Quando habilitado, `ObservadorLangfuse` registra para cada caso:
- `execucao_id` (UUID da execução), `provedor`, `modelo`, `versao_prompt`, `latencia_ms`;
- `usage_details` (`input` e `output` tokens, somente quando retornados pelo provedor);
- `cost_details` com `origem_custo` diferenciando `"real"`, `"estimado"` (tabela explícita por modelo no Bedrock) ou `"indisponivel"` (nunca inventa métricas);
- `level` (`"ERROR"` em falhas) e `status_message` com a mensagem de erro;
- Span final `avaliacao-golden-set` com o resumo e chamada a `flush()`.

Quando as chaves do Langfuse não estão configuradas, a aplicação usa `ObservadorNulo` automaticamente.

---

## Como executar a CI

O workflow em `.github/workflows/ci.yml` é acionado em `push` e `pull_request` na branch `main` e executa:

1. Instalação de dependências (`pip install -e ".[dev]"`).
2. `ruff check .`
3. `mypy src tests`
4. `pytest -v`
5. `python -m agente.validacao_ci` (executa o Quality Gate sobre `evals/casos_ouro.jsonl` com provedor determinístico controlado e grava o relatório apenas em diretório temporário, preservando `resultados/`).

Para reproduzir localmente a etapa de Quality Gate da CI sem custos:

```powershell
.\.venv\Scripts\python.exe -m agente.validacao_ci
```

---

## Limitações conhecidas

- **Entrada em texto**: o agente processa texto extraído; leitura direta de PDFs e OCR estão fora do escopo atual.
- **Golden Set sintético**: os 20 casos atuais são fictícios e não substituem validação em documentos reais.
- **Execuções reais com provedores externos**: chamadas reais à OpenAI, ao AWS Bedrock e envio real ao servidor Langfuse dependem de credenciais, cotas e permissões externas válidas; neste ambiente, ambos os provedores e a observabilidade foram validados localmente com mocks.
