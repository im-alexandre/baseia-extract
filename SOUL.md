# Sobre o projeto: 
segue uma contextualização da aplicação. Algumas coisas ainda estão fora do escopo que já definimos, mas são etapas futuras, como o caso do uso de diferentes parsers. 

## Uso do framework
esta é mais do que uma aplicação, é um framework para eu trabalhar. Eu vou utilizar esse framework próprio para prestar consultorias de diagnóstico e organização de bases de conhecimento, e indexação/embedsing/chunking via qdrant (qdrant ainda está fora do escopo. 

### Modos de utilização 

#### experimentos e diagnósticos em ambiente local ou minimamente distribuído 

Provavelmente o trabalho vai começa comigo recebendo um dump de documentos e vou precisar executar, entre outras, as seguintes tarefas:
- inventário e amostragem inicial (as tasks existentes no pyproject já são o suficiente)
- extração pontual de amostras ou até coleções inteiras (também local ou com infra mínima 
- Nesta etapa, vou variar diversas formas de execução (ex.: mineru pipeline local, mineru com ou sem ocr, outros parsers customizados) interfaces, adapters e abstrações para isso estão fora do escopo do plano. na prática esse será eu instalando libs aleatórias, usanco via cli das libs ou via tasks poe

- verificação, diagnóstico e interações para encontrar uma estratégia de parsing/extração/ingestão adequada. -> tipo uma sandbox mesmo, para eu explirar e experimentar

- inspeção de documentos gerados. (vou abrir o markdown no vim/vscode localmente, ver os pdfs anotados no explorer, etc) tudo local e artesanal -> ferramentas de exibição, anotação etc estão fora do escopo.

- provavelmente essa fase será local ou com serviços mínimos (inventário no postgres direto, sem fila, storage local ou s3 local em container, mineru local (comandos com poe + backend local ou url) ou com poucos serviços externos). é tipo uma fase de pré processamento/definição de estratégia. neste momento, a simplicidade na operação e a agilidade na execução são mais importantes. a persistência das amostras/coleções/runs e etapas executadas será em ambiente dev, são apenas formas de eu não me perder na coleção, não perder documentos e saber o que eu já executei. a persistência de versões de desenvolvimento junto com a coleção final (entrega ao cliente) só vai acontecer quando eu definir explicitamente via configuração ou comando artesanal mesmo, fora do escopo deste projeto.

- nessa fase, eu pretendo priorizar tasks com poe, uv, venv python e dependências locais. os comandos de inventário, amostragem, extração até o embedding serão via cli com poe <task> (só precisa mexer nessas tasks se precisar modificar algo que já esteja no escopo do plano. não precisa melhorar nada)


#### ambiente de produção e geração dos entregáveis ao cliente

- depois de traçada a estratégia para extração, organização, parser, ingestão, organização dos documentos, chunking e embedding, entra a fase de execução/produção, quando provavelmente eu vá utilizar mais recursos, outros nodes/serviços com mineru-api/router e execução destes serviços de forma distribuída em diferentes ambientes. 

- nessa fase eu vou precisar de escala (talvez alguns milhares ou dezenas de milhares de documentos) velocidade importa. 

- os registros de produção não devem trazer metadados, manifestos do ambiente de experimento/diagnóstico. então, no início do trabalho de produção, eu vou gerar o manifesto do zero. 

- vamos fazer um inventário em disco, subir a coleção para o s3, fazer o inventário no s3 e, se nada se perdeu, modificou, o manifesto local sai de cena e fica valendo o inventário inicial do s3. 

- registros, metadados, inventários serão recriados para evitar contaminação com manifesto de desenvolvimento. 

- a ideia aqui é começar do zero em relação a inventário e organização, espelhando a estrutura de diretórios local no s3 verificação de integridade e "esquecendo" o que tava em disco, como path original do documento. os nomes dos arquivos precisam ser mantidos. 

- a ideia aqui é pegar o que eu "aprendi" na fase de desenvolvimento e iniciar um pipeline sem a necessidade de intervenção. 

- a entrega ao meu cliente pode variar, mas no geral, este framework existe pra eu pegar um diretório, caminho da rede etc e conseguir entregar um dump dos arquivos reorganizados + uma coleção chunkada e embeddada no qdrant (qdrant, embedding e chunking fora deste escopo)

### Documentação 
Tal qual qualquer framework que se preze, este projeto precisa de uma documentação forte. Deve ter contextualização, quick start, exemplos de uso, principais recursos e comandos, tutorial de como trabalhar local/dev e em prod/serviços.
a documentação não precisa ser nada de implementação. Uma arvore de diretórios com documentação markdown organizada, com index e links, navegável entre os documentos via link local no próprio markdown já tá maravilhoso. 

também precisamos de uma documentação técnica. afinal este framework é mantido por mim e eu preciso de orientação para desenvolver. 

Uma boa documentação precisa: 

- Me ajudar a desenvolver os próprios recursos do framework, entender as implementações e funcionamento

- Permitir que o usuário deste framework seja capaz de se situar inicialmente (quick start, tutoriais) até ser capaz de entender a documentação mais técnica e recursos mais avançados, como a operação em ambientes distribuídos/de produção. 
