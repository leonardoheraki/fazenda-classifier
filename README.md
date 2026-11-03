# Fazenda Classifier

QGIS plugin for forest sampling, canopy-height measurements from DSM/DTM rasters,
manual crown measurements, and optional RGB patch classification with a
user-supplied Fazenda LeNet model. Measurements and exports support external
forest carbon, aboveground carbon (AGC), and climate studies; the plugin does
not calculate AGC or run climate projections.

**Author:** Leonardo Heraki. **Version:** 1.1.0-rc4, experimental.
Proposed compatibility range: QGIS 3.36 to 3.x. QGIS 4 has not been validated.

## Funcionalidades

- Geração de conglomerados de 100 × 100 m, com dez subparcelas e cem pontos.
- Altura nos conglomerados: máximo do MDS entre centros de pixels na janela de
  1 × 10 m, menos o MDT na mesma localização física.
- Leitura de rasters em SRCs diferentes mediante transformação horizontal.
- Medidas de copa delimitada manualmente: área plana e maior distância entre
  vértices. Na árvore individual, a altura é MDS − MDT no ponto selecionado.
- Classificação opcional de recortes RGB em *Araucaria angustifolia*,
  *Cedrela fissilis* e *Ocotea porosa*, com limiar operacional de 0,60.
- Exportação CSV de medidas, estados, probabilidades, métodos e SRCs.

## Instalação

Use um ZIP instalável com a pasta raiz `fazenda_classifier/` em
**Complementos → Gerenciar e Instalar Complementos → Instalar a partir de ZIP**.
O ZIP completo deste repositório tem outra estrutura: gere o pacote instalável
com o comando abaixo ou use um pacote disponibilizado nas versões do projeto.

```bash
python scripts/build_plugin.py
```

A saída fica em `dist/fazenda_classifier_1.1.0-rc4.zip`.
Reinicie o QGIS depois de substituir uma versão já carregada.
Salve camadas temporárias como GeoPackage se quiser preservá-las.
A RC4 cria seu próprio conjunto de camadas de memória. Camadas de versões
anteriores, camadas importadas e arquivos com os mesmos nomes não são adotados
para gravação nem exportados como novas saídas da RC4. Gere um novo conglomerado
para testar esta versão. As camadas anteriores podem continuar no projeto.
Use um perfil de teste separado para preservar a instalação do complemento usada
no trabalho. O perfil, sozinho, não isola as bibliotecas Python compartilhadas.

## Dependências e modelo

Parcelas, alturas e medidas de copa usam QGIS e NumPy. Para a classificação,
instale PyTorch estável ≥ 2.10.0, torchvision compatível e Pillow no Python utilizado pelo
QGIS. Consulte o [seletor oficial do PyTorch](https://pytorch.org/get-started/locally/)
para escolher a combinação compatível com seu Python e sistema operacional.
O complemento não instala dependências automaticamente.
A RC4 bloqueia a CNN antes de abrir pesos se encontrar PyTorch anterior a 2.10.0,
uma versão de prévia ou uma versão que não consiga identificar. Parcelas, alturas
e copas continuam disponíveis sem a CNN. A restrição segue o aviso
[GHSA-63cw-57p8-fm3p](https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p).

O par PyTorch 2.10.0 / torchvision 0.25.0 para CPU é uma combinação oficialmente
publicada, ainda não validada com os pesos do autor neste ambiente. Teste em uma
segunda instalação do QGIS com Python e perfil próprios antes de alterar o ambiente
de trabalho. Compare as classes e probabilidades dos mesmos recortes; resultados
numericamente idênticos entre versões não são garantidos.

Os pesos `.pth` não estão incluídos neste repositório. Na primeira classificação,
selecione seu modelo Fazenda LeNet compatível; o caminho fica nas configurações
do QGIS. A arquitetura e a ordem das classes precisam corresponder aos pesos.
Consulte o [manual do complemento](fazenda_classifier/README.txt).

## Uso

1. Abra os rasters MDS, MDT e a ortofoto RGB. Use um SRC de trabalho projetado,
   com unidades em metros e adequado à área.
2. Confira os rasters escolhidos nos controles do complemento.
3. Para conglomerados, clique em **Gerar Conglomerado de Parcelas** e marque
   a localização. Exporte as alturas pelo botão correspondente.
4. Para uma árvore, clique em **Selecionar árvore** e marque seu ponto dentro
   da copa. Aguarde a classificação, quando disponível.
5. Delimite a copa com ao menos três vértices distintos, finalize e exporte o CSV.
6. Para espécies no conglomerado, use o botão próprio de classificação.

As elevações do MDS e MDT devem usar metros e o mesmo referencial vertical.
A transformação horizontal não corrige diferenças de datum vertical.

## Interpretação das saídas

- Os 625 recortes de classificação por conglomerado não são contagens de árvores.
  A grade tem espaçamento de 4 m e os recortes medem 8 × 8 m, com sobreposição.
- Confiança do modelo não equivale a acurácia demonstrada em campo.
- Pontos de altura amostrados não equivalem automaticamente à métrica H5.
- O conglomerado de 1 ha não reproduz a geometria de parcelas da FLONA ou do IFN.
- Esta versão não executa a equação de carbono do artigo CMIP6.
- Patches são arquivos temporários locais; copie os PNGs se quiser preservá-los.
  Cada execução usa uma pasta aleatória independente da UA. Nenhuma pasta de uma
  execução anterior é apagada automaticamente, incluindo tentativas interrompidas.
- Uma reclassificação com falha em qualquer amostra não substitui a saída anterior.
  Os resultados novos são preparados em memória e publicados após a gravação completa.
- CSVs incluem coordenadas e caminhos locais de patches. Pastas compartilhadas ou
  sincronizadas podem disponibilizar esses arquivos conforme suas permissões de acesso.

## Testes

Os 52 testes automatizados usam adaptadores isolados de QGIS/Qt e uma CNN simulada
nos testes de fluxo. Eles cobrem as regras numéricas, o bloqueio antes de carregar
pesos, camadas persistentes com nomes iguais, gravação parcial, falhas de troca de
camadas e duas classificações simuladas de 625 amostras sem acumular duplicatas.
Não executam QGIS ou PyTorch reais.

```bash
python -m unittest discover -s fazenda_classifier/tests -p "test_*.py" -v
python -O -m unittest discover -s fazenda_classifier/tests -p "test_*.py" -v
```

No Console Python do QGIS, execute as 12 verificações de integração da RC4:

```python
from fazenda_classifier.tests.smoke_rc4 import run
run()
```

O roteiro inclui os oito testes anteriores de rasters/copa e quatro verificações
adicionais. Usa rasters sintéticos temporários e um projeto QGIS isolado; não
modifica as camadas do projeto aberto e não executa a CNN real.

Para testar a CNN real com seu modelo e pequenos recortes PNG/JPEG:

```python
from fazenda_classifier.tests.smoke_model import run
run()
```

Com PyTorch 2.5.0, o retorno esperado é `status: bloqueada`, antes de escolher ou
abrir o modelo. Com a versão suportada, o roteiro permite selecionar seus pesos
e recortes, verifica probabilidades e informa as classes. Não certifica acurácia
botânica nem equivalência com o ambiente anterior. Veja o
[roteiro de teste](fazenda_classifier/TESTE_E_PUBLICACAO.txt) e o
[registro de validação](docs/VALIDACAO.md). A execução nativa desses roteiros da
RC4 no QGIS do autor ainda está pendente.

## Verificação de segurança da RC3

O Bandit 1.9.4 reproduziu 14 ocorrências na RC2: 12 usos de `assert` no teste de
integração, um uso de `exec` no adaptador de testes e um `except` que continuava
sem informar o erro na limpeza de resultados por UA. A RC3 corrige esses trechos
e passou pela análise local do Bandit sem ocorrências, sem ignorar regras ou
remover testes do pacote. Essa análise não substitui a validação do portal QGIS
nem os testes reais de interface e inferência.

Para repetir a análise após instalar o Bandit no seu ambiente de desenvolvimento:

```bash
python -m bandit -r fazenda_classifier/
```

## Código e licença

O código do complemento está na pasta [fazenda_classifier](fazenda_classifier).
Licença: **GNU GPL versão 2 ou posterior**. Veja [LICENSE](LICENSE).
Os pesos externos e os dados de campo não são distribuídos por esta licença.

Código-fonte: https://github.com/leonardoheraki/fazenda-classifier

Registro de problemas: https://github.com/leonardoheraki/fazenda-classifier/issues

Os metadados do complemento apontam para esses endereços. A RC2 foi submetida ao
portal QGIS e bloqueada na análise automática do Bandit. O autor apresentou
a captura de aprovação da análise automática da versão então enviada. A RC4 é um
novo candidato para teste; sua validação e aprovação no portal são etapas próprias.
