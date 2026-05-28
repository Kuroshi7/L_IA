package main

import (
	"context"
	"log/slog"
	"os"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tamy-ai/menu-ai/api/internal/config"
	"github.com/tamy-ai/menu-ai/api/internal/db"
)

type alimento struct {
	nome                string
	categoria           string
	ingredientes        []string
	alergenos           []string
	restricoesAtendidas []string
	naoIndicadoPara     []string
	calorias            int
	prot, carb, gord    float64
	proteinaDoDia       bool
}

type unidade struct {
	nome, slug string
	pratos     []alimento
}

func main() {
	log := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := config.Load()
	ctx := context.Background()

	pool, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Error("conectar", "err", err)
		os.Exit(1)
	}
	defer pool.Close()
	if err := db.Migrate(ctx, pool); err != nil {
		log.Error("migrations", "err", err)
		os.Exit(1)
	}

	unidades := []unidade{
		{
			nome: "Refeitório Central", slug: "central",
			pratos: []alimento{
				{nome: "Frango Grelhado", categoria: "Proteína", ingredientes: []string{"frango", "azeite", "alho"}, restricoesAtendidas: []string{"sem gluten", "sem lactose", "low carb", "proteico"}, naoIndicadoPara: []string{"vegetariano", "vegano"}, calorias: 165, prot: 31, carb: 0, gord: 4, proteinaDoDia: true},
				{nome: "Strogonoff de Grão-de-Bico", categoria: "Proteína", ingredientes: []string{"grao-de-bico", "creme de leite", "tomate"}, alergenos: []string{"lactose"}, restricoesAtendidas: []string{"vegetariano"}, naoIndicadoPara: []string{"vegano", "intolerante a lactose"}, calorias: 220, prot: 12, carb: 30, gord: 8},
				{nome: "Arroz Integral", categoria: "Acompanhamento", ingredientes: []string{"arroz integral"}, restricoesAtendidas: []string{"vegetariano", "vegano", "sem lactose"}, calorias: 110, prot: 3, carb: 23, gord: 1},
				{nome: "Feijão Carioca", categoria: "Acompanhamento", ingredientes: []string{"feijao carioca"}, restricoesAtendidas: []string{"vegetariano", "vegano", "sem lactose", "sem gluten"}, calorias: 95, prot: 6, carb: 17, gord: 1},
				{nome: "Salada Verde", categoria: "Salada", ingredientes: []string{"alface", "rucula", "tomate"}, restricoesAtendidas: []string{"vegetariano", "vegano", "sem lactose", "sem gluten", "low carb"}, calorias: 30, prot: 2, carb: 5, gord: 0},
			},
		},
		{
			nome: "Refeitório Norte", slug: "norte",
			pratos: []alimento{
				{nome: "Peixe Assado", categoria: "Proteína", ingredientes: []string{"tilapia", "limao", "azeite"}, alergenos: []string{"peixe"}, restricoesAtendidas: []string{"sem gluten", "sem lactose", "proteico"}, naoIndicadoPara: []string{"vegetariano", "vegano", "alergico a peixe"}, calorias: 150, prot: 28, carb: 0, gord: 4, proteinaDoDia: true},
				{nome: "Bowl Vegano de Quinoa", categoria: "Proteína", ingredientes: []string{"quinoa", "grao-de-bico", "brocolis"}, alergenos: []string{"gergelim"}, restricoesAtendidas: []string{"vegetariano", "vegano", "sem gluten", "sem lactose"}, calorias: 240, prot: 12, carb: 38, gord: 7},
				{nome: "Arroz Branco", categoria: "Acompanhamento", ingredientes: []string{"arroz branco"}, restricoesAtendidas: []string{"vegetariano", "vegano", "sem lactose", "sem gluten"}, calorias: 130, prot: 3, carb: 28, gord: 0},
				{nome: "Lentilha", categoria: "Acompanhamento", ingredientes: []string{"lentilha", "cebola"}, restricoesAtendidas: []string{"vegetariano", "vegano", "sem lactose", "sem gluten"}, calorias: 115, prot: 9, carb: 20, gord: 0},
				{nome: "Legumes no Vapor", categoria: "Acompanhamento", ingredientes: []string{"cenoura", "abobrinha", "vagem"}, restricoesAtendidas: []string{"vegetariano", "vegano", "sem lactose", "sem gluten", "low carb"}, calorias: 45, prot: 2, carb: 9, gord: 0},
			},
		},
	}

	for _, u := range unidades {
		if err := seedUnidade(ctx, pool, log, u); err != nil {
			log.Error("seed unidade", "slug", u.slug, "err", err)
			os.Exit(1)
		}
	}
	if err := seedMedidas(ctx, pool); err != nil {
		log.Error("seed medidas", "err", err)
		os.Exit(1)
	}
	if err := seedGuias(ctx, pool); err != nil {
		log.Error("seed guias", "err", err)
		os.Exit(1)
	}
	log.Info("seed concluído")
}

// nz garante slice não-nil (pgx envia nil como NULL, violando NOT NULL nas colunas TEXT[]).
func nz(s []string) []string {
	if s == nil {
		return []string{}
	}
	return s
}

var diasSemanaPT = map[time.Weekday]string{
	time.Sunday: "Domingo", time.Monday: "Segunda-feira", time.Tuesday: "Terça-feira",
	time.Wednesday: "Quarta-feira", time.Thursday: "Quinta-feira", time.Friday: "Sexta-feira",
	time.Saturday: "Sábado",
}

func seedUnidade(ctx context.Context, pool *pgxpool.Pool, log *slog.Logger, u unidade) error {
	var unidadeID int64
	var existed bool
	err := pool.QueryRow(ctx, `SELECT id FROM unidades WHERE slug = $1`, u.slug).Scan(&unidadeID)
	if err == nil {
		existed = true
	} else {
		if err := pool.QueryRow(ctx,
			`INSERT INTO unidades (nome, slug) VALUES ($1, $2) RETURNING id`, u.nome, u.slug,
		).Scan(&unidadeID); err != nil {
			return err
		}
	}
	if existed {
		log.Info("unidade já existe, mantendo", "slug", u.slug, "id", unidadeID)
	}

	// Cardápio para hoje + próximos 2 dias.
	for d := 0; d < 3; d++ {
		data := time.Now().AddDate(0, 0, d)
		dataStr := data.Format("2006-01-02")

		var diaID int64
		if err := pool.QueryRow(ctx,
			`INSERT INTO cardapio_dias (unidade_id, data, dia_semana) VALUES ($1, $2, $3)
			 ON CONFLICT (unidade_id, data) DO UPDATE SET dia_semana = EXCLUDED.dia_semana
			 RETURNING id`,
			unidadeID, dataStr, diasSemanaPT[data.Weekday()],
		).Scan(&diaID); err != nil {
			return err
		}

		for _, p := range u.pratos {
			var alimentoID int64
			if err := pool.QueryRow(ctx,
				`INSERT INTO alimentos
				   (unidade_id, nome, categoria, ingredientes, alergenos, restricoes_atendidas,
				    nao_indicado_para, calorias, proteinas_g, carboidratos_g, gorduras_g)
				 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
				 RETURNING id`,
				unidadeID, p.nome, p.categoria, nz(p.ingredientes), nz(p.alergenos), nz(p.restricoesAtendidas),
				nz(p.naoIndicadoPara), p.calorias, p.prot, p.carb, p.gord,
			).Scan(&alimentoID); err != nil {
				return err
			}
			if _, err := pool.Exec(ctx,
				`INSERT INTO cardapio_itens (cardapio_dia_id, alimento_id, is_proteina_do_dia)
				 VALUES ($1, $2, $3) ON CONFLICT (cardapio_dia_id, alimento_id) DO NOTHING`,
				diaID, alimentoID, p.proteinaDoDia,
			); err != nil {
				return err
			}
		}
	}
	return nil
}

func seedMedidas(ctx context.Context, pool *pgxpool.Pool) error {
	medidas := []struct {
		medida, alimento string
		gramas, kcal     float64
	}{
		{"colher de sopa", "arroz cozido", 25, 32},
		{"concha", "feijão cozido", 80, 76},
		{"filé médio", "frango grelhado", 100, 165},
		{"colher de servir", "legumes cozidos", 40, 18},
		{"pegador", "salada verde", 30, 9},
		{"concha", "lentilha cozida", 80, 92},
		{"posta média", "peixe assado", 100, 150},
	}
	for _, m := range medidas {
		if _, err := pool.Exec(ctx,
			`INSERT INTO medidas_caseiras (medida, alimento, gramas, kcal) VALUES ($1,$2,$3,$4)
			 ON CONFLICT (medida, alimento) DO NOTHING`,
			m.medida, m.alimento, m.gramas, m.kcal,
		); err != nil {
			return err
		}
	}
	return nil
}

func seedGuias(ctx context.Context, pool *pgxpool.Pool) error {
	guias := []struct{ tipo, titulo, conteudo string }{
		{"medidas_caseiras", "Guia de Medidas Caseiras",
			"Tabela de referência para porções em self-service. Uma colher de sopa de arroz cozido tem cerca de 25g (32 kcal). " +
				"Uma concha de feijão cozido tem cerca de 80g (76 kcal). Um filé médio de frango grelhado tem cerca de 100g (165 kcal). " +
				"Uma colher de servir de legumes cozidos tem cerca de 40g (18 kcal). Um pegador de salada verde tem cerca de 30g (9 kcal). " +
				"Use estas medidas para traduzir recomendações calóricas em porções práticas."},
		{"nutricao", "Referência Nutricional Básica",
			"O cálculo de necessidade calórica diária usa a fórmula de Mifflin-St Jeor, considerando peso, altura, idade, sexo e nível de atividade. " +
				"O IMC é peso dividido pela altura ao quadrado e indica a faixa de peso. Proteínas auxiliam na saciedade e manutenção muscular; " +
				"priorize a proteína do dia (limitada a uma porção por pessoa) combinada com acompanhamentos e salada."},
	}
	for _, g := range guias {
		if _, err := pool.Exec(ctx,
			`INSERT INTO guias (unidade_id, tipo, titulo, conteudo) VALUES (NULL, $1, $2, $3)`,
			g.tipo, g.titulo, g.conteudo,
		); err != nil {
			return err
		}
	}
	return nil
}
