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
incluídas na faixa de compatibilidade declarada.

Após informar a instalação da RC3, o autor forneceu nova captura do Console
Python em 02/11/2026, mostrando novamente as oito verificações concluídas sem
erros. Essa evidência registra a repetição do teste sintético no ambiente do
autor; não demonstra por si só a reclassificação de uma UA real sem duplicação
de amostras, nem mede a acurácia botânica ou a precisão das alturas em campo.

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

## RC4 — 03/11/2026

A RC4 trata os riscos identificados depois da análise automática da RC3:
versões afetadas do PyTorch, diretório temporário derivado da UA, exclusão de
resultados antes do sucesso e adoção de camadas apenas pelo nome.

Os 52 testes automatizados passaram com Python normal e `python -O`. Eles incluem
adaptações isoladas de QGIS/Qt e uma CNN simulada. A comparação de versões bloqueia
2.5.0+cpu antes de abrir pesos ou importar torchvision. Os testes de caminhos cobrem
separadores Unix/Windows, caminhos absolutos, compartilhamentos e identificadores
vazios. A substituição usa uma camada de memória preparada, verifica a gravação
completa e preserva as outras UAs. Foram simulados gravação parcial, recusa do
projeto, falha depois de destacar a camada antiga, edição manual ativa, erro de
recorte e erro de inferência. Duas classificações simuladas de 625 amostras não
acumularam registros para a mesma UA.

Os três testes antigos de exclusão por UA foram substituídos por verificações de
preservação e substituição, porque a RC4 não exclui registros do provedor anterior.
As regras de alturas, copa e CSV das versões anteriores continuam cobertas.

`smoke_rc4.run()` inclui os oito testes nativos anteriores e quatro adicionais,
com projeto QGIS isolado. `smoke_model.run()` testa a CNN real somente com uma
versão suportada do PyTorch e pesos/recortes escolhidos pelo autor. A presença
no pacote não significa que esses roteiros tenham sido executados neste ambiente.

Limites: QGIS e PyTorch não estão instalados no ambiente de preparação. Não houve
execução independente do modelo treinado, validação de DLLs no Windows nem teste
nativo da RC4 no QGIS do autor. Com seu PyTorch 2.5.0+cpu, a CNN deve ficar bloqueada;
parcelas, alturas e copas podem ser testadas antes de mudar as bibliotecas.
A comparação com PyTorch 2.10.0/torchvision 0.25.0 deve usar instalação e perfil
separados, os mesmos pesos e recortes, preservando o ambiente de trabalho.

Análise estática local da RC4: Bandit 1.9.4 sem ocorrências ou erros; varredura
com detect-secrets 1.5.0 sem ocorrências nas regras padrão e sem verificação remota.
Nenhuma regra foi suprimida. O pacote contém os testes e seu conteúdo foi comparado
com o código-fonte, com CRC conferido. Esses resultados não são auditoria completa
nem aprovação automática ou manual do portal QGIS.
