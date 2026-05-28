package domain

import "math"

// IMC = peso(kg) / altura(m)². Retorna 0 se dados insuficientes.
func IMC(pesoKg, alturaCm float64) float64 {
	if pesoKg <= 0 || alturaCm <= 0 {
		return 0
	}
	m := alturaCm / 100.0
	return pesoKg / (m * m)
}

// ClassificacaoIMC segue as faixas da OMS.
func ClassificacaoIMC(imc float64) string {
	switch {
	case imc <= 0:
		return ""
	case imc < 18.5:
		return "abaixo do peso"
	case imc < 25:
		return "peso normal"
	case imc < 30:
		return "sobrepeso"
	case imc < 35:
		return "obesidade grau I"
	case imc < 40:
		return "obesidade grau II"
	default:
		return "obesidade grau III"
	}
}

// fatorAtividade traduz o nível de atividade no multiplicador da TMB.
func fatorAtividade(nivel string) float64 {
	switch nivel {
	case "sedentario":
		return 1.2
	case "leve":
		return 1.375
	case "moderado":
		return 1.55
	case "intenso":
		return 1.725
	case "muito_intenso":
		return 1.9
	default:
		return 1.2
	}
}

// MetaCalorica calcula a necessidade calórica diária (kcal) por Mifflin-St Jeor.
// sexo: "M" | "F" | "O" (O usa a média M/F). Retorna 0 se dados insuficientes.
func MetaCalorica(pesoKg, alturaCm float64, idade int, sexo, nivelAtividade string) int {
	if pesoKg <= 0 || alturaCm <= 0 || idade <= 0 {
		return 0
	}
	// TMB Mifflin-St Jeor: 10*peso + 6.25*altura - 5*idade + s
	base := 10*pesoKg + 6.25*alturaCm - 5*float64(idade)
	var tmb float64
	switch sexo {
	case "M":
		tmb = base + 5
	case "F":
		tmb = base - 161
	default: // "O" ou desconhecido: média
		tmb = base + (5-161)/2.0
	}
	return int(math.Round(tmb * fatorAtividade(nivelAtividade)))
}

// MontarPerfil deriva o PerfilNutricional (IMC, meta calórica) a partir do usuário.
func (u Usuario) MontarPerfil() PerfilNutricional {
	p := PerfilNutricional{
		Nome:         u.Nome,
		Restricoes:   u.Restricoes,
		Preferencias: u.Preferencias,
		Alergias:     u.Alergias,
	}
	if u.PesoKg != nil && u.AlturaCm != nil {
		imc := IMC(*u.PesoKg, *u.AlturaCm)
		if imc > 0 {
			p.IMC = &imc
			p.ClassificacaoIMC = ClassificacaoIMC(imc)
		}
	}
	if u.PesoKg != nil && u.AlturaCm != nil && u.Idade != nil {
		sexo, nivel := "O", ""
		if u.Sexo != nil {
			sexo = *u.Sexo
		}
		if u.NivelAtividade != nil {
			nivel = *u.NivelAtividade
		}
		if meta := MetaCalorica(*u.PesoKg, *u.AlturaCm, *u.Idade, sexo, nivel); meta > 0 {
			p.MetaCalorica = &meta
		}
	}
	return p
}
