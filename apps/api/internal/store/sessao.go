package store

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/jackc/pgx/v5"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

type Sessao struct {
	ID        string
	UnidadeID int64
	UsuarioID *int64
	Canal     string
}

func (s *Store) CriarSessao(ctx context.Context, unidadeID int64, usuarioID *int64, canal string) (Sessao, error) {
	if canal == "" {
		canal = "web"
	}
	var sess Sessao
	err := s.pool.QueryRow(ctx,
		`INSERT INTO sessoes (unidade_id, usuario_id, canal)
		 VALUES ($1, $2, $3)
		 RETURNING id, unidade_id, usuario_id, canal`,
		unidadeID, usuarioID, canal,
	).Scan(&sess.ID, &sess.UnidadeID, &sess.UsuarioID, &sess.Canal)
	return sess, err
}

func (s *Store) GetSessao(ctx context.Context, id string) (Sessao, error) {
	var sess Sessao
	err := s.pool.QueryRow(ctx,
		`SELECT id, unidade_id, usuario_id, canal FROM sessoes WHERE id = $1`, id,
	).Scan(&sess.ID, &sess.UnidadeID, &sess.UsuarioID, &sess.Canal)
	if errors.Is(err, pgx.ErrNoRows) {
		return sess, ErrNotFound
	}
	return sess, err
}

// ListMensagens retorna as últimas `limit` mensagens da sessão em ordem cronológica.
func (s *Store) ListMensagens(ctx context.Context, sessaoID string, limit int) ([]domain.Mensagem, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT papel, conteudo, created_at FROM (
		     SELECT papel, conteudo, created_at
		       FROM mensagens WHERE sessao_id = $1
		      ORDER BY created_at DESC LIMIT $2
		 ) t ORDER BY created_at ASC`,
		sessaoID, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []domain.Mensagem
	for rows.Next() {
		var m domain.Mensagem
		if err := rows.Scan(&m.Papel, &m.Conteudo, &m.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

// PrimeiraMensagemDoDia diz se esta é a primeira mensagem do usuário HOJE nesta
// unidade (regra contratual: a primeira recomendação do dia apresenta o cardápio
// completo). Usuário identificado → olha todas as sessões dele na unidade; sessão
// anônima → olha só a própria sessão. Dia calculado no fuso do refeitório.
func (s *Store) PrimeiraMensagemDoDia(ctx context.Context, unidadeID int64, usuarioID *int64, sessaoID string) (bool, error) {
	const tz = "America/Sao_Paulo"
	var existe bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS (
		     SELECT 1
		       FROM mensagens m
		       JOIN sessoes se ON se.id = m.sessao_id
		      WHERE m.papel = 'user'
		        AND (m.created_at AT TIME ZONE $4)::date = (now() AT TIME ZONE $4)::date
		        AND se.unidade_id = $1
		        AND CASE WHEN $2::bigint IS NOT NULL THEN se.usuario_id = $2
		                 ELSE m.sessao_id = $3::uuid END
		 )`,
		unidadeID, usuarioID, sessaoID, tz,
	).Scan(&existe)
	return !existe, err
}

// AddMensagem persiste uma mensagem e, na MESMA transação, grava um evento no
// outbox (publicação confiável). Mantém atomicidade entre estado e evento.
func (s *Store) AddMensagem(ctx context.Context, sessaoID, papel, conteudo string) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx,
		`INSERT INTO mensagens (sessao_id, papel, conteudo) VALUES ($1, $2, $3)`,
		sessaoID, papel, conteudo,
	); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx,
		`UPDATE sessoes SET updated_at = now() WHERE id = $1`, sessaoID,
	); err != nil {
		return err
	}

	payload, _ := json.Marshal(map[string]any{
		"sessao_id": sessaoID, "papel": papel, "conteudo": conteudo,
	})
	if _, err := tx.Exec(ctx,
		`INSERT INTO outbox (aggregate, event_type, payload) VALUES ($1, $2, $3)`,
		"sessao", "mensagem.registrada", payload,
	); err != nil {
		return err
	}

	return tx.Commit(ctx)
}

// VincularSessaoUsuario associa um usuário a uma sessão anônima já existente.
func (s *Store) VincularSessaoUsuario(ctx context.Context, sessaoID string, usuarioID int64) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE sessoes SET usuario_id = $2, updated_at = now() WHERE id = $1`,
		sessaoID, usuarioID)
	return err
}

func (s *Store) ResetSessao(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx, `DELETE FROM mensagens WHERE sessao_id = $1`, id)
	return err
}
