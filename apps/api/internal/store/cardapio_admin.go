package store

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
)

var diasPT = []string{"Domingo", "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado"}

func diaSemanaPT(t time.Time) string { return diasPT[int(t.Weekday())] }

// GetCardapioSemana monta a grade seg–dom (7 dias) a partir de `inicio` (segunda, YYYY-MM-DD).
// Inclui itens ativos e inativos (a grade é a fonte da verdade para edição).
func (s *Store) GetCardapioSemana(ctx context.Context, unidadeID int64, inicio string) (domain.CardapioSemana, error) {
	base, err := time.Parse("2006-01-02", inicio)
	if err != nil {
		return domain.CardapioSemana{}, fmt.Errorf("data inicial inválida: %w", err)
	}
	sem := domain.CardapioSemana{UnidadeID: unidadeID, Inicio: inicio, Dias: []domain.CardapioDia{}}

	for d := 0; d < 7; d++ {
		dt := base.AddDate(0, 0, d)
		ds := dt.Format("2006-01-02")
		dia := domain.CardapioDia{UnidadeID: unidadeID, Data: ds, DiaSemana: diaSemanaPT(dt), Pratos: []domain.Alimento{}}

		var diaID int64
		err := s.pool.QueryRow(ctx,
			`SELECT id FROM cardapio_dias WHERE unidade_id=$1 AND data=$2::date`, unidadeID, ds,
		).Scan(&diaID)
		if err == nil {
			dia.ID = diaID
			pratos, err := s.listItensDoDia(ctx, diaID)
			if err != nil {
				return sem, err
			}
			dia.Pratos = pratos
		} else if !errors.Is(err, pgx.ErrNoRows) {
			return sem, err
		}
		sem.Dias = append(sem.Dias, dia)
	}
	return sem, nil
}

func (s *Store) listItensDoDia(ctx context.Context, diaID int64) ([]domain.Alimento, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT `+alimentoSelect+`, ci.is_proteina_do_dia
		   FROM cardapio_itens ci JOIN alimentos a ON a.id = ci.alimento_id
		  WHERE ci.cardapio_dia_id = $1 ORDER BY a.categoria, a.nome`, diaID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []domain.Alimento{}
	for rows.Next() {
		var a domain.Alimento
		if err := rows.Scan(&a.ID, &a.UnidadeID, &a.Nome, &a.Categoria,
			&a.Ingredientes, &a.Alergenos, &a.RestricoesAtendidas, &a.NaoIndicadoPara,
			&a.Calorias, &a.ProteinasG, &a.CarboidratosG, &a.GordurasG, &a.Ativo, &a.NutriAlimentoID,
			&a.IsProteinaDoDia); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

// SetCardapioItens substitui (replace) os itens do cardápio de uma data da unidade.
// Cria o dia se necessário. Só aceita alimentos que pertencem à própria unidade.
func (s *Store) SetCardapioItens(ctx context.Context, unidadeID int64, data string, itens []domain.CardapioItemInput) (domain.CardapioDia, error) {
	dt, err := time.Parse("2006-01-02", data)
	if err != nil {
		return domain.CardapioDia{}, fmt.Errorf("data inválida: %w", err)
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.CardapioDia{}, err
	}
	defer tx.Rollback(ctx)

	diaID, err := upsertCardapioDiaTx(ctx, tx, unidadeID, data, diaSemanaPT(dt))
	if err != nil {
		return domain.CardapioDia{}, err
	}

	if _, err := tx.Exec(ctx, `DELETE FROM cardapio_itens WHERE cardapio_dia_id=$1`, diaID); err != nil {
		return domain.CardapioDia{}, err
	}
	for _, it := range itens {
		if _, err := tx.Exec(ctx,
			`INSERT INTO cardapio_itens (cardapio_dia_id, alimento_id, is_proteina_do_dia)
			 SELECT $1, $2, $3 WHERE EXISTS (SELECT 1 FROM alimentos WHERE id=$2 AND unidade_id=$4)
			 ON CONFLICT (cardapio_dia_id, alimento_id) DO UPDATE SET is_proteina_do_dia = EXCLUDED.is_proteina_do_dia`,
			diaID, it.AlimentoID, it.IsProteinaDoDia, unidadeID,
		); err != nil {
			return domain.CardapioDia{}, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.CardapioDia{}, err
	}

	pratos, err := s.listItensDoDia(ctx, diaID)
	if err != nil {
		return domain.CardapioDia{}, err
	}
	return domain.CardapioDia{ID: diaID, UnidadeID: unidadeID, Data: data, DiaSemana: diaSemanaPT(dt), Pratos: pratos}, nil
}

func upsertCardapioDiaTx(ctx context.Context, tx pgx.Tx, unidadeID int64, data, diaSemana string) (int64, error) {
	var id int64
	err := tx.QueryRow(ctx,
		`INSERT INTO cardapio_dias (unidade_id, data, dia_semana) VALUES ($1,$2::date,$3)
		 ON CONFLICT (unidade_id, data) DO UPDATE SET dia_semana = EXCLUDED.dia_semana
		 RETURNING id`,
		unidadeID, data, diaSemana,
	).Scan(&id)
	return id, err
}

// CopiarSemana copia o cardápio seg–dom de `origemInicio` para `destinoInicio` (datas de segunda).
func (s *Store) CopiarSemana(ctx context.Context, unidadeID int64, origemInicio, destinoInicio string) (domain.CardapioSemana, error) {
	origem, err := s.GetCardapioSemana(ctx, unidadeID, origemInicio)
	if err != nil {
		return domain.CardapioSemana{}, err
	}
	destBase, err := time.Parse("2006-01-02", destinoInicio)
	if err != nil {
		return domain.CardapioSemana{}, fmt.Errorf("data destino inválida: %w", err)
	}

	for d, dia := range origem.Dias {
		destData := destBase.AddDate(0, 0, d).Format("2006-01-02")
		itens := make([]domain.CardapioItemInput, 0, len(dia.Pratos))
		for _, p := range dia.Pratos {
			itens = append(itens, domain.CardapioItemInput{AlimentoID: p.ID, IsProteinaDoDia: p.IsProteinaDoDia})
		}
		if _, err := s.SetCardapioItens(ctx, unidadeID, destData, itens); err != nil {
			return domain.CardapioSemana{}, err
		}
	}
	return s.GetCardapioSemana(ctx, unidadeID, destinoInicio)
}
