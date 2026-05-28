package store

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

func (s *Store) GetUsuario(ctx context.Context, id int64) (domain.Usuario, error) {
	var u domain.Usuario
	err := s.pool.QueryRow(ctx,
		`SELECT id, unidade_id, nome, peso_kg, altura_cm, idade, sexo, nivel_atividade,
		        restricoes, preferencias, alergias
		   FROM usuarios WHERE id = $1`, id,
	).Scan(&u.ID, &u.UnidadeID, &u.Nome, &u.PesoKg, &u.AlturaCm, &u.Idade, &u.Sexo,
		&u.NivelAtividade, &u.Restricoes, &u.Preferencias, &u.Alergias)
	if errors.Is(err, pgx.ErrNoRows) {
		return u, ErrNotFound
	}
	return u, err
}

// GetPerfil retorna o recorte nutricional do usuário (IMC, meta calórica, restrições).
func (s *Store) GetPerfil(ctx context.Context, id int64) (domain.PerfilNutricional, error) {
	u, err := s.GetUsuario(ctx, id)
	if err != nil {
		return domain.PerfilNutricional{}, err
	}
	return u.MontarPerfil(), nil
}
