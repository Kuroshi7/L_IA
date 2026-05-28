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

// FetchPendingOutbox seleciona eventos pendentes para publicação, usando
// FOR UPDATE SKIP LOCKED para permitir múltiplos relays sem dupla publicação.
func (s *Store) FetchPendingOutbox(ctx context.Context, limit int) ([]OutboxEvent, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, aggregate, event_type, payload
		   FROM outbox
		  WHERE status = 'pending'
		  ORDER BY created_at
		  LIMIT $1
		  FOR UPDATE SKIP LOCKED`,
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []OutboxEvent
	for rows.Next() {
		var e OutboxEvent
		if err := rows.Scan(&e.ID, &e.Aggregate, &e.EventType, &e.Payload); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

func (s *Store) MarkOutboxPublished(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE outbox SET status = 'published', published_at = now() WHERE id = $1`, id)
	return err
}

func (s *Store) MarkOutboxFailed(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE outbox SET attempts = attempts + 1,
		        status = CASE WHEN attempts + 1 >= 5 THEN 'failed' ELSE 'pending' END
		  WHERE id = $1`, id)
	return err
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
