"""Gera os dados da demonstração web (web/dados/demo.json) rodando o sistema de verdade.

A página em web/ é estática: não tem Python nem banco no navegador. Por isso os resultados
são calculados aqui, pelo mesmo código da linha de comando (modo por regras, sem IA), e
gravados em JSON. Se a regra mudar, rode de novo e a demonstração acompanha.

    uv run python scripts/gerar_dados_web.py
"""

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from orcamento.avaliacao import avaliar, carregar_conjunto
from orcamento.busca import buscar_candidatos
from orcamento.config import get_settings
from orcamento.db import conectar
from orcamento.escolha import EscolhaRegra
from orcamento.extracao import ExtratorRegra
from orcamento.importador import ultima_referencia
from orcamento.orcamento import Orcamentista

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "web" / "dados" / "demo.json"

# Linhas extras para quem quiser montar outra lista na demonstração
EXTRAS = [
    "3 m3 brita 1",
    "20 barras ferro 10mm",
    "8 h eletricista",
    "100 m fio flexivel 2,5mm",
    "2 caixa d'agua 1000 litros",
    "30 m2 piso ceramico",
    "6 kg prego 18x27",
    "1 milheiro bloco concreto",
]


def _json(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, dict):
        return {k: _json(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_json(v) for v in valor]
    return valor


def main() -> None:
    settings = get_settings()
    with conectar(settings.database_url) as conn:
        referencia = ultima_referencia(conn, settings.uf)
        if referencia is None:
            raise SystemExit("Importe a tabela de exemplo antes: uv run orcamento importar ...")

        def buscar(texto: str) -> list:
            return buscar_candidatos(
                conn, texto, settings.uf, referencia, settings.candidatos_por_item
            )

        orcamentista = Orcamentista(
            ExtratorRegra(), EscolhaRegra(), buscar, settings.uf, referencia
        )
        extrator = ExtratorRegra()

        lista_reforma = [
            linha.strip()
            for linha in (RAIZ / "dados/exemplo/lista_reforma.txt").read_text("utf-8").splitlines()
            if linha.strip() and not linha.lstrip().startswith("#")
        ]
        casos = carregar_conjunto(RAIZ / "dados/avaliacao/conjunto.csv")
        relatorio = avaliar(orcamentista, casos)

        linhas: dict[str, Any] = {}
        for texto in [*lista_reforma, *(c.linha for c in casos), *EXTRAS]:
            if texto in linhas:
                continue
            item = extrator.extrair(texto)
            candidatos = buscar(item.descricao) if item else []
            linhas[texto] = {
                "resultado": asdict(orcamentista.orcar_linha(texto)),
                "candidatos": [asdict(c) for c in candidatos],
            }

        insumos = conn.execute(
            "SELECT codigo, descricao, unidade, preco_centavos FROM insumos_sinapi"
            " WHERE uf = %s AND referencia = %s ORDER BY descricao",
            (settings.uf, referencia),
        ).fetchall()

    dados = {
        "uf": settings.uf,
        "referencia": referencia.strftime("%m/%Y"),
        "modo": "regras (sem IA)",
        "insumos": [dict(i) for i in insumos],
        "listas": {
            "reforma": lista_reforma,
            "avaliacao": [c.linha for c in casos],
            "extras": EXTRAS,
        },
        "linhas": linhas,
        "avaliacao": {
            "total": relatorio.total,
            "acertos": relatorio.acertos,
            "revisoes": relatorio.revisoes,
            "erros_calados": relatorio.erros_calados,
            "casos": [
                {
                    "linha": r.caso.linha,
                    "esperado": r.caso.codigo_esperado,
                    "obtido": r.obtido.codigo,
                    "confianca": r.obtido.confianca,
                    "tipo": r.tipo,
                }
                for r in relatorio.resultados
            ],
        },
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(_json(dados), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(linhas)} linhas, {len(insumos)} insumos -> {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
