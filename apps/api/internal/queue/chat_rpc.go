package queue

import (
	"context"
	"fmt"
	"strconv"
	"sync"
	"time"

	"github.com/google/uuid"
	amqp "github.com/rabbitmq/amqp091-go"
)

// ChatClient implementa o padrão RPC sobre AMQP: publica requisições de chat na
// fila chat.requests com ReplyTo/CorrelationId e correlaciona as respostas que
// chegam na fila de callback exclusiva deste processo.
type ChatClient struct {
	pubCh      *amqp.Channel
	mu         sync.Mutex // protege publicação (canal AMQP não é concorrente)
	replyQueue string

	pendMu  sync.Mutex
	pending map[string]chan []byte
}

func NewChatClient(r *Rabbit) (*ChatClient, error) {
	pubCh, err := r.Conn.Channel()
	if err != nil {
		return nil, err
	}
	conCh, err := r.Conn.Channel()
	if err != nil {
		pubCh.Close()
		return nil, err
	}

	// Fila de callback exclusiva e auto-deletável (uma por processo).
	q, err := conCh.QueueDeclare("", false, true, true, false, nil)
	if err != nil {
		pubCh.Close()
		conCh.Close()
		return nil, err
	}

	c := &ChatClient{
		pubCh:      pubCh,
		replyQueue: q.Name,
		pending:    make(map[string]chan []byte),
	}

	deliveries, err := conCh.Consume(q.Name, "", true, true, false, false, nil)
	if err != nil {
		pubCh.Close()
		conCh.Close()
		return nil, err
	}

	go func() {
		for d := range deliveries {
			c.pendMu.Lock()
			ch, ok := c.pending[d.CorrelationId]
			if ok {
				delete(c.pending, d.CorrelationId)
			}
			c.pendMu.Unlock()
			if ok {
				ch <- d.Body
			}
		}
	}()

	return c, nil
}

// Call publica a requisição e aguarda a resposta correlacionada (ou ctx expira).
func (c *ChatClient) Call(ctx context.Context, body []byte) ([]byte, error) {
	corrID := uuid.NewString()
	respCh := make(chan []byte, 1)

	c.pendMu.Lock()
	c.pending[corrID] = respCh
	c.pendMu.Unlock()

	// Timestamp + Expiration: quando este contexto expirar, o front já recebeu
	// 502 e ninguém espera mais a resposta — o TTL faz o RabbitMQ descartar a
	// mensagem parada na fila (evita head-of-line blocking no worker), e o
	// timestamp deixa o worker descartar as que expiraram já em processamento.
	pub := amqp.Publishing{
		ContentType:   "application/json",
		CorrelationId: corrID,
		ReplyTo:       c.replyQueue,
		Timestamp:     time.Now(),
		Body:          body,
	}
	if deadline, ok := ctx.Deadline(); ok {
		if ttl := time.Until(deadline); ttl > 0 {
			pub.Expiration = strconv.FormatInt(ttl.Milliseconds(), 10)
		}
	}
	c.mu.Lock()
	err := c.pubCh.PublishWithContext(ctx, "", QueueChatRequests, false, false, pub)
	c.mu.Unlock()
	if err != nil {
		c.pendMu.Lock()
		delete(c.pending, corrID)
		c.pendMu.Unlock()
		return nil, fmt.Errorf("publish chat request: %w", err)
	}

	select {
	case <-ctx.Done():
		c.pendMu.Lock()
		delete(c.pending, corrID)
		c.pendMu.Unlock()
		return nil, ctx.Err()
	case resp := <-respCh:
		return resp, nil
	}
}
