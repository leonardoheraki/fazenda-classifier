FAZENDA CLASSIFIER 1.1.0-rc8 — CSV PARA FAZENDA ECO REV9

Complemento experimental para QGIS 3.36–3.x. Testes nativos desta revisão
executados com QGIS 3.40.6 em Linux; funcionamento e CSVs confirmados pelo autor no Windows.
Autor: Leonardo Heraki. Licença: GPL-2.0-or-later.

INSTALAÇÃO
1. Guarde a versão atual e use um perfil de teste separado do QGIS.
2. Complementos > Gerenciar e Instalar Complementos > Instalar a partir de ZIP.
3. Instale fazenda_classifier_1.1.0-rc8.zip, ative e reinicie o QGIS.
4. Leia CSV_FAZENDA_ECO.md deste pacote para os campos e o passo a passo.
Perfis não isolam bibliotecas Python compartilhadas. Não é necessário trocar
pacotes Python ou pesos para usar as alterações de exportação CSV.

PAINEL
MDS, MDT e RGB ficam no topo, compartilhados pelas três abas:
- Árvore individual: seleção, delimitação, medidas de copa, ID/UA e CSV.
- Parcelas: geração no mapa, amostragem de alturas e CSV.
- Grade de espécies: classificação e CSV de diagnóstico dos recortes RGB.
Cada aba tem rolagem própria. Cartões destacam altura, área e diâmetro máximo.
As medidas na tela usam vírgula decimal; a precisão do CSV é preservada.
Após Concluir copa, escolha Adicionar outra árvore ou Finalizar lista. Confira
as árvores na tabela e use Exportar árvores CSV. Nova lista inicia outro arquivo
após confirmação. O painel avisa ao fechar uma lista ainda não exportada.
Parcela: 100 m × 100 m. Subparcelas: 100 janelas de 1 m × 10 m, nos mesmos
centros dos 100 pontos originais. Camadas antigas de faixas são preservadas.

DEPENDÊNCIAS E MODELO EXTERNO
Parcelas, alturas e medidas de copa usam QGIS e NumPy. A classificação opcional
usa PyTorch, torchvision compatível e Pillow no Python utilizado pelo QGIS.
O modelo externo precisa ser um state_dict da arquitetura Fazenda LeNet,
com as três classes Araucaria angustifolia, Cedrela fissilis e Ocotea porosa,
na ordem e com o pré-processamento definidos em fazenda_model.py.
O limiar operacional permanece 0.60 e o carregamento usa weights_only=True.
Não há bloqueio pelo número da versão do PyTorch. Os pesos treinados privados
não são fornecidos neste pacote. A exportação de relatório completo permite
obter medidas e diagnóstico da árvore sem classificação executada.

PERFIS DE CSV
- Parcelas: um ponto amostral raster por linha, com altura_m, status,
  UA, subparcela_id, ponto_id, x_utm, y_utm e crs_trabalho. Cinco alturas
  válidas por UA são exigidas pelo perfil para o app. Um relatório de
  diagnóstico permanece disponível quando há menos de cinco alturas.
- Árvore por copa: uma ou mais árvores delimitadas e com classificação aceita por
  arquivo; cada árvore ocupa uma linha. Usa arvore_id editável, UA opcional, especie, area_copa_m2 e
  altura_m. Distingue diâmetro máximo e circular equivalente. Sem altura,
  o app calcula apenas DAP. Rejeições ficam no relatório completo separado.
- Grade de espécies: diagnóstico de recortes RGB, não árvores delimitadas.
  Não contém área de copa, DAP ou altura de árvore inventados.

Os perfis novos usam UTF-8/BOM, ponto e vírgula e vírgula decimal. Confiança,
limiar, probabilidades e medidas mantêm precisão completa. A confiança em
porcentagem exibida na interface não altera a escala 0–1 do CSV.
O relatório completo de árvore mantém o formato legado, também documentado.
O Fazenda ECO revisão 9 aceita as novas saídas sem renomear colunas e sem
CSV de apoio. O Classifier não calcula AGC, H5 ou projeções climáticas.

MEDIÇÕES E RESULTADOS
Altura das parcelas: máximo do MDS em centros de pixels na janela de
1 × 10 m, menos MDT na mesma posição física. Árvore individual: MDS menos
MDT no ponto selecionado. Rasters em SRCs distintos recebem transformação
horizontal. O SRC de trabalho precisa ser projetado e métrico.
Copa: área plana do polígono e maior distância entre vértices; o diâmetro
máximo não é DAP nem diâmetro circular equivalente.
Resultados continuam em camadas próprias de memória. Salve-as, por exemplo
em GeoPackage, quando desejar preservá-las. Camadas externas não são adotadas
como resultados próprios. A exportação lê atributos e não edita a origem.

VERIFICAÇÃO
79 testes automatizados com o Fazenda ECO rev9 disponível, incluindo seis
testes de HTTP. Sem o app, seis testes são ignorados. No Console do QGIS:
    from fazenda_classifier.tests.smoke_csv_eco import run
    run()
O roteiro completou 25 verificações nativas em projeto isolado e com dados
sintéticos. Os CSVs de árvores e parcelas produzidos pelos callbacks nativos foram
aceitos nas rotas do app (HTTP 200) e seus resultados numéricos conferidos.
No app rev9, o resultado de Árvore por copa entra em Inventário por DAP.
Os DAPs são importados desse resultado; UA, área e tipologia são completadas
no app quando ausentes. O Classifier não exporta inventário medido. A CNN privada não foi executada. A implementação não representa calibração
ou validação científica; os dados de medição das parcelas da FLONA ainda
não foram recebidos nesta etapa. Inferência e algoritmos de amostragem não
foram modificados. Nenhuma dependência foi acrescentada.

TESTE E RETORNO
Veja TESTE_E_PUBLICACAO.txt. Para preservar a instalação de trabalho, teste
em outro perfil; para retornar, reinstale o ZIP anterior que você guardou e reinicie.
