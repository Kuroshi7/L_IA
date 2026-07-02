package store

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

var ErrSlugEmUso = errors.New("slug já está em uso")

func isUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}

// ListUnidadesAdmin retorna todas as unidades, inclusive inativas (visão do admin).
func (s *Store) ListUnidadesAdmin(ctx context.Context) ([]domain.Unidade, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, nome, slug, ativo FROM unidades ORDER BY nome`)
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

func (s *Store) CreateUnidade(ctx context.Context, in domain.UnidadeInput) (domain.Unidade, error) {
	var u domain.Unidade
	err := s.pool.QueryRow(ctx,
		`INSERT INTO unidades (nome, slug) VALUES ($1, $2)
		 RETURNING id, nome, slug, ativo`,
		in.Nome, in.Slug,
	).Scan(&u.ID, &u.Nome, &u.Slug, &u.Ativo)
	if isUniqueViolation(err) {
		return u, ErrSlugEmUso
	}
	return u, err
}

func (s *Store) UpdateUnidade(ctx context.Context, id int64, in domain.UnidadeInput) (domain.Unidade, error) {
	var u domain.Unidade
	err := s.pool.QueryRow(ctx,
		`UPDATE unidades SET nome = $2, slug = $3 WHERE id = $1
		 RETURNING id, nome, slug, ativo`,
		id, in.Nome, in.Slug,
	).Scan(&u.ID, &u.Nome, &u.Slug, &u.Ativo)
	if errors.Is(err, pgx.ErrNoRows) {
		return u, ErrNotFound
	}
	if isUniqueViolation(err) {
		return u, ErrSlugEmUso
	}
	return u, err
}

// SetUnidadeAtivo ativa/desativa a unidade (soft-delete: preserva cardápios e histórico).
func (s *Store) SetUnidadeAtivo(ctx context.Context, id int64, ativo bool) error {
	tag, err := s.pool.Exec(ctx, `UPDATE unidades SET ativo = $2 WHERE id = $1`, id, ativo)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}
