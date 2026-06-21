package store

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

// SearchNutriAlimentos busca na base de referência (medidas caseiras) por nome/alias,
// para o admin vincular um alimento do menu a uma referência já existente.
func (s *Store) SearchNutriAlimentos(ctx context.Context, q string, limit int) ([]domain.NutriAlimento, error) {
	if limit <= 0 || limit > 50 {
		limit = 10
	}
	norm := domain.Normalizar(q)
	rows, err := s.pool.Query(ctx,
		`SELECT id, nome, COALESCE(categoria,''), COALESCE(fonte,''), aliases
		   FROM nutri_alimentos
		  WHERE nome_norm ILIKE '%'||$1||'%' OR similarity(nome_norm, $1) > 0.2 OR $1 = ANY(aliases)
		  ORDER BY similarity(nome_norm, $1) DESC, nome
		  LIMIT $2`,
		norm, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []domain.NutriAlimento{}
	for rows.Next() {
		var a domain.NutriAlimento
		if err := rows.Scan(&a.ID, &a.Nome, &a.Categoria, &a.Fonte, &a.Aliases); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

// GetNutriAlimentoComPorcoes retorna a referência nutricional com suas porções.
func (s *Store) GetNutriAlimentoComPorcoes(ctx context.Context, id int64) (domain.NutriAlimentoDetalhe, error) {
	var d domain.NutriAlimentoDetalhe
	err := s.pool.QueryRow(ctx,
		`SELECT id, nome, COALESCE(categoria,''), COALESCE(fonte,''), aliases FROM nutri_alimentos WHERE id=$1`, id,
	).Scan(&d.ID, &d.Nome, &d.Categoria, &d.Fonte, &d.Aliases)
	if errors.Is(err, pgx.ErrNoRows) {
		return d, ErrNotFound
	}
	if err != nil {
		return d, err
	}

	rows, err := s.pool.Query(ctx,
		`SELECT id, alimento_id, medida_label, COALESCE(medida_cod,''), quantidade_g,
		        COALESCE(kcal,0), COALESCE(proteina_g,0), COALESCE(carboidrato_g,0), COALESCE(gordura_g,0)
		   FROM nutri_porcoes WHERE alimento_id=$1 ORDER BY quantidade_g`, id)
	if err != nil {
		return d, err
	}
	defer rows.Close()

	d.Porcoes = []domain.NutriPorcao{}
	for rows.Next() {
		var p domain.NutriPorcao
		if err := rows.Scan(&p.ID, &p.AlimentoID, &p.MedidaLabel, &p.MedidaCod, &p.QuantidadeG,
			&p.Kcal, &p.ProteinaG, &p.CarboidratoG, &p.GorduraG); err != nil {
			return d, err
		}
		d.Porcoes = append(d.Porcoes, p)
	}
	return d, rows.Err()
}

// CreateNutriAlimento cria uma referência nutricional independente (com porções).
func (s *Store) CreateNutriAlimento(ctx context.Context, ref domain.NutriRefInput) (domain.NutriAlimentoDetalhe, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.NutriAlimentoDetalhe{}, err
	}
	defer tx.Rollback(ctx)

	id, err := s.createNutriRefTx(ctx, tx, ref)
	if err != nil {
		return domain.NutriAlimentoDetalhe{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.NutriAlimentoDetalhe{}, err
	}
	return s.GetNutriAlimentoComPorcoes(ctx, id)
}

// createNutriRefTx insere (ou atualiza) um nutri_alimentos e suas porções dentro de uma transação.
// Espelha cmd/seed/main.go:seedNutricao; normaliza aliases e resolve o código da medida quando ausente.
func (s *Store) createNutriRefTx(ctx context.Context, tx pgx.Tx, ref domain.NutriRefInput) (int64, error) {
	seen := map[string]bool{}
	aliases := make([]string, 0, len(ref.Aliases)+1)
	add := func(a string) {
		n := domain.Normalizar(a)
		if n != "" && !seen[n] {
			seen[n] = true
			aliases = append(aliases, n)
		}
	}
	for _, a := range ref.Aliases {
		add(a)
	}
	add(ref.Nome) // o próprio nome como alias ajuda a resolução do motor de consumo

	var id int64
	if err := tx.QueryRow(ctx,
		`INSERT INTO nutri_alimentos (nome, nome_norm, categoria, fonte, aliases)
		 VALUES ($1,$2,NULLIF($3,''),'admin',$4)
		 ON CONFLICT (nome_norm) DO UPDATE SET nome = EXCLUDED.nome, categoria = EXCLUDED.categoria
		 RETURNING id`,
		ref.Nome, domain.Normalizar(ref.Nome), ref.Categoria, aliases,
	).Scan(&id); err != nil {
		return 0, err
	}

	for _, p := range ref.Porcoes {
		cod := p.MedidaCod
		if cod == "" {
			cod = s.resolverMedidaCod(ctx, p.MedidaLabel)
		}
		if _, err := tx.Exec(ctx,
			`INSERT INTO nutri_porcoes
			   (alimento_id, medida_label, medida_cod, quantidade_g, kcal, proteina_g, carboidrato_g, gordura_g)
			 VALUES ($1,$2,NULLIF($3,''),$4,$5,$6,$7,$8)
			 ON CONFLICT (alimento_id, medida_label) DO UPDATE SET
			   medida_cod=EXCLUDED.medida_cod, quantidade_g=EXCLUDED.quantidade_g, kcal=EXCLUDED.kcal,
			   proteina_g=EXCLUDED.proteina_g, carboidrato_g=EXCLUDED.carboidrato_g, gordura_g=EXCLUDED.gordura_g`,
			id, p.MedidaLabel, cod, p.QuantidadeG, p.Kcal, p.ProteinaG, p.CarboidratoG, p.GorduraG,
		); err != nil {
			return 0, err
		}
	}
	return id, nil
}
