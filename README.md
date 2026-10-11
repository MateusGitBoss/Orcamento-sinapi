# orcamento-sinapi

[![CI](https://github.com/MateusGitBoss/Or-amento-sinapi/actions/workflows/ci.yml/badge.svg)](https://github.com/MateusGitBoss/Or-amento-sinapi/actions/workflows/ci.yml)

Transforma uma lista de materiais escrita de qualquer jeito ("10 sacos cimento cp2", "1500 tijolo 8 furos") em orçamento com o código e o preço de referência do SINAPI de cada item, e separa o que precisa de conferência humana.

**Para quem não é técnico:** orçar uma obra pequena é pegar a lista que o mestre de obras mandou no WhatsApp e procurar, item por item, o material equivalente na tabela oficial de preços da Caixa (SINAPI). Este programa faz essa procura: entende a linha, acha os insumos parecidos na tabela, escolhe o certo e calcula o subtotal com o preço da tabela. Quando não tem certeza, ele não chuta: marca o item para revisão e deixa fora do total.

## Fluxo

```mermaid
flowchart LR
    L[lista.txt<br/>uma linha por item] --> E[Extração<br/>quantidade, unidade, material]
    E --> B[(Postgres<br/>busca full-text + trigramas)]
    B -->|até 5 candidatos| C[Escolha<br/>qual candidato, ou nenhum]
    C --> P[Preço do banco<br/>conversão de unidade]
    P --> R{confiança baixa,<br/>sem candidato ou<br/>unidade incompatível?}
    R -->|sim| V[REVISAR<br/>fora do total]
    R -->|não| T[Entra no total]
    T --> X[CSV / XLSX]
    V --> X
    I[Planilha SINAPI<br/>da Caixa] -->|orcamento importar| B
```

Extração e escolha têm duas versões com a mesma interface: **por regra** (grátis, previsível) e **por IA** (Claude Haiku, com cache). O conjunto de avaliação mede as duas.

## Regras que não se negociam

1. **O preço nunca vem da IA.** A IA só interpreta o texto e escolhe entre candidatos que o banco devolveu. Código que não está entre os candidatos é descartado.
2. **Item duvidoso não entra calado no total.** Confiança baixa, nenhum candidato ou unidade que não dá para converter com segurança (saco para kg depende do produto) vão para revisão.
3. **Medir antes de mudar.** `orcamento avaliar` roda um gabarito de 30 linhas e conta acertos, revisões e **erros calados** (código errado sem pedir revisão, o único erro que custa dinheiro).

## Exemplo

```text
$ orcamento orcar dados/exemplo/lista_reforma.txt --sem-ia
REVISAR  10 sacos cimento cp2                  1379 CIMENTO PORTLAND COMPOSTO CP II-32                    -
         motivo: maior nota da busca (0.30, 0.05 acima do segundo); pedido em SC, SINAPI em KG: conversão depende do produto
ok       2 m3 areia media                       370 AREIA MEDIA - POSTO JAZIDA/FORNECEDOR (R      R$ 190,00
ok       1500 tijolo 8 furos                   7271 BLOCO CERAMICO (ALVENARIA DE VEDACAO), 8    R$ 1.170,00
...
REVISAR  6 parafuso sextavado 3/8                 -                                                       -
         motivo: busca não achou candidatos

Total dos itens ok: R$ 3.557,80 (SINAPI MA 08/2026). Itens para revisar: 4.
```

Repare em "1500 tijolo": a tabela vende por milheiro, então o programa converte 1500 UN em 1,5 MIL antes de multiplicar.

## Avaliação

Conjunto em [`dados/avaliacao/conjunto.csv`](dados/avaliacao/conjunto.csv): 30 linhas no jeito que se escreve em obra, com o código SINAPI esperado (uma delas sem correspondência, para testar se o sistema sabe dizer "não achei").

| Modo | Acertos | Revisões | Erros calados |
|---|---|---|---|
| Regras (`--sem-ia`), medido | 22 (73%) | 7 (23%) | 1 (3%) |
| IA (Claude Haiku) | rode `orcamento avaliar` com `ANTHROPIC_API_KEY` | | |

O erro calado das regras é "fio flexível 2,5mm": a busca por palavras achou "eletroduto flexível" na frente do cabo. As revisões das regras são quase todas apelidos de obra ("cp2", "ferro 8mm", "ac3"), que é exatamente onde a extração por IA reescreve o texto no vocabulário do SINAPI.

**Importante:** a tabela de exemplo tem 61 insumos e **preços fictícios**, no layout da planilha da Caixa. O gabarito também é de exemplo. Para números que valem alguma coisa, importe a planilha oficial do mês e troque o gabarito por linhas reais de obra.

## Demonstração no navegador

A pasta `web/` tem uma página estática com o orçamento da lista de exemplo, os candidatos que a busca devolveu para cada linha, a avaliação contra o gabarito e a tabela de insumos. Tudo foi calculado pelo código Python (modo por regras, sem IA) sobre a tabela de exemplo com preços fictícios; a página só exibe e soma. Para regerar com o banco rodando e a tabela importada:

```bash
uv run python scripts/gerar_dados_web.py   # regrava web/dados/demo.json
python -m http.server -d web 8000          # abre em http://localhost:8000
```

## Como rodar

Pré-requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/) e Postgres (ou `docker compose`).

```bash
cp .env.example .env                 # DATABASE_URL e, para usar IA, ANTHROPIC_API_KEY
uv sync
uv run orcamento migrar
uv run orcamento importar dados/exemplo/SINAPI_exemplo_MA_202608.xlsx --referencia 2026-08
uv run orcamento buscar "tijolo 8 furos"
uv run orcamento orcar dados/exemplo/lista_reforma.txt --sem-ia --saida orcamento.xlsx
uv run orcamento orcar dados/exemplo/lista_reforma.txt            # com IA
uv run orcamento avaliar --sem-ia                                  # e sem a flag, com IA
```

Planilha oficial: baixe em [caixa.gov.br/sinapi](https://www.caixa.gov.br/poder-publico/modernizacao-gestao/sinapi/) a planilha de preços de insumos do estado e mês e importe com `--referencia AAAA-MM` e `--uf`. Se a Caixa mudar o layout, o ajuste fica em `COLUNAS` no `importador.py`.

### Testes e qualidade

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
DATABASE_URL_TESTE=postgresql://postgres:postgres@localhost:5432/orcamento_teste uv run pytest
```

Nenhum teste chama a API do Claude: as respostas são dublês (`tests/fakes.py`), incluindo recusa, JSON cortado e código inventado. Importação, busca e cache rodam contra Postgres de verdade (service container no CI).

## Decisões técnicas

- **Full-text + trigramas em vez de embeddings.** O full-text em português entende plural e radical; o trigrama tolera erro de digitação ("cimeto"). Somados, cobrem os dois pontos fracos, rodam dentro do Postgres e não custam nada por busca. Embeddings ajudariam com sinônimos, mas aqui a IA da extração já reescreve o apelido ("tijolo" vira "bloco cerâmico") antes da busca.
- **IA em duas etapas pequenas, não uma grande.** Extrair e depois escolher entre candidatos do banco deixa cada chamada simples de testar e impede a IA de inventar insumo.
- **Structured outputs + Pydantic.** A API garante o JSON no esquema; o Pydantic valida regras de negócio (quantidade > 0). Qualquer coisa fora disso vira revisão.
- **Cache com versão do prompt na chave.** A mesma linha não paga duas vezes e o resultado é reprodutível. Mudou o prompt, o cache antigo deixa de valer sozinho.
- **Conversão de unidade só quando é segura.** UN ↔ MIL e KG ↔ T são matemática; saco ↔ kg depende do produto e vai para revisão.
- **`COPY` na importação** e reimportação idempotente por UF e mês, numa transação: ou entra o mês inteiro, ou nada muda.

## Limitações conhecidas

- Tabela de exemplo pequena e com preços fictícios (o ambiente de desenvolvimento não acessa o site da Caixa).
- Só insumos. Composições (serviço com material + mão de obra, como "m² de alvenaria") ficaram fora.
- Os limiares de confiança do modo por regras foram calibrados na tabela de exemplo.
- O preço do SINAPI é referência para obra pública; obra particular costuma ter preço de mercado diferente.

## Como este projeto foi construído

Construído com o Claude Code como ferramenta de desenvolvimento, com cada mudança entrando por pull request. O roteiro de estudo em [`docs/ENTREVISTA.md`](docs/ENTREVISTA.md) explica cada decisão.

## Licença

MIT
