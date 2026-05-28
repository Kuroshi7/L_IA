package queue

import (
	"context"
	"log/slog"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"

	"github.com/tamy-ai/menu-ai/api/internal/store"
)

// Relay lê o outbox periodicamente e publica os eventos no exchange de domínio.
// Garante publicação confiável: o evento foi gravado na mesma transação do estado.
type Relay struct {
	store  *store.Store
	ch     *amqp.Channel
	log    *slog.Logger
	period time.Duration
}

func NewRelay(r *Rabbit, st *store.Store, log *slog.Logger) (*Relay, error) {
	ch, err := r.Conn.Channel()
	if err != nil {
		return nil, err
	}
	return &Relay{store: st, ch: ch, log: log, period: 1 * time.Second}, nil
}

func (rl *Relay) Run(ctx context.Context) {
	ticker := time.NewTicker(rl.period)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			rl.drain(ctx)
		}
	}
}

func (rl *Relay) drain(ctx context.Context) {
	events, err := rl.store.FetchPendingOutbox(ctx, 50)
	if err != nil {
		rl.log.Error("outbox fetch", "err", err)
		return
	}
	for _, e := range events {
		err := rl.ch.PublishWithContext(ctx, ExchangeEvents, e.EventType, false, false, amqp.Publishing{
			ContentType:  "application/json",
			MessageId:    e.ID,
			Type:         e.EventType,
			Body:         e.Payload,
			DeliveryMode: amqp.Persistent,
		})
		if err != nil {
			rl.log.Error("outbox publish", "id", e.ID, "err", err)
			_ = rl.store.MarkOutboxFailed(ctx, e.ID)
			continue
		}
		if err := rl.store.MarkOutboxPublished(ctx, e.ID); err != nil {
			rl.log.Error("outbox mark published", "id", e.ID, "err", err)
		}
	}
}
