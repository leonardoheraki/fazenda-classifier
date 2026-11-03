# Registro de validação — 02/11/2026

Este registro descreve os testes observados durante a revisão do complemento.
Resultados de execução e consistência numérica não estimam acurácia botânica
ou a precisão das alturas em relação a medições de campo.

## Testes automatizados

Na RC2 foram concluídos 28 testes de lógica numérica, estado e exportação, com
adaptadores mínimos da API do QGIS. Esses testes não executam a interface real,
PROJ/GEOS do QGIS ou a CNN com os pesos treinados.

Na RC3, os 31 testes passaram em Python normal e com `python -O`. Os três testes
adicionados cobrem a exclusão apenas da UA escolhida, a preservação das amostras
quando falta o campo UA e a interrupção quando o provedor recusa a exclusão.
O adaptador agora importa o módulo completo da interface com APIs isoladas;
não gera trechos de código para execução. Os testes de integração passaram a
usar `unittest` para não serem desativados pela otimização do Python.

## Análise de segurança da RC3

A RC2 foi submetida ao portal QGIS, que mostrou bloqueio no Bandit com 14
ocorrências. As outras quatro verificações do portal foram concluídas sem
apontamentos na captura fornecida pelo autor.

O Bandit 1.9.4 reproduziu localmente 14 ocorrências no mesmo código: B101 (12),
B102 (1) e B112 (1). Após os ajustes da RC3, a análise local do código não
apresentou ocorrências nem erros de leitura. Nenhuma regra foi ignorada e os
testes continuam no pacote. O resultado local não certifica a segurança integral
do complemento e não equivale à aprovação do portal.

## Integração no QGIS do autor

Na RC2, o autor executou `fazenda_classifier.tests.smoke_qgis.run()` e forneceu a saída
com as oito verificações abaixo concluídas:

1. SRC idêntico: máximo em um centro real de pixel e altura sintética de 49,2 m.
2. MDS projetado e MDT geográfico lidos na mesma localização física.
3. Três SRCs: trabalho EPSG:31982, MDS EPSG:32722 e MDT EPSG:4326.
4. NoData não tratado como altura válida.
5. SRC geográfico de trabalho rejeitado.
6. Copa sintética válida: 48 m², diâmetro máximo de 10 m e ponto interno.
7. Copa com cruzamento de arestas rejeitada pelo GEOS.
8. Inferência ausente explicitamente registrada, com área e SRC preservados no CSV.

Saída informada: `Integração QGIS: 8 verificações concluídas.`
Isso documenta o ambiente do autor; não certifica todas as versões e plataformas
incluídas na faixa de compatibilidade declarada. A repetição dessas oito
verificações no QGIS com a RC3 ainda não foi observada neste registro.

## Fluxos com rasters reais na RC2

O autor forneceu CSVs e uma captura da interface após executar a seleção de
árvore, a classificação RGB, a delimitação da copa e a exportação. Foram
conferidos MDS − MDT, maior distância entre vértices, área do polígono, ponto
interno, probabilidades, regra do limiar e registro de coordenadas/SRCs.

No teste de conglomerado foram conferidos cem pontos de altura, dez por
subparcela, e 625 recortes RGB. Os CSVs apresentaram coordenadas únicas, máximos
dentro das janelas correspondentes, diferença MDS − MDT consistente, classes e
estados coerentes com o limiar e campos de SRC preenchidos.

Os rasters originais e os pesos não foram disponibilizados neste ambiente de
revisão. Não houve reprodução independente da inferência nem das leituras
nativas dos rasters reais. A identificação botânica de referência não foi
fornecida. Os dados de campo e os recortes não integram o repositório.

## Verificações adicionais

Ainda é útil documentar: seleção consecutiva de árvores na interface real;
reclassificação do mesmo conglomerado sem duplicar amostras; comportamento em
outras plataformas e versões; referência de campo independente para espécies
e alturas. A aprovação no repositório QGIS é uma etapa posterior.
