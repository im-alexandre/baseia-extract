# AGENTS.md

## Testes de infraestrutura

Não crie testes unitários artificiais para código de infraestrutura,
provisionamento ou orquestração, especialmente testes baseados em mocks de
CLI, processos, pods, GPUs ou serviços externos.

Para esse tipo de alteração, prefira:

- validação estática e de sintaxe;
- inspeção dos comandos gerados;
- smoke tests operacionais quando forem seguros e autorizados;
- testes de integração somente quando houver ambiente apropriado e solicitação
  explícita.

Não adicione uma suíte unitária apenas para simular `runpodctl`, criação de
processos em background ou disponibilidade de pods.
