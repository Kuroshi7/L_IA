package domain

import (
	"errors"
	"strings"
)

// UsuarioInput é o payload de cadastro/edição de um usuário (cliente do refeitório).
// Os campos corporais alimentam o cálculo de IMC e da meta calórica (Mifflin-St Jeor).
type UsuarioInput struct {
	UnidadeID      *int64   `json:"unidade_id,omitempty"`
	Nome           string   `json:"nome"`
	PesoKg         *float64 `json:"peso_kg,omitempty"`
	AlturaCm       *float64 `json:"altura_cm,omitempty"`
	Idade          *int     `json:"idade,omitempty"`
	Sexo           *string  `json:"sexo,omitempty"`
	NivelAtividade *string  `json:"nivel_atividade,omitempty"`
	Restricoes     []string `json:"restricoes"`
	Preferencias   []string `json:"preferencias"`
	Alergias       []string `json:"alergias"`
	// Identidade leve (opcional): telefone + PIN permitem recuperar o perfil em
	// outro aparelho. O PIN nunca é armazenado em claro (bcrypt no store).
	Telefone *string `json:"telefone,omitempty"`
	Pin      *string `json:"pin,omitempty"`
}

// NormalizarTelefone mantém só os dígitos (aceita "(11) 98888-7777" etc.).
func NormalizarTelefone(t string) string {
	var b strings.Builder
	for _, r := range t {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	return b.String()
}

var niveisAtividade = map[string]bool{
	"sedentario": true, "leve": true, "moderado": true, "intenso": true, "muito_intenso": true,
}

func (in UsuarioInput) Validar() error {
	if strings.TrimSpace(in.Nome) == "" {
		return errors.New("nome é obrigatório")
	}
	if in.PesoKg != nil && (*in.PesoKg <= 0 || *in.PesoKg > 500) {
		return errors.New("peso_kg fora da faixa válida")
	}
	if in.AlturaCm != nil && (*in.AlturaCm <= 0 || *in.AlturaCm > 260) {
		return errors.New("altura_cm fora da faixa válida")
	}
	if in.Idade != nil && (*in.Idade <= 0 || *in.Idade > 130) {
		return errors.New("idade fora da faixa válida")
	}
	if in.Sexo != nil && *in.Sexo != "M" && *in.Sexo != "F" && *in.Sexo != "O" {
		return errors.New("sexo deve ser M, F ou O")
	}
	if in.NivelAtividade != nil && *in.NivelAtividade != "" && !niveisAtividade[*in.NivelAtividade] {
		return errors.New("nivel_atividade inválido")
	}
	if in.Telefone != nil && *in.Telefone != "" {
		d := NormalizarTelefone(*in.Telefone)
		if len(d) < 10 || len(d) > 13 {
			return errors.New("telefone inválido (use DDD + número)")
		}
	}
	if in.Pin != nil && *in.Pin != "" {
		p := strings.TrimSpace(*in.Pin)
		if len(p) < 4 || len(p) > 6 {
			return errors.New("PIN deve ter de 4 a 6 dígitos")
		}
		for _, r := range p {
			if r < '0' || r > '9' {
				return errors.New("PIN deve conter apenas números")
			}
		}
	}
	return nil
}

// ValidarCadastroComTelefone é a regra extra da CRIAÇÃO: telefone sem PIN não
// permite login depois, então o PIN é obrigatório junto. Na edição o PIN atual
// é mantido quando não reenviado.
func (in UsuarioInput) ValidarCadastroComTelefone() error {
	if in.Telefone != nil && *in.Telefone != "" && (in.Pin == nil || *in.Pin == "") {
		return errors.New("informe um PIN junto com o telefone")
	}
	return nil
}

// UnidadeInput é o payload de criação/edição de uma unidade (admin).
type UnidadeInput struct {
	Nome string `json:"nome"`
	Slug string `json:"slug"`
}

func (in UnidadeInput) Validar() error {
	if strings.TrimSpace(in.Nome) == "" {
		return errors.New("nome é obrigatório")
	}
	if strings.TrimSpace(in.Slug) == "" {
		return errors.New("slug é obrigatório")
	}
	slug := strings.TrimSpace(in.Slug)
	for _, r := range slug {
		if !(r >= 'a' && r <= 'z') && !(r >= '0' && r <= '9') && r != '-' {
			return errors.New("slug deve conter apenas letras minúsculas, números e hífens")
		}
	}
	return nil
}
