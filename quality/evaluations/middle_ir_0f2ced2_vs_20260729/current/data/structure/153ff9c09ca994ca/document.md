22 a 25 de outubro de 2017

XXIVSNPTEE

XXIV SNPTEE
SEMINÁRIO NACIONAL DE RODUÇÃO
TRANSMISSÃO DE ENERGIA ELÉTRICA

CB/GTM/10

Curitiba - PR

GRUPO - XIII

# GRUPO DE ESTUDO DE TRANSFORMADORES, REATORES, MATERIAIS E TECNOLOGIAS EMERGENTES -<br>
GTM

# CONDIÇÕES DE SOBRECARGA E IMPLICAÇÕES DA NBR 5356-7 DURANTE O DESIGN REVIEW DE<br>
TRANSFORMADORES

Luiz Fernando de Oliveira (*)

Álvaro Portillo

Gilson Semiano

Odirlan Iaronka

# WEG – WTD Transformadores

## RESUMO

Na iminência da publicação da NBR 5356-7, baseada na IEC 60076-7, é fundamental o domínio da metodologia
de cálculo térmico utilizado pela norma, na qual pequenas variações na aplicação podem levar a resultados bastante
diferentes. A norma introduzirá ainda o “Anexo H” com caráter normativo estabelecendo o ensaio de elevação de
temperatura em sobrecarga com o objetivo de assegurar a verificação das características dos transformadores frente
a sobrecargas de curta duração, onde as medições das temperaturas são realizadas sem a estabilização em regime
permanente. Este trabalho visa propiciar um entendimento melhor destas implicações, para comprador e fabricante.

## PALAVRAS-CHAVE

Transformador, Sobrecarga em transformadores, Temperatura de Hot-Spot, Design Review, Vida útil.

## 1.0 - INTRODUÇÃO

Historicamente, os valores das características que descrevem o desempenho de transformadores são garantidos
com base nos dados de medicões em regime permanente (é assim com perdas. temperatura. etc.). Os valores de
temperatura exigem ensaios de longa duração devido aos valores das constantes térmicas serem relativamente
elevados, consequentemente, o transformador leva horas para atingir as temperaturas de regime. O Anexo H da
NBR 5356-7 deve introduzir o ensaio de elevação de temperatura em sobrecarga e, como é de se esperar, o tempo
dessas sobrecargas são inferiores ao tempo necessário para estabilização das temperaturas, sobretudo do fluido
isolante.

Tendo em vista a necessidade da análise transitória das temperaturas e as informações geralmente solicitadas
durante o Design Review, este trabalho abordará os seguintes tópicos:

 Comparativo entre o método exponencial e o método diferencial sugeridos pela IEC 60076-7 [1];

 Influência da temperatura ambiente na vida útil e durante o ensaio de sobrecarga;

 Efeito do fluxo disperso adicional em shunts magnéticos

Influência do fator de Hot-Spot variável;

Em muitas análises ao longo deste trabalho será utilizado o ciclo denominado como “Ciclo de sobrecarga” da
nota técnica elaborada pelo ONS [2], exibido na Figura 1.

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/1c22e578ca18331f09aa0cff3e1e7e95f88dd5e72c5893ce7c3e860cda1317e4.jpg>)

Figura 1 – Ciclo de sobrecarga (fonte: NT. ONS [2])

## 2.0 - COMPARATIVO ENTRE OS MÉTODOS EXPONENCIAL E DIFERENCIAL

O draftda norma NBR 5356-7 (assim como [1]), apresenta dois métodos para calcular a evolução de temperatura
do Hot-Spot de transformadores em função das variações de carga:

Solução de equações exponenciais: adequadas para variações de carga típicas da função degrau com
temperatura ambiente constante, principalmente quando são intercalados degraus de acréscimo com
degraus de decréscimo de carga. Caso esta condição não se cumpra, o gradiente de temperatura do ponto
mais quente sobre a temperatura do topo do óleo precisa alcançar o regime permanente.

Solução de equações diferenciais: especialmente aplicáveis quando ambos, fator de carga e temperatura
ambiente, variam simultânea e/ou independentemente. Por não haver restrições quanto ao perfil de carga,
é particularmente aplicável para monitoramento on-line.

Embora as aplicações pareçam distintas, ambas modelam os mesmos fenômenos adequadamente e levam a
resultados muito similares quando respeitadas as recomendações da norma. As maiores discrepâncias ocorrem
durante um decréscimo de carga, o que se deve principalmente da aplicação do fator$k _ { 1 1 }$, descrita em [3]. Na Figura
2 é exibido um comparativo entre os dois métodos de modelagem e vale ressaltar que o passo de tempo (��) utilizado
para calcular a evolução das temperaturas ao longo de cada período influencia ambos os métodos.

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/28d3f4a58aac46d373a7550e09341e313f48507e52c406ae32a7d36151c2e8f3.jpg>)

Figura 2 – Comparativo da modelagem usando equações exponenciais e diferenciais

Em relação ao método das equações diferenciais, a Figura 3 exibe o resultado da utilização de diferentes passos
de tempo na modelagem de um transformador cuja constante de tempo do enrolamento$( \tau _ { w } )$é de 8,25���. Embora
a IEC 60076-7 [1] recomende um passo de tempo inferior à metade da constante térmica do enrolamento, foram
modelados os seguintes intervalos de tempo: �� = 8���, 4���, 2��� e 1���. Os resultados em termos de vida útil
(�/����� �� �����) foram$0 , 7 3 , \ 0 , 7 4 , \ 0 , 7 5 \ \in \ 0 , 7 5$, respectivamente. Constata-se portanto que o passo utilizado
influencia, embora não de forma acentuada, na evolução das temperaturas ao longo dos transitórios de carga, mas
a influência no valor final das temperaturas em regime permanente pode-se dizer insignificante.

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/b410144319a8709329e293e9cb500bea4fd885245dc147d1dcd3eab435d81cc3.jpg>)

Figura 3 – Modelagem por equações diferenciais com diferentes intervalos de integração

## 3.0 - INFLUÊNCIA DA TEMPERATURA AMBIENTE

Durante análises de ciclos de carga, a IEC 60076-7 [1] recomenda a utilização dos seguintes valores de
temperatura ambiente:

Para quesitos de envelhecimento térmico e vida útil: utilizar a temperatura ambiente média anual, em geral,
aquelas indicadas pela Tabela 2 da IEC 60076-2 [4];

Para quesitos de temperatura do ponto mais quente: utilizar a temperatura ambiente média mensal do mês
mais quente.

Extraindo de [5] as temperaturas médias mensais ao longo do ano de 2016, a Figura 4 é construída. Observa-
se, para as cinco cidades analisadas com posição geográfica bastante distintas, que as médias máximas são muito
similares, variando entre 26 e 28°�. Contudo, a média anual é de 20°� para Porto Alegre (RS) enquanto que para
João Pessoa (PB) é de 27,3°�.

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/3af7101f95e5964ff89fbe2c5a390d7be0b84428c0be394c67ba41ea114e84b3.jpg>)

Figura 4 – Temperaturas ambiente média mensal de diferentes cidades brasileiras ao longo do ano de 2016

Tomando como referência estas duas temperaturas, 20 e 27,3°� e utilizando o método das equações diferenciais
(optou-se pela utilização deste método para obter maior precisão no decréscimo de carga) para modelar um
transformador convencional com margens de segurança razoáveis, pode-se construir os gráficos apresentados na
Figura 5 aplicando o ciclo de sobrecarga definido na Figura 1.

Analisando a Figura 5 (a), observa-se que a diferença de temperatura do ponto mais quente nas duas séries é
de aprox. 7°�, como era de se esperar. Na Figura 5 (b), percebe-se que essa diferença faz com que o transformador
que está submetido à 27,3°� de temperatura ambiente, quando em sobrecarga de 40%, envelheça duas vezes mais
rápido do que o transformador submetido à 20°� ambiente. Com a taxa de envelhecimento acelerada o consumo de
vida útil dispara em uma ascendência bastante íngreme. como apresentado na Figura 5 (c). As observacões
convergem com a seção “Ambient Temperature” da IEC 60076-7.

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/f00286465a1d0749ccf07fc24c1b6d90b3ddb75148935df17ebfc61dd82641eb.jpg>)

Figura 5 – Para diferentes temperaturas ambiente: (a) evolução do ponto mais quente, (b) taxa de
envelhecimento e (c) consumo de vida útil

## 4.0 - EFEITO DO FLUXO DISPERSO ADICIONAL EM BLINDAGENS (SHUNTS) MAGNÉTICOS

Embora a constante térmica do óleo$( \tau _ { o } )$seja da ordem de horas para grandes transformadores de potência, a
elevação de temperatura ocasionada pelas perdas em anteparos metálicos (como o tanque e ferragens) oriundas do
campo magnético disperso é mais rápida, similar à constante dos enrolamentos.

Ao longo do ensaio de elevação de temperatura tradicional sempre foi fácil verificar deficiências de projeto
relativas à campo disperso incidindo com amplitude elevada no tanque, bastando a utilização de verificação com, por
exemplo, câmeras de imagem térmica por infravermelho. A constatação de aquecimento nas ferragens e suportes
do núcleo (internos ao tanque) não é tão direta, de forma que só é possível inferir a existência de pontos quentes
com a análise dos gases dissolvidos no óleo (DGA) que ocorrem quando a temperatura de algum ponto em contato
com o óleo mineral supera 150°�, como descrito em [6].

Com a inclusão do ensaio de temperatura em sobrecarga tornou-se absolutamente viável a verificação da
temperatura na superfície externa do tanque com 40% de fluxo excedente. O fluxo excedente pode saturar blindagens
magnéticas e o campo magnético pode então permear as laterais metálicas do tanque, causando perdas por
correntes parasitas.

Um autotransformador regulador monofásico 250��� ���� 550/460�� � = 12,9% foi modelado para ilustrar o
fenômeno, utilizando o aplicativo FEMM 4.2 ( [7]). Obviamente há limitações na modelagem já que o aplicativo
considera apenas geometrias em duas dimensões. O caso específico foi elaborado em coordenadas cilíndricas
(axissimétrica) no domínio da frequência utilizando a técnica “frequency-dependent permeability” para
aproximadamente modelar os efeitos da histerese e saturação das blindagens magnéticas. Um circuito térmico foi
utilizado para então calcular a temperatura estimada da lateral do tanque. Três distintas configurações foram
modeladas e os detalhes são apresentados na Tabela 1.

Tabela 1 – Configurações e resultados das simulações de fluxo magnético disperso

|  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- |
| Espessuradablindagem(shunt)[mm] | Comprimentoda blindagem(shunt)[mm] | Perdasinduzidasno tanque[W] | Induçãomáximanablindagem[T] | Elevação detemperaturaestimada nocentro do tanque[°C] | Elevação de temperaturaestimada do tanquepróximo à extremidade dablindagem[°c] |
| 17 | 2800 | 23319 | 2,03 | 21 | 35,8 |
| 26 | 2800 | 20142 | 1,52 | 1,1 | 43,5 |
| 26 | 3300 | 5697 | 1,55 | 0,2 | 9,3 |

Utilizando uma blindagem magnética com espessura de 17��, a indução máxima foi de 2,03�, como pode ser
observado na Figura 6, de forma que na parte central do tanque as perdas tornaram-se elevadas (Figura 7) causando
uma elevação de temperatura de$2 1 ^ { \circ } C$nesta parte do tanque e$3 5 { , } 8 ^ { \circ } C$nas extremidades. Com a blindagem de 26��
a indução limitou-se a 1,52�, eliminando as perdas na parte central do tanque, mas causando uma elevação de
temperatura de$4 3 , 5 ^ { \circ } C ,$agravando o problema já que o campo total conduzido pela blindagem aumentou. Finalmente,
alterando também o comprimento da blindagem em 500��, o problema do ponto quente no tanque próximo às
extremidades da blindagem foi mitigado (9,3°� de elevação).

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/75d39a823e167c3731d491e07a4da1000b89a11ce349d23b07190877683b32d7.jpg>)

Figura 6 – Indução ao longo de diferentes configurações de blindagem magnética

Há ainda a questão de que o valor de elevação de temperatura máximo permitido é passível de discussão. A
tabela 4 da IEC 60076-7 limita a temperatura das partes metálicas em contato com o óleo em 180°�. Para o
transformador modelado cuja elevação do topo do óleo garantida é de 65°�, sob temperatura ambiente de 40°�, a
temperatura final da lateral do tanque seria de$6 5 + 4 0 + 4 3 , 5 = 1 4 8 , 5 ^ { \circ } C$. Embora esse valor esteja abaixo do valor
admissível de acordo com a norma, há limitações para as gaxetas de vedação e em alguns casos para a própria tinta
que reveste o tanque.

Outra consideração que merece atenção é o tempo de duração de tais pontos quentes. a nota técnica do ONS
[2] especifica que para apenas 10% do tempo de operação do transformador deve ser considerado o “ciclo de
sobrecarga”, no restante do tempo a carga deve ser considerada constante e de valor nominal. Isso implica em uma
exposição bem menor ao intenso fluxo disperso derivados da corrente à sobrecarga de 40%.

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/77e8631a917a8f450d7f2e1f035e6b50db27ab32c01d1cb0fb73f32b7650d485.jpg>)

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/01a3d61328c89a3fcb4a6b429496876d5c1b7449c6776ac0d77047e05eae849b.jpg>)

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/366447594e94729fbbac036468698cca366330ce446627c9c82ee359d002fa29.jpg>)

Figura 7 – Linhas equipotenciais de fluxo magnético disperso devido à corrente de carga (140%) com
blindagem de: (a) 17mm, (b) 26mm e (c) 26mm com comprimento adicional de 500mm. Em destaque as regiões
com elevacão de temperatura em potencia

## 5.0 - INFLUÊNCIA DO FATOR DE HOT-SPOTVARIÁVEL

Um dos dados de entrada fundamentais para o cálculo apresentado na IEC 60076-7 é o fator de Hot-Spot (�),
que relaciona a elevação de temperatura máxima de um determinado enrolamento com a elevação média obtida no
ensaio de aquecimento tradicional por meio da variação da resistência do próprio enrolamento. Em geral, a norma
não faz nenhuma recomendação para uso de um fator de Hot-Spot variável, contudo, é fato que o fator de Hot-Spot
pode variar com a carga, tal fenômeno pode ser observado nos dados de [8] e é discutido em [9] onde detalhes dos
fatores � e � (� = � ∙ �) são apresentados sob a análise da aplicação de circuitos termo-hidráulicos (THNM) [10].

Para explicitar o efeito e deixar a questão mais palpável, foi desenvolvida uma análise utilizando a metodologia
de equações diferenciais na tentativa de modelar o fenômeno e verificar qual pode ser o impacto do fator de Hot-
Spot variável. Duas séries foram desenvolvidas, na primeira série foi utilizado fator de Hot-Spot fixo enquanto que na
segunda série o fator de Hot-Spot foi introduzido como um dado de entrada com os valores de: 1,25 para 100% de
carga, 1,3 para 120% de carga e 1,35 para 140% de carga. A Figura 8 exibe o resultado da análise e compara as
duas séries desenvolvidas. Foram utilizados os dados de um transformador 180��� ���� 230/69�� com margens
de seguran a típicas para transformadores deste porte.

Para a primeira série, que utiliza o fator fixo, a temperatura máxima de Hot-Spot foi de 131,5°� enquanto que
para a segunda série, utilizando fator variável, a temperatura máxima foi 134,7°�, uma diferença de 3,2°�. Esse
acréscimo de temperatura resulta em uma taxa de consumo de vida útil 35% maior (10,8 em relação a 8) enquanto
o transformador estiver submetido à sobrecarga de 40%. Por fim, considerando que o “ciclo de sobrecarga” é exigido
em apenas 10% do tempo de operação (conforme [2]) e que a sobrecarga de 40% ocorre durante apenas 2,1% do
ciclo, a vida útil final do transformador será reduzida em um total de 2,5%.

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/75fd5cc830d17f3437c011be0207739e87d2e6110e692d8960679eda212b1c98.jpg>)

Figura 8 – Comparativo utilizando fator de Hot-Spot fixo vs. Fator de Hot-Spot variável

## 6.0 - CONCLUSÕES

O objetivo deste trabalho consistiu em elencar e propor discussões sobre pontos específicos da NBR 5356-7
dando “alternativas para modelagem”. As abordagens foram expostas de forma breve embora tenham sido
elaboradas de maneira mais aprofundada, sendo decorrentes da experiência adquirida com a aplicação da IEC
60076-7 cada vez mais frequente em transformadores destinados a rede básica. Com base nessas análises, uma
série de conclusões podem ser evidenciadas:

Quanto ao comparativo entre os métodos exponencial e diferencial, as recomendações da norma são válidas e
precisam ser observadas para a obtenção de resultados adequados. Do ponto de vista da aplicação em sistemas
computacionais a solução por equações diferenciais permite maior flexibilidade já que considera variação da
temperatura ambiente de forma independente do perfil de carga;

Em relação à influência da temperatura ambiente, a própria IEC 60076-7 afirma que uma diferença de 6°� na
temperatura ambiente leva à uma taxa de consumo de vida útil duas vezes maior e essa afirmação foi verificada
neste trabalho afirmativamente. A nota técnica da ONS [2] considera para temperatura ambiente a ser utilizada em
análises de vida útil o valor apresentado pela NBR 5356, que por sua vez indica o valor de 30°�. Este valor mostrou-
se adequado e, em geral, está acima da média anual até para as cidades mais quentes do Brasil [5]. Contudo,
principalmente para localidades da região sul, as análises de vida útil resultarão em valores sempre mais otimistas
que a média nacional se forem utilizados os valores de temperatura média reais da região;

Sobre o efeito do fluxo adicional em shunts magnéticos, as análises, assim como a experiência prática durante
os ensaios, mostram que pode ocorrer saturação das blindagens (shunts) magnéticas que protegem o tanque do
fluxo disperso dos enrolamentos. Com a saturação das blindagens (que por si só já pode ser um problema
ocasionando vibrações excessivas), o fluxo excedente incide sobre as laterais do tanque com potencial para geração
de pontos quentes que devem sempre ser evitados. A recomendacão. tal qual iá é citada nas normas principais. é
de que as blindagens sejam dimensionadas considerando a condição de sobrecarga;

Quanto à influência do fator de Hot-Spot variável, constatou-se com a análise efetuada que admitindo a variação
de 1,25 à 1,35 (valor acima do sugerido em [9], mas razoável conforme [8]), a temperatura de Hot-Spot sofrerá um
acréscimo de 3.2°C. Embora o impacto na vida útil não seia demasiado (2.5%), essa discrepância pode ser relevante
para a avaliação da temperatura máxima admissível durante a sobrecarga já que algumas especificações têm
solicitado valores garantidos abaixo daqueles indicados pelas normas. Neste caso, a aplicação de circuitos termo-
hidráulicos torna-se uma das poucas opções viáveis para o cálculo do fator � que indica o aumento da temperatura
de Hot-Spot devido às restrições de fluxo de óleo.

Há ainda que se mencionar sobre a precisão do cálculo de elevação de temperatura. Todo cálculo térmico
aplicado em grandes transformadores possuirá uma margem de erro devido às aproximações que são feitas em
algum ponto, até mesmo as mais modernas técnicas de modelagem, como indicado em [10], fazem aproximações
de maior ou menor grau e possuem uma margem de erro de alguns graus Celsius (geralmente entre 2 e 5°�) para
mais ou para menos nas temperaturas de regime permanente. O assunto tratado na IEC 60076-7 excede a condição
de regime permanente e trata essencialmente dos transitórios de temperatura entre um e outro valor de regime frente
as oscilações de carga. Nesse caso, é de se esperar que o erro seja ainda maior já que as temperaturas partirão de
um valor que já fora aproximado e utilizar-se-á uma técnica também aproximada e baseada em fatores (fatos
evidenciados em [3]). Tendo em vista tal contexto, ressalta-se o cuidado com as garantias de valores de Hot-Spot
durante o processo de Design Review e quando do ensaio de elevação de temperatura em sobrecarga, seja por
medições com imagem térmica ou fibra ótica.

## 7.0 - REFERÊNCIAS BIBLIOGRÁFICAS

[1]IEC - International Electrotechnical Commission, IEC 60076-7: Loading guide for oil-immersed power
transformers, Geneva, 2005.

[2]ONS - Operador Nacional do Sistema Elétrico, “Ensaio de elevação de temperatura de transformadroes
emsobrecarga,”25Fevereiro2014.[Online].Available:
http://www.ons.org.br/download/administracao_transmissao/padroes_desempenho/NT-ONS-038-
2014_ElevacaoTemperatura_transformadoresemsobrecarga.pdf. [Acesso em Março 2017].

[3]H. Nordman, N. Rafsback e D. Susa, “Temperature Responses to Step Changes in the Load Current
of Power Transformers,” IEEE Transactions on power delivery, Vol. 18, pp. 1110-1117, Outubro 2003.

[4]IEC - International Electrotechnical Commission, IEC 60076-2: Temperature rise for liquid-immersed
transformers, IEC, 2011.

[5]INMET - Instituto Nacional de Meteorologia, “Gráficos,” INMET, [Online]. Available:
http://www.inmet.gov.br/. [Acesso em 21 Março 2017].

[6]IEEE - Institute of Electrical and Electronics Engineers, IEEE Std C57.104-2008: Guide for the
Interpretation of Gases Generated in Oil-Immersed Transformers, New York: IEEE, 2008.

[7]D. Meeker, “Finite Element Method magnetics: HomePage,” 6 Abril 2014. [Online]. Available:
www.femm.info. [Acesso em 21 Março 2017].

[8]S. G. Montenegro, P. Dionne, R. P. Bersi, C. S. S. Xavier, J. N. Berubé e C. Deligi, “Ensaio de
aquecimento em sobrecarga usando medição direta de temperatura - estudo de caso do 3° transformador
SE João Câmara II,” VIII Workspot Cigré, 20-23 Novembro 2016.

[9]Z. Radakonic, U. Radoman e P. Kostic, “Decomposition of the Hot-Spot Factor,” IEEE Transactions on
Power Delivery, Vol. 30, pp. 403-411, Fevereiro 2015.

[10] Z. R. Radakovic e M. S. Sorgic, “Basics of Detailed Thermal-Hydraulic Model for Thermal Design of Oil
Power Transformers,” IEEE Transactions on Power Delivery, Vol. 25, No. 2, pp. 790-802, Abril 2010.

## 8.0 - DADOS BIOGRÁFICOS

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/4c18fa27a84dfec41f35bf93b5f439f047b400bbc37e3e250cbf6fa4c3269049.jpg>)

Luiz Fernando de Oliveira nasceu em Blumenau-SC, Brasil em 1988. Graduou-se em
Engenharia Elétrica na Universidade Regional de Blumenau (FURB) em 2013 e atualmente cursa
mestrado também em Engenharia Elétrica na UFSC (GRUCAD). Trabalha na WEG T&D desde
2007, onde passou pelas áreas de produção e técnica, entre 2009 e 2013 trabalhou diretamente
com cálculo e dimensionamento de transformadores e desde 2013 exerce atividades no
departamento de pesquisa e desenvolvimento com foco em pesquisa, simulações numéricas e
desenvolvimento de softwares para engenharia. É membro do Cigré-Brasil.

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/a53745232f80716686ce2fd84f10b931107470818d67726cd4688fe2dd71057a.jpg>)

Álvaro Portillo nasceu no Uruguai em 1954. Graduou-se em Engenharia Elétrica na
Universidad de la República del Uruguay em 1979. Trabalhou na companhia elétrica uruguaia
(UTE) até 1985 em atividades relacionadas a aprova ão, instala ão e manuten ão de
transformadores. De 1985 a 1999 trabalhou na MAK AS (fabricante uruguaio de transformadores,
até 20MVA, 72,5kV), de 2000 a 2007 como consultor na TRAFO (fabricante brasileiro de
transformadores, até 20MVA, 72,5kV) e desde então atua como consultor e desenvolvedor de
ferramentas para projeto de transformadores na WEG (fabricante brasileiro de transformadores,
até 500MVA, 500kV). É professor na Universidad de la República del Uruguay desde 1977, sendo

atualmente responsável pelos cursos de pós-graduação em transformadores (especificação, projeto, operação,
manutenção, etc.), é também membro sênior da IEEE e membro do Cigré, tem participação ativa em vários grupos
de trabalho dessas entidades.

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/50d0aef62981027b3f1bf2d5675cf66cb79ef40445d054083b1b4bc4040cb7c4.jpg>)

Gilson Semiano nasceu em Taió-SC, Brasil em 1980. Graduou-se em Engenharia Elétrica
na Universidade Regional de Blumenau (FURB) em 2005 e concluiu o curso de Mestrado em
Engenharia Elétrica pela mesma instituição em 2015. Trabalha na WEG T&D desde 2001, onde
passou pela área de laboratório de ensaios e atualmente trabalha diretamente com cálculo e
dimensionamento de transformadores. Seus interesses de pesquisa incluem técnicas de medição
e modelagem de transientes eletromagnéticos, VFTOs e projeto de transformadores móveis.

![](<../../mineru/documents/153ff9c09ca994ca/153ff9c09ca994ca35b79fede481f1340c0a29b5a969a0be401e6aac5330606b/auto/images/c4075d547ef6dc604f4c49fd5f43a47c3c0ddf5235cc5baeeb5dc32312edd0b3.jpg>)

Odirlan Iaronka nasceu em Casca-RS, Brasil em 1990. Graduou-se em Engenharia Elétrica
pela Universidade Federal de Santa Maria (UFSM) em 2014. Atualmente cursa Mestrado pela
Universidade Federal de Santa Catarina (UFSC) na área de Eletromagnetismo aplicado em
Engenharia Elétrica no GRUCAD - Grupo de Concepção e Análise de Dispositivos
Eletromagnéticos. Exerce a função de Engenheiro de Aplicação e Pesquisador no setor de
Pesquisa, Desenvolvimento e Inovação da empresa WEG - Equipamentos Elétricos S.A. na
Unidade de Transmissão e Distribuição de Energia. Atua na área de Simulações Numéricas
Computacionais de campos eletromagnéticos e no desenvolvimento de ferramentas de análise

e otimizacão do projeto eletromagnético e térmico de transformadores e reatores de potência. transformadores seco
e chaves secionadoras.

Rua Dr. Pedro Zimmermann, n˚ 6751 – CEP 89068-001 Blumenau, SC – Brasil
Tel: (+55 47) 3337-1000 – Fax: (+55 47) 3337-1090 – email: luizo@weg.net
