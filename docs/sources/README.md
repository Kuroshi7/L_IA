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

> Após a extração, rode o **passe de conferência**. A base é a fonte da verdade do
> cálculo nutricional, e o produto inteiro se apoia nela.

### Conferência (obrigatória)

```bash
cd apps/ai
python -m app.nutrition.auditoria            # relatório
python -m app.nutrition.auditoria --aplicar  # marca nutri_porcoes.suspeito
```

Cruza cada alimento com a **TACO** (NEPA/UNICAMP, versionada em
`app/nutrition/dados/taco.json`) por 100 g — o denominador comum entre as duas
tabelas, já que a TACO não tem medidas caseiras.

Duas coisas importantes sobre o resultado:

1. **Divergência não é sinônimo de erro.** O livro registra pratos brasileiros
   preparados; a TACO registra o alimento. Refogar em óleo muda o número
   legitimamente. Por isso o limite é folgado (40%) e o efeito é rebaixar a
   confiança do cálculo, nunca reescrever o valor.
2. **A cobertura é parcial** (~26%): a TACO não cataloga estrogonofe, farofa,
   escondidinho. Os alimentos sem par ficam para revisão manual da nutricionista.

Na conferência de 2026-08-23, 17 de 37 alimentos casados divergiram acima de 40%,
**todos com a base acima da TACO** (1,41× a 4,22×) — viés sistemático de método,
não dígito trocado.
