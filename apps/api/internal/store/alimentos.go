package store

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

// arr garante slice não-nil (pgx envia nil como NULL, violando NOT NULL nas colunas TEXT[]).
func arr(s []string) []string {
	if s == nil {
		return []string{}
	}
	return s
}

// alimentoSelect lista as colunas de `alimentos` (com alias `a`) na ordem esperada por scanAlimento.
const alimentoSelect = `a.id, a.unidade_id, a.nome, COALESCE(a.categoria,''),
	a.ingredientes, a.alergenos, a.restricoes_atendidas, a.nao_indicado_para,
	COALESCE(a.calorias,0), COALESCE(a.proteinas_g,0), COALESCE(a.carboidratos_g,0),
	COALESCE(a.gorduras_g,0), a.ativo, a.nutri_alimento_id`

func scanAlimento(row pgx.Row, a *domain.Alimento) error {
	return row.Scan(&a.ID, &a.UnidadeID, &a.Nome, &a.Categoria,
		&a.Ingredientes, &a.Alergenos, &a.RestricoesAtendidas, &a.NaoIndicadoPara,
		&a.Calorias, &a.ProteinasG, &a.CarboidratosG, &a.GordurasG, &a.Ativo, &a.NutriAlimentoID)
}

// ListAlimentos retorna o catálogo de alimentos da unidade (ativos e inativos).
func (s *Store) ListAlimentos(ctx context.Context, unidadeID int64) ([]domain.Alimento, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT `+alimentoSelect+` FROM alimentos a WHERE a.unidade_id = $1 ORDER BY a.categoria, a.nome`,
		unidadeID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []domain.Alimento{}
	for rows.Next() {
		var a domain.Alimento
		if err := scanAlimento(rows, &a); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

func (s *Store) GetAlimento(ctx context.Context, id int64) (domain.Alimento, error) {
	var a domain.Alimento
	err := scanAlimento(s.pool.QueryRow(ctx, `SELECT `+alimentoSelect+` FROM alimentos a WHERE a.id = $1`, id), &a)
	if errors.Is(err, pgx.ErrNoRows) {
		return a, ErrNotFound
	}
	return a, err
}

// CreateAlimento insere um alimento no catálogo da unidade. Quando `in.NovaRef` é informado,
// cria também a referência nutricional (medidas caseiras) na mesma transação e a vincula;
// alternativamente usa `in.NutriAlimentoID` para vincular uma referência existente.
func (s *Store) CreateAlimento(ctx context.Context, unidadeID int64, in domain.AlimentoInput) (domain.Alimento, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Alimento{}, err
	}
	defer tx.Rollback(ctx)

	nutriID, err := s.resolverRefNutricional(ctx, tx, in)
	if err != nil {
		return domain.Alimento{}, err
	}

	var id int64
	err = tx.QueryRow(ctx,
		`INSERT INTO alimentos
		   (unidade_id, nome, categoria, ingredientes, alergenos, restricoes_atendidas,
		    nao_indicado_para, calorias, proteinas_g, carboidratos_g, gorduras_g, ativo, nutri_alimento_id)
		 VALUES ($1,$2,NULLIF($3,''),$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
		 RETURNING id`,
		unidadeID, in.Nome, in.Categoria, arr(in.Ingredientes), arr(in.Alergenos), arr(in.RestricoesAtendidas),
		arr(in.NaoIndicadoPara), in.Calorias, in.ProteinasG, in.CarboidratosG, in.GordurasG, in.Ativo, nutriID,
	).Scan(&id)
	if err != nil {
		return domain.Alimento{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.Alimento{}, err
	}
	return s.GetAlimento(ctx, id)
}

// UpdateAlimento edita um alimento. Mantém o vínculo nutricional atual se nada novo for enviado.
func (s *Store) UpdateAlimento(ctx context.Context, id int64, in domain.AlimentoInput) (domain.Alimento, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Alimento{}, err
	}
	defer tx.Rollback(ctx)

	nutriID, err := s.resolverRefNutricional(ctx, tx, in)
	if err != nil {
		return domain.Alimento{}, err
	}

	ct, err := tx.Exec(ctx,
		`UPDATE alimentos SET
		   nome=$2, categoria=NULLIF($3,''), ingredientes=$4, alergenos=$5, restricoes_atendidas=$6,
		   nao_indicado_para=$7, calorias=$8, proteinas_g=$9, carboidratos_g=$10, gorduras_g=$11,
		   ativo=$12, nutri_alimento_id=COALESCE($13, nutri_alimento_id), updated_at=now()
		 WHERE id=$1`,
		id, in.Nome, in.Categoria, arr(in.Ingredientes), arr(in.Alergenos), arr(in.RestricoesAtendidas),
		arr(in.NaoIndicadoPara), in.Calorias, in.ProteinasG, in.CarboidratosG, in.GordurasG, in.Ativo, nutriID,
	)
	if err != nil {
		return domain.Alimento{}, err
	}
	if ct.RowsAffected() == 0 {
		return domain.Alimento{}, ErrNotFound
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.Alimento{}, err
	}
	return s.GetAlimento(ctx, id)
}

// SetAlimentoAtivo ativa/desativa um alimento (soft-delete — preserva histórico de cardápio).
func (s *Store) SetAlimentoAtivo(ctx context.Context, id int64, ativo bool) error {
	ct, err := s.pool.Exec(ctx, `UPDATE alimentos SET ativo=$2, updated_at=now() WHERE id=$1`, id, ativo)
	if err != nil {
		return err
	}
	if ct.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// resolverRefNutricional decide o nutri_alimento_id a gravar: cria uma nova referência
// (com porções) quando `in.NovaRef` vem preenchido, senão usa o id informado (ou nil).
func (s *Store) resolverRefNutricional(ctx context.Context, tx pgx.Tx, in domain.AlimentoInput) (*int64, error) {
	if in.NovaRef == nil {
		return in.NutriAlimentoID, nil
	}
	ref := *in.NovaRef
	if ref.Nome == "" {
		ref.Nome = in.Nome
	}
	if ref.Categoria == "" {
		ref.Categoria = in.Categoria
	}
	id, err := s.createNutriRefTx(ctx, tx, ref)
	if err != nil {
		return nil, err
	}
	return &id, nil
}
