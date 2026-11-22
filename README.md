# Fazenda Classifier

Complemento experimental do QGIS para inventário florestal e medições por sensoriamento remoto.

**Autor:** Leonardo Heraki  
**Versão:** 1.1.1 — edição pública de inventário, baseada na RC17  
**Licença:** GPL-2.0-or-later

## Ferramentas disponíveis

### Parcelas e alturas

- Parcelas de 100 × 100 m.
- Posicionamento, movimentação e rotação antes da confirmação.
- 100 janelas de amostragem de 1 × 10 m por parcela.
- Extração do máximo do modelo digital de superfície (MDS) em cada janela.
- Amostragem do modelo digital de terreno (MDT) na mesma posição física.
- Cálculo da altura pela diferença entre MDS e MDT.
- Exportação de alturas, coordenadas, sistemas de referência e indicadores de validade em CSV.

### Árvores individuais e copas

- Seleção do ponto da árvore e delimitação manual da copa.
- Altura MDS–MDT no ponto selecionado.
- Área plana da copa e maior distância entre seus vértices.
- Lista de árvores com identificadores, revisão e remoção de registros.
- Exportação do relatório de medições em CSV.
- Geração de GeoTIFFs de copas mascarados na resolução nativa da ortofoto.

Os GeoTIFFs são gravados em uma pasta temporária. Copie-os para uma pasta permanente para conservá-los; o CSV registra os caminhos, mas não incorpora as imagens.

## Escopo desta edição

Esta edição pública não inclui classificação de espécies por CNN, arquitetura de rede neural, carregamento de modelos ou pesos treinados.

As ferramentas de inventário funcionam sem PyTorch, torchvision ou Pillow.

## Requisitos

- QGIS 3.36 a 3.99, conforme a faixa declarada.
- NumPy e GDAL disponíveis no ambiente do QGIS.
- SRC de trabalho projetado em metros.
- MDS e MDT para as medições de altura.
- Ortofoto RGB para arquivar as imagens das copas.

QGIS 4 não está declarado compatível.

## Instalação pelo ZIP

1. Obtenha o pacote instalável `fazenda_classifier_1.1.1.zip`.
2. No QGIS, abra **Complementos → Gerenciar e Instalar Complementos → Instalar a partir de ZIP**.
3. Selecione o ZIP sem extraí-lo.
4. Reinicie o QGIS e confira a versão no painel.

O ZIP gerado pelo botão **Code → Download ZIP** do GitHub contém o repositório completo e não corresponde ao pacote instalável do plugin.

## Integração com Fazenda ECO

O perfil CSV de parcelas permite encaminhar as alturas para processamento externo no Fazenda ECO.

O relatório de árvores contém medições, sem identificação de espécies. Ele não é uma entrada pronta para cálculos que dependam da espécie: essa informação deve ser obtida independentemente e vinculada pelo identificador da árvore.

Consulte a [documentação dos CSVs](fazenda_classifier/CSV_FAZENDA_ECO.md).

## Limitações e interpretação

- Pontos amostrais raster não representam automaticamente árvores individuais.
- Diâmetro de copa não é DAP.
- O plugin não calcula H5, DAP, biomassa, AGC ou projeções climáticas.
- As transformações de coordenadas são horizontais; confira as unidades e referências verticais dos rasters.
- Os resultados precisam ser avaliados com dados de referência adequados à pesquisa.

## Verificações da edição 1.1.1

Foram aprovados 42 testes unitários e 5 testes de integração no QGIS 3.40.6, em Linux, com dados sintéticos.

Esses testes verificam o funcionamento do software e não substituem validação científica em campo ou conferência em outras plataformas.

Consulte o [registro das verificações](fazenda_classifier/VALIDACAO_PUBLICA.txt).

## Documentação e contato

- [Manual do plugin](fazenda_classifier/README.txt)
- [Página no repositório QGIS](https://plugins.qgis.org/plugins/fazenda_classifier/)
- [Relatar problemas](https://github.com/leonardoheraki/fazenda-classifier/issues)
