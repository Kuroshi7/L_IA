# Fontes de dados

## Tabela de Medidas Caseiras (base nutricional)

Coloque aqui o PDF original:

```
docs/sources/tabela-medidas-caseiras.pdf
```

Fonte: *Tabela para Avaliação de Consumo Alimentar em Medidas Caseiras* (Atheneu, 4ª ed.).

### Ingestão (ETL → banco)

As páginas são imagens escaneadas, então a extração usa visão da LLM (Anthropic),
página a página, com merge no seed versionado `apps/api/seed/nutricao.json`
(o núcleo verificado manualmente nunca é sobrescrito; só são adicionados novos alimentos).

```bash
cd apps/ai
pip install -r requirements-etl.txt
export ANTHROPIC_API_KEY=sk-ant-...
# extraia em lotes (páginas 3..66 contêm a tabela)
python -m app.nutrition.etl --start 3 --end 12
python -m app.nutrition.etl --start 13 --end 30
# ... continue até a 66

# carregue no banco
cd ../../deploy
docker compose run --rm api-seed
```

> Após a extração completa, faça um **passe de conferência** dos números (OCR/visão
> pode errar dígitos). A base é a fonte da verdade do cálculo nutricional.
