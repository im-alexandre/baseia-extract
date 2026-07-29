1332
GLT/21

XXVI SNPTEE

Produção e Transmissão
de Energia Elétrica

# GRUPO DE ESTUDO DE LINHAS DE TRANSMISSÃO - GLT

# SISTEMA EMBARCADO PARA INSPEÇÃO PREDITIVA DE TIRANTES DE ANCORAGEM DE TORRES DE LINHAS DE TRANSMISSÃO AÉREAS

MARCELO DE SÁ COUTINHO (1); LAURO RODRIGO GOMES DA SILVA LOURENÇO NOVO (1); DOUGLAS   
CONTENTE PIMENTEL BARBOSA (1); LUIZ HENRIQUE ALVES DE MEDEIROS (1); MARCOS TAVARES   
DE MELO (1); MARCELO MACÊDO ALVES (1); RENAN GUILHERME MATIAS DOS SANTOS (1); VINÍCIUS LEAL TARRAGÔ (1); HENRIQUE BAPTISTA DUFFLES TEIXEIRA LOTT NETO (2); PAULO HENRIQUE RAMALHO PEREIRA GAMA (3); UNIVERSIDADE FEDERAL DE PERNAMBUCO (1); SISTEMA DE TRANSMISSAO NORDESTE S. A. (2); INSTITUTO AVANÇADO DE TECNOLOGIA E INOVAÇÃO (3)

## RESUMO

Torres estaiadas são estruturas utilizadas no suporte de linhas aéreas de transmissão de energia elétrica cuja fixação ao solo utiliza hastes de ancoragem. Estas âncoras podem apresentar corrosão, ocasionada pelas intempéries ambientais ou falhas de instalação, cujo rompimento pode levar à queda da torre e consequente interrupção do fornecimento de energia. Um sistema inteligente preditivo foi desenvolvido para diagnóstico das âncoras, em substituição à onerosa técnica de inspeção visual atualmente empregada pelas empresas transmissoras. Este sistema, embarcado em uma maleta industrial, é composto por hardware e software proprietário, e apresenta acurácia superior a 80% para testes realizados em hastes operacionais.

## PALAVRAS-CHAVE

Linhas de transmissão aéreas, torres estaiadas, hastes de âncora, corrosão, sistema embarcado, avaliação estrutural, inspeção preditiva

## 1.0 INTRODUÇÃO

O sistema interligado nacional (SIN) para produção e transmissão de energia elétrica gerencia a interconexão dos seus subsistemas elétricos regionais para atender à crescente demanda por eletricidade, exigida pelas atividades econômicas nas diversas regiões do país. A transferência de energia entre os subsistemas de produção (oferta) e as regiões consumidoras (demanda) é suportada pela malha nacional de transmissão, a qual exige investimentos expressivos em infraestrutura. A abrangência da rede de transmissão de energia elétrica brasileira atualmente é de cerca de 148.000 km (1), o que implica na utilização de torres de transmissão cuja instalação seja menos dispendiosa, como é o caso das estruturas estaiadas comparativamente às autoportantes.

Nas torres estaiadas, os estais de sustentação são fixados ao terreno utilizando as hastes de âncora, as quais são susceptíveis a sofrerem processos corrosivos, ocasionados pelas intempéries do meio ou falhas na execução do projeto de instalação. A condição estrutural das hastes de âncora influencia no equilíbrio mecânico da torre, e sua deterioração pode levar à queda da estrutura e consequentemente à indisponibilidade da linha de transmissão. Um novo sistema de inspeção preditiva foi desenvolvido e embarcado em uma maleta industrial para diagnóstico in loco das âncoras, em substituição à onerosa técnica de inspeção visual a qual exige a remoção da haste.

O sistema tem como grande vantagem a utilização de técnicas não destrutivas de inspeção e análise (2)-(6) para diagnosticar a condição estrutural da haste sem a necessidade de escavar o solo a priori. A inserção do sistema de inspeção embarcado em maletas industriais, projetadas para o ambiente de linhas de transmissão, permite o uso tanto para atividades acadêmicas (7)-(8) como atividades de campo em ambientes reais (9)-(11).

O sistema atualmente possui autonomia energética de seis horas ininterruptas de medições em campo. O hardware é composto por instrumentação de medição, interface homem-máquina, e circuito de controle e gerenciamento de alimentação elétrica. O software proprietário realiza funções de gerenciamento da medição, calibração do instrumento, e diagnóstico da haste por meio de ferramenta de inteligência artificial (12) e correlação de Pearson.

A instrumentação é composta por analisador de redes vetorial (ARV), cabos coaxiais, conectores de RF, um conector de altas frequências, denominado MDSC (Microwave Device of Support and Connection) (13), luvas de conexão, hastes cobreadas, e ferramentas de uso geral. O instrumento analisador de redes utiliza kit de calibração e ferramentas especiais. O circuito de controle da alimentação elétrica do sistema utiliza dispositivos como contactores, contatos auxiliares, módulos relés, chaves de acionamento, inversor CC-CA e carregador de bateria. A autonomia energética é garantida por bateria interna, e fontes de alimentação externas, como exemplos carregador veicular, e gerador a combustível para uso in loco, ou rede elétrica comercial para carregamento da bateria interna.

O software embarcado é apresentado por uma interface homem-máquina que permite o gerenciamento da medição a partir de uma tela sensível ao toque, e é executado por um minicomputador Raspberry para comunicação com o instrumento. A comunicação lógica é feita pela linguagem de programação VISA, com conjunto de operações dadas pelo instrumento analisador, e possui comandos na linguagem Python.

A manutenção das hastes de âncora passa, portanto, a ser preditiva com a utilização deste sistema de inspeção, diminuindo sensivelmente os custos atuais de manutenção das empresas transmissoras, além de possíveis implicações para a empresa junto aos órgãos fiscalizadores e de regulação, como exemplo da obrigatoriedade de cumprimento da PVI (Parcela Variável por Indisponibilidade).

## 2.0 SISTEMA EMBARCADO DE INSPEÇÃO PREDITIVA

O referido sistema de inspeção é composto por duas maletas industrias, denominadas CASE 1 e CASE 2. A primeira maleta ou CASE 1, é composta pelo circuito de autonomia de energia, instrumento analisador de redes vetorial (ARV), minicomputador Raspberry, e tela sensível ao toque. O conector MDSC, cabos coaxiais, elementos de calibração, e ferramentas de uso geral são previstos no CASE 2. Para montagem do sistema os itens do CASE 2 são conectados ao CASE 1, tornando o sistema apto para realizar as inspeções.

## 2.1 CASE 1

O CASE 1 é a principal maleta do sistema embarcado de inspeção das hastes de âncora, e é a partir dela que a inspeção é realizada (FIGURA 1). O sistema de autonomia de energia é composto uma bateria de 12 V e 18 Ah, que garante autonomia de trabalho superior a seis horas ininterruptas. Além da bateria, o inversor de frequência faz a conversão CC-CA necessária para atender a demanda energética do ARV, da tela sensível ao toque e do Raspberry. O sistema possui ainda um carregador de 4 A para carregamento da bateria interna. Os contactores, contatos auxiliares, módulos relés e chaves de acionamento viabilizam os modos de carregamento do CASE 1.

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/2d3f666f9ed69ccf3ec18f7154c4aea786af7f4b23e898faca09edb74a74298f.jpg>)

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/e5920563ff03793032d9d24a6bebe78d4fd89dd270c46d346a0d7091e07a5989.jpg>)

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/c421c047128b7b0c92b99212cb9274ba32f9f941bb6efdf7fbc328b093705077.jpg>)  
FIGURA 1 – Fotografias do CASE 1.

## 2.1.1 Modos de carregamento

A alimentação elétrica dos componentes inseridos no CASE 1 é dividida de acordo com a necessidade operacional. Para isso, foram estabelecidos 3 modos de carregamento para suporte às atividades realizadas em campo, onde a rede elétrica comercial não é acessível: o Modo de Carregamento Autônomo (MCA), por meio de uma fonte interna; o Modo de Carregamento Diurno (MCD) e o Modo de Carregamento Noturno (MCN), ambos através de fontes externas.

A coordenação destes modos consiste no uso da lógica de comando através dos contactores e técnicas de acionamentos e intertravamentos. O MCA tem o objetivo de ser a principal forma de alimentação fornecida para o sistema, a qual é garantida pela bateria interna ao CASE 1. Esta bateria é carregada durante a execução do MCN.

O MCA é acionado pelas ligações da chave geral do acionamento interno (INT). Neste modo o ARV, a Tela sensível ao toque e o Raspberry são alimentados e o sistema passar a funcionar normalmente.

O modo de carregamento noturno (MCN) visa alimentar a bateria interna em períodos fora do expediente de trabalho em campo, garantindo o funcionamento do MCA.

O acionamento do MCN é realizado pela chave EXT e a botoeira de impulso MCN. Neste caso, o sistema alimenta o ARV e a bateria através de seu carregador. Os demais elementos não são acionados neste modo de operação. Se o MCA não puder ser operado por algum motivo, e houver o acesso a alguma fonte externa de energia onde a atividade é realizada (gerador a combustível, por exemplo), então o modo MCD é acionado. O MCD tem o objetivo de substituir o MCA devido à algum contratempo, garantindo a operação ininterrupta do sistema de medições.

O acionamento do MCD é feito pela chave EXT e a botoeira de impulso MCD, alimentando o ARV, a tela sensível ao toque, e o Raspberry. As chaves e botoeiras de acionamento são apresentadas na FIGURA 2.

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/76abf7f79a8e6c2446c53d4ad26e097da896e4d2c812a325e41460cba5b1f6f1.jpg>)  
FIGURA 2 – Chaves de ligação e botoeiras de acionamento.

## 2.2 CASE 2

O CASE 2 (FIGURA 3) comporta os periféricos do CASE 1. Os cabos coaxiais são conectados ao ARV e ao MDSC, que por sua vez, faz a interconexão do sistema com a haste de âncora. As cargas de calibração são responsáveis por eliminar quaisquer ruídos e reflexões do sinal até a extremidade do cabo. As ferramentas de uso geral como parafusadeira, multímetro, alicates etc., auxiliam a montagem dos itens do CASE 2 no CASE 1.

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/1ee22a0beafdbbc2642ffd04492ef1a48fa78494815c765cee9d4982b0fc1504.jpg>)  
FIGURA 3 – Fotografias do CASE 2.

## 2.3 Software embarcado

O software executado no CASE 1 foi projetado para controlar a interface entre o operador humano e o sistema, dada por uma tela sensível ao toque 10”, para gerenciar as medições e diagnosticar as hastes medidas, e é executado por um microcomputador Raspberry Pi, modelo B. Este equipamento possui 1 GB de memória volátil (RAM), e interface RJ32 onde é feita a comunicação com o ARV. A linguagem de programação utilizada é VISA, que inclui um conjunto de operações que são executadas pelo ARV. A linguagem de programação Python possui bibliotecas desenvolvidas para a integração da linguagem VISA em seu código, e foi utilizada para executar os comandos escritos em VISA.

As operações para o controle do analisador, habilitadas pelas linguagens Python e VISA, são integradas a um serviço HTTP implementado na linguagem Node JS. Dessa forma, os comandos VISA são disponibilizados por um serviço que pode atender clientes em diversas plataformas como celulares, tablets e telas sensíveis ao toque, executados por diferentes sistemas operacionais. Vale lembrar que esse serviço é habilitado remotamente utilizando as tecnologias Bluetooth ou WIFI, suportadas pelo Raspberry Pi.

A tela inicial da interface desenvolvida é apresentada inicialmente para o usuário (FIGURA 4), e contém um botão relativo ao início da medição, como também indicações do nível de bateria no canto superior esquerdo, e de configuração do sistema no canto superior direito.

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/0946bd1268a50c446b48c0d62bb61b0f3ae71dae2ad00e72b8e2b20f55f32083.jpg>)  
FIGURA 4 – Tela inicial do sistema.

O processo de medição é iniciado quando o usuário toca no botão Iniciar exibido na tela inicial, e uma tela de aviso é mostrada para que o operador ou usuário conecte o cabo coaxial no analisador de redes. Após isso, o operador será questionado se deseja realizar uma nova calibração, levando em conta a informação da última calibração realizada. Optando pela calibração eletrônica, o processo é realizado e, logo em seguida, o operador será direcionado para a tela de preenchimento do formulário de medição na qual será perguntado qual o nome da torre e do estai a ser medido. Caso o operador opte pela calibração manual, o sistema entrará no processo de calibração mecânica.

Após a calibração realizada, aparecerá a tela para preenchimento do formulário de medição, e em seguida o operador será questionado se o cabo coaxial foi conectado devidamente ao MDSC. O processo é repetido enquanto o operador não informar sobre a conexão do cabo coaxial. O sistema solicita ao usuário um mínimo de três medições correlacionadas superiormente a 95 % para evitar que dados espúrios reduzam a confiabilidade das medições.

Após a apresentação do resultado de medição (FIGURA 5) ou de não haver correlação dos sinais coletados, o sistema irá perguntar se o operador deseja realizar a medição em uma nova haste. Caso sim, o processo será repetido desde da etapa de calibração do sistema.

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/6b44b6f65c066fc0ef5d04331cdc6786646add14252a0e72f354b0cd4564e630.jpg>)  
FIGURA 5 – Resultado da medição.

## 2.3.1 Ferramenta de inteligência artificia

Devido à grande variação de padrões passíveis de serem observados nas hastes enterradas em relação à extensão, profundidade, formato ou ponto exato de ocorrência de corrosão, se torna uma tarefa complexa e inviável tentar definir um algoritmo ou um conjunto de regras capazes de associar um determinado sinal medido a uma haste corroída ou normal. Algoritmos de aprendizado de máquina são ferramentas poderosas para lidar com problemas dessa natureza, pois são capazes de automaticamente encontrar relações subjacentes ou ocultas no fenômeno observado que relacione um conjunto de entradas, no caso, os sinais eletromagnéticos medidos, com suas respectivas saídas, ou seja, a presença ou ausência de corrosão em uma determinada haste.

O processo de classificação das hastes medidas em normal ou defeituosa no sistema proposto é feito por uma ferramenta de inteligência artificial. Essa ferramenta consiste em um classificador binário baseado na técnica de aprendizado de máquina de regressão logística (14) e que é treinado previamente com uma base de dados formada por sinais de amostras conhecidas de hastes de âncora nas duas condições: defeituosa/corroída ou normal/íntegra.

Apesar de seu nome sugerir uma regressão, a regressão logística é na verdade um modelo paramétrico de classificação, no qual a saída é dada por uma função logística sigmoidal agindo em uma função linear do vetor de parâmetros de entrada (15). O modelo gerado pela regressão logística provê uma função que expressa a probabilidade a posteriori de um novo elemento apresentado ao algoritmo ser um membro de uma das duas classes existentes, com base nos exemplos que o algoritmo observou previamente durante a sua etapa de treinamento.

Os sinais utilizados para treinar o algoritmo foram obtidos em medições de campo realizadas em torres de linhas de transmissão operacionais em diversas locações geográficas nos estados do Ceará (CE) e Piauí (PI). Foram coletadas 03 (três) amostras válidas de cada haste medida em campo. A validade das medições foi aferida pelo grau de similaridade dos sinais medidos, calculado pela correlação de Pearson (16), o que garantia que os sinais eram, ao mesmo tempo, representativos dos estados da haste, mas que incorporavam também informação referente às variações inerentes à própria repetibilidade do processo de medição em campo.

Devido ao fato de a Regressão Logística ser um algoritmo de natureza essencialmente estatística, para que seja obtido um bom nível de generalização pelo sistema é de fundamental importância estruturar a base de dados com uma grande diversidade de sinais, o que se traduz em medições de hastes em diversos níveis de degradação por corrosão. A cada haste medida em campo e escavada para verificação do seu nível de corrosão foi atribuído por um comitê de analistas um grau de severidade que variou continuamente de 0,0 (zero), para uma haste perfeitamente intacta, a 1,0 (um) para uma haste completamente deteriorada pela corrosão. A FIGURA 6 ilustra exemplos de hastes que foram classificadas com diferentes graus de severidade.

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/ea59939bd41160fbbec9ce2a8182a3f670328f30414f6d13b8224269f380661a.jpg>)  
(a)

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/70bd3632e7255a101f2ffb434312cd8b56544aced108d2b86c19f512d9cb3ab7.jpg>)  
(b)

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/f57774f04e658278de0abcdf17793ce1dd25a53c4d21c524f2cebc76274184b7.jpg>)  
(c)  
FIGURA 6 – Fotografias de âncoras com diferentes níveis de corrosão. (a) Nível 0,0. (b) Nível 0,6. (c) Nível 0,9.

Os sinais devidamente classificados foram estruturados em uma base de dados que foi utilizada para treinamento do classificador binário, por meio de um processo de aprendizado supervisionado (17). Nesse processo, as amostras de sinais pertencentes a cada uma das duas classes (normal ou corroída) são apresentadas continua e iterativamente ao algoritmo, para que ele aprenda quais características desses sinais são indicativas de cada uma das classes. Com base nessas observações, o algoritmo automaticamente ajusta seus parâmetros de modo a melhor se adaptar aos padrões de sinal observados nas amostras e reduzir o erro de predição. Após ajustes nos hiperparâmetros do modelo e conclusão do processo de treinamento, o sistema se torna capaz de classificar novas amostras.

## 2.4 Medições das hastes de âncora operacionais

Medições foram realizadas nas linhas de transmissão de energia da empresa STN S.A. implantadas no Estado do Ceará, conforme fotografias apresentadas na FIGURA 7. Um total de 161 amostras de hastes de âncora operacionais foi medido, sendo 19 hastes corroídas, e 142 amostras de hastes consideradas normais (sem corrosão). O banco de dados da ferramenta de inteligência artificial foi dividido convencionalmente em 80% dos resultados de medição foi utilizado para treinamento do sistema, e os 20% restantes para seus testes. A acurácia geral média obtida para estes testes do sistema foi de 82,22%, sendo que para os subconjuntos de hastes normais e corroídas esta acurácia média foi de 97,43% e 85,00%, respectivamente.

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/0956fec035c987c625e2ac76fcd6a3a5931857016f411321c69dc19f4902998f.jpg>)

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/cc05d3adf4a571359a57ce8d3777ec9658b44065cd00a903383ce953e5f59c10.jpg>)

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/751969f5903d32fb2241e5fd5dd4a03372849972706a605955cd44ebe3c13919.jpg>)

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/5757a04d5addb1a0adbb5fbbdc65db77d60f508096bbe99c79b485ed773a8edb.jpg>)  
FIGURA 7 – Fotografias das medições nas linhas de transmissão de energia.

## 3.0 CONCLUSÃO

Este trabalho apresentou um novo sistema de inspeção preditiva não destrutivo para diagnóstico in loco de corrosão das hastes de âncora de torres estaiadas de linhas de transmissão de energia, em substituição à técnica de manutenção utilizada atualmente, a inspeção visual.

O sistema foi desenvolvido para ser de fácil manipulação ao operador humano, e mostrou ser um equipamento prático para as medições em campo. Com autonomia energética de mais de 6 horas ininterruptas de duração, a equipe de campo poderá utilizar o sistema em praticamente um expediente diário de trabalho.

Para as inspeções realizadas nas linhas de transmissão pertencentes à empresa Sistema de Transmissão Nordeste S.A., a acurácia conferida pelo sistema é superior a 80%, viabilizando sua aplicação. A ferramenta de inteligência artificial permite ampliação da acurácia a partir de novos dados de medições, inferindo reconfigurabilidade ao sistema.

O diagnóstico instantâneo da condição estrutural da haste possibilitará à empresa priorizar a substituição das hastes com presença de corrosão prioritariamente aos maiores percentuais de corrosão obtidos.

A acurácia geral do sistema alcançou 82,22% para uma base de dados contendo 161 amostras, sendo 19 hastes corroídas e 142 hastes normais. As taxas de acertos dos subconjuntos de hastes normais e corroídas foram, 97,43% e 85,00%, respectivamente. Estes resultados indicam que o sistema inteligente proposto pode ser utilizado preditivamente na manutenção de hastes de âncora para o estaiamento de linhas de transmissão de energia elétrica.

O referido sistema embarcado de inspeção permite preditivamente evitar a ocorrência de sinistros sobre as hastes de âncora, e assim evitar a interrupção do fornecimento da energia elétrica aos consumidores destas linhas. Sua aplicação melhora os índices de qualidade de transmissão de energia, e reduz os custos de manutenção associados.

## 4.0 AGRADECIMENTOS

Este artigo é resultado de um projeto de pesquisa desenvolvido pelas instituições UFPE – Universidade Federal de Pernambuco, e IATI – Instituto Avançado de Tecnologia e Inovação, para a empresa transmissora de energia elétrica STN S.A. – Sistema de Transmissão Nordeste S.A., como parte do Programa de Pesquisa e Desenvolvimento do Setor Elétrico Brasileiro promovido pela ANEEL – Agência Nacional de Energia Elétrica.

## 5.0 BIBLIOGRAFIA

(1) Anuário Estatístico de Energia Elétrica, 2021. Disponível em <https://www.epe.gov.br/sitespt/publicacoes-dados-abertos/publicacoes/PublicacoesArquivos/publicacao-160/topico- 168/Anu%C3%A1rio%20Estat%C3%ADstico%20de%20Energia%20El%C3%A9trica%202021%2 0-%20Workbook.xlsx>. Acesso em 16 julho 2021.

(2) M. S. Coutinho; L. R. G. S. L. Novo; M. T. De Melo; L. H. A. De Medeiros; D. C. P. Barbosa; M. M. Alves; T. G. S. Martins; V. L. Tarrago; R. G. M. Santos; H. B. D. T. Lott Neto; P. H. R. P Gama. Sistema diagnóstico da integridade de hastes de âncora de torres estaiadas de linhas de transmissão de energia elétrica. In: XVIII Encontro Regional Ibero- americano do Cigré - ERIAC, 2019, Foz do Iguaçú. Proceedings XVIII ERIAC, 2019.

(3) D. C. P. Barbosa; L. H. A. De Medeiros; M. T. De Melo; L. R. G. S. L. Novo; M. S. Coutinho; M. M. Alves; T. G. S. Martins; V. L. Tarrago; R. G. M. Santos; H. B. D. T. Lott Neto; P. H. R. P Gama. Arquitetura de rede neural artificial para detecção de falhas estruturais em hastes de âncora de torres estaiadas de linhas de transmissão de energia elétrica. In: XVIII Encontro Regional Iberoamericano do Cigré - ERIAC, 2019, Foz do Iguaçú. Proceedings XVIII ERIAC, 2019.

(4) J. M. Bezerra, L. H. de Medeiros, R. R. Aquino, O. N. Neto, L. R. Novo, M. T. de Melo, D. S. Santos, M. A. Fontan, and P. R. Britto, “Localization and diagnosis of stay rod of v guyed towers corrosion,” in High Voltage Engineering and Application (ICHVE), 2014 International Conference on. IEEE, 2014, pp. 1–5.

(5) D. C. P. Barbosa; L. H. A. De Medeiros; M. T. De Melo; L. R. G. S. L. Novo; M. S. Coutinho; M. M. Alves; T. G. S. Martins; V. L. Tarrago; R. G. M. Santos; H. B. D. T. Lott Neto; P. H. R. P Gama, "Machine Learning Approach to Detect Faults in Anchor Rods of Power Transmission Lines", in IEEE Antennas And Wireless Propagation Letters, vol. 18, no. 11, pp. 2335–2339, 2019.

(6) M. S. Coutinho; L. R. G. S. L. Novo; M. T. De Melo; L. H. A. De Medeiros; D. C. P. Barbosa; M. M. Alves; V. L. Tarrago; R. G. M. Santos; H. B. D. T. Lott Neto; P. H. R. P Gama, "Machine learningbased system for fault detection on anchor rods of cable-stayed power transmission towers", in Electric Power Systems Research, vol. 194, pp. 1–8, 2021.

(7) M. A. Santos; D. O. Maionchi, "Maleta Didática – Máquina de corrente contínua no ensino do eletromagnetismo para o nível médio", em Revista Brasileira de Ensino de Física, vol. 43, pp. 1–8, 2021.

(8) M. Artiyasa; N. Destria; M. A. Desima, "Creating kit and plc application with industrial applications for practice learning of plc technology in electronics Nusaputra university Sukabumi", in Journal of Physics: Conference Series, vol. 1516, pp.1–9, 2020.

(9) P. Castello; C. Muscas; P. A. Pegoraro; S. Sulis, "Low-cost Implementation of an Active Phasor Data Concentrator for Smart Grid", in 2018 Workshop on Metrology for Industry 4.0 and IoT, Brescia,

pp. 78–82, 2018.

(10) Z. Hong-Tao; Y. Ying; A. Qing, "Research on power quality monitoring and analyzing system based on embedded technology", in CICED 2010 Proceedings, Nanjing: [s.n], 2011.

(11) R. Song; F. Zhu; Z. Zhai; P. Yao, "Design and implementation of network-based embedded electricity management system", in 2011 International Conference on Electronic & Mechanical Engineering and Information Technology, Harbin, pp. 3533–3538, 2011.

(12) S. Haykin, Neural networks and learning machines. Pearson, 2009.

(13) D. C. P. Barbosa; L. H. A. De Medeiros; M. T. De Melo; L. R. G. S. L. Novo; M. S. Coutinho; M. M. Alves; V. L. Tarrago; R. G. M. Santos; H. B. D. T. Lott Neto; P. H. R. P Gama, "Artificial Neural Network-Based System for Location of Structural Faults on Anchor Rods Using Input Impedance Response", in IEEE TRANSACTIONS ON MAGNETICS, vol. 56, pp. 1–4, 2021.

(14) Harrell F.E. (2015) Binary Logistic Regression. In: Regression Modeling Strategies. Springer Series in Statistics. Springer, Cham. https://doi.org/10.1007/978-3-319-19425-7\_10.

(15) DREISEITL, S.; OHNO-MACHADO, L. Logistic regression and artificial neural network classification models: a methodology review. Journal of Biomedical Informatics, v. 35, n. 6-6, p. 352-359, 2002.

(16) Benesty J., Chen J., Huang Y., Cohen I. (2009) Pearson Correlation Coefficient. In: Noise Reduction in Speech Processing. Springer Topics in Signal Processing, vol 2. Springer, Berlin, Heidelberg. https://doi.org/10.1007/978-3-642-00296-0\_5.

(17) A. Singh, N. Thakur and A. Sharma, "A review of supervised machine learning algorithms," 2016 3rd International Conference on Computing for Sustainable Global Development (INDIACom), 2016, pp. 1310-1315.

## DADOS BIOGRÁFICOS

![](<../../mineru/documents/01bcb00e543fd06c/01bcb00e543fd06c33a2d5fd21d37e2e9c72243c2cb5f91a4955932e8c1ae718/auto/images/9c266691d959d6c65a42893b599202f8ff63138e861a2bc974d9a151082353a8.jpg>)

## (1) MARCELO DE SÁ COUTINHO

Engenheiro de Telecomunicações formado pelo Centro Universitário Maurício de Nassau, Recife, Brasil, em 2014. Atuou durante 1 ano e meio como engenheiro de RF e celular, realizando a implantação dos sistemas 3G e 4G. Em 2015 iniciou o mestrado em engenharia elétrica pela Universidade Federal de Pernambuco, obtendo o título de mestre em 2017. Ainda em 2017 iniciou o doutorado pela mesma universidade, obtendo o título de doutor em 2021. Atualmente trabalha como pesquisador em projetos de pesquisa entre empresas privadas e a universidade, como na detecção de falhas em estruturas metálicas por meio de dispositivos de altas frequências.

## (2) LAURO RODRIGO GOMES DA SILVA LOURENÇO NOVO

Lauro Novo atualmente trabalha como Professor do Magistério Superior vinculado ao Departamento de Eletrônica e Sistemas da Universidade Federal de Pernambuco, e ministra disciplinas ofertadas para os Cursos de Engenharia Eletrônica, Eletrotécnica, Controle e Automação, e Engenharia de Energia. Obteve os títulos de Doutor, Mestre e Bacharel em Engenharia Elétrica, pela UFPE, respectivamente em 2015, 2009 e 2007. Sua linha de pesquisa inclui detecção de descargas atmosféricas em linhas de transmissão, e construção de dispositivos de enlace de R.F. Participa de projeto de P&D para desenvolvimento de equipamento de detecção de corrosão em hastes de âncora em torres estaiadas.

## (3) DOUGLAS CONTENTE PIMENTEL BARBOSA

Douglas Contente Pimentel Barbosa, D.Sc., MBA, PMP é engenheiro eletrônico com graduação, mestrado e

doutorado pela UFPE. Possui certificação PMP e MBA em gerenciamento de projetos, programas e portfólio pela

UFRJ. Atuou na Petrobras como engenheiro de equipamentos de 2008 a 2020, implantando sistemas de automação,

controle e segurança industrial para refino e em projetos da área de transformação digital e inovação. Atualmente é

professor adjunto do Departamento de Engenharia Elétrica da UFPE. Suas áreas de interesse incluem redes

industriais, instrumentação, automação e controle, inteligência artificial, aprendizado de máquina, ciência de dados,

processamento de sinais, micro-ondas e gerenciamento de projetos.

## (4) LUIZ HENRIQUE ALVES DE MEDEIROS

Possui graduação em Engenharia Elétrica pela Universidade Federal de Santa Catarina (1992), mestrado em Engenharia Elétrica pela Universidade Federal de Santa Catarina (1994) e doutorado em Engenharia Elétrica pelo Institut National Polytechnique de Grenoble (1998). Atualmente é professor associado da Universidade Federal de Pernambuco. Tem experiência na área de Engenharia Elétrica, com ênfase em Compatibilidade Eletromagnética e sistemas de armazenamento, atuando principalmente nos seguintes temas: compatibilidade eletromagnética em sistemas elétricos de potência/subestações, efeitos biológicos dos campos elétricos, magnéticos e eletromagnéticos, qualidade de energia, integração elétrica de novas fontes, armazenamento e mobilidade elétrica.

## (5) MARCOS TAVARES DE MELO

Concluiu Física-UFPE em 1983. Em 1986 terminou sua Pós-Graduação em Matemática Aplicada na Universidade de Pernambuco, focando em Equivalência Mecânica de Circuitos Elétricos. Retornando a UFPE concluiu o mestrado em Física em 1992 na área de Absorção de Microondas em Amostras Supercondutoras. Em 1997 concluiu seu doutorado em Engenharia Elétrica pela University of Birmingham, na Inglaterra, com foco em dispositivos supercondutores de micro-ondas. Em 1999 ingressou no Grupo de Fotônica do Departamento de Eletrônica e Sistemas da UFPE. Foi professor visitante do Department of Electronic and Electrical Engineering of The Imperial College London durante fev 2012 a fev 2013.

## (6) MARCELO MACÊDO ALVES

Formado em Engenharia da Computação pela Universidade Federal de Pernambuco, Recife, Brasil, em 2012. Atuou durante 3 anos e meio como desenvolvedor de software áreas de logística e mercado de energia. Em 2017 iniciou o mestrado em engenharia elétrica pela Universidade Federal de Pernambuco, obtendo o título de mestre em 2018. Ainda em 2018 iniciou o doutorado pela mesma universidade, e hoje está em busca do título de doutor. Atualmente trabalha como pesquisador em um projeto de pesquisa que envolve a identificação e localização de falhas em estruturas metálicas por meio de dispositivos de altas frequências.

## (7) RENAN GUILHERME MATIAS DOS SANTOS

Engenheiro Eletricista pela Universidade Federal de Pernambuco, Recife, Brasil, em 2021. Possui curso técnico em Automação Industrial pelo Instituto Federal de Pernambuco, Ipojuca, Brasil em 2015 e Eletromecânica pelo Senai, Cabo, Brasil, em 2013. Atuou durante um ano como jovem aprendiz na empresa Unilever S.A., auxiliando nas manutenções corretivas e inventários através do sistema SAP, de 2014 a 2015. Atualmente trabalha como pesquisador bolsista em projeto de pesquisa e desenvolvimento entre empresa privada e universidade, no projeto de detecção de falhas em estruturas metálicas por meio de dispositivos de altas frequências.

## (8) VINÍCIUS LEAL TARRAGÔ

Nasceu em agosto de 1996, no Recife-PE. Engenheiro eletricista pela Universidade Federal de Pernambuco (UFPE) e pesquisador associado ao Instituto Avançado de Tecnologia e Inovação (IATI). Interesses de pesquisa incluem detecção de corrosão em estruturas metálicas, aterramento e sistemas de proteção contra descargas atmosféricas.

## (9) HENRIQUE BAPTISTA DUFFLES TEIXEIRA LOTT NETO

Henrique B. D. T. Lott Neto graduado em Engenharia Mecânica (1984) na Universidade Santa Ursula (USU) e pósgraduado pela Universidade Federal do Rio de Janeiro, Brasil. Engenheiro sênior e diretor de R & D na empresa Sistema de Transmissão Nordeste Ltda – STN Ltda. Experiência em engenharia elétrica, com ênfase em sistemas elétricos.

## (10) PAULO HENRIQUE RAMALHO PEREIRA GAMA

Possui graduação e mestrado em Engenharia Elétrica pela Universidade Federal de Itajubá e doutorado pela Universidade de São Paulo. Foi consultor em P&D&I para mais de 30 empresas do setor elétrico da cadeia GTD. É proprietário da Versattus Pesquisa e Consultoria em Energia EIRELI. Já coordenou e participou de vários projetos de P&D&I. Tem experiência em temas como: geração distribuída, eficiência energética, energias renováveis, transmissão. Foi coordenador do Grupo de Estudos CE C6 - Distribuição de Energia e Geração Distribuída do CIGRE Brasil. Atualmente é Diretor de Negócios no Instituto Avançado de Tecnologia e Inovação - IATI.

msacou@gmail.com
