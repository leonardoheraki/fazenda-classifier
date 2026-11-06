# CSVs do Fazenda Classifier para o Fazenda ECO

Fazenda Classifier **1.1.0-rc8**, esquema CSV **1.0**. Destino testado:
**Fazenda ECO — Predição de carbono florestal, revisão 9**, de 05/11/2026.

## Escolha a saída conforme seus dados

| Saída no QGIS | Uma linha representa | Modo no Fazenda ECO |
| --- | --- | --- |
| Exportar alturas CSV | Ponto amostral de altura raster | Parcelas — Alturas e dados climáticos |
| Exportar árvores CSV, perfil Fazenda ECO | Uma árvore com copa delimitada e classificação aceita; várias linhas por arquivo | Árvore por copa |
| Exportar diagnóstico CSV | Um recorte RGB da grade | Diagnóstico da classificação; não é entrada de árvore individual |

Cada cálculo no app recebe **um CSV**, sem arquivo de apoio. A grade RGB não
contém copas individuais nem DAPs medidos. Não se combinam recortes e pontos
raster por proximidade para tratá-los como árvores.

## Formato e precisão

Os perfis novos usam **UTF-8 com BOM**, separador **ponto e vírgula** e
**vírgula decimal**. O Fazenda ECO rev9 lê esse formato diretamente.
Não é necessário renomear colunas ou converter o arquivo no Excel.
Coordenadas, alturas, áreas e probabilidades mantêm a precisão numérica.
Valores NULL do QGIS são exportados vazios. IDs textuais mantêm zeros à esquerda.

`perfil_csv`, `versao_csv`, `origem_dados` e `unidade_registro` identificam
o contrato e a unidade de observação; esses campos não entram nas equações.
O relatório completo das árvores mantém separador vírgula e ponto decimal,
também com UTF-8/BOM. Na RC8 acrescenta arvore_id e UA e reúne todas as
árvores da lista, incluindo classificações rejeitadas ou não executadas.

A gravação dos perfis novos prepara um arquivo temporário no destino e
substitui o CSV apenas depois de concluir a escrita. Falhas de validação ou
de substituição preservam um arquivo anterior. A exportação não edita a
camada fonte nem acrescenta campos a ela.

## Parcelas

Na aba **Parcela**, gere a parcela e escolha **Exportar alturas CSV**.
Na janela de gravação, mantenha o perfil **Fazenda ECO — Parcelas**.
No app, escolha **Parcelas — Alturas e dados climáticos** e envie o arquivo.

| Campo | Significado/unidade |
| --- | --- |
| `UA` | Identificador da parcela |
| `subparcela_id`, `ponto_id` | Identificadores originais do ponto |
| `altura_m` | Altura raster em m; não é uma árvore individual identificada |
| `status` | `valido` ou diagnóstico original do ponto |
| `x_utm`, `y_utm` | Coordenadas do ponto no SRC métrico da camada |
| `crs_trabalho` | SRC efetivo da camada de pontos, por exemplo EPSG:31982 |
| `x_mds_max`, `y_mds_max` | Localização do máximo usado na janela |
| `mds_max`, `mdt_mdsmax` | MDS e MDT na localização do máximo, em m |
| `largura_janela_m`, `comprimento_janela_m` | Dimensões da janela, em m |
| `n_pixels_janela` | Número de pixels considerados |
| `crs_mds`, `crs_mdt`, `metodo_altura` | Procedência do cálculo |

São necessárias **pelo menos cinco alturas positivas, finitas e com status
válido em cada UA** para o perfil Fazenda ECO. Os pontos inválidos também
permanecem no CSV para auditoria, sem converter NoData em altura zero.
Pontos duplicados ou coordenadas inválidas interrompem a exportação.
Um SRC declarado que conflite com o SRC da camada também provoca erro.

Se houver menos de cinco alturas válidas, escolha **Relatório completo dos
pontos** na janela de gravação. Esse perfil permite conferir a falha amostral;
ele não torna a parcela apta ao cálculo de H5.

O plugin não acrescenta H5, BIO8, BIO9 ou altitude como preditores: o app
calcula H5 e consulta suas bases incluídas. O H5 derivado desses pontos
raster continua experimental em relação ao H5 de árvores medidas em campo.

Cada parcela mede 100 m × 100 m. A RC8 desenha 100 subparcelas de 1 m × 10 m,
uma para cada janela de altura já usada nos 100 centros amostrais originais.
A camada nova `subparcelas_1x10_M37` tem IDs SP_001 a SP_100; faixas
antigas de 10 m × 100 m não são adotadas nem reescritas como novas janelas.
Os nomes internos do perfil CSV e as rotas do app mantêm a identificação
legada de conglomerados para preservar a compatibilidade com o Fazenda ECO rev9.

## Árvore por copa

1. Na aba **Árvore individual**, selecione a árvore, aguarde a classificação
   quando executada e delimite a copa.
2. Confira **Identificador da árvore** e, se necessário, **UA / parcela**.
3. Clique em **Concluir copa**. Use **Adicionar outra árvore** para guardar
   a medição e selecionar a próxima árvore; repita o fluxo para cada copa.
4. Ao terminar, clique em **Finalizar lista** e confira a tabela de árvores.
5. Clique em **Exportar árvores CSV**. Mantenha o perfil **Fazenda ECO — Árvore por copa** na janela de gravação.
6. No app, escolha **Árvore por copa** e envie o arquivo com todas as linhas.

O ID automático identifica a seleção realizada. Para relacionar a copa com
medições de campo ou revisitar uma árvore, substitua-o pelo código de campo
correspondente. Uma nova seleção cria outro ID; não há reconhecimento
automático de que dois cliques representam a mesma árvore.
UA é opcional e informada pelo usuário; não é inferida da última parcela gerada.
O botão exporta todas as árvores da lista finalizada, uma linha por árvore.
Cada medição é guardada de forma independente antes da próxima seleção.
IDs repetidos na mesma parcela bloqueiam a inclusão sem substituir registros.
A tabela permite remover uma árvore. Nova lista e o fechamento com dados não
exportados pedem confirmação; cancelar a gravação mantém a lista no painel.
Uma árvore sem classificação aceita bloqueia todo o perfil Fazenda ECO; use
o relatório completo para preservar também os diagnósticos dessas árvores.

| Campo | Origem/significado |
| --- | --- |
| `arvore_id` | ID editável da árvore/seleção |
| `UA` | Parcela/UA informada pelo usuário, opcional |
| `especie`, `final_class` | Mesma classe final aceita: Araucaria angustifolia, Cedrela fissilis ou Ocotea porosa |
| `area_copa_m2` | Área plana do polígono de copa, em m² |
| `altura_m` | MDS − MDT no ponto selecionado, em m, quando válido |
| `diametro_copa_max_m` | Maior distância entre vértices da copa, em m |
| `diametro_copa_equivalente_m` | `2 × sqrt(area_copa_m2 / pi)`, em m |
| `x_arvore`, `y_arvore`, `crs_trabalho` | Ponto selecionado e seu SRC |
| `predicted_class`, `confidence`, `threshold`, `status` | Predição e decisão originais da CNN |
| `prob_Araucaria_angustifolia`, `prob_Cedrela_fissilis`, `prob_Ocotea_porosa` | Probabilidades originais, de 0 a 1 |
| `crs_mds`, `crs_mdt`, `crs_rgb`, `mds_no_ponto`, `mdt_no_ponto` | Fontes e leituras |
| `status_altura`, `metodo_altura`, `metodo_diametro`, `metodo_area` | Situação e métodos de medição |
| `metodo_classificacao`, `patch_path`, `crown_coords`, `detalhe_classificacao` | Procedência e geometria |
| `especie_origem`, `calculo_disponivel` | CNN aceita; DAP e AGC ou somente DAP |

`area_copa_m2` é um alias já aceito pelo app para `area_copa`. A exportação
não inclui os dois nomes simultaneamente. Usa-se apenas `altura_m`, sem
repetir o alias `altura`. Isso evita colunas equivalentes duplicadas.

**Diâmetro máximo de copa não é DAP nem diâmetro circular equivalente.**
Os três descritores mantêm significados distintos. O exportador não prediz
DAP nem calcula AGC; essas etapas continuam no Fazenda ECO.

Sem altura válida, o perfil ainda pode ser exportado com classificação aceita:
o app calcula somente DAP e deixa o carbono vazio. Uma classificação rejeitada,
não executada, pendente ou com erro não é convertida em espécie aceita.
Nesses casos, escolha **Relatório completo da árvore** para obter as medidas
e o diagnóstico, inclusive sem modelo de CNN disponível.

A confiança e o limiar ficam em escala **0–1** no CSV. A porcentagem exibida
na interface não altera probabilidades nem o limiar operacional de classificação.
Os campos de DAP, AGC, biomassa e densidade da madeira não são inventados
ou preenchidos pelo Classifier.

As equações de DAP pela copa do app rev9 continuam experimentais; mudanças
de formato não calibram coeficientes nem validam inversões alométricas.

## Resultado de Árvore por copa → Inventário por DAP

Após processar as copas no Fazenda ECO revisão 9, salve o resultado
`resultado_copa_DAP_AGC.csv`. Esse arquivo é a entrada do fluxo
**Inventário por DAP**. O app lê `dap_cm`, espécie e procedência da equação,
sem recalcular os DAPs nem pedir que sejam digitados.

Se estiverem ausentes, complete UA, área representada em hectares e tipologia
FO/FOM/FOD no painel do app. UAs existentes e DAPs são preservados. A saída
agrupa as árvores pela UA e identifica os DAPs como preditos pela copa.
A seleção de copas não representa automaticamente todas as árvores da parcela.
O resultado do fluxo Parcelas/Alturas não é a entrada desse modo.

O Classifier não exporta inventário medido e não altera suas camadas para
acrescentar DAPs. A integração não calibra as equações nem valida sua transferência.

## Grade de espécies

Na aba **Grade de espécies**, **Exportar diagnóstico CSV** preserva todos os recortes,
inclusive rejeições, probabilidades, confiança, limiar, coordenadas e SRCs.
O perfil registra `unidade_registro=recorte_RGB_grade_nao_e_arvore`.
Não acrescenta `area_copa_m2`, altura de árvore ou DAP a recortes RGB.
Esse diagnóstico não pode ser usado no modo Árvore por copa do Fazenda ECO.

## Instalação e verificação

1. Guarde o pacote utilizado atualmente e salve suas camadas temporárias,
   se quiser preservá-las. Crie um perfil de teste separado no QGIS.
2. Nesse perfil, instale `fazenda_classifier_1.1.0-rc8.zip` em **Complementos →
   Gerenciar e Instalar Complementos → Instalar a partir de ZIP**.
3. Reinicie o QGIS e confirme a versão **1.1.0-rc8**.
4. Abra o Classifier, confira os rasters no topo e selecione a aba do fluxo.
   Cada aba tem rolagem própria; a exportação fica junto das medidas correspondentes.
5. Gere dados de teste, exporte o perfil adequado e carregue diretamente no
   modo correspondente do Fazenda ECO rev9, em `http://127.0.0.1:5002`.

Esta alteração não exige instalar bibliotecas Python adicionais ou trocar
pesos da CNN. Perfis de QGIS não isolam bibliotecas Python compartilhadas.
O ZIP não inclui pesos `.pth`/`.pt`, rasters ou medições privadas.

Para executar as verificações nativas no Console Python do QGIS:

```python
from fazenda_classifier.tests.smoke_csv_eco import run
run()
```

Resultado observado no ambiente de desenvolvimento: **25 verificações nativas
no QGIS 3.40.6** e **79 testes automatizados** com o app rev9 disponível.
Além dos testes por serializador, os CSVs de árvores e parcelas produzidos pelos callbacks
nativos foram aceitos pelas rotas reais do app, com HTTP 200 e conferência
numérica dos resultados. A CNN privada não foi executada nesses testes.
A instalação Windows/QGIS 3.36 do usuário ainda deve ser conferida.

O tratamento de NULL usa `QgsVariantUtils.isNull`, disponível no
[QGIS 3.36](https://api.qgis.org/api/3.36/classQgsVariantUtils.html).
O contrato CSV, as fontes de altura e os avisos metodológicos continuam
distintos da validação científica das equações ou da classificação de espécies.
