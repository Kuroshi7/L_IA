// Package seed embute os dados de seed (JSON) no binário.
package seed

import _ "embed"

//go:embed nutricao.json
var NutricaoJSON []byte
