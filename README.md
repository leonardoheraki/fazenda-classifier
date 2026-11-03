# Fazenda Classifier

QGIS plugin for forest sampling, canopy-height measurements from DSM/DTM rasters,
manual crown measurements, and optional RGB patch classification with a
user-supplied Fazenda LeNet model.

**Author:** Leonardo Heraki. **Version:** 1.1.0-rc3, experimental.
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

A saída fica em `dist/fazenda_classifier_1.1.0-rc3.zip`.
Reinicie o QGIS depois de substituir uma versão já carregada.
Salve camadas temporárias como GeoPackage se quiser preservá-las.

## Dependências e modelo

Parcelas, alturas e medidas de copa usam QGIS e NumPy. Para a classificação,
instale PyTorch ≥ 2.2, torchvision compatível e Pillow no Python utilizado pelo
QGIS. Consulte o [seletor oficial do PyTorch](https://pytorch.org/get-started/locally/)
para escolher a combinação compatível com seu Python e sistema operacional.
O complemento não instala dependências automaticamente.

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

## Testes

Os 31 testes de lógica e estado usam a biblioteca padrão do Python:

```bash
python -m unittest discover -s fazenda_classifier/tests -p "test_*.py" -v
```

Na RC3, os 31 testes também passaram com `python -O`. Os testes importam o
módulo real da interface com adaptadores isolados, sem compilar ou executar
trechos de código gerados. As verificações de integração usam `unittest` e
continuam ativas com otimização. A limpeza dos resultados de uma UA agora
valida o campo obrigatório e interrompe a reclassificação se a exclusão falhar.

No Console Python do QGIS, execute os oito testes de integração:

```python
from fazenda_classifier.tests.smoke_qgis import run
run()
```

O teste de integração usa rasters sintéticos temporários e não modifica as
camadas do projeto. O autor relatou os oito testes concluídos em seu QGIS em
02/11/2026. Consulte [o registro de validação](docs/VALIDACAO.md) para o escopo
dos testes reais e suas limitações. As oito verificações no QGIS foram observadas
na RC2; sua execução na RC3 ainda precisa ser documentada.

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
portal QGIS e bloqueada na análise automática do Bandit. A RC3 foi preparada
para novo envio; sua aprovação depende da análise do portal e de seus mantenedores.
