package domain

import (
	"strings"
	"unicode"

	"golang.org/x/text/runes"
	"golang.org/x/text/transform"
	"golang.org/x/text/unicode/norm"
)

// NutriAlimento é um alimento da base de referência (medidas caseiras).
type NutriAlimento struct {
	ID        int64    `json:"id"`
	Nome      string   `json:"nome"`
	Categoria string   `json:"categoria"`
	Fonte     string   `json:"fonte"`
	Aliases   []string `json:"aliases"`
}

// NutriPorcao representa uma porção (medida caseira) já com nutrientes calculados.
type NutriPorcao struct {
	ID           int64   `json:"id"`
	AlimentoID   int64   `json:"alimento_id"`
	MedidaLabel  string  `json:"medida_label"`
	MedidaCod    string  `json:"medida_cod"`
	QuantidadeG  float64 `json:"quantidade_g"`
	Kcal         float64 `json:"kcal"`
	ProteinaG    float64 `json:"proteina_g"`
	CarboidratoG float64 `json:"carboidrato_g"`
	GorduraG     float64 `json:"gordura_g"`

	// Valor implausível pela checagem determinística da migração 0007. Não
	// invalida o cálculo — rebaixa a confiança, para a resposta sair como
	// aproximação em vez de número exato.
	Suspeito bool `json:"suspeito,omitempty"`
}

// ConsumoItemEntrada é um item informado pelo usuário (já estruturado pela LLM).
type ConsumoItemEntrada struct {
	Alimento   string  `json:"alimento"`
	Medida     string  `json:"medida"`
	Quantidade float64 `json:"quantidade"`
}

// ConsumoItemResultado é o item resolvido contra a base, com nutrientes do total consumido.
type ConsumoItemResultado struct {
	Entrada           ConsumoItemEntrada `json:"entrada"`
	AlimentoResolvido string             `json:"alimento_resolvido"`
	PorcaoResolvida   string             `json:"porcao_resolvida"`
	GramasTotais      float64            `json:"gramas_totais"`
	Kcal              float64            `json:"kcal"`
	ProteinaG         float64            `json:"proteina_g"`
	CarboidratoG      float64            `json:"carboidrato_g"`
	GorduraG          float64            `json:"gordura_g"`
	Confianca         string             `json:"confianca"` // alta | media | baixa
	Obs               string             `json:"obs,omitempty"`
}

// ConsumoTotais agrega o consumo de uma refeição.
//
// Completo/ItensIgnorados existem porque um item que não resolve contra a base
// entra na lista com nutrientes ZERADOS e não soma aos totais. Sem sinalizar
// isso, o total sai silenciosamente subestimado — e ele alimenta a pontuação do
// usuário e o índice de resto do dashboard. Um número incompleto apresentado
// como final é pior que a ausência do número.
type ConsumoTotais struct {
	Itens        []ConsumoItemResultado `json:"itens"`
	Kcal         float64                `json:"kcal"`
	ProteinaG    float64                `json:"proteina_g"`
	CarboidratoG float64                `json:"carboidrato_g"`
	GorduraG     float64                `json:"gordura_g"`
	GramasTotais float64                `json:"gramas_totais"`

	// Termos crus do usuário que não puderam ser resolvidos contra a base.
	// Alimentam também a lista de aliases faltantes em nutri_alimentos.
	ItensIgnorados []string `json:"itens_ignorados,omitempty"`

	// false = ao menos um item ficou de fora da soma.
	Completo bool `json:"completo"`
}

// PontuacaoPendente explica por que uma refeição registrada não pontuou.
type PontuacaoPendente struct {
	Motivo         string   `json:"motivo"`
	ItensIgnorados []string `json:"itens_ignorados,omitempty"`
}

var _accentStripper = transform.Chain(norm.NFD, runes.Remove(runes.In(unicode.Mn)), norm.NFC)

// Normalizar deixa o texto em minúsculo, sem acento e com espaços colapsados.
func Normalizar(s string) string {
	out, _, err := transform.String(_accentStripper, s)
	if err != nil {
		out = s
	}
	out = strings.ToLower(strings.TrimSpace(out))
	return strings.Join(strings.Fields(out), " ")
}
