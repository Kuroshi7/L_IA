// Package migrations embute os arquivos .sql de migração no binário.
package migrations

import "embed"

//go:embed *.sql
var FS embed.FS
