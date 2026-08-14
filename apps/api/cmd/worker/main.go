package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	amqp "github.com/rabbitmq/amqp091-go"

	"github.com/tamy-ai/menu-ai/api/internal/config"
	"github.com/tamy-ai/menu-ai/api/internal/db"
	"github.com/tamy-ai/menu-ai/api/internal/queue"
	"github.com/tamy-ai/menu-ai/api/internal/store"
)

const (
	consumerName  = "go-worker"
	dlqName       = "go.worker.events.dlq"
	maxTentativas = 5 // após isso a mensagem vai para a DLQ (evita loop de poison message)
)

// Worker de efeitos colaterais: consome eventos de domínio (menuai.events) de
// forma idempotente (inbox). Responsável pelo ETL de desperdício: cada
// `consumo.registrado` incrementa o agregado diário lido pelo dashboard admin.
// A pontuação de gamificação é síncrona (o usuário precisa do feedback imediato);
// aqui ficam só os efeitos que podem ser eventualmente consistentes.
func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	cfg := config.Load()

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	pool, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Error("conectar ao banco", "err", err)
		os.Exit(1)
	}
	defer pool.Close()
	st := store.New(pool)

	rabbit, err := queue.Connect(cfg.RabbitURL)
	if err != nil {
		log.Error("conectar ao rabbitmq", "err", err)
		os.Exit(1)
	}
	defer rabbit.Close()

	ch, err := rabbit.Conn.Channel()
	if err != nil {
		log.Error("abrir canal", "err", err)
		os.Exit(1)
	}
	defer ch.Close()

	q, err := ch.QueueDeclare("go.worker.events", true, false, false, false, nil)
	if err != nil {
		log.Error("declarar fila", "err", err)
		os.Exit(1)
	}
	if _, err := ch.QueueDeclare(dlqName, true, false, false, false, nil); err != nil {
		log.Error("declarar dlq", "err", err)
		os.Exit(1)
	}
	if err := ch.QueueBind(q.Name, "#", queue.ExchangeEvents, false, nil); err != nil {
		log.Error("bind fila", "err", err)
		os.Exit(1)
	}
	if err := ch.Qos(10, 0, false); err != nil { // prefetch: controla concorrência
		log.Error("qos", "err", err)
		os.Exit(1)
	}

	deliveries, err := ch.Consume(q.Name, consumerName, false, false, false, false, nil)
	if err != nil {
		log.Error("consumir", "err", err)
		os.Exit(1)
	}

	log.Info("worker de eventos iniciado")
	for {
		select {
		case <-ctx.Done():
			return
		case d, ok := <-deliveries:
			if !ok {
				return
			}
			handle(ctx, st, ch, log, d)
		}
	}
}

func handle(ctx context.Context, st *store.Store, ch *amqp.Channel, log *slog.Logger, d amqp.Delivery) {
	processed, err := st.AlreadyProcessed(ctx, d.MessageId, consumerName)
	if err != nil {
		log.Error("checar inbox", "err", err)
		retryOuDLQ(ctx, ch, log, d, err)
		return
	}
	if processed {
		_ = d.Ack(false) // efeito exactly-once: já tratado
		return
	}

	switch d.Type {
	case "consumo.registrado":
		if err := st.AplicarConsumoNoAgregado(ctx, d.Body); err != nil {
			log.Error("agregar desperdício", "err", err, "msg_id", d.MessageId)
			retryOuDLQ(ctx, ch, log, d, err)
			return
		}
		log.Info("desperdício agregado", "msg_id", d.MessageId)
	default:
		// eventos sem efeito colateral (ex.: mensagem.registrada) — só auditoria.
		log.Info("evento recebido", "type", d.Type, "msg_id", d.MessageId)
	}

	if err := st.MarkProcessed(ctx, d.MessageId, consumerName); err != nil {
		log.Error("marcar processado", "err", err)
		retryOuDLQ(ctx, ch, log, d, err)
		return
	}
	_ = d.Ack(false)
}

// retryOuDLQ limita reprocessamento: republica a mensagem com contador incrementado
// até maxTentativas; depois disso a manda para a DLQ (poison message não pode travar
// a fila em loop infinito de Nack+requeue).
func retryOuDLQ(ctx context.Context, ch *amqp.Channel, log *slog.Logger, d amqp.Delivery, causa error) {
	tentativas := int32(0)
	if v, ok := d.Headers["x-retries"]; ok {
		switch n := v.(type) {
		case int32:
			tentativas = n
		case int64:
			tentativas = int32(n)
		}
	}

	// republica direto na fila (default exchange) — publicar no exchange de eventos
	// faria fan-out da retentativa para todas as filas vinculadas.
	destino := "go.worker.events"
	headers := amqp.Table{"x-retries": tentativas + 1}
	if tentativas+1 >= maxTentativas {
		destino = dlqName
		headers["x-erro"] = causa.Error()
		log.Error("mensagem enviada para DLQ", "msg_id", d.MessageId, "type", d.Type, "tentativas", tentativas+1)
	}

	err := ch.PublishWithContext(ctx, "", destino, false, false, amqp.Publishing{
		ContentType:  d.ContentType,
		DeliveryMode: amqp.Persistent,
		MessageId:    d.MessageId,
		Type:         d.Type,
		Headers:      headers,
		Body:         d.Body,
	})
	if err != nil {
		// não conseguiu republicar → devolve para a fila (melhor duplicar tentativa que perder)
		log.Error("republicar mensagem", "err", err, "msg_id", d.MessageId)
		_ = d.Nack(false, true)
		return
	}
	_ = d.Ack(false)
}
