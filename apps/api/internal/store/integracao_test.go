//go:build integration

// Testes de integração REAIS (Postgres): exercitam o caminho completo de
// gamificação e desperdício contra um banco com as migrations aplicadas.
//
// Rodar:  ./scripts/test-integration.sh   (sobe um pgvector descartável)
// ou:     TEST_DATABASE_URL=postgres://... go test -tags integration ./internal/store/
package store_test

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tamy-ai/menu-ai/api/internal/db"
	"github.com/tamy-ai/menu-ai/api/internal/domain"
	"github.com/tamy-ai/menu-ai/api/internal/store"
)

var (
	pool *pgxpool.Pool
	st   *store.Store
)

func TestMain(m *testing.M) {
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		fmt.Println("TEST_DATABASE_URL não definido — pulando testes de integração")
		os.Exit(0)
	}
	ctx := context.Background()
	var err error
	pool, err = db.Connect(ctx, url)
	if err != nil {
		fmt.Println("conectar:", err)
		os.Exit(1)
	}
	if err := db.Migrate(ctx, pool); err != nil {
		fmt.Println("migrations:", err)
		os.Exit(1)
	}
	st = store.New(pool)
	os.Exit(m.Run())
}

// limpar zera as tabelas de domínio entre testes (mantém o schema).
func limpar(t *testing.T) {
	t.Helper()
	_, err := pool.Exec(context.Background(), `
		TRUNCATE consumos, eventos_pontuacao, gamificacao, desperdicio_diario,
		         inbox_processados, outbox, cardapio_itens, cardapio_dias,
		         alimentos, nutri_porcoes, nutri_alimentos, medida_aliases,
		         mensagens, sessoes, usuarios, unidades RESTART IDENTITY CASCADE`)
	if err != nil {
		t.Fatalf("limpar tabelas: %v", err)
	}
}

// seedBase cria unidade + base nutricional mínima (arroz por concha) e devolve o id da unidade.
func seedBase(t *testing.T) int64 {
	t.Helper()
	ctx := context.Background()
	var unidadeID int64
	if err := pool.QueryRow(ctx,
		`INSERT INTO unidades (nome, slug) VALUES ('Unidade Teste','unidade-teste') RETURNING id`,
	).Scan(&unidadeID); err != nil {
		t.Fatalf("seed unidade: %v", err)
	}

	var arrozID int64
	if err := pool.QueryRow(ctx,
		`INSERT INTO nutri_alimentos (nome, nome_norm, categoria, aliases)
		 VALUES ('Arroz cozido','arroz cozido','Cereais','{arroz}') RETURNING id`,
	).Scan(&arrozID); err != nil {
		t.Fatalf("seed nutri_alimento: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO nutri_porcoes (alimento_id, medida_label, medida_cod, quantidade_g, kcal, proteina_g, carboidrato_g, gordura_g)
		 VALUES ($1,'CO CH','CO',80,110,2,23,0.2), ($1,'100g',NULL,100,130,2.5,28,0.3)`, arrozID,
	); err != nil {
		t.Fatalf("seed porcoes: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO medida_aliases (alias, medida_cod, descricao) VALUES ('concha','CO','concha')`,
	); err != nil {
		t.Fatalf("seed medida_aliases: %v", err)
	}
	return unidadeID
}

func criarUsuario(t *testing.T, unidadeID int64, nome string) domain.Usuario {
	t.Helper()
	peso, altura, sexo, nivel := 80.0, 175.0, "M", "moderado"
	idade := 40
	u, err := st.CreateUsuario(context.Background(), domain.UsuarioInput{
		UnidadeID: &unidadeID, Nome: nome, PesoKg: &peso, AlturaCm: &altura,
		Idade: &idade, Sexo: &sexo, NivelAtividade: &nivel,
	})
	if err != nil {
		t.Fatalf("criar usuário: %v", err)
	}
	return u
}

func registrar(t *testing.T, unidadeID, usuarioID int64, conchas, sobraConchas float64) store.RegistroConsumoResultado {
	t.Helper()
	in := store.RegistroConsumoInput{
		UsuarioID: &usuarioID, UnidadeID: unidadeID,
		Itens: []domain.ConsumoItemEntrada{{Alimento: "arroz", Medida: "concha", Quantidade: conchas}},
	}
	if sobraConchas > 0 {
		in.Sobras = []domain.ConsumoItemEntrada{{Alimento: "arroz", Medida: "concha", Quantidade: sobraConchas}}
	}
	out, err := st.RegistrarConsumo(context.Background(), in)
	if err != nil {
		t.Fatalf("registrar consumo: %v", err)
	}
	return out
}

// TestIntegracaoRegistrarConsumo cobre a transação completa: consumo + pontuação
// + evento de pontuação + outbox, com valores calculados da base nutricional.
func TestIntegracaoRegistrarConsumo(t *testing.T) {
	limpar(t)
	unidadeID := seedBase(t)
	u := criarUsuario(t, unidadeID, "Seu João")
	ctx := context.Background()

	out := registrar(t, unidadeID, u.ID, 3, 1)

	if out.Consumido.Kcal != 330 { // 3 conchas × 110 kcal
		t.Errorf("kcal consumida = %v, esperado 330", out.Consumido.Kcal)
	}
	if out.Resto.GramasTotais != 80 {
		t.Errorf("resto = %vg, esperado 80", out.Resto.GramasTotais)
	}
	if out.Pontuacao == nil || out.Gamificacao == nil {
		t.Fatalf("pontuação/gamificação ausentes: %+v", out)
	}
	if out.Gamificacao.Pontos != out.Pontuacao.Pontos {
		t.Errorf("gamificação acumulada (%d) difere dos pontos do registro (%d)",
			out.Gamificacao.Pontos, out.Pontuacao.Pontos)
	}

	// As 4 escritas da transação.
	for tabela, esperado := range map[string]int{"consumos": 1, "eventos_pontuacao": 1, "gamificacao": 1} {
		var n int
		if err := pool.QueryRow(ctx, `SELECT count(*) FROM `+tabela).Scan(&n); err != nil || n != esperado {
			t.Errorf("%s: count=%d err=%v, esperado %d", tabela, n, err, esperado)
		}
	}
	var payload []byte
	if err := pool.QueryRow(ctx,
		`SELECT payload FROM outbox WHERE event_type = 'consumo.registrado'`).Scan(&payload); err != nil {
		t.Fatalf("evento consumo.registrado não gravado no outbox: %v", err)
	}
	var ev store.ConsumoRegistradoEvento
	if err := json.Unmarshal(payload, &ev); err != nil {
		t.Fatalf("payload inválido: %v", err)
	}
	if ev.UnidadeID != unidadeID || ev.RestoG != 80 {
		t.Errorf("payload inconsistente: %+v", ev)
	}
	// data do evento = dia local do refeitório (America/Sao_Paulo)
	loc, _ := time.LoadLocation("America/Sao_Paulo")
	if hoje := time.Now().In(loc).Format("2006-01-02"); ev.Data != hoje {
		t.Errorf("data do evento = %s, esperado %s (fuso do refeitório)", ev.Data, hoje)
	}
}

// TestIntegracaoStreak cobre a progressão real do streak em múltiplos dias
// (mesmo dia mantém, ontem incrementa, gap reinicia).
func TestIntegracaoStreak(t *testing.T) {
	limpar(t)
	unidadeID := seedBase(t)
	u := criarUsuario(t, unidadeID, "Seu João")
	ctx := context.Background()

	if out := registrar(t, unidadeID, u.ID, 3, 0); out.Gamificacao.StreakDias != 1 {
		t.Fatalf("primeiro registro: streak = %d, esperado 1", out.Gamificacao.StreakDias)
	}
	// registrar de novo no mesmo dia mantém o streak
	if out := registrar(t, unidadeID, u.ID, 3, 0); out.Gamificacao.StreakDias != 1 {
		t.Errorf("mesmo dia: streak = %d, esperado 1", out.Gamificacao.StreakDias)
	}
	// simula último registro ontem → incrementa
	if _, err := pool.Exec(ctx,
		`UPDATE gamificacao SET ultimo_registro = ultimo_registro - 1 WHERE usuario_id = $1`, u.ID); err != nil {
		t.Fatal(err)
	}
	out := registrar(t, unidadeID, u.ID, 3, 0)
	if out.Gamificacao.StreakDias != 2 {
		t.Errorf("registro no dia seguinte: streak = %d, esperado 2", out.Gamificacao.StreakDias)
	}
	if out.Pontuacao.BonusStreak != 5 { // +5 a partir do 2º dia consecutivo
		t.Errorf("bônus streak = %d, esperado 5", out.Pontuacao.BonusStreak)
	}
	// simula gap de 3 dias → reinicia
	if _, err := pool.Exec(ctx,
		`UPDATE gamificacao SET ultimo_registro = ultimo_registro - 3 WHERE usuario_id = $1`, u.ID); err != nil {
		t.Fatal(err)
	}
	if out := registrar(t, unidadeID, u.ID, 3, 0); out.Gamificacao.StreakDias != 1 {
		t.Errorf("após gap: streak = %d, esperado 1", out.Gamificacao.StreakDias)
	}
}

// TestIntegracaoNivelERanking cobre subida de nível ao cruzar 500 pontos e o
// ranking por unidade (ordenação + isolamento entre unidades).
func TestIntegracaoNivelERanking(t *testing.T) {
	limpar(t)
	unidadeID := seedBase(t)
	ctx := context.Background()

	joao := criarUsuario(t, unidadeID, "Seu João")
	maria := criarUsuario(t, unidadeID, "Maria")

	// outra unidade, não pode aparecer no ranking da primeira
	var outraID int64
	if err := pool.QueryRow(ctx,
		`INSERT INTO unidades (nome, slug) VALUES ('Outra','outra') RETURNING id`).Scan(&outraID); err != nil {
		t.Fatal(err)
	}
	fora := criarUsuario(t, outraID, "Fora Da Unidade")

	registrar(t, unidadeID, joao.ID, 3, 0)
	registrar(t, unidadeID, maria.ID, 1, 0) // 110 kcal, longe da meta → menos pontos
	registrar(t, outraID, fora.ID, 3, 0)

	// João a 490 pontos: próximo registro deve cruzar 500 → nível 2
	if _, err := pool.Exec(ctx,
		`UPDATE gamificacao SET pontos = 490 WHERE usuario_id = $1`, joao.ID); err != nil {
		t.Fatal(err)
	}
	out := registrar(t, unidadeID, joao.ID, 3, 0)
	if out.Gamificacao.Pontos < 500 || out.Gamificacao.Nivel != 2 {
		t.Errorf("nível = %d (pontos %d), esperado nível 2 com ≥500 pontos",
			out.Gamificacao.Nivel, out.Gamificacao.Pontos)
	}

	ranking, err := st.GetRanking(ctx, unidadeID, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(ranking) != 2 {
		t.Fatalf("ranking da unidade tem %d entradas, esperado 2 (isolamento por unidade): %+v", len(ranking), ranking)
	}
	if ranking[0].UsuarioID != joao.ID {
		t.Errorf("1º do ranking = %s, esperado Seu João", ranking[0].Nome)
	}
	if ranking[0].Pontos < ranking[1].Pontos {
		t.Errorf("ranking fora de ordem: %+v", ranking)
	}
	geral, err := st.GetRanking(ctx, 0, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(geral) != 3 {
		t.Errorf("ranking geral tem %d entradas, esperado 3", len(geral))
	}
}

// TestIntegracaoDesperdicio cobre o ETL do worker (agregado diário) com a
// idempotência do inbox e o resumo lido pelo dashboard admin.
func TestIntegracaoDesperdicio(t *testing.T) {
	limpar(t)
	unidadeID := seedBase(t)
	u := criarUsuario(t, unidadeID, "Seu João")
	ctx := context.Background()

	// registro real com sobra → evento no outbox
	registrar(t, unidadeID, u.ID, 3, 1)
	var msgID string
	var payload []byte
	if err := pool.QueryRow(ctx,
		`SELECT id::text, payload FROM outbox WHERE event_type='consumo.registrado'`).Scan(&msgID, &payload); err != nil {
		t.Fatal(err)
	}

	// simula o worker (mesma lógica do cmd/worker): inbox → agrega → marca.
	entregar := func() {
		processado, err := st.AlreadyProcessed(ctx, msgID, "go-worker")
		if err != nil {
			t.Fatal(err)
		}
		if processado {
			return
		}
		if err := st.AplicarConsumoNoAgregado(ctx, payload); err != nil {
			t.Fatal(err)
		}
		if err := st.MarkProcessed(ctx, msgID, "go-worker"); err != nil {
			t.Fatal(err)
		}
	}
	entregar()
	entregar() // redelivery: não pode dobrar o agregado

	var refeicoes int
	var restoG float64
	if err := pool.QueryRow(ctx,
		`SELECT refeicoes, resto_g FROM desperdicio_diario WHERE unidade_id = $1`, unidadeID,
	).Scan(&refeicoes, &restoG); err != nil {
		t.Fatalf("agregado não criado: %v", err)
	}
	if refeicoes != 1 {
		t.Errorf("refeições agregadas = %d, esperado 1 (idempotência via inbox)", refeicoes)
	}
	if restoG != 80 {
		t.Errorf("resto agregado = %vg, esperado 80", restoG)
	}

	// dashboard: índice = 80/(240+80) = 25% → crítico; top inclui o arroz
	loc, _ := time.LoadLocation("America/Sao_Paulo")
	hoje := time.Now().In(loc).Format("2006-01-02")
	resumo, err := st.GetDesperdicioResumo(ctx, unidadeID, hoje, hoje)
	if err != nil {
		t.Fatal(err)
	}
	if resumo.IndiceResto != 25.0 {
		t.Errorf("índice de resto = %v%%, esperado 25%%", resumo.IndiceResto)
	}
	if resumo.Classificacao != "critico" {
		t.Errorf("classificação = %q, esperado critico (>15%%)", resumo.Classificacao)
	}
	if resumo.RestoPerCapitaG != 80 {
		t.Errorf("resto per capita = %v, esperado 80", resumo.RestoPerCapitaG)
	}
	if len(resumo.TopDesperdicados) == 0 || resumo.TopDesperdicados[0].Alimento != "Arroz cozido" {
		t.Errorf("top desperdiçados não trouxe o arroz: %+v", resumo.TopDesperdicados)
	}
}

// TestIntegracaoPrimeiraMensagemDoDia cobre a regra contratual: a flag que obriga
// o agente a mostrar o cardápio completo na primeira conversa do dia.
func TestIntegracaoPrimeiraMensagemDoDia(t *testing.T) {
	limpar(t)
	unidadeID := seedBase(t)
	u := criarUsuario(t, unidadeID, "Seu João")
	ctx := context.Background()

	sess, err := st.CriarSessao(ctx, unidadeID, &u.ID, "web")
	if err != nil {
		t.Fatal(err)
	}
	if ok, err := st.PrimeiraMensagemDoDia(ctx, unidadeID, &u.ID, sess.ID); err != nil || !ok {
		t.Errorf("sem mensagens hoje: primeira=%v err=%v, esperado true", ok, err)
	}
	if err := st.AddMensagem(ctx, sess.ID, "user", "oi"); err != nil {
		t.Fatal(err)
	}
	if ok, _ := st.PrimeiraMensagemDoDia(ctx, unidadeID, &u.ID, sess.ID); ok {
		t.Error("após mensagem: esperado false")
	}
	// usuário identificado: vale entre sessões (nova sessão no mesmo dia NÃO é primeira)
	sess2, err := st.CriarSessao(ctx, unidadeID, &u.ID, "web")
	if err != nil {
		t.Fatal(err)
	}
	if ok, _ := st.PrimeiraMensagemDoDia(ctx, unidadeID, &u.ID, sess2.ID); ok {
		t.Error("nova sessão do mesmo usuário no mesmo dia: esperado false")
	}
	// sessão anônima é independente
	anon, err := st.CriarSessao(ctx, unidadeID, nil, "web")
	if err != nil {
		t.Fatal(err)
	}
	if ok, _ := st.PrimeiraMensagemDoDia(ctx, unidadeID, nil, anon.ID); !ok {
		t.Error("sessão anônima nova: esperado true")
	}
	if err := st.AddMensagem(ctx, anon.ID, "user", "oi"); err != nil {
		t.Fatal(err)
	}
	if ok, _ := st.PrimeiraMensagemDoDia(ctx, unidadeID, nil, anon.ID); ok {
		t.Error("sessão anônima com mensagem: esperado false")
	}
}

// TestIntegracaoLoginTelefonePin cobre a identidade leve: criar com telefone+PIN,
// logar com credencial certa/errada e conflito de telefone.
func TestIntegracaoLoginTelefonePin(t *testing.T) {
	limpar(t)
	unidadeID := seedBase(t)
	ctx := context.Background()

	tel, pin := "(11) 98888-7777", "1234"
	peso := 80.0
	u, err := st.CreateUsuario(ctx, domain.UsuarioInput{
		UnidadeID: &unidadeID, Nome: "Seu João", PesoKg: &peso, Telefone: &tel, Pin: &pin,
	})
	if err != nil {
		t.Fatal(err)
	}
	if u.Telefone == nil || *u.Telefone != "11988887777" {
		t.Errorf("telefone não normalizado: %v", u.Telefone)
	}

	logado, err := st.LoginPorTelefone(ctx, "11 98888 7777", "1234")
	if err != nil {
		t.Fatalf("login válido falhou: %v", err)
	}
	if logado.ID != u.ID {
		t.Errorf("login devolveu usuário %d, esperado %d", logado.ID, u.ID)
	}
	if _, err := st.LoginPorTelefone(ctx, tel, "9999"); err != store.ErrCredenciais {
		t.Errorf("PIN errado: err = %v, esperado ErrCredenciais", err)
	}
	if _, err := st.LoginPorTelefone(ctx, "11900000000", "1234"); err != store.ErrCredenciais {
		t.Errorf("telefone inexistente: err = %v, esperado ErrCredenciais", err)
	}

	// telefone duplicado → ErrTelefoneEmUso
	if _, err := st.CreateUsuario(ctx, domain.UsuarioInput{
		Nome: "Outro", Telefone: &tel, Pin: &pin,
	}); err != store.ErrTelefoneEmUso {
		t.Errorf("telefone duplicado: err = %v, esperado ErrTelefoneEmUso", err)
	}
}

// TestIntegracaoItemNaoResolvidoNaoPontua cobre o buraco que existia no cálculo:
// um alimento fora da base entrava no registro com nutrientes zerados e NÃO
// somava ao total, mas a pontuação era calculada em cima desse total menor — e
// a refeição ainda contaminava o índice de resto do dashboard.
func TestIntegracaoItemNaoResolvidoNaoPontua(t *testing.T) {
	limpar(t)
	unidadeID := seedBase(t)
	u := criarUsuario(t, unidadeID, "Seu João")
	ctx := context.Background()

	out, err := st.RegistrarConsumo(ctx, store.RegistroConsumoInput{
		UsuarioID: &u.ID, UnidadeID: unidadeID,
		Itens: []domain.ConsumoItemEntrada{
			{Alimento: "arroz", Medida: "concha", Quantidade: 2},
			{Alimento: "xyzabc que nao existe", Medida: "concha", Quantidade: 1},
		},
	})
	if err != nil {
		t.Fatalf("registrar consumo: %v", err)
	}

	if out.Consumido.Completo {
		t.Error("total deveria se declarar incompleto: um item não resolveu")
	}
	if len(out.Consumido.ItensIgnorados) != 1 || out.Consumido.ItensIgnorados[0] != "xyzabc que nao existe" {
		t.Errorf("itens ignorados = %v, esperado o termo cru do usuário", out.Consumido.ItensIgnorados)
	}
	if out.Pontuacao != nil {
		t.Errorf("não deveria pontuar sobre total incompleto, pontuou: %+v", out.Pontuacao)
	}
	if out.PontuacaoPendente == nil || len(out.PontuacaoPendente.ItensIgnorados) == 0 {
		t.Errorf("faltou explicar por que não pontuou: %+v", out.PontuacaoPendente)
	}

	// O consumo É gravado (é histórico do usuário), mas marcado como incompleto
	// para o agregado de desperdício poder deixá-lo de fora.
	var completo bool
	if err := pool.QueryRow(ctx, `SELECT completo FROM consumos WHERE id = $1`, out.ConsumoID).Scan(&completo); err != nil {
		t.Fatalf("ler consumo: %v", err)
	}
	if completo {
		t.Error("linha de consumos deveria estar marcada como incompleta")
	}

	// Sem pontuação, também não há evento de pontuação nem streak.
	var eventos int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM eventos_pontuacao WHERE usuario_id = $1`, u.ID).Scan(&eventos); err != nil {
		t.Fatalf("contar eventos: %v", err)
	}
	if eventos != 0 {
		t.Errorf("eventos de pontuação = %d, esperado 0", eventos)
	}
}

// TestIntegracaoAgregadoIgnoraConsumoIncompleto garante que o KPI do gestor
// (índice de resto, resto per capita) só some refeições com cobertura total.
func TestIntegracaoAgregadoIgnoraConsumoIncompleto(t *testing.T) {
	limpar(t)
	unidadeID := seedBase(t)
	ctx := context.Background()

	incompleto := false
	payload, _ := json.Marshal(map[string]any{
		"consumo_id": 1, "unidade_id": unidadeID, "data": "2026-08-23",
		"consumido_g": 100.0, "consumido_kcal": 200.0,
		"resto_g": 50.0, "resto_kcal": 80.0, "completo": incompleto,
	})
	if err := st.AplicarConsumoNoAgregado(ctx, payload); err != nil {
		t.Fatalf("aplicar agregado: %v", err)
	}

	var n int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM desperdicio_diario WHERE unidade_id = $1`, unidadeID).Scan(&n); err != nil {
		t.Fatalf("contar agregado: %v", err)
	}
	if n != 0 {
		t.Errorf("agregado somou refeição incompleta (%d linhas) — contamina o índice de resto", n)
	}

	// Evento antigo (sem o campo `completo`) continua sendo aplicado.
	antigo, _ := json.Marshal(map[string]any{
		"consumo_id": 2, "unidade_id": unidadeID, "data": "2026-08-23",
		"consumido_g": 100.0, "consumido_kcal": 200.0, "resto_g": 50.0, "resto_kcal": 80.0,
	})
	if err := st.AplicarConsumoNoAgregado(ctx, antigo); err != nil {
		t.Fatalf("aplicar agregado (evento antigo): %v", err)
	}
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM desperdicio_diario WHERE unidade_id = $1`, unidadeID).Scan(&n); err != nil {
		t.Fatalf("contar agregado: %v", err)
	}
	if n != 1 {
		t.Errorf("evento sem o campo `completo` deveria contar; linhas = %d", n)
	}
}
