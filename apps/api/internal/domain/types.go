package domain

import "time"

type Unidade struct {
	ID    int64  `json:"id"`
	Nome  string `json:"nome"`
	Slug  string `json:"slug"`
	Ativo bool   `json:"ativo"`
}

type Usuario struct {
	ID             int64    `json:"id"`
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

type Alimento struct {
	ID                  int64    `json:"id"`
	UnidadeID           int64    `json:"unidade_id"`
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
	IsProteinaDoDia     bool     `json:"is_proteina_do_dia"`
	NutriAlimentoID     *int64   `json:"nutri_alimento_id,omitempty"`
}

type CardapioDia struct {
	ID        int64      `json:"id"`
	UnidadeID int64      `json:"unidade_id"`
	Data      string     `json:"data"`
	DiaSemana string     `json:"dia_semana"`
	Pratos    []Alimento `json:"pratos"`
}

type Mensagem struct {
	Papel     string    `json:"papel"`
	Conteudo  string    `json:"conteudo"`
	CreatedAt time.Time `json:"created_at"`
}

type MedidaCaseira struct {
	Medida   string  `json:"medida"`
	Alimento string  `json:"alimento"`
	Gramas   float64 `json:"gramas"`
	Kcal     float64 `json:"kcal"`
}

// PerfilNutricional é o recorte do usuário que o agente de IA consome.
type PerfilNutricional struct {
	Nome             string   `json:"nome"`
	Restricoes       []string `json:"restricoes"`
	Preferencias     []string `json:"preferencias"`
	Alergias         []string `json:"alergias"`
	IMC              *float64 `json:"imc,omitempty"`
	ClassificacaoIMC string   `json:"classificacao_imc,omitempty"`
	MetaCalorica     *int     `json:"meta_calorica_kcal,omitempty"`
}
