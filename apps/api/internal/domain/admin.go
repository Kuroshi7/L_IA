package domain

import (
	"errors"
	"strings"
)

// PorcaoInput é uma medida caseira informada pelo nutricionista ao cadastrar um alimento
// (ex.: "concha" → 80g → kcal/macros). Alimenta nutri_porcoes (motor de consumo).
type PorcaoInput struct {
	MedidaLabel  string  `json:"medida_label"`
	MedidaCod    string  `json:"medida_cod"`
	QuantidadeG  float64 `json:"quantidade_g"`
	Kcal         float64 `json:"kcal"`
	ProteinaG    float64 `json:"proteina_g"`
	CarboidratoG float64 `json:"carboidrato_g"`
	GorduraG     float64 `json:"gordura_g"`
}

// NutriRefInput é a referência nutricional (medidas caseiras) a ser criada para o alimento.
type NutriRefInput struct {
	Nome      string        `json:"nome"`
	Categoria string        `json:"categoria"`
	Aliases   []string      `json:"aliases"`
	Porcoes   []PorcaoInput `json:"porcoes"`
}

// AlimentoInput é o payload de criação/edição de um alimento do catálogo da unidade.
// A referência nutricional vem de UMA das opções: vincular uma existente (NutriAlimentoID)
// ou criar uma nova com porções (NovaRef).
type AlimentoInput struct {
	Nome                string   `json:"nome"`
	Categoria           string   `json:"categoria"`
	Ingredientes        []string `json:"ingredientes"`
	Alergenos           []string `json:"alergenos"`
	RestricoesAtendidas []string `json:"restricoes_atendidas"`
	NaoIndicadoPara     []string `json:"nao_indicado_para"`
	Calorias            int      `json:"calorias"`
	ProteinasG          float64  `json:"proteinas_g"`
	CarboidratosG       float64  `json:"carboidratos_g"`
	GordurasG           float64  `json:"gorduras_g"`
	Ativo               bool     `json:"ativo"`

	NutriAlimentoID *int64         `json:"nutri_alimento_id,omitempty"`
	NovaRef         *NutriRefInput `json:"nova_ref,omitempty"`
}

// Validar checa o payload. Em `exigirMedidas` (criação), exige ao menos uma medida caseira
// ou o vínculo a uma referência existente — preenchimento que é trabalho do nutricionista.
func (in AlimentoInput) Validar(exigirMedidas bool) error {
	if strings.TrimSpace(in.Nome) == "" {
		return errors.New("nome é obrigatório")
	}
	if in.Calorias < 0 || in.ProteinasG < 0 || in.CarboidratosG < 0 || in.GordurasG < 0 {
		return errors.New("valores nutricionais não podem ser negativos")
	}
	if exigirMedidas && in.NutriAlimentoID == nil {
		if in.NovaRef == nil || len(in.NovaRef.Porcoes) == 0 {
			return errors.New("informe ao menos uma medida caseira (porção) ou vincule uma referência nutricional existente")
		}
	}
	if in.NovaRef != nil {
		for _, p := range in.NovaRef.Porcoes {
			if strings.TrimSpace(p.MedidaLabel) == "" || p.QuantidadeG <= 0 {
				return errors.New("cada medida caseira precisa de rótulo e quantidade em gramas maior que zero")
			}
		}
	}
	return nil
}

// CardapioItemInput é um item do cardápio de um dia.
type CardapioItemInput struct {
	AlimentoID      int64 `json:"alimento_id"`
	IsProteinaDoDia bool  `json:"is_proteina_do_dia"`
}

// NutriAlimentoDetalhe é a referência nutricional com suas porções (para edição/visualização).
type NutriAlimentoDetalhe struct {
	NutriAlimento
	Porcoes []NutriPorcao `json:"porcoes"`
}

// CardapioSemana é a grade seg–sex de uma unidade a partir de uma data inicial (segunda).
type CardapioSemana struct {
	UnidadeID int64         `json:"unidade_id"`
	Inicio    string        `json:"inicio"`
	Dias      []CardapioDia `json:"dias"`
}
