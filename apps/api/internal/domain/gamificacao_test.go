package domain

import "testing"

func TestPontuarConsumo(t *testing.T) {
	// meta diária 2000 → meta da refeição 700 kcal
	casos := []struct {
		nome       string
		kcal       float64
		resto      float64
		meta       int
		streak     int
		esperado   int
		base       int
		pratoLimpo int
	}{
		{"meta exata + prato limpo", 700, 0, 2000, 1, 120, 100, 20},
		{"desvio 25% (525 kcal)", 525, 0, 2000, 1, 70, 50, 20},
		{"desvio >=50% zera a base", 1400, 0, 2000, 1, 20, 0, 20},
		{"resto grande tira o bônus", 700, 200, 2000, 1, 100, 100, 0},
		{"sem meta = engajamento", 500, 0, 0, 1, 30, 10, 20},
	}
	for _, c := range casos {
		p := PontuarConsumo(c.kcal, c.resto, c.meta, c.streak)
		if p.PontosBase != c.base {
			t.Errorf("%s: base = %d, esperado %d", c.nome, p.PontosBase, c.base)
		}
		if p.BonusPratoLimpo != c.pratoLimpo {
			t.Errorf("%s: prato limpo = %d, esperado %d", c.nome, p.BonusPratoLimpo, c.pratoLimpo)
		}
		if p.Pontos != c.esperado {
			t.Errorf("%s: pontos = %d, esperado %d", c.nome, p.Pontos, c.esperado)
		}
	}
}

func TestBonusStreak(t *testing.T) {
	if p := PontuarConsumo(700, 0, 2000, 3); p.BonusStreak != 10 {
		t.Errorf("streak 3 → bônus %d, esperado 10", p.BonusStreak)
	}
	if p := PontuarConsumo(700, 0, 2000, 10); p.BonusStreak != 25 {
		t.Errorf("streak 10 → bônus %d, esperado 25 (teto)", p.BonusStreak)
	}
}

func TestIndiceRestoEClassificacao(t *testing.T) {
	if idx := IndiceResto(450, 50); idx != 10.0 {
		t.Errorf("índice = %v, esperado 10.0", idx)
	}
	if IndiceResto(0, 0) != 0 {
		t.Error("sem dados deve ser 0")
	}
	for idx, classe := range map[float64]string{2: "otimo", 8: "bom", 12: "atencao", 20: "critico"} {
		if got := ClassificarResto(idx); got != classe {
			t.Errorf("classificar(%v) = %s, esperado %s", idx, got, classe)
		}
	}
}

func TestNivelPara(t *testing.T) {
	for pontos, nivel := range map[int]int{0: 1, 499: 1, 500: 2, 1250: 3} {
		if got := NivelPara(pontos); got != nivel {
			t.Errorf("nivel(%d) = %d, esperado %d", pontos, got, nivel)
		}
	}
}
