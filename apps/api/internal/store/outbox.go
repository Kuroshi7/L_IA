package store

import (
	"context"
	"encoding/json"
)

type OutboxEvent struct {
	ID        string
	Aggregate string
	EventType string
	Payload   json.RawMessage
}

// ProcessPendingOutbox seleciona eventos pendentes (FOR UPDATE SKIP LOCKED) e,
// SEGURANDO o lock numa única transação, chama `publish` para cada um e marca o
// resultado (published/failed) na MESMA transação. O lock só é liberado no commit,
// então dois relays concorrentes nunca pegam o mesmo evento — a garantia que o
// FetchPendingOutbox anterior prometia mas não cumpria (o lock morria no fim da
// query, antes do mark).
//
// `publish` faz I/O de rede segurando o lock; por isso o batch é modesto e o
// relay roda a cada ~1s. Um erro de publish marca o evento como failed/retry e não
// interrompe os demais do lote.
func (s *Store) ProcessPendingOutbox(ctx context.Context, limit int, publish func(OutboxEvent) error) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	rows, err := tx.Query(ctx,
		`SELECT id, aggregate, event_type, payload
		   FROM outbox
		  WHERE status = 'pending'
		  ORDER BY created_at
		  LIMIT $1
		  FOR UPDATE SKIP LOCKED`,
		limit,
	)
	if err != nil {
		return err
	}
	// pgx: numa mesma conexão/tx não dá para executar UPDATE com o cursor aberto —
	// coletamos todos os eventos e fechamos o cursor antes de publicar/marcar.
	var events []OutboxEvent
	for rows.Next() {
		var e OutboxEvent
		if err := rows.Scan(&e.ID, &e.Aggregate, &e.EventType, &e.Payload); err != nil {
			rows.Close()
			return err
		}
		events = append(events, e)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return err
	}

	for _, e := range events {
		if perr := publish(e); perr != nil {
			if _, err := tx.Exec(ctx,
				`UPDATE outbox SET attempts = attempts + 1,
				        status = CASE WHEN attempts + 1 >= 5 THEN 'failed' ELSE 'pending' END
				  WHERE id = $1`, e.ID); err != nil {
				return err
			}
			continue
		}
		if _, err := tx.Exec(ctx,
			`UPDATE outbox SET status = 'published', published_at = now() WHERE id = $1`, e.ID); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

// AlreadyProcessed indica se uma mensagem já foi tratada por um consumidor (inbox).
func (s *Store) AlreadyProcessed(ctx context.Context, msgID, consumer string) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM inbox_processados WHERE msg_id = $1 AND consumer = $2)`,
		msgID, consumer,
	).Scan(&exists)
	return exists, err
}

func (s *Store) MarkProcessed(ctx context.Context, msgID, consumer string) error {
	_, err := s.pool.Exec(ctx,
		`INSERT INTO inbox_processados (msg_id, consumer) VALUES ($1, $2)
		 ON CONFLICT (msg_id) DO NOTHING`,
		msgID, consumer,
	)
	return err
}
