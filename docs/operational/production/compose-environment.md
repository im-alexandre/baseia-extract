---
id: operational.production.compose
title: Ambiente de produção com Compose
kind: tutorial
audience: operator
mode: production
stage: installation
status: current
nav_order: 320
---

# Ambiente de produção com Compose

[Documentação](../../README.md) · [Uso](../README.md) ·
[Local](../local/README.md) ·
[Dev catalogado](../cataloged-development/README.md) ·
[Produção](README.md) · [Referência](../reference/README.md) ·
[Documentação técnica](../../technical/README.md)

## O que é

O Compose oferece uma topologia local de referência para compreender e testar
os serviços. Ele não substitui decisões de segurança, backup e alta
disponibilidade de uma implantação real.

## Preparar

Crie um `.env` próprio e substitua:

- senhas PostgreSQL;
- credenciais S3;
- token do catálogo;
- bind e URLs;
- tags de imagem;
- limites do ambiente.

Em produção, habilite:

```powershell
$env:BASEIA_REQUIRE_CATALOG_TOKEN = "true"
```

## Subir a infraestrutura sem GPU

```powershell
docker compose --profile production config
docker compose --profile production up -d --build
docker compose --profile production ps
```

Esse perfil inicia:

- PostgreSQL do catálogo;
- SeaweedFS como S3 compatível;
- Catalog API;
- Qdrant;
- PostgreSQL do Temporal;
- Temporal e sua UI.

Temporal está provisionado, mas os workflows do pipeline ainda não estão
implementados. O CLI Poe continua coordenando as stages.

## Adicionar GPU no mesmo host

```powershell
docker compose `
    --profile production `
    --profile gpu `
    up -d --build
```

O perfil `gpu` não é incluído automaticamente em `production`.

## Verificar

```powershell
docker compose --profile production ps
Invoke-RestMethod "http://127.0.0.1:8088/health"
Invoke-RestMethod "http://127.0.0.1:9333/cluster/status"
Invoke-RestMethod "http://127.0.0.1:6333/collections"
```

Com GPU local:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/baseia-capabilities"
Invoke-RestMethod "http://127.0.0.1:8000/baseia-persistence-health"
```

## Segurança

Os defaults de `.env.example` são apenas de desenvolvimento. Antes de expor:

- mantenha serviços em rede privada;
- use TLS;
- gere segredos fortes;
- exija token no catálogo;
- restrinja portas;
- fixe imagens por tag imutável ou digest;
- defina backup para PostgreSQL e S3.

Anterior: [Promover a estratégia](promoting-the-strategy.md)
Próximo: [Publicar e ativar a coleção](collection-bootstrap.md)
Referência: [Configuração](../reference/configuration.md)
Avançado: [Estrutura de infraestrutura](../../technical/repository-structure.md#infraestrutura)
