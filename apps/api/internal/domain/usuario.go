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
