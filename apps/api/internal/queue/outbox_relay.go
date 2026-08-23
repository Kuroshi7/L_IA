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
	// fetch + publish + mark rodam na mesma transação (lock segurado até o commit),
	// então dois relays concorrentes não pegam o mesmo evento. A entrega segue
	// at-least-once (uma falha de commit após o publish reenvia o evento); a
	// deduplicação final é do inbox do consumidor.
	err := rl.store.ProcessPendingOutbox(ctx, 50, func(e store.OutboxEvent) error {
		perr := rl.ch.PublishWithContext(ctx, ExchangeEvents, e.EventType, false, false, amqp.Publishing{
			ContentType:  "application/json",
			MessageId:    e.ID,
			Type:         e.EventType,
			Body:         e.Payload,
			DeliveryMode: amqp.Persistent,
		})
		if perr != nil {
			rl.log.Error("outbox publish", "id", e.ID, "err", perr)
		}
		return perr
	})
	if err != nil {
		rl.log.Error("outbox drain", "err", err)
	}
}
