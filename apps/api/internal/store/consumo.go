package store

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

// RegistroConsumoInput é a entrada do registro de consumo (regra §5/§6).
// Itens = o que o usuário comeu; Sobras = o que deixou no prato (opcional —
// alimenta o índice de resto-ingesta do admin).
type RegistroConsumoInput struct {
	UsuarioID *int64                      `json:"usuario_id,omitempty"`
	UnidadeID int64                       `json:"unidade_id"`
	SessaoID  *string                     `json:"sessao_id,omitempty"`
	Refeicao  string                      `json:"refeicao,omitempty"`
	Itens     []domain.ConsumoItemEntrada `json:"itens"`
	Sobras    []domain.ConsumoItemEntrada `json:"sobras,omitempty"`
}

// RegistroConsumoResultado devolve o cálculo, a pontuação e o estado de gamificação.
type RegistroConsumoResultado struct {
	ConsumoID   int64                    `json:"consumo_id"`
	Consumido   domain.ConsumoTotais     `json:"consumido"`
	Resto       domain.ConsumoTotais     `json:"resto"`
	IndiceResto float64                  `json:"indice_resto_perc"`
	Pontuacao   *domain.PontuacaoConsumo `json:"pontuacao,omitempty"`
	Gamificacao *domain.Gamificacao      `json:"gamificacao,omitempty"`

	// Preenchido quando o registro foi salvo mas NÃO pontuou.
	PontuacaoPendente *domain.PontuacaoPendente `json:"pontuacao_pendente,omitempty"`
}

// RegistrarConsumo calcula os nutrientes (determinístico, via base de medidas
// caseiras), persiste o consumo, pontua o usuário (quando identificado) e grava
// o evento `consumo.registrado` no outbox NA MESMA transação — o worker Go
// consome esse evento para manter o agregado de desperdício do admin.
func (s *Store) RegistrarConsumo(ctx context.Context, in RegistroConsumoInput) (RegistroConsumoResultado, error) {
	var out RegistroConsumoResultado

	// O cardápio daquela unidade, naquele dia, tem precedência sobre a base
	// geral: é a melhor evidência do que a pessoa comeu. Data no fuso do
	// refeitório — em UTC, a partir das 21h a data vira e o cardápio some.
	escopo := EscopoCardapio{UnidadeID: in.UnidadeID, Data: agoraLocal().Format("2006-01-02")}

	consumido, err := s.CalcularConsumo(ctx, in.Itens, escopo)
	if err != nil {
		return out, err
	}
	// Completo: true — conjunto vazio de sobras é trivialmente completo. O zero
	// value diria o contrário e reprovaria toda refeição sem sobra.
	resto := domain.ConsumoTotais{Completo: true}
	if len(in.Sobras) > 0 {
		resto, err = s.CalcularConsumo(ctx, in.Sobras, escopo)
		if err != nil {
			return out, err
		}
	}
	out.Consumido = consumido
	out.Resto = resto
	out.IndiceResto = domain.IndiceResto(consumido.GramasTotais, resto.GramasTotais)

	refeicao := in.Refeicao
	if refeicao == "" {
		refeicao = "almoco"
	}

	// Meta calórica e streak (para pontuação) — fora da transação, leitura simples.
	metaDiaria := 0
	streak := 0
	if in.UsuarioID != nil {
		if perfil, err := s.GetPerfil(ctx, *in.UsuarioID); err == nil && perfil.MetaCalorica != nil {
			metaDiaria = *perfil.MetaCalorica
		}
		streak = s.streakAtualizado(ctx, *in.UsuarioID)
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return out, err
	}
	defer tx.Rollback(ctx)

	itensJSON, _ := json.Marshal(consumido.Itens)
	restoJSON, _ := json.Marshal(resto.Itens)

	// O registro é sempre gravado (é histórico do usuário), mas a PONTUAÇÃO
	// depende de o total estar completo: pontuar é medir a distância entre o que
	// a pessoa comeu e a meta dela, e com item fora da soma essa distância é
	// falsa. Pontos são a moeda do produto — distribuí-los sobre número errado
	// corrompe o ranking e não tem como ser desfeito depois.
	completo := consumido.Completo && resto.Completo

	var pontuacao domain.PontuacaoConsumo
	pontos := 0
	pontua := in.UsuarioID != nil && completo
	if pontua {
		pontuacao = domain.PontuarConsumo(consumido.Kcal, resto.Kcal, metaDiaria, streak)
		pontos = pontuacao.Pontos
		out.Pontuacao = &pontuacao
	} else if in.UsuarioID != nil {
		ignorados := append(append([]string{}, consumido.ItensIgnorados...), resto.ItensIgnorados...)
		out.PontuacaoPendente = &domain.PontuacaoPendente{
			Motivo: "não reconhecemos todos os itens informados, então o total calórico " +
				"está incompleto e a pontuação não pôde ser calculada",
			ItensIgnorados: ignorados,
		}
	}

	metaRefeicao := 0
	if metaDiaria > 0 {
		metaRefeicao = domain.MetaRefeicao(metaDiaria)
	}

	// cardapio_dia de hoje (se existir) para correlação com o cardápio servido.
	var cardapioDiaID *int64
	_ = s.pool.QueryRow(ctx,
		`SELECT id FROM cardapio_dias WHERE unidade_id = $1 AND data = $2::date`,
		in.UnidadeID, agoraLocal().Format("2006-01-02"),
	).Scan(&cardapioDiaID)

	err = tx.QueryRow(ctx,
		`INSERT INTO consumos (usuario_id, unidade_id, cardapio_dia_id, sessao_id, refeicao,
		                       itens, kcal_estimada, gramas_estimadas, proteina_g, carboidrato_g,
		                       gordura_g, meta_kcal_refeicao, resto_itens, resto_g, resto_kcal, pontos,
		                       completo)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
		 RETURNING id`,
		in.UsuarioID, in.UnidadeID, cardapioDiaID, in.SessaoID, refeicao,
		itensJSON, consumido.Kcal, consumido.GramasTotais, consumido.ProteinaG,
		consumido.CarboidratoG, consumido.GorduraG, metaRefeicao,
		restoJSON, resto.GramasTotais, resto.Kcal, pontos, completo,
	).Scan(&out.ConsumoID)
	if err != nil {
		return out, err
	}

	if pontua {
		g, err := s.aplicarPontuacaoTx(ctx, tx, *in.UsuarioID, out.ConsumoID, pontuacao, streak)
		if err != nil {
			return out, err
		}
		out.Gamificacao = &g
	}

	payload, _ := json.Marshal(map[string]any{
		"consumo_id":  out.ConsumoID,
		"unidade_id":  in.UnidadeID,
		"data":        agoraLocal().Format("2006-01-02"),
		"consumido_g": consumido.GramasTotais, "consumido_kcal": consumido.Kcal,
		"resto_g": resto.GramasTotais, "resto_kcal": resto.Kcal,
		"completo": completo,
	})
	if _, err := tx.Exec(ctx,
		`INSERT INTO outbox (aggregate, event_type, payload) VALUES ('consumo', 'consumo.registrado', $1)`,
		payload,
	); err != nil {
		return out, err
	}

	return out, tx.Commit(ctx)
}

// streakAtualizado devolve o streak que o usuário terá APÓS registrar hoje:
// registrou ontem → streak+1; já registrou hoje → mantém; senão → recomeça em 1.
func (s *Store) streakAtualizado(ctx context.Context, usuarioID int64) int {
	var streak int
	var ultimo *time.Time
	err := s.pool.QueryRow(ctx,
		`SELECT streak_dias, ultimo_registro FROM gamificacao WHERE usuario_id = $1`,
		usuarioID,
	).Scan(&streak, &ultimo)
	if err != nil || ultimo == nil {
		return 1
	}
	// ultimo_registro é DATE (sem fuso): pgx devolve meia-noite UTC. Lemos a data
	// "crua" em UTC e comparamos com a data-calendário local do refeitório.
	uy, um, ud := ultimo.UTC().Date()
	ultimoDia := time.Date(uy, um, ud, 0, 0, 0, 0, locRefeitorio)
	dias := int(dataDe(agoraLocal()).Sub(ultimoDia).Hours() / 24)
	switch dias {
	case 0:
		return streak
	case 1:
		return streak + 1
	default:
		return 1
	}
}

func (s *Store) aplicarPontuacaoTx(ctx context.Context, tx pgx.Tx, usuarioID, consumoID int64,
	p domain.PontuacaoConsumo, streak int) (domain.Gamificacao, error) {

	var g domain.Gamificacao
	// data local do refeitório (não CURRENT_DATE do servidor, que roda em UTC):
	// registro às 22h não pode contar como "amanhã".
	hoje := agoraLocal().Format("2006-01-02")
	err := tx.QueryRow(ctx,
		`INSERT INTO gamificacao (usuario_id, pontos, nivel, streak_dias, ultimo_registro, updated_at)
		 VALUES ($1, $2, 1, $3, $4::date, now())
		 ON CONFLICT (usuario_id) DO UPDATE
		    SET pontos = gamificacao.pontos + EXCLUDED.pontos,
		        streak_dias = $3, ultimo_registro = $4::date, updated_at = now()
		 RETURNING usuario_id, pontos, streak_dias, ultimo_registro`,
		usuarioID, p.Pontos, streak, hoje,
	).Scan(&g.UsuarioID, &g.Pontos, &g.StreakDias, &g.UltimoRegistro)
	if err != nil {
		return g, err
	}

	g.Nivel = domain.NivelPara(g.Pontos)
	if _, err := tx.Exec(ctx,
		`UPDATE gamificacao SET nivel = $2 WHERE usuario_id = $1`, usuarioID, g.Nivel); err != nil {
		return g, err
	}

	if _, err := tx.Exec(ctx,
		`INSERT INTO eventos_pontuacao (usuario_id, consumo_id, pontos, motivo)
		 VALUES ($1, $2, $3, $4)`,
		usuarioID, consumoID, p.Pontos, p.Motivo,
	); err != nil {
		return g, err
	}
	return g, nil
}

// GetGamificacao retorna o estado de gamificação + eventos recentes do usuário.
func (s *Store) GetGamificacao(ctx context.Context, usuarioID int64) (domain.Gamificacao, []domain.EventoPontuacao, error) {
	var g domain.Gamificacao
	err := s.pool.QueryRow(ctx,
		`SELECT usuario_id, pontos, nivel, streak_dias, ultimo_registro
		   FROM gamificacao WHERE usuario_id = $1`, usuarioID,
	).Scan(&g.UsuarioID, &g.Pontos, &g.Nivel, &g.StreakDias, &g.UltimoRegistro)
	if errors.Is(err, pgx.ErrNoRows) {
		g = domain.Gamificacao{UsuarioID: usuarioID, Pontos: 0, Nivel: 1}
	} else if err != nil {
		return g, nil, err
	}

	rows, err := s.pool.Query(ctx,
		`SELECT id, pontos, COALESCE(motivo,''), created_at
		   FROM eventos_pontuacao WHERE usuario_id = $1
		  ORDER BY created_at DESC LIMIT 20`, usuarioID)
	if err != nil {
		return g, nil, err
	}
	defer rows.Close()

	var eventos []domain.EventoPontuacao
	for rows.Next() {
		var e domain.EventoPontuacao
		if err := rows.Scan(&e.ID, &e.Pontos, &e.Motivo, &e.CreatedAt); err != nil {
			return g, nil, err
		}
		eventos = append(eventos, e)
	}
	return g, eventos, rows.Err()
}

// GetRanking retorna o top-N de pontos da unidade.
func (s *Store) GetRanking(ctx context.Context, unidadeID int64, limit int) ([]domain.RankingEntry, error) {
	if limit <= 0 || limit > 100 {
		limit = 10
	}
	rows, err := s.pool.Query(ctx,
		`SELECT u.id, u.nome, g.pontos, g.nivel
		   FROM gamificacao g
		   JOIN usuarios u ON u.id = g.usuario_id
		  WHERE ($1 = 0 OR u.unidade_id = $1)
		  ORDER BY g.pontos DESC, u.nome
		  LIMIT $2`, unidadeID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []domain.RankingEntry
	for rows.Next() {
		var e domain.RankingEntry
		if err := rows.Scan(&e.UsuarioID, &e.Nome, &e.Pontos, &e.Nivel); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}
