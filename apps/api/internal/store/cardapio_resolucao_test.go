package store

import "testing"

// O cardápio de 24/08/2026, que produziu o defeito IA-19.
var cardapioDoDia = []ItemDoCardapio{
	{Nome: "Arroz Integral", NutriAlimentoID: 11},
	{Nome: "Feijão Carioca", NutriAlimentoID: 12},
	{Nome: "Frango Grelhado", NutriAlimentoID: 13},
	{Nome: "Salada Verde", NutriAlimentoID: 14},
}

func TestResolverPeloCardapio(t *testing.T) {
	casos := []struct {
		nome     string
		consulta string
		querID   int64
		querOK   bool
	}{
		// O defeito: a pessoa disse "arroz", o refeitório serviu integral, e a
		// base geral devolvia o arroz branco da TACO — outro valor calórico.
		{"palavra solta casa o prato do dia", "arroz", 11, true},
		{"acento não atrapalha", "feijao", 12, true},
		{"nome composto", "frango grelhado", 13, true},
		{"maiúsculas e minúsculas", "SALADA", 14, true},
		{"consulta igual ao prato", "Arroz Integral", 11, true},

		// Fora do cardápio: precisa cair no caminho geral, não chutar.
		{"não serviu hoje", "lasanha", 0, false},
		{"vazio", "", 0, false},
		// "ovo" não pode casar "novo" nem nada por substring solta.
		{"substring não basta", "rroz", 0, false},
	}

	for _, c := range casos {
		t.Run(c.nome, func(t *testing.T) {
			prato, ok := resolverPeloCardapio(c.consulta, cardapioDoDia)
			if ok != c.querOK {
				t.Fatalf("%q: casou=%v, esperado %v", c.consulta, ok, c.querOK)
			}
			var id int64
			if prato != nil {
				id = prato.NutriAlimentoID
			}
			if id != c.querID {
				t.Fatalf("%q: id=%d, esperado %d", c.consulta, id, c.querID)
			}
		})
	}
}

func TestCardapioVazioNaoCasaNada(t *testing.T) {
	// Sem cardápio publicado, a resolução tem de devolver "não sei" para o
	// caminho geral assumir — nunca inventar um casamento.
	if _, ok := resolverPeloCardapio("arroz", nil); ok {
		t.Fatal("casou com cardápio vazio")
	}
}

func TestPrecedenciaEntreExatoEParcial(t *testing.T) {
	// Com "Arroz" e "Arroz Integral" no mesmo dia, o exato ganha — senão a
	// ordem de leitura do banco decidiria o valor calórico do usuário.
	cardapio := []ItemDoCardapio{
		{Nome: "Arroz Integral", NutriAlimentoID: 11},
		{Nome: "Arroz", NutriAlimentoID: 99},
	}
	prato, _ := resolverPeloCardapio("arroz", cardapio)
	if prato == nil || prato.NutriAlimentoID != 99 {
		t.Fatalf("prato=%+v, esperado o exato (99)", prato)
	}
}

func TestEscopoInvalidoDesligaAPrecedencia(t *testing.T) {
	casos := []EscopoCardapio{
		{},
		{UnidadeID: 1},
		{Data: "2026-08-24"},
		{UnidadeID: 0, Data: "2026-08-24"},
	}
	for _, e := range casos {
		if e.valido() {
			t.Fatalf("escopo %+v deveria ser inválido", e)
		}
	}
	if !(EscopoCardapio{UnidadeID: 1, Data: "2026-08-24"}).valido() {
		t.Fatal("escopo completo deveria ser válido")
	}
}

func TestProcedenciaCarregaOValorDeclarado(t *testing.T) {
	// IA-20: a recomendação mostra o kcal que a nutricionista declarou; o
	// registro calcula pela medida caseira. Divergir é legítimo — "1 filé" não
	// é a porção padrão — mas os dois números precisam sair com procedência,
	// senão a mesma refeição aparece com dois valores e nada explica por quê.
	kcal := 165.0
	cardapio := []ItemDoCardapio{{Nome: "Frango Grelhado", NutriAlimentoID: 13, Calorias: &kcal}}
	prato, ok := resolverPeloCardapio("frango", cardapio)
	if !ok || prato.Calorias == nil || *prato.Calorias != 165.0 {
		t.Fatalf("prato=%+v: valor declarado não veio junto", prato)
	}
}
