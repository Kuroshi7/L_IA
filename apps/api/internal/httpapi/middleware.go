package httpapi

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"net/http"
)

// captureWriter intercepta status e corpo da resposta para cachear na idempotência.
type captureWriter struct {
	http.ResponseWriter
	status int
	body   bytes.Buffer
}

func (c *captureWriter) WriteHeader(status int) {
	c.status = status
	c.ResponseWriter.WriteHeader(status)
}

func (c *captureWriter) Write(b []byte) (int, error) {
	c.body.Write(b)
	return c.ResponseWriter.Write(b)
}

// idempotency: se houver Idempotency-Key, evita reprocessar e devolve a resposta
// cacheada. Chave reutilizada com corpo diferente → 409.
func (s *Server) idempotency(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := r.Header.Get("Idempotency-Key")
		if key == "" {
			next.ServeHTTP(w, r)
			return
		}

		bodyBytes, _ := io.ReadAll(r.Body)
		r.Body = io.NopCloser(bytes.NewReader(bodyBytes))
		sum := sha256.Sum256(bodyBytes)
		hash := hex.EncodeToString(sum[:])

		if prev, found, err := s.store.GetIdempotent(r.Context(), key); err == nil && found {
			if prev.RequestHash != hash {
				writeError(w, http.StatusConflict, "Idempotency-Key reutilizada com corpo diferente")
				return
			}
			status := prev.StatusCode
			if status == 0 {
				status = http.StatusOK
			}
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("Idempotent-Replayed", "true")
			w.WriteHeader(status)
			_, _ = w.Write(prev.Response)
			return
		}

		cw := &captureWriter{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(cw, r)

		if cw.status < 500 {
			_ = s.store.SaveIdempotent(r.Context(), key, hash, cw.status, cw.body.Bytes())
		}
	})
}
