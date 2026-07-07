package store

import (
	"time"
	_ "time/tzdata" // embute tzdata: containers alpine/scratch não têm zoneinfo
)

// TZRefeitorio é o fuso usado para "dia" em todo o domínio (streak, desperdício,
// primeira conversa do dia). O container roda em UTC; sem fuso fixo, refeições
// registradas à noite cairiam no dia seguinte.
const TZRefeitorio = "America/Sao_Paulo"

var locRefeitorio = func() *time.Location {
	l, err := time.LoadLocation(TZRefeitorio)
	if err != nil {
		return time.UTC
	}
	return l
}()

func agoraLocal() time.Time { return time.Now().In(locRefeitorio) }

// dataDe devolve a meia-noite (calendário local) do instante dado.
func dataDe(t time.Time) time.Time {
	y, m, d := t.In(locRefeitorio).Date()
	return time.Date(y, m, d, 0, 0, 0, 0, locRefeitorio)
}
