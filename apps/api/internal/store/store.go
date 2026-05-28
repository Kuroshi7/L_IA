package store

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

var ErrNotFound = errors.New("not found")

type Store struct {
	pool *pgxpool.Pool
}

func New(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

func (s *Store) Pool() *pgxpool.Pool { return s.pool }

// ----------------------------------------------------------------------------
// Unidades
// ----------------------------------------------------------------------------

func (s *Store) ListUnidades(ctx context.Context) ([]domain.Unidade, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, nome, slug, ativo FROM unidades WHERE ativo = TRUE ORDER BY nome`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []domain.Unidade
	for rows.Next() {
		var u domain.Unidade
		if err := rows.Scan(&u.ID, &u.Nome, &u.Slug, &u.Ativo); err != nil {
			return nil, err
		}
		out = append(out, u)
	}
	return out, rows.Err()
}

func (s *Store) GetUnidade(ctx context.Context, id int64) (domain.Unidade, error) {
	var u domain.Unidade
	err := s.pool.QueryRow(ctx,
		`SELECT id, nome, slug, ativo FROM unidades WHERE id = $1`, id,
	).Scan(&u.ID, &u.Nome, &u.Slug, &u.Ativo)
	if errors.Is(err, pgx.ErrNoRows) {
		return u, ErrNotFound
	}
	return u, err
}

// ----------------------------------------------------------------------------
// Cardápio
// ----------------------------------------------------------------------------

// GetCardapioDoDia retorna o cardápio (pratos ativos) de uma unidade numa data.
func (s *Store) GetCardapioDoDia(ctx context.Context, unidadeID int64, data string) (domain.CardapioDia, error) {
	var dia domain.CardapioDia
	err := s.pool.QueryRow(ctx,
		`SELECT id, unidade_id, data::text, dia_semana
		   FROM cardapio_dias WHERE unidade_id = $1 AND data = $2::date`,
		unidadeID, data,
	).Scan(&dia.ID, &dia.UnidadeID, &dia.Data, &dia.DiaSemana)
	if errors.Is(err, pgx.ErrNoRows) {
		return dia, ErrNotFound
	}
	if err != nil {
		return dia, err
	}

	rows, err := s.pool.Query(ctx,
		`SELECT a.id, a.unidade_id, a.nome, COALESCE(a.categoria,''),
		        a.ingredientes, a.alergenos, a.restricoes_atendidas, a.nao_indicado_para,
		        COALESCE(a.calorias,0), COALESCE(a.proteinas_g,0), COALESCE(a.carboidratos_g,0),
		        COALESCE(a.gorduras_g,0), a.ativo, ci.is_proteina_do_dia
		   FROM cardapio_itens ci
		   JOIN alimentos a ON a.id = ci.alimento_id
		  WHERE ci.cardapio_dia_id = $1 AND a.ativo = TRUE
		  ORDER BY a.categoria, a.nome`,
		dia.ID,
	)
	if err != nil {
		return dia, err
	}
	defer rows.Close()

	for rows.Next() {
		var a domain.Alimento
		if err := rows.Scan(&a.ID, &a.UnidadeID, &a.Nome, &a.Categoria,
			&a.Ingredientes, &a.Alergenos, &a.RestricoesAtendidas, &a.NaoIndicadoPara,
			&a.Calorias, &a.ProteinasG, &a.CarboidratosG, &a.GordurasG, &a.Ativo, &a.IsProteinaDoDia,
		); err != nil {
			return dia, err
		}
		dia.Pratos = append(dia.Pratos, a)
	}
	return dia, rows.Err()
}

// ----------------------------------------------------------------------------
// Medidas caseiras
// ----------------------------------------------------------------------------

func (s *Store) ListMedidasCaseiras(ctx context.Context) ([]domain.MedidaCaseira, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT medida, alimento, gramas, kcal FROM medidas_caseiras ORDER BY alimento, medida`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []domain.MedidaCaseira
	for rows.Next() {
		var m domain.MedidaCaseira
		if err := rows.Scan(&m.Medida, &m.Alimento, &m.Gramas, &m.Kcal); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, rows.Err()
}
