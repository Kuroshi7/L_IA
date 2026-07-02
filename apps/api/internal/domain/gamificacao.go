package domain

import (
	"math"
	"time"
)

// FracaoRefeicaoAlmoco é a fatia da meta calórica diária atribuída ao almoço
// (padrão nutricional: almoço concentra 30–40% do VET; usamos 35%).
const FracaoRefeicaoAlmoco = 0.35

// PontosPorNivel define quantos pontos acumulados sobem um nível.
const PontosPorNivel = 500

// Gamificacao é o estado acumulado do usuário.
type Gamificacao struct {
	UsuarioID      int64      `json:"usuario_id"`
	Pontos         int        `json:"pontos"`
	Nivel          int        `json:"nivel"`
	StreakDias     int        `json:"streak_dias"`
	UltimoRegistro *time.Time `json:"ultimo_registro,omitempty"`
}

// EventoPontuacao é uma entrada do histórico de pontos.
type EventoPontuacao struct {
	ID        int64     `json:"id"`
	Pontos    int       `json:"pontos"`
	Motivo    string    `json:"motivo"`
	CreatedAt time.Time `json:"created_at"`
}

// RankingEntry é uma linha do ranking da unidade.
type RankingEntry struct {
	UsuarioID int64  `json:"usuario_id"`
	Nome      string `json:"nome"`
	Pontos    int    `json:"pontos"`
	Nivel     int    `json:"nivel"`
}

// PontuacaoConsumo detalha a pontuação de um registro de consumo.
type PontuacaoConsumo struct {
	Pontos          int      `json:"pontos"`
	PontosBase      int      `json:"pontos_base"`
	BonusPratoLimpo int      `json:"bonus_prato_limpo"`
	BonusStreak     int      `json:"bonus_streak"`
	MetaKcal        int      `json:"meta_kcal_refeicao"`
	DesvioPerc      *float64 `json:"desvio_perc,omitempty"`
	Motivo          string   `json:"motivo"`
}

// MetaRefeicao converte a meta calórica diária na meta de uma refeição.
func MetaRefeicao(metaDiaria int) int {
	return int(math.Round(float64(metaDiaria) * FracaoRefeicaoAlmoco))
}

// NivelPara converte pontos acumulados em nível (nível 1 = 0..499, etc.).
func NivelPara(pontos int) int {
	if pontos < 0 {
		pontos = 0
	}
	return 1 + pontos/PontosPorNivel
}

// PontuarConsumo aplica a regra de negócio §6: a pontuação mede a PROXIMIDADE
// entre as calorias consumidas e a meta da refeição — não a aderência item a item.
//   - desvio 0%  → 100 pontos (base máxima)
//   - desvio ≥50% → 0 pontos (linear entre os extremos)
//   - "prato limpo" (resto ≤10% do servido — critério FNDE de aceitação) → +20
//   - streak de dias consecutivos registrando → +5 por dia, máx. +25
//
// metaDiaria==0 (perfil incompleto): pontua-se só o engajamento (registro + prato limpo).
func PontuarConsumo(kcalConsumida, restoKcal float64, metaDiaria, streakDias int) PontuacaoConsumo {
	p := PontuacaoConsumo{}

	if metaDiaria > 0 && kcalConsumida > 0 {
		meta := MetaRefeicao(metaDiaria)
		p.MetaKcal = meta
		desvio := math.Abs(kcalConsumida-float64(meta)) / float64(meta)
		perc := math.Round(desvio*1000) / 10
		p.DesvioPerc = &perc
		base := 100 * (1 - desvio/0.5)
		if base < 0 {
			base = 0
		}
		p.PontosBase = int(math.Round(base))
		p.Motivo = "proximidade da meta calórica da refeição"
	} else {
		p.PontosBase = 10
		p.Motivo = "registro de consumo (sem meta calórica no perfil)"
	}

	servido := kcalConsumida + restoKcal
	if servido > 0 && restoKcal <= servido*0.10 {
		p.BonusPratoLimpo = 20
	}
	if streakDias > 1 {
		bonus := (streakDias - 1) * 5
		if bonus > 25 {
			bonus = 25
		}
		p.BonusStreak = bonus
	}

	p.Pontos = p.PontosBase + p.BonusPratoLimpo + p.BonusStreak
	return p
}

// ----------------------------------------------------------------------------
// Desperdício (visão do admin)
// ----------------------------------------------------------------------------

// DesperdicioDia é o agregado diário de uma unidade (mantido pelo worker).
type DesperdicioDia struct {
	Data          string  `json:"data"`
	Refeicoes     int     `json:"refeicoes"`
	ConsumidoG    float64 `json:"consumido_g"`
	ConsumidoKcal float64 `json:"consumido_kcal"`
	RestoG        float64 `json:"resto_g"`
	RestoKcal     float64 `json:"resto_kcal"`
}

// AlimentoDesperdicado agrega o resto reportado por alimento.
type AlimentoDesperdicado struct {
	Alimento    string  `json:"alimento"`
	Ocorrencias int     `json:"ocorrencias"`
	RestoG      float64 `json:"resto_g"`
	RestoKcal   float64 `json:"resto_kcal"`
}

// DesperdicioResumo é a resposta do dashboard de desperdício.
type DesperdicioResumo struct {
	UnidadeID        int64                  `json:"unidade_id"`
	De               string                 `json:"de"`
	Ate              string                 `json:"ate"`
	Refeicoes        int                    `json:"refeicoes"`
	ConsumidoG       float64                `json:"consumido_g"`
	RestoG           float64                `json:"resto_g"`
	RestoKcal        float64                `json:"resto_kcal"`
	IndiceResto      float64                `json:"indice_resto_perc"`
	Classificacao    string                 `json:"classificacao"`
	RestoPerCapitaG  float64                `json:"resto_per_capita_g"`
	Dias             []DesperdicioDia       `json:"dias"`
	TopDesperdicados []AlimentoDesperdicado `json:"top_desperdicados"`
}

// IndiceResto calcula o índice de resto-ingesta proxy (%): resto / servido.
// Servido = consumido + resto (auto-relato; análogo digital da pesagem em UAN).
func IndiceResto(consumidoG, restoG float64) float64 {
	servido := consumidoG + restoG
	if servido <= 0 {
		return 0
	}
	return math.Round(restoG/servido*1000) / 10
}

// ClassificarResto aplica as faixas de referência de UAN (Vaz 2006 / Teixeira 1990).
func ClassificarResto(indicePerc float64) string {
	switch {
	case indicePerc <= 3:
		return "otimo"
	case indicePerc <= 10:
		return "bom"
	case indicePerc <= 15:
		return "atencao"
	default:
		return "critico"
	}
}
