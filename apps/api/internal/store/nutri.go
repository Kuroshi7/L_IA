package store

import (
	"context"
	"errors"
	"strings"

	"github.com/jackc/pgx/v5"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

// ResolverAlimento encontra o alimento de referência mais próximo de `q`
// (exato → alias → similaridade trigram). Retorna o score [0..1].
func (s *Store) ResolverAlimento(ctx context.Context, q string) (domain.NutriAlimento, float64, error) {
	norm := domain.Normalizar(q)
	var a domain.NutriAlimento
	var score float64
	err := s.pool.QueryRow(ctx,
		`SELECT id, nome, COALESCE(categoria,''), COALESCE(fonte,''), aliases,
		        CASE WHEN nome_norm = $1 OR $1 = ANY(aliases) THEN 1.0
		             ELSE similarity(nome_norm, $1) END AS score
		   FROM nutri_alimentos
		  WHERE nome_norm = $1 OR $1 = ANY(aliases) OR similarity(nome_norm, $1) > 0.25
		  ORDER BY score DESC
		  LIMIT 1`,
		norm,
	).Scan(&a.ID, &a.Nome, &a.Categoria, &a.Fonte, &a.Aliases, &score)
	if errors.Is(err, pgx.ErrNoRows) {
		return a, 0, ErrNotFound
	}
	return a, score, err
}

func (s *Store) resolverMedidaCod(ctx context.Context, medida string) string {
	norm := domain.Normalizar(medida)
	if norm == "" {
		return ""
	}
	var cod string
	err := s.pool.QueryRow(ctx,
		`SELECT medida_cod FROM medida_aliases
		  WHERE alias = $1 OR similarity(alias, $1) > 0.4
		  ORDER BY CASE WHEN alias = $1 THEN 1.0 ELSE similarity(alias, $1) END DESC
		  LIMIT 1`,
		norm,
	).Scan(&cod)
	if err != nil {
		return ""
	}
	return cod
}

// ResolverPorcao escolhe a porção do alimento que melhor casa com a medida informada.
// Sem correspondência, cai na referência de 100g (confiança baixa).
func (s *Store) ResolverPorcao(ctx context.Context, alimentoID int64, medida string) (domain.NutriPorcao, string, string) {
	cod := s.resolverMedidaCod(ctx, medida)

	var p domain.NutriPorcao
	if cod != "" {
		err := s.pool.QueryRow(ctx,
			`SELECT id, alimento_id, medida_label, COALESCE(medida_cod,''),
			        quantidade_g, COALESCE(kcal,0), COALESCE(proteina_g,0),
			        COALESCE(carboidrato_g,0), COALESCE(gordura_g,0), suspeito
			   FROM nutri_porcoes
			  WHERE alimento_id = $1 AND medida_cod = $2
			  ORDER BY quantidade_g
			  LIMIT 1`,
			alimentoID, cod,
		).Scan(&p.ID, &p.AlimentoID, &p.MedidaLabel, &p.MedidaCod,
			&p.QuantidadeG, &p.Kcal, &p.ProteinaG, &p.CarboidratoG, &p.GorduraG, &p.Suspeito)
		if err == nil {
			return p, "alta", ""
		}
	}

	// fallback: 100g de referência
	err := s.pool.QueryRow(ctx,
		`SELECT id, alimento_id, medida_label, COALESCE(medida_cod,''),
		        quantidade_g, COALESCE(kcal,0), COALESCE(proteina_g,0),
		        COALESCE(carboidrato_g,0), COALESCE(gordura_g,0), suspeito
		   FROM nutri_porcoes
		  WHERE alimento_id = $1 AND medida_label = '100g'
		  LIMIT 1`,
		alimentoID,
	).Scan(&p.ID, &p.AlimentoID, &p.MedidaLabel, &p.MedidaCod,
		&p.QuantidadeG, &p.Kcal, &p.ProteinaG, &p.CarboidratoG, &p.GorduraG, &p.Suspeito)
	if err != nil {
		return domain.NutriPorcao{}, "baixa", "porção não encontrada"
	}
	return p, "baixa", "medida '" + medida + "' não encontrada; usando 100g como referência"
}

func menorConfianca(a, b string) string {
	rank := map[string]int{"baixa": 0, "media": 1, "alta": 2}
	if rank[a] <= rank[b] {
		return a
	}
	return b
}

// EscopoCardapio limita a resolução ao cardápio de um dia. Zero = sem escopo,
// e o comportamento é o antigo (só a base geral).
type EscopoCardapio struct {
	UnidadeID int64
	Data      string // YYYY-MM-DD
}

func (e EscopoCardapio) valido() bool { return e.UnidadeID > 0 && e.Data != "" }

// CalcularConsumo resolve cada item contra a base e soma os nutrientes consumidos.
//
// Com escopo, o cardápio do dia tem PRECEDÊNCIA sobre a base geral: quem disse
// "arroz" num refeitório que serviu "Arroz Integral" quis dizer o integral, e a
// busca por similaridade na base geral devolvia o arroz branco. O valor errado
// ia para consumos, para a pontuação e para o índice de resto-ingesta — erro
// silencioso, com aparência de acerto.
func (s *Store) CalcularConsumo(ctx context.Context, itens []domain.ConsumoItemEntrada, escopo EscopoCardapio) (domain.ConsumoTotais, error) {
	var doCardapio []ItemDoCardapio
	if escopo.valido() {
		var err error
		if doCardapio, err = s.itensDoCardapio(ctx, escopo.UnidadeID, escopo.Data); err != nil {
			// Cardápio indisponível não impede o cálculo — só perde a precedência.
			doCardapio = nil
		}
	}

	tot := domain.ConsumoTotais{Completo: true}
	for _, it := range itens {
		qtd := it.Quantidade
		if qtd <= 0 {
			qtd = 1
		}
		res := domain.ConsumoItemResultado{Entrada: it}

		var alimento domain.NutriAlimento
		var score float64
		var err error

		if id, nomeDoPrato, ok := resolverPeloCardapio(it.Alimento, doCardapio); ok {
			alimento, err = s.alimentoPorID(ctx, id)
			// Casou com o prato que a unidade serviu hoje: é a melhor evidência
			// que existe sobre o que a pessoa comeu.
			score = 1.0
			if err == nil {
				res.Obs = "resolvido pelo cardápio do dia: " + nomeDoPrato
			}
		} else {
			alimento, score, err = s.ResolverAlimento(ctx, it.Alimento)
		}

		if errors.Is(err, ErrNotFound) {
			// O item entra na lista (para o usuário ver que foi lido) mas NÃO
			// soma — e é por isso que o total precisa se declarar incompleto.
			res.Confianca = "baixa"
			res.Obs = "alimento não encontrado na base"
			tot.Itens = append(tot.Itens, res)
			tot.ItensIgnorados = append(tot.ItensIgnorados, it.Alimento)
			tot.Completo = false
			continue
		}
		if err != nil {
			return tot, err
		}
		confAlimento := "alta"
		if score < 0.999 {
			if score >= 0.5 {
				confAlimento = "media"
			} else {
				confAlimento = "baixa"
			}
		}

		porcao, confPorcao, obs := s.ResolverPorcao(ctx, alimento.ID, it.Medida)
		if porcao.ID == 0 {
			// Alimento existe, mas sem nenhuma porção utilizável: os nutrientes
			// seriam todos zero. Mesma consequência do caso acima.
			tot.ItensIgnorados = append(tot.ItensIgnorados, it.Alimento)
			tot.Completo = false
		}

		res.AlimentoResolvido = alimento.Nome
		res.PorcaoResolvida = porcao.MedidaLabel
		res.GramasTotais = porcao.QuantidadeG * qtd
		res.Kcal = porcao.Kcal * qtd
		res.ProteinaG = porcao.ProteinaG * qtd
		res.CarboidratoG = porcao.CarboidratoG * qtd
		res.GorduraG = porcao.GorduraG * qtd
		res.Confianca = menorConfianca(confAlimento, confPorcao)
		res.Obs = obs
		if porcao.Suspeito {
			// O casamento do nome pode ter sido perfeito e o NÚMERO ainda estar
			// errado. Sem isto, a resposta sai com a mesma cara de certeza de um
			// valor verificado — que é exatamente o comportamento que o produto
			// existe para não ter.
			res.Confianca = menorConfianca(res.Confianca, "media")
			if res.Obs == "" {
				res.Obs = "valor da tabela marcado para revisão nutricional; trate como aproximação"
			}
		}

		tot.Kcal += res.Kcal
		tot.ProteinaG += res.ProteinaG
		tot.CarboidratoG += res.CarboidratoG
		tot.GorduraG += res.GorduraG
		tot.GramasTotais += res.GramasTotais
		tot.Itens = append(tot.Itens, res)
	}
	return tot, nil
}

// ItemDoCardapio é um prato do dia já ligado à sua referência nutricional.
type ItemDoCardapio struct {
	Nome            string
	NutriAlimentoID int64
}

// itensDoCardapio devolve os pratos daquele dia que têm referência nutricional.
// Sem referência o item não serve para resolver consumo — cai no caminho geral.
func (s *Store) itensDoCardapio(ctx context.Context, unidadeID int64, data string) ([]ItemDoCardapio, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT a.nome, a.nutri_alimento_id
		   FROM cardapio_dias d
		   JOIN cardapio_itens ci ON ci.cardapio_dia_id = d.id
		   JOIN alimentos a       ON a.id = ci.alimento_id
		  WHERE d.unidade_id = $1 AND d.data = $2::date
		    AND a.nutri_alimento_id IS NOT NULL
		    AND a.ativo`,
		unidadeID, data,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var itens []ItemDoCardapio
	for rows.Next() {
		var it ItemDoCardapio
		if err := rows.Scan(&it.Nome, &it.NutriAlimentoID); err != nil {
			return nil, err
		}
		itens = append(itens, it)
	}
	return itens, rows.Err()
}

// resolverPeloCardapio tenta casar `q` com um prato servido naquele dia.
//
// Existe porque a base geral não sabe o que a unidade serviu: o usuário diz
// "arroz", o refeitório serviu "Arroz Integral", e a busca por similaridade
// devolve o arroz branco da TACO — que tem outro valor calórico. O prato certo
// estava no cardápio, e ninguém olhava.
//
// Deliberadamente conservador: casa por igualdade ou por palavra inteira contida
// no nome do prato. Similaridade difusa aqui trocaria um erro conhecido por
// outro imprevisível — se não houver certeza, o caminho geral assume.
func resolverPeloCardapio(q string, itens []ItemDoCardapio) (int64, string, bool) {
	alvo := domain.Normalizar(q)
	if alvo == "" {
		return 0, "", false
	}

	var exato, parcial *ItemDoCardapio
	for i := range itens {
		nome := domain.Normalizar(itens[i].Nome)
		if nome == alvo {
			exato = &itens[i]
			break
		}
		if parcial == nil && contemPalavra(nome, alvo) {
			parcial = &itens[i]
		}
	}
	if exato != nil {
		return exato.NutriAlimentoID, exato.Nome, true
	}
	if parcial != nil {
		return parcial.NutriAlimentoID, parcial.Nome, true
	}
	return 0, "", false
}

// contemPalavra diz se `alvo` aparece como palavra inteira em `nome`.
// Palavra inteira e não substring: "arroz" casa "arroz integral", mas "ovo"
// não pode casar "novo" nem "ovos de codorna" virar qualquer coisa com "ovo".
func contemPalavra(nome, alvo string) bool {
	for _, p := range strings.Fields(nome) {
		if p == alvo {
			return true
		}
	}
	// A consulta pode ser composta ("arroz integral") e o prato ter algo a mais.
	if len(strings.Fields(alvo)) > 1 && strings.Contains(nome, alvo) {
		return true
	}
	return false
}

// alimentoPorID busca a referência nutricional já identificada.
func (s *Store) alimentoPorID(ctx context.Context, id int64) (domain.NutriAlimento, error) {
	var a domain.NutriAlimento
	err := s.pool.QueryRow(ctx,
		`SELECT id, nome, COALESCE(categoria,''), COALESCE(fonte,''), aliases
		   FROM nutri_alimentos WHERE id = $1`, id,
	).Scan(&a.ID, &a.Nome, &a.Categoria, &a.Fonte, &a.Aliases)
	if errors.Is(err, pgx.ErrNoRows) {
		return a, ErrNotFound
	}
	return a, err
}
