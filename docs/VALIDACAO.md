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

A RC4 usa uma pasta temporária independente da UA e prepara resultados antes de
substituir uma classificação. Grava apenas em saídas próprias de memória, sem
adotar camadas de mesmo nome. Essas correções permanecem no pacote de teste.

Por orientação do autor, o candidato atualizado não bloqueia a classificação
pelo número da versão do PyTorch. O arquivo fazenda_model.py é idêntico ao da
RC3: mesma arquitetura, carregamento com weights_only=True, pré-processamento,
classes e limiar. O autor testou o par CPU 2.10.0/0.25.0; o roteiro permite voltar
ao par 2.5.0/0.20.0 com o ZIP da RC3 se houver incompatibilidade.

Os 51 testes automatizados passaram em Python normal e otimizado, com APIs
isoladas e uma CNN simulada. O carregador real foi exercitado com adaptadores
para versões 2.5 e 2.10, conferindo passagem dos pesos, dispositivo CPU, modo de
avaliação e manutenção de weights_only=True, sem tentar recarga insegura após erro.
Esses adaptadores não executam as bibliotecas PyTorch/torchvision nem a CNN real.

Foram simuladas falhas de recorte, inferência, gravação parcial e troca de camada.
Duas classificações de 625 amostras preservaram a outra UA sem acumular duplicatas.
Os testes de caminhos incluem separadores Windows/Unix e caminhos absolutos.

smoke_rc4.run() mantém 12 verificações nativas: oito de rasters/copa
e quatro de proteção das saídas em um projeto QGIS isolado, sem pesos treinados.
smoke_model.run() executa a CNN real com pesos e pequenos recortes selecionados
pelo autor; não contém bloqueio por versão.

Bandit 1.9.4 e detect-secrets 1.5.0 não apresentaram ocorrências na análise local,
sem suprimir regras e com verificação remota de segredos desativada. O conteúdo
do ZIP foi comparado ao código-fonte e seu CRC foi conferido.

### Evidência recebida do QGIS do autor

Em 03/11/2026, o autor forneceu o Console Python com PyTorch 2.10.0+cpu e
torchvision 0.25.0+cpu carregados sem erro no QGIS. A captura do gerenciador de
complementos confirmou a instalação da RC4. O roteiro smoke_rc4.run() concluiu
as 12 verificações, incluindo a substituição de camadas em projeto isolado.

Também foram recebidas capturas e três CSVs de execução real. A revisão local
dos CSVs encontrou:

- Uma árvore com inferência executada, altura coerente com MDS menos MDT, área e
  maior distância entre vértices coerentes com as coordenadas da copa e ponto
  selecionado dentro do polígono.
- Cem alturas válidas, dez por subparcela, sem coordenadas ou identificadores
  duplicados; os máximos exportados estão dentro das janelas declaradas e as
  diferenças MDS menos MDT correspondem às alturas.
- Seiscentos e vinte e cinco recortes RGB em grade 25 x 25, sem duplicatas ou
  erros de processamento; 515 aceitos e 110 abaixo do limiar. As probabilidades
  somam aproximadamente 1 e as classes/estados obedecem ao limiar 0,60.

A captura exibiu 0,60 para a árvore rejeitada, enquanto o CSV registrou confiança
0,597001, corretamente abaixo do limiar. O pacote de publicação altera apenas a
apresentação desse valor para 59,70%, preservando a precisão do CSV, o limiar e
o carregador/inferência byte a byte idênticos aos da RC3. O texto formatado foi
conferido localmente; a captura do autor antecede esse ajuste visual.

Não são publicados os CSVs, os rasters, as coordenadas de campo ou os pesos.
Os resultados demonstram execução no ambiente do autor e consistência dos
arquivos exportados. QGIS e PyTorch não estão instalados no ambiente de
preparação, e não houve repetição independente da inferência nem das leituras
dos rasters originais. A repetição real das 625 amostras sobre a mesma UA ainda
não foi demonstrada. Os testes simulados cobrem esse caso e a integração nativa
cobre a substituição de uma camada sintética. Não foi fornecida referência
botânica ou de alturas de campo para estimar acurácia.

### Exportação adicional de 16 conglomerados

O autor forneceu depois um CSV de alturas com 16 conglomerados, CG_001 a CG_016,
totalizando 1.600 pontos válidos. A revisão confirmou 100 pontos por conglomerado,
dez subparcelas com dez pontos em cada um, 1.600 coordenadas distintas e ausência
de inconsistências nas diferenças MDS menos MDT. Todos os máximos exportados
estão dentro das respectivas janelas de 1 x 10 m. Os registros de CG_001 são
idênticos aos do CSV anterior. Esse arquivo verifica geração e exportação de
alturas; não comprova a repetição das 625 classificações RGB sobre a mesma UA.
Somente os resultados agregados são registrados aqui; os dados não são distribuídos.


## RC5 — integração CSV com Fazenda ECO, 05/11/2026

Fonte de partida: main no commit a396ffd36ebecb8b61955e57125dd8eb4b506d95.
O app de destino foi o pacote Fazenda_ECO_copa_DAP_rev7_2026-11-05.zip,
SHA-256 ad778f205946d2d8eeb7e6149989ead9220299124b0e52adbd8247aaa0008b73.
Nenhuma mudança no app foi necessária para ler os novos perfis.

74 testes automatizados com o app rev7 disponível, incluindo cinco de HTTP.
20 verificações nativas com QGIS 3.40.6-Bratislava em Linux, Qt sem tela,
projeto isolado, geometria/rasters/camadas sintéticos e sem pesos de CNN.
O novo roteiro smoke_csv_eco inclui as 12 verificações anteriores de RC4,
a interface de identificação, rolagem, serialização e callbacks de exportação.

Os arquivos gerados pelos callbacks nativos foram enviados às rotas reais do
app por seu cliente de testes: árvore por copa, conglomerados e inventário por
DAP retornaram HTTP 200. Conferidos AC=48 m², H5=12 m e AGC_ref aproximado
0,873953409333213 Mg C/ha para os respectivos exemplos sintéticos. A grade de
classificação sem copas não é aceita como árvore individual. A ausência de
altura em uma árvore aceita produz somente DAP, sem carbono inventado.

Mantidos probabilidade/limiar com precisão completa, registros NoData para
auditoria e IDs textuais com zeros. A gravação padrão usa arquivo temporário e
substituição ao final, sem truncar um resultado anterior em falhas de validação.
A exportação lê atributos, sem adicionar campos ou editar a camada fonte.

Os códigos de inferência/carregamento e amostragem não foram alterados.
Não houve teste com dados de campo novos ou com o modelo treinado privado;
não se atribui acurácia botânica ou validação alométrica a estes testes.
A base de medições das parcelas da FLONA ainda não foi fornecida nesta etapa.


## RC6 — remoção do exportador de inventário medido, 05/11/2026

O botão Exportar inventário medido e seu callback/serializador foram removidos
do Classifier, junto das verificações exclusivas desse fluxo. O complemento
mantém as saídas de alturas dos conglomerados, árvores com copa e diagnóstico
de classificação em grade. A importação de medições de campo continua no
Fazenda ECO, cujo código não foi modificado por esta correção.

68 testes automatizados com o app rev7 disponível e 19 verificações nativas
no QGIS 3.40.6. Dados sintéticos; sem execução da CNN privada ou calibração
de equações. A nova identificação 1.1.0-rc6 distingue o pacote corrigido da RC5.


## RC7 — reorganização do painel nativo, 05/11/2026

O painel Qt passa a ter seletores MDS/MDT/RGB compartilhados e três abas:
Árvore individual, Conglomerados e Grade de espécies. Medidas de copa ficam
em cartões; ID/UA, exportação e estados permanecem próximos ao respectivo
fluxo. Há rolagem independente por aba e vírgula decimal somente na exibição.
Nenhum exportador de inventário medido foi reintroduzido.

Passaram 68 testes automatizados, incluindo quatro verificações HTTP com o
Fazenda ECO rev7, e 19 verificações nativas no QGIS 3.40.6-Bratislava em Linux.
O roteiro nativo confirmou o acesso aos três botões de exportação em uma
janela de 540 × 600 pixels, com os rasters compartilhados visíveis.

A revisão visual usou telas de 660 × 800 e 540 × 600 pixels, com rótulos e
valores fictícios. A imagem painel_rc7.png é uma demonstração visual sintética.
Não foram alterados os módulos de modelo, amostragem, geometria de copa ou
serialização CSV da RC6. Não houve teste de CNN privada, dados de campo novos
ou instalação no Windows do usuário nesta revisão.


## RC8 — parcelas e lista de árvores, 05/11/2026

O autor confirmou a instalação da RC7, validou o layout e forneceu um CSV de
copa e o resultado correspondente do Fazenda ECO. Foram conferidos o mesmo
identificador e a preservação de área, altura, DAP e AGC na rota de copas do
app rev7. Os arquivos privados e suas coordenadas não integram o repositório.
Essa conferência demonstra interoperabilidade de software, sem recalibrar ou
validar cientificamente as relações alométricas.

A RC8 acrescenta uma lista de árvores: Concluir copa, Adicionar outra árvore
ou Finalizar lista, revisão e remoção de registros, Nova lista e CSV com uma
linha por árvore. Cada inclusão guarda uma cópia independente da medição.
Foram conferidos IDs repetidos por UA, fechamento cancelado, cancelamento da
gravação e preservação dos registros. Uma árvore rejeitada impede o perfil
ECO integral; o relatório completo preserva os estados de todas as árvores.

A aba Parcela mostra Dimensões de 100 m × 100 m. No código anterior, as dez
geometrias de subparcelas eram faixas de 10 m × 100 m, enquanto cada leitura
de altura já utilizava uma janela de 1 m × 10 m. A RC8 desenha essas 100 janelas
na nova camada subparcelas_1x10_M37, com IDs SP_001 a SP_100. A verificação
nativa confirmou largura de 1 m, comprimento de 10 m e área de 10 m² em todas
as janelas, correspondência de IDs com os pontos e manutenção exata dos 100
centros amostrais. Uma camada antiga com polígono de 1.000 m² foi preservada
sem adoção ou reescrita. O algoritmo de leitura do MDS/MDT permanece igual.

Passaram 79 testes automatizados, incluindo seis de HTTP com o app rev7, e
25 verificações nativas no QGIS 3.40.6-Bratislava/Linux. Um CSV de três árvores,
gerado pelos botões nativos, foi aceito na rota do app com HTTP 200, mantendo
os três IDs e apenas DAP na árvore sem altura. O teste não executou a CNN
privada. As imagens da RC8 usam somente árvores fictícias.
