FAZENDA CLASSIFIER 1.1.0-rc4 — CANDIDATO PARA TESTE NO QGIS 3.36–3.x

Forest sampling tools for QGIS. Create metric plots, sample canopy height from
DSM/DTM, and optionally classify RGB patches using a user-supplied LeNet model.

INSTALAÇÃO PARA TESTE
1. Desative a versão antiga do Fazenda Classifier no gerenciador de complementos.
2. Complementos > Gerenciar e Instalar Complementos > Instalar a partir de ZIP.
3. Selecione fazenda_classifier_1.1.0-rc4.zip e ative Fazenda Classifier.
4. O comando Classificar Imagem aparece no menu Raster e na barra de ferramentas.
5. A instalação não precisa do arquivo .pth para gerar parcelas e alturas.

CORREÇÃO DE COORDENADAS
O projeto deve usar um SRC projetado em metros, adequado à área (por exemplo,
SIRGAS 2000 / UTM 22S para a área em questão). MDS e MDT precisam ter SRCs
válidos; podem estar em SRCs horizontais diferentes entre si e do projeto.
O plugin transforma as posições durante a leitura, sem reprojetar os arquivos.
Uma mudança de SRC com transformação suportada deixa de abrir avisos repetidos.
O Painel de Mensagens de Log registra os SRCs do projeto, MDS e MDT.
SRC ausente, transformação inválida ou unidades incompatíveis interrompem a operação.
As elevações do MDS e MDT devem estar em metros e no mesmo referencial vertical.
A transformação horizontal não corrige diferenças de datum vertical.

REGRA DE ALTURA
Mantém-se a janela de 1 m x 10 m. Agora são avaliados os centros reais dos
pixels do MDS contidos nessa janela. Obtém-se o maior valor válido do MDS e
lê-se o MDT na mesma localização física, convertida para seu próprio SRC.
As alturas podem mudar em relação à versão antiga, que usava posições
interpoladas por linspace e coordenadas sem conversão entre SRCs.
NoData, valores não finitos e alturas não positivas não são marcados como válidos.
O limite de 100.000 pixels por janela previne processamento acidental excessivo.

SAÍDAS
São preservados os nomes conglomerados_M37, subparcelas_M37 e pontos_altura_M37
para compatibilidade. O conglomerado permanece 100 x 100 m, com 10 subparcelas
e 100 pontos. Essa geometria não é a UA de 0,4 ha do IFN nem a parcela de
0,25 ha da FLONA. O plugin não executa a equação de carbono do artigo.
O CSV de alturas mantém as colunas antigas e acrescenta crs_trabalho, crs_mds,
crs_mdt e metodo_altura. Os campos x_utm/y_utm e x_mds_max/y_mds_max estão no
SRC de trabalho registrado, que pode ser um SRC projetado não UTM.
Dados gerados antes da correção não são recalculados ou certificados automaticamente.
Se mudar o SRC do projeto, use um novo conjunto de camadas ou retorne ao SRC
original. O plugin impede misturar coordenadas novas nas camadas antigas.
Salve as camadas temporárias como GeoPackage para preservá-las ao fechar o QGIS.

DEPENDÊNCIAS E MODELO OPCIONAL
Parcelas/alturas: NumPy e as bibliotecas fornecidas pelo QGIS.
Classificação: PyTorch estável >= 2.10.0, torchvision compatível e Pillow no Python do QGIS.
Consulte o seletor oficial https://pytorch.org/get-started/locally/ para uma
instalação compatível com seu Python/SO. O plugin não instala bibliotecas.
Não instale outra cópia de PyQt em substituição à fornecida pelo QGIS.
Funções legadas de segmentação do fazenda_model.py, quando chamadas diretamente,
também usam SciPy, OpenCV ou rasterio; esses imports foram tornados opcionais.

O arquivo fazenda_lenet_3classes_best.pth não está incluído no ZIP: o modelo
existente tem aproximadamente 139 MB, acima do limite de pacote do repositório.
Na primeira classificação, selecione seu arquivo .pth; o caminho fica salvo
nas configurações do QGIS. Não há download automático.
Classes e limiar preservados: Araucaria angustifolia, Cedrela fissilis,
Ocotea porosa; limiar operacional 0,60. A CNN e seus parâmetros não foram treinados
novamente. A inferência real precisa ser conferida com seu modelo instalado.
Pesos de terceiros precisam ter licença e procedência compatíveis com seu uso.

H5 E ESCOPO CIENTÍFICO
100 pontos de altura de superfície não equivalem a 100 árvores individuais.
O CSV não deve ser tratado automaticamente como H5 (mediana das cinco maiores
alturas de árvores identificadas) sem validar a correspondência dessa métrica.
A compatibilidade do plugin com o modelo CMIP6 não certifica a precisão local
desse modelo ou sua transferência para outras áreas.

TESTES
A RC4 passou por 52 testes automatizados em Python normal e otimizado, incluindo
coordenadas, pixels, NoData, medidas, estados, CSV e proteção das saídas. Os testes
de interface usam adaptadores mínimos da API e não substituem o QGIS real.
O ambiente de preparação não tem QGIS ou PyTorch: interface, PROJ real e
classificação CNN não foram executados aqui.
Para testar a integração real, no Console Python do QGIS execute:

    from fazenda_classifier.tests.smoke_qgis import run
    run()

A RC2 acrescenta três verificações de copa e estado às cinco de rasters.
O teste usa GeoTIFFs temporários sintéticos e não modifica seu projeto.
Faça também o roteiro de interface em TESTE_E_PUBLICACAO.txt antes de publicar.

LICENÇA DO CÓDIGO
GPL-2.0-or-later, texto integral em LICENSE. Essa licença não se aplica
automaticamente aos pesos externos ou aos dados de campo.

CORREÇÕES DA RC2 — ÁRVORE INDIVIDUAL
O teste de 02/11/2026 revelou exportação com Desconhecida e probabilidades vazias.
Esse estado não representava rejeição da CNN. Agora o CSV distingue nao_executada,
em_processamento (bloqueia exportação), erro_processamento e o status do modelo.
A seleção de outra árvore limpa medidas, polígono e inferência anteriores.
A ortofoto usada é a escolhida no combo RGB, mesmo com uma camada vetorial ativa.

1. Escolha MDS, MDT e ortofoto RGB nos controles.
2. Clique em Selecionar árvore e marque seu ponto dentro da copa.
3. Aguarde a classe e a confiança. Se cancelar a escolha do modelo ou ocorrer
   falha, as medidas ainda podem ser exportadas com o estado explícito da CNN.
4. Delimite a copa com ao menos três vértices distintos e sem cruzamentos.
5. Clique em Finalizar Delimitação e depois em Exportar dados da árvore CSV.
   Finalizar já não abre uma segunda rotina de salvamento.

A altura individual é MDS menos MDT NO PONTO SELECIONADO. Ela não é o máximo
sobre o polígono da copa nem usa a janela 1 x 10 m dos conglomerados. Diâmetro
é a maior distância entre vértices, não o diâmetro do círculo de área equivalente.
A área é a área plana do polígono no SRC projetado em metros. O ponto selecionado
precisa pertencer à copa. Mudança do SRC exige selecionar a árvore novamente.
O recorte individual mantém 256 pixels nativos reduzidos a 128 x 128 pixels.
A delimitação manual não altera o recorte usado pela CNN nesta versão.

Um único esquema CSV inclui área, diâmetro, vértices, ponto selecionado, leituras
MDS/MDT, estados, métodos e SRCs. O arquivo usa valores numéricos completos;
a tela exibe duas casas. A coordenada da árvore deixou de ser o primeiro vértice.
O CSV de espécies inclui crs_trabalho e crs_rgb. Reclassifique dados da RC1 para
registrar a origem RGB por amostra; não se inventa a origem dos registros antigos.
Caminhos de patches são temporários locais: salve os PNGs se quiser preservá-los.

TESTES OBSERVADOS NO QGIS DO AUTOR (RC2, 02/11/2026)
O autor executou as oito verificações de integração e forneceu a saída sem erros.
Também foram conferidos o fluxo individual e os CSVs de um conglomerado real,
com 100 pontos de altura e 625 recortes classificados. Isso não mede a acurácia
botânica ou a precisão de campo. Consulte docs/VALIDACAO.md no repositório.

CORREÇÕES DA RC3 — ANÁLISE AUTOMÁTICA
O Bandit 1.9.4 reproduziu 14 ocorrências na RC2. A RC3 substitui os asserts do
teste de integração por verificações unittest, que continuam ativas com python -O;
importa o módulo real da interface nos testes sem gerar código; e valida o campo
UA e o resultado da exclusão antes de reclassificar um conglomerado. Uma falha
na exclusão interrompe a operação com mensagem explícita para evitar duplicação.
Os 31 testes passaram em Python normal e otimizado. A análise local do Bandit
não apresentou ocorrências; nenhuma regra foi desativada. Os testes continuam
incluídos no pacote. O portal fará uma nova análise após o envio desta versão.
Repita as oito verificações de integração no QGIS após instalar a RC3 e reiniciar.

CORREÇÕES DA RC4 — PESOS, ARQUIVOS E PRESERVAÇÃO DOS RESULTADOS
A CNN bloqueia versões do PyTorch anteriores a 2.10.0, prévias e versões não
identificadas antes de importar torchvision ou abrir pesos. Não atualiza o Python
nem instala dependências. Seu ambiente com PyTorch 2.5.0 pode testar parcelas,
alturas e copas; o bloqueio da CNN nessa versão é esperado.
Uma atualização de PyTorch deve ser validada em uma instalação independente do
QGIS, com sua própria pasta Python e perfil de usuário. Apenas um novo perfil
não separa as bibliotecas da instalação. Par de referência CPU: torch 2.10.0 e
torchvision 0.25.0. Use pesos próprios ou de procedência confiável.

A RC4 grava apenas em camadas de memória identificadas como suas saídas. Ela
não adota camadas da RC3 nem arquivos de mesmo nome. Gere um novo conglomerado.
Camadas antigas permanecem disponíveis para comparação, e as novas podem ter
os mesmos nomes na legenda; o plugin usa sua própria identificação para escolhê-las.
Cada classificação usa uma pasta aleatória de temporários; UA não compõe nomes
de diretórios ou arquivos. Nenhuma pasta anterior é removida automaticamente.
Recortes de tentativas com falha também podem permanecer; seus caminhos são
informados para conferência e limpeza manual. CSVs podem revelar coordenadas e
caminhos locais. Compartilhamento e sincronização seguem as permissões da pasta.

A reclassificação é preparada em memória. Qualquer falha de recorte ou inferência
interrompe a tentativa antes de substituir a camada anterior. Uma gravação parcial
ou falha de registro da nova camada também interrompe a substituição. Amostras de
outras UAs são copiadas para a saída nova. Finalize edições manuais antes de
reclassificar. Classes, limiar 0,60, arquitetura, pesos, alturas e copas não foram
reajustados. O plugin fornece dados para modelos externos de carbono florestal,
AGC e climate studies; esta versão não calcula carbono nem projeções climáticas.

Integração RC4 no Console Python do QGIS (12 verificações; sem CNN real):
    from fazenda_classifier.tests.smoke_rc4 import run
    run()

Teste separado com seus pesos e pequenos recortes RGB:
    from fazenda_classifier.tests.smoke_model import run
    run()

Os testes nativos da RC4 e a comparação de probabilidades com a versão anterior
continuam pendentes até a execução no QGIS do autor. O resultado automático da
RC3 no portal não se transfere automaticamente para a RC4.
