package store

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

// ConsumoRegistradoEvento é o payload do evento `consumo.registrado` (outbox).
type ConsumoRegistradoEvento struct {
	ConsumoID     int64   `json:"consumo_id"`
	UnidadeID     int64   `json:"unidade_id"`
	Data          string  `json:"data"`
	ConsumidoG    float64 `json:"consumido_g"`
	ConsumidoKcal float64 `json:"consumido_kcal"`
	RestoG        float64 `json:"resto_g"`
	RestoKcal     float64 `json:"resto_kcal"`

	// false = algum item não resolveu e os totais estão subestimados.
	// Ponteiro para distinguir "veio false" de "evento antigo, sem o campo".
	Completo *bool `json:"completo,omitempty"`
}

// AplicarConsumoNoAgregado incrementa o agregado diário de desperdício da unidade.
// Chamado pelo worker Go ao consumir `consumo.registrado` (idempotência garantida
// pelo inbox do worker). ETL incremental: o dashboard admin lê o agregado pronto.
func (s *Store) AplicarConsumoNoAgregado(ctx context.Context, raw []byte) error {
	var ev ConsumoRegistradoEvento
	if err := json.Unmarshal(raw, &ev); err != nil {
		return fmt.Errorf("payload de consumo.registrado inválido: %w", err)
	}
	if ev.UnidadeID == 0 || ev.Data == "" {
		return fmt.Errorf("evento consumo.registrado sem unidade/data")
	}
	// Refeição com item não reconhecido tem gramas/kcal subestimados; somá-la ao
	// agregado contamina o índice de resto e o resto per capita, que são o
	// número que o gestor usa para decidir. Melhor cobrir menos refeições e
	// responder certo. Retorna nil (não erro) para o inbox marcar como
	// processado e não ficar retentando um evento que nunca vai ser aplicado.
	if ev.Completo != nil && !*ev.Completo {
		return nil
	}
	_, err := s.pool.Exec(ctx,
		`INSERT INTO desperdicio_diario (unidade_id, data, refeicoes, consumido_g, consumido_kcal, resto_g, resto_kcal)
		 VALUES ($1, $2::date, 1, $3, $4, $5, $6)
		 ON CONFLICT (unidade_id, data) DO UPDATE
		    SET refeicoes      = desperdicio_diario.refeicoes + 1,
		        consumido_g    = desperdicio_diario.consumido_g + EXCLUDED.consumido_g,
		        consumido_kcal = desperdicio_diario.consumido_kcal + EXCLUDED.consumido_kcal,
		        resto_g        = desperdicio_diario.resto_g + EXCLUDED.resto_g,
		        resto_kcal     = desperdicio_diario.resto_kcal + EXCLUDED.resto_kcal,
		        updated_at     = now()`,
		ev.UnidadeID, ev.Data, ev.ConsumidoG, ev.ConsumidoKcal, ev.RestoG, ev.RestoKcal)
	return err
}

// GetDesperdicioResumo monta o dashboard de desperdício de uma unidade no período:
// série diária (do agregado), índice de resto-ingesta proxy, classificação de UAN
// e os alimentos mais deixados no prato (a partir dos itens de resto reportados).
func (s *Store) GetDesperdicioResumo(ctx context.Context, unidadeID int64, de, ate string) (domain.DesperdicioResumo, error) {
	out := domain.DesperdicioResumo{UnidadeID: unidadeID, De: de, Ate: ate}

	if _, err := time.Parse("2006-01-02", de); err != nil {
		return out, fmt.Errorf("data inicial inválida")
	}
	if _, err := time.Parse("2006-01-02", ate); err != nil {
		return out, fmt.Errorf("data final inválida")
	}

	rows, err := s.pool.Query(ctx,
		`SELECT data::text, refeicoes, consumido_g, consumido_kcal, resto_g, resto_kcal
		   FROM desperdicio_diario
		  WHERE unidade_id = $1 AND data BETWEEN $2::date AND $3::date
		  ORDER BY data`, unidadeID, de, ate)
	if err != nil {
		return out, err
	}
	defer rows.Close()

	for rows.Next() {
		var d domain.DesperdicioDia
		if err := rows.Scan(&d.Data, &d.Refeicoes, &d.ConsumidoG, &d.ConsumidoKcal, &d.RestoG, &d.RestoKcal); err != nil {
			return out, err
		}
		out.Dias = append(out.Dias, d)
		out.Refeicoes += d.Refeicoes
		out.ConsumidoG += d.ConsumidoG
		out.RestoG += d.RestoG
		out.RestoKcal += d.RestoKcal
	}
	if err := rows.Err(); err != nil {
		return out, err
	}

	out.IndiceResto = domain.IndiceResto(out.ConsumidoG, out.RestoG)
	out.Classificacao = domain.ClassificarResto(out.IndiceResto)
	if out.Refeicoes > 0 {
		out.RestoPerCapitaG = out.RestoG / float64(out.Refeicoes)
	}

	top, err := s.topDesperdicados(ctx, unidadeID, de, ate)
	if err != nil {
		return out, err
	}
	out.TopDesperdicados = top
	return out, nil
}

// topDesperdicados agrega os itens de resto reportados no período, por alimento.
func (s *Store) topDesperdicados(ctx context.Context, unidadeID int64, de, ate string) ([]domain.AlimentoDesperdicado, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT COALESCE(NULLIF(item->>'alimento_resolvido',''), item->'entrada'->>'alimento') AS alimento,
		        count(*) AS ocorrencias,
		        COALESCE(sum((item->>'gramas_totais')::numeric), 0) AS resto_g,
		        COALESCE(sum((item->>'kcal')::numeric), 0) AS resto_kcal
		   FROM consumos c, jsonb_array_elements(c.resto_itens) AS item
		  WHERE c.unidade_id = $1
		    AND c.completo
	    AND (c.created_at AT TIME ZONE '`+TZRefeitorio+`')::date BETWEEN $2::date AND $3::date
		  GROUP BY 1
		  ORDER BY resto_g DESC
		  LIMIT 10`, unidadeID, de, ate)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []domain.AlimentoDesperdicado
	for rows.Next() {
		var a domain.AlimentoDesperdicado
		if err := rows.Scan(&a.Alimento, &a.Ocorrencias, &a.RestoG, &a.RestoKcal); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}
