package store

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

// ResolverAlimento encontra o alimento de referência mais próximo de `q`
// (exato → alias → similaridade trigram). Retorna o score [0..1].
func (s *Store) ResolverAlimento(ctx context.Context, q string) (domain.NutriAlimento, float64, error) {
	norm := domain.Normalizar(q)
	var a domain.NutriAlimento
	var score float64
	err := s.pool.QueryRow(ctx,
		`SELECT id, nome, COALESCE(categoria,''), COALESCE(fonte,''), aliases,
		        CASE WHEN nome_norm = $1 OR $1 = ANY(aliases) THEN 1.0
		             ELSE similarity(nome_norm, $1) END AS score
		   FROM nutri_alimentos
		  WHERE nome_norm = $1 OR $1 = ANY(aliases) OR similarity(nome_norm, $1) > 0.25
		  ORDER BY score DESC
		  LIMIT 1`,
		norm,
	).Scan(&a.ID, &a.Nome, &a.Categoria, &a.Fonte, &a.Aliases, &score)
	if errors.Is(err, pgx.ErrNoRows) {
		return a, 0, ErrNotFound
	}
	return a, score, err
}

func (s *Store) resolverMedidaCod(ctx context.Context, medida string) string {
	norm := domain.Normalizar(medida)
	if norm == "" {
		return ""
	}
	var cod string
	err := s.pool.QueryRow(ctx,
		`SELECT medida_cod FROM medida_aliases
		  WHERE alias = $1 OR similarity(alias, $1) > 0.4
		  ORDER BY CASE WHEN alias = $1 THEN 1.0 ELSE similarity(alias, $1) END DESC
		  LIMIT 1`,
		norm,
	).Scan(&cod)
	if err != nil {
		return ""
	}
	return cod
}

// ResolverPorcao escolhe a porção do alimento que melhor casa com a medida informada.
// Sem correspondência, cai na referência de 100g (confiança baixa).
func (s *Store) ResolverPorcao(ctx context.Context, alimentoID int64, medida string) (domain.NutriPorcao, string, string) {
	cod := s.resolverMedidaCod(ctx, medida)

	var p domain.NutriPorcao
	if cod != "" {
		err := s.pool.QueryRow(ctx,
			`SELECT id, alimento_id, medida_label, COALESCE(medida_cod,''),
			        quantidade_g, COALESCE(kcal,0), COALESCE(proteina_g,0),
			        COALESCE(carboidrato_g,0), COALESCE(gordura_g,0)
			   FROM nutri_porcoes
			  WHERE alimento_id = $1 AND medida_cod = $2
			  ORDER BY quantidade_g
			  LIMIT 1`,
			alimentoID, cod,
		).Scan(&p.ID, &p.AlimentoID, &p.MedidaLabel, &p.MedidaCod,
			&p.QuantidadeG, &p.Kcal, &p.ProteinaG, &p.CarboidratoG, &p.GorduraG)
		if err == nil {
			return p, "alta", ""
		}
	}

	// fallback: 100g de referência
	err := s.pool.QueryRow(ctx,
		`SELECT id, alimento_id, medida_label, COALESCE(medida_cod,''),
		        quantidade_g, COALESCE(kcal,0), COALESCE(proteina_g,0),
		        COALESCE(carboidrato_g,0), COALESCE(gordura_g,0)
		   FROM nutri_porcoes
		  WHERE alimento_id = $1 AND medida_label = '100g'
		  LIMIT 1`,
		alimentoID,
	).Scan(&p.ID, &p.AlimentoID, &p.MedidaLabel, &p.MedidaCod,
		&p.QuantidadeG, &p.Kcal, &p.ProteinaG, &p.CarboidratoG, &p.GorduraG)
	if err != nil {
		return domain.NutriPorcao{}, "baixa", "porção não encontrada"
	}
	return p, "baixa", "medida '" + medida + "' não encontrada; usando 100g como referência"
}

func menorConfianca(a, b string) string {
	rank := map[string]int{"baixa": 0, "media": 1, "alta": 2}
	if rank[a] <= rank[b] {
		return a
	}
	return b
}

// CalcularConsumo resolve cada item contra a base e soma os nutrientes consumidos.
func (s *Store) CalcularConsumo(ctx context.Context, itens []domain.ConsumoItemEntrada) (domain.ConsumoTotais, error) {
	var tot domain.ConsumoTotais
	for _, it := range itens {
		qtd := it.Quantidade
		if qtd <= 0 {
			qtd = 1
		}
		res := domain.ConsumoItemResultado{Entrada: it}

		alimento, score, err := s.ResolverAlimento(ctx, it.Alimento)
		if errors.Is(err, ErrNotFound) {
			res.Confianca = "baixa"
			res.Obs = "alimento não encontrado na base"
			tot.Itens = append(tot.Itens, res)
			continue
		}
		if err != nil {
			return tot, err
		}
		confAlimento := "alta"
		if score < 0.999 {
			if score >= 0.5 {
				confAlimento = "media"
			} else {
				confAlimento = "baixa"
			}
		}

		porcao, confPorcao, obs := s.ResolverPorcao(ctx, alimento.ID, it.Medida)

		res.AlimentoResolvido = alimento.Nome
		res.PorcaoResolvida = porcao.MedidaLabel
		res.GramasTotais = porcao.QuantidadeG * qtd
		res.Kcal = porcao.Kcal * qtd
		res.ProteinaG = porcao.ProteinaG * qtd
		res.CarboidratoG = porcao.CarboidratoG * qtd
		res.GorduraG = porcao.GorduraG * qtd
		res.Confianca = menorConfianca(confAlimento, confPorcao)
		res.Obs = obs

		tot.Kcal += res.Kcal
		tot.ProteinaG += res.ProteinaG
		tot.CarboidratoG += res.CarboidratoG
		tot.GorduraG += res.GorduraG
		tot.GramasTotais += res.GramasTotais
		tot.Itens = append(tot.Itens, res)
	}
	return tot, nil
}
