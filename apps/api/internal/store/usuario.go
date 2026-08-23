package store

import (
	"context"
	"errors"
	"strings"

	"github.com/jackc/pgx/v5"
	"golang.org/x/crypto/bcrypt"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

// ErrCredenciais indica telefone não cadastrado ou PIN incorreto (login).
var ErrCredenciais = errors.New("telefone ou PIN incorretos")

// ErrTelefoneEmUso indica tentativa de cadastrar um telefone já vinculado a outro perfil.
var ErrTelefoneEmUso = errors.New("telefone já cadastrado em outro perfil")

func hashPin(in domain.UsuarioInput) (telefone, pinHash *string, err error) {
	if in.Telefone != nil && *in.Telefone != "" {
		t := domain.NormalizarTelefone(*in.Telefone)
		telefone = &t
	}
	if in.Pin != nil && *in.Pin != "" {
		h, e := bcrypt.GenerateFromPassword([]byte(strings.TrimSpace(*in.Pin)), bcrypt.DefaultCost)
		if e != nil {
			return nil, nil, e
		}
		hs := string(h)
		pinHash = &hs
	}
	return telefone, pinHash, nil
}

func isUniqueTelefone(err error) bool {
	return err != nil && strings.Contains(err.Error(), "idx_usuarios_telefone")
}

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

func nonNil(v []string) []string {
	if v == nil {
		return []string{}
	}
	return v
}

func (s *Store) CreateUsuario(ctx context.Context, in domain.UsuarioInput) (domain.Usuario, error) {
	var u domain.Usuario
	telefone, pinHash, err := hashPin(in)
	if err != nil {
		return u, err
	}
	err = s.pool.QueryRow(ctx,
		`INSERT INTO usuarios (unidade_id, nome, peso_kg, altura_cm, idade, sexo, nivel_atividade,
		                       restricoes, preferencias, alergias, telefone, pin_hash)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
		 RETURNING id, unidade_id, nome, peso_kg, altura_cm, idade, sexo, nivel_atividade,
		           restricoes, preferencias, alergias, telefone`,
		in.UnidadeID, in.Nome, in.PesoKg, in.AlturaCm, in.Idade, in.Sexo, in.NivelAtividade,
		nonNil(in.Restricoes), nonNil(in.Preferencias), nonNil(in.Alergias), telefone, pinHash,
	).Scan(&u.ID, &u.UnidadeID, &u.Nome, &u.PesoKg, &u.AlturaCm, &u.Idade, &u.Sexo,
		&u.NivelAtividade, &u.Restricoes, &u.Preferencias, &u.Alergias, &u.Telefone)
	if isUniqueTelefone(err) {
		return u, ErrTelefoneEmUso
	}
	return u, err
}

func (s *Store) UpdateUsuario(ctx context.Context, id int64, in domain.UsuarioInput) (domain.Usuario, error) {
	var u domain.Usuario
	telefone, pinHash, err := hashPin(in)
	if err != nil {
		return u, err
	}
	// telefone/pin_hash: COALESCE mantém o valor atual quando não reenviados —
	// editar o perfil não pode apagar a credencial de login.
	err = s.pool.QueryRow(ctx,
		`UPDATE usuarios
		    SET unidade_id = $2, nome = $3, peso_kg = $4, altura_cm = $5, idade = $6,
		        sexo = $7, nivel_atividade = $8, restricoes = $9, preferencias = $10,
		        alergias = $11, telefone = COALESCE($12, telefone),
		        pin_hash = COALESCE($13, pin_hash), updated_at = now()
		  WHERE id = $1
		 RETURNING id, unidade_id, nome, peso_kg, altura_cm, idade, sexo, nivel_atividade,
		           restricoes, preferencias, alergias, telefone`,
		id, in.UnidadeID, in.Nome, in.PesoKg, in.AlturaCm, in.Idade, in.Sexo, in.NivelAtividade,
		nonNil(in.Restricoes), nonNil(in.Preferencias), nonNil(in.Alergias), telefone, pinHash,
	).Scan(&u.ID, &u.UnidadeID, &u.Nome, &u.PesoKg, &u.AlturaCm, &u.Idade, &u.Sexo,
		&u.NivelAtividade, &u.Restricoes, &u.Preferencias, &u.Alergias, &u.Telefone)
	if errors.Is(err, pgx.ErrNoRows) {
		return u, ErrNotFound
	}
	if isUniqueTelefone(err) {
		return u, ErrTelefoneEmUso
	}
	return u, err
}

// LoginPorTelefone valida telefone+PIN e devolve o usuário. Erros de credencial
// são indistintos (não revelar se o telefone existe).
func (s *Store) LoginPorTelefone(ctx context.Context, telefone, pin string) (domain.Usuario, error) {
	t := domain.NormalizarTelefone(telefone)
	var (
		u       domain.Usuario
		pinHash *string
	)
	err := s.pool.QueryRow(ctx,
		`SELECT id, unidade_id, nome, peso_kg, altura_cm, idade, sexo, nivel_atividade,
		        restricoes, preferencias, alergias, telefone, pin_hash
		   FROM usuarios WHERE telefone = $1`, t,
	).Scan(&u.ID, &u.UnidadeID, &u.Nome, &u.PesoKg, &u.AlturaCm, &u.Idade, &u.Sexo,
		&u.NivelAtividade, &u.Restricoes, &u.Preferencias, &u.Alergias, &u.Telefone, &pinHash)
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Usuario{}, ErrCredenciais
	}
	if err != nil {
		return domain.Usuario{}, err
	}
	if pinHash == nil || bcrypt.CompareHashAndPassword([]byte(*pinHash), []byte(strings.TrimSpace(pin))) != nil {
		return domain.Usuario{}, ErrCredenciais
	}
	return u, nil
}

// ListUsuariosAdmin lista usuários com o resumo de gamificação (visão do admin).
func (s *Store) ListUsuariosAdmin(ctx context.Context, unidadeID int64) ([]map[string]any, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT u.id, u.nome, u.unidade_id, u.restricoes, u.alergias,
		        COALESCE(g.pontos,0), COALESCE(g.nivel,1), COALESCE(g.streak_dias,0),
		        (SELECT count(*) FROM consumos c WHERE c.usuario_id = u.id)
		   FROM usuarios u
		   LEFT JOIN gamificacao g ON g.usuario_id = u.id
		  WHERE ($1 = 0 OR u.unidade_id = $1)
		  ORDER BY u.nome`, unidadeID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []map[string]any
	for rows.Next() {
		var (
			id, pontos, nivel, streak, consumos int64
			nome                                string
			unID                                *int64
			restricoes, alergias                []string
		)
		if err := rows.Scan(&id, &nome, &unID, &restricoes, &alergias, &pontos, &nivel, &streak, &consumos); err != nil {
			return nil, err
		}
		out = append(out, map[string]any{
			"id": id, "nome": nome, "unidade_id": unID,
			"restricoes": restricoes, "alergias": alergias,
			"pontos": pontos, "nivel": nivel, "streak_dias": streak, "registros_consumo": consumos,
		})
	}
	return out, rows.Err()
}

// VincularTelegram associa um chat do Telegram a um usuário (1:1).
func (s *Store) VincularTelegram(ctx context.Context, usuarioID, chatID int64) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	// remove vínculo anterior deste chat (se trocou de usuário)
	if _, err := tx.Exec(ctx,
		`UPDATE usuarios SET telegram_chat_id = NULL WHERE telegram_chat_id = $1 AND id <> $2`,
		chatID, usuarioID); err != nil {
		return err
	}
	tag, err := tx.Exec(ctx,
		`UPDATE usuarios SET telegram_chat_id = $2, updated_at = now() WHERE id = $1`,
		usuarioID, chatID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return tx.Commit(ctx)
}

// GetUsuarioPorTelegram resolve o usuário vinculado a um chat do Telegram.
func (s *Store) GetUsuarioPorTelegram(ctx context.Context, chatID int64) (domain.Usuario, error) {
	var u domain.Usuario
	err := s.pool.QueryRow(ctx,
		`SELECT id, unidade_id, nome, peso_kg, altura_cm, idade, sexo, nivel_atividade,
		        restricoes, preferencias, alergias
		   FROM usuarios WHERE telegram_chat_id = $1`, chatID,
	).Scan(&u.ID, &u.UnidadeID, &u.Nome, &u.PesoKg, &u.AlturaCm, &u.Idade, &u.Sexo,
		&u.NivelAtividade, &u.Restricoes, &u.Preferencias, &u.Alergias)
	if errors.Is(err, pgx.ErrNoRows) {
		return u, ErrNotFound
	}
	return u, err
}
