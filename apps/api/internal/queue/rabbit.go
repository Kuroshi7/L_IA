package queue

import (
	"fmt"

	amqp "github.com/rabbitmq/amqp091-go"
)

const (
	// QueueChatRequests: fila consumida pelos workers de IA (Python).
	QueueChatRequests = "chat.requests"
	// ExchangeEvents: topic exchange para eventos de domínio publicados via outbox.
	ExchangeEvents = "menuai.events"
)

type Rabbit struct {
	Conn *amqp.Connection
}

func Connect(url string) (*Rabbit, error) {
	conn, err := amqp.Dial(url)
	if err != nil {
		return nil, fmt.Errorf("amqp dial: %w", err)
	}
	r := &Rabbit{Conn: conn}
	if err := r.declareTopology(); err != nil {
		conn.Close()
		return nil, err
	}
	return r, nil
}

// declareTopology garante que filas/exchanges existam (idempotente).
func (r *Rabbit) declareTopology() error {
	ch, err := r.Conn.Channel()
	if err != nil {
		return err
	}
	defer ch.Close()

	if _, err := ch.QueueDeclare(QueueChatRequests, true, false, false, false, nil); err != nil {
		return fmt.Errorf("declare %s: %w", QueueChatRequests, err)
	}
	if err := ch.ExchangeDeclare(ExchangeEvents, "topic", true, false, false, false, nil); err != nil {
		return fmt.Errorf("declare exchange %s: %w", ExchangeEvents, err)
	}
	return nil
}

func (r *Rabbit) Close() error {
	if r.Conn != nil {
		return r.Conn.Close()
	}
	return nil
}
