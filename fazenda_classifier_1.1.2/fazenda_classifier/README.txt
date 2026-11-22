FAZENDA CLASSIFIER 1.1.2 — INVENTÁRIO FLORESTAL

Edição pública experimental derivada das ferramentas de inventário da RC17.
Autor: Leonardo Heraki. Licença: GPL-2.0-or-later.
Faixa declarada: QGIS 3.36–3.99. QGIS 4 não está declarado compatível.

Esta edição disponibiliza medições e exportações de inventário. Não inclui
classificação de espécies, arquiteturas de redes neurais, carregamento de modelos,
pesos ou dependências de aprendizado profundo.

INSTALAÇÃO
1. Salve as camadas temporárias e os dados da sessão atual que desejar conservar.
2. No QGIS, abra Complementos > Gerenciar e Instalar Complementos >
   Instalar a partir de ZIP e selecione fazenda_classifier_1.1.2.zip.
3. Reinicie o QGIS e confira a versão 1.1.2 no painel.
4. Carregue MDS, MDT e, para arquivar imagens de copas, a ortofoto RGB.
5. Use um SRC de trabalho projetado em metros. Confira as camadas selecionadas.

A instalação utiliza os componentes do QGIS, NumPy e GDAL. Não requer
PyTorch, torchvision ou Pillow. Instalar pelo repositório requer que a versão
esteja publicada/aprovada e que complementos experimentais estejam habilitados.

PARCELA
Clique em Gerar parcela no mapa e marque o centro. Use Mover para reposicionar
a prévia; clique no novo centro. Use Girar e clique no mapa para orientar a
parcela, ou preencha Azimute. Fixar parcela confirma a posição e executa a
amostragem. Cancelar, Esc ou o botão direito descartam a prévia.

Cada parcela mede 100 m × 100 m e contém 100 janelas de amostragem de altura
com dimensões de 1 m × 10 m. O azimute parte do norte do SRC do projeto e
cresce no sentido horário. A orientação é registrada em azimute_graus.
A altura amostral é o máximo do MDS na janela menos o MDT na mesma posição
física. Pontos raster não são automaticamente árvores individuais.

Exportar alturas CSV oferece o perfil Fazenda ECO — Parcelas, que exige
cinco alturas positivas, finitas e válidas por UA, e o relatório completo dos
pontos, que permite inspecionar parcelas com menos de cinco alturas válidas.

ÁRVORE INDIVIDUAL
Selecione o centro da árvore, confira ID/UA, delimite a copa e clique em
Concluir copa. Adicionar outra árvore guarda a medição e inicia a próxima.
Finalizar lista permite revisar e exportar todas as árvores em um CSV.
IDs repetidos na mesma UA são rejeitados. A lista permite remover registros.

As medidas incluem altura MDS–MDT no ponto selecionado, área plana da copa e
maior distância entre seus vértices. O diâmetro máximo de copa não é DAP.
Copas concluídas podem gerar GeoTIFFs mascarados na resolução nativa da
ortofoto, preservando georreferenciamento. Esses arquivos são temporários:
copie os arquivos apontados no relatório para uma pasta durável se quiser
conservá-los. O CSV não incorpora os bytes das imagens.

O relatório de árvores contém apenas medições e sua procedência. Não atribui
espécie nem calcula DAP, AGC ou biomassa. Para cálculos externos dependentes
da espécie, obtenha identificação independente e vincule-a pelo ID da árvore.
O relatório não é apresentado como entrada pronta do fluxo Árvore por copa
do Fazenda ECO, que exige informações adicionais.

LIMITES E REPRODUTIBILIDADE
As transformações de SRC são horizontais. Confira unidades verticais e datum
dos rasters. NoData não deve ser interpretado como altura zero. Medidas por
sensoriamento remoto não substituem validação com dados de campo.

O plugin não calcula H5, preditores climáticos, AGC ou projeções climáticas.
O perfil de parcelas pode alimentar análises externas no Fazenda ECO.
Esta edição preserva os métodos de medição da RC17; a remoção da classificação
não constitui nova validação científica. Testes anteriores de outras versões
não certificam automaticamente esta distribuição. Execute a conferência nativa
descrita em TESTE_E_PUBLICACAO.txt antes de publicação.

Consulte CSV_FAZENDA_ECO.md para os campos e formatos de exportação.
