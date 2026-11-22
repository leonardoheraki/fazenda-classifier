# CSVs — Fazenda Classifier 1.1.2

Edição pública de inventário derivada da RC17. Há dois tipos de registro:
pontos amostrais de altura raster e árvores com copas delimitadas.

| Saída | Uma linha representa | Uso |
| --- | --- | --- |
| Alturas, perfil Fazenda ECO — Parcelas | Um ponto amostral raster | Fluxo externo de parcelas e alturas |
| Relatório completo dos pontos | Um ponto amostral raster, inclusive inválido | Conferência da amostragem |
| Relatório de árvores | Uma árvore selecionada com copa delimitada | Inventário e análises externas após identificação independente da espécie, quando necessária |

A exportação não combina pontos raster e árvores por proximidade, não atribui
espécie e não prediz DAP ou carbono. Não há exportação de grade de espécies.

## Parcelas

Na aba **Parcela**, confirme a posição e a orientação da parcela e clique em
**Exportar alturas CSV**. Escolha o perfil para o Fazenda ECO ou o relatório
completo dos pontos conforme a finalidade.

Os perfis de parcelas usam UTF-8 com BOM, separador ponto e vírgula e vírgula
decimal. Mantêm a precisão numérica e exportam valores ausentes como células
vazias. `perfil_csv`, `versao_csv`, `origem_dados` e `unidade_registro` informam
a procedência e o tipo de observação.

| Campo | Significado/unidade |
| --- | --- |
| `UA` | Identificador da parcela |
| `subparcela_id`, `ponto_id` | Identificadores da janela e do ponto |
| `altura_m`, `status` | Altura em metros e situação da amostragem |
| `x_utm`, `y_utm`, `crs_trabalho` | Coordenadas e SRC efetivo da camada |
| `x_mds_max`, `y_mds_max` | Posição do máximo do MDS usado |
| `mds_max`, `mdt_mdsmax` | MDS e MDT na mesma posição física, em metros |
| `largura_janela_m`, `comprimento_janela_m` | Dimensões da janela |
| `n_pixels_janela` | Número de pixels considerados |
| `crs_mds`, `crs_mdt`, `metodo_altura` | Procedência do cálculo |

O perfil Fazenda ECO exige pelo menos cinco alturas positivas, finitas e com
status válido por UA. O relatório completo permite exportar parcelas abaixo
desse mínimo para diagnóstico. Pontos inválidos não são convertidos em altura
zero; IDs duplicados e coordenadas inválidas impedem a exportação.

Cada parcela mede 100 m × 100 m e contém 100 janelas de 1 m × 10 m. A altura
é o máximo do MDS da janela menos o MDT na mesma posição. O plugin não calcula
H5 nem consulta bases climáticas. O uso dos pontos para predição externa de
carbono requer avaliação metodológica e validação próprias.

## Árvores e copas

1. Selecione a árvore e confira seu identificador e a UA, quando aplicável.
2. Delimite a copa e clique em **Concluir copa**.
3. Use **Adicionar outra árvore** para guardar a medição e continuar.
4. Clique em **Finalizar lista**, revise os registros e exporte o relatório CSV.

O relatório usa UTF-8 com BOM, separador vírgula e ponto decimal. Uma linha
corresponde a uma árvore, com identificação, altura, área e diâmetro máximo de
copa, coordenadas, SRCs e procedência das medições. A altura pode ficar vazia
quando não houver leitura válida. Copas incompletas não podem ser exportadas.

| Campo | Significado/unidade |
| --- | --- |
| `arvore_id`, `UA` | Identificador da árvore e parcela informada |
| `altura` | MDS menos MDT no ponto selecionado, em metros |
| `diametro_copa` | Maior distância entre vértices, em metros |
| `area_copa` | Área plana do polígono, em m² |
| `coord_tree`, `x_arvore`, `y_arvore` | Coordenadas da seleção |
| `crown_coords` | Vértices do polígono de copa |
| `crs_trabalho`, `crs_mds`, `crs_mdt`, `crs_rgb` | Sistemas de referência |
| `mds_no_ponto`, `mdt_no_ponto`, `status_altura` | Leituras e validade da altura |
| `metodo_altura`, `metodo_diametro`, `metodo_area` | Métodos de medição |
| `crown_tiff_path`, `crown_tiff_detail` | Caminho do GeoTIFF temporário da copa e eventual falha de gravação |

O ID automático identifica a seleção; substitua-o pelo código de campo quando
precisar relacionar dados externos. A UA é informada pelo usuário. A lista
bloqueia IDs repetidos na mesma UA e não reconhece automaticamente seleções
diferentes da mesma árvore.

**Diâmetro máximo de copa não é DAP.** O CSV não contém espécie, probabilidades
de classificação ou estimativas de AGC. Para análises que dependem da espécie,
vincule uma identificação independente pelo ID da árvore. Este relatório não
é uma entrada pronta do modo **Árvore por copa** do Fazenda ECO, pois não traz
a identificação exigida por aquele fluxo.

Os GeoTIFFs de copas são arquivos separados; o CSV só registra seus caminhos.
Copie os arquivos temporários para um destino permanente para conservá-los.
