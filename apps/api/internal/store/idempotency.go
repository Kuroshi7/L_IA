package store

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/jackc/pgx/v5"
)

type IdempotentResult struct {
	StatusCode  int
	Response    json.RawMessage
	RequestHash string
}

// GetIdempotent busca uma resposta já registrada para a chave de idempotência.
func (s *Store) GetIdempotent(ctx context.Context, chave string) (IdempotentResult, bool, error) {
	var r IdempotentResult
	err := s.pool.QueryRow(ctx,
		`SELECT status_code, response, request_hash FROM idempotency_keys WHERE chave = $1`, chave,
	).Scan(&r.StatusCode, &r.Response, &r.RequestHash)
	if errors.Is(err, pgx.ErrNoRows) {
		return r, false, nil
	}
	if err != nil {
		return r, false, err
	}
	return r, true, nil
}

// SaveIdempotent grava a resposta associada a uma chave de idempotência.
func (s *Store) SaveIdempotent(ctx context.Context, chave, requestHash string, status int, response []byte) error {
	_, err := s.pool.Exec(ctx,
		`INSERT INTO idempotency_keys (chave, request_hash, status_code, response)
		 VALUES ($1, $2, $3, $4)
		 ON CONFLICT (chave) DO NOTHING`,
		chave, requestHash, status, response,
	)
	return err
}
