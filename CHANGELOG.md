# Changelog

## 1.1.1 — 2026-11-22

Edição pública experimental de inventário florestal, baseada na RC17.

- Mantém parcelas, posicionamento e rotação, alturas MDS–MDT,
  delimitação e medidas de copas, lista de árvores e exportação CSV.
- Inclui exportação de copas em GeoTIFF na resolução nativa.
- Remove a classificação de espécies, a arquitetura CNN,
  o carregamento de modelos e as dependências de aprendizado profundo.
- Não distribui pesos treinados.
- Mantém o perfil CSV de parcelas para integração com Fazenda ECO.
  O relatório de árvores contém medições sem identificação de espécie.

Verificação: 42 testes unitários e 5 testes de integração aprovados
no QGIS 3.40.6/Linux, com dados sintéticos. Esses testes não substituem
a validação científica de campo nem a conferência em outras plataformas.
