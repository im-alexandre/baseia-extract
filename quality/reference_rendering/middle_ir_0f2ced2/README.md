# Referência histórica de qualidade — Middle JSON → IR

Este diretório preserva um snapshot imutável da exploração feita em notebooks
no commit `0f2ced2`.

Ele serve como padrão de comparação para a reconstrução semântica e a
renderização de documentos derivados do `middle.json`, sem alterar nem depender
dos artefatos transitórios da extração atual.

## Conjunto de referência

O protótipo contém cinco documentos, totalizando:

- 43 páginas;
- 569 blocos de conteúdo;
- 60 blocos descartados preservados separadamente;
- 28 imagens;
- 10 gráficos;
- 6 tabelas;
- 19 fórmulas interlineares;
- 141 fórmulas inline.

Documentos:

1. `Chain-optimazation-pscc-2002`
2. `GLT_1332`
3. `10.1080_096031096334006`
4. `GEC_0012`
5. `GTM10`

## Conteúdo

- `artifacts/ir_prototype/**/document_ir.json`: cinco documentos canônicos;
- `artifacts/ir_prototype/validation_report.json`: validação documento a
  documento;
- `artifacts/ir_prototype/observed_types.json`: tipos observados;
- `artifacts/ir_prototype/summary.json`: métricas consolidadas;
- `notebooks/03_inspecao_middle.ipynb`: notebook executado, com a inspeção
  visual preservada;
- `notebooks/03_inspecao_middle.py`: fonte Jupytext em formato percent;
- `notebooks/04_build_ir_prototype.py`: conversão `middle.json` → IR;
- `notebooks/05_validate_ir.py`: validação e round-trip do IR;
- `data/samples/benchmark_smoke_sample.csv`: amostra smoke original.

## Proveniência e limitações

- Commit de origem: `0f2ced2`.
- Os arquivos são cópias exatas dos blobs Git desse commit.
- Os `middle.json` e recursos MinerU brutos de `artifacts/mineru/smoke` não
  estavam versionados e, portanto, não fazem parte deste snapshot.
- Os caminhos históricos gravados dentro dos JSON são metadados de
  proveniência e não devem ser tratados como caminhos atuais.
- Alterações futuras no padrão devem criar uma nova versão deste diretório, sem
  modificar silenciosamente esta referência.
