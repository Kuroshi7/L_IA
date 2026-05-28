package httpapi

import (
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"github.com/tamy-ai/menu-ai/api/internal/chat"
	"github.com/tamy-ai/menu-ai/api/internal/store"
)

type Server struct {
	store *store.Store
	chat  *chat.Service
	log   *slog.Logger
}

func NewServer(st *store.Store, chatSvc *chat.Service, log *slog.Logger) *Server {
	return &Server{store: st, chat: chatSvc, log: log}
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.Recoverer)
	r.Use(s.cors)

	r.Get("/health", s.handleHealth)

	// API pública (consumida pelo front).
	r.Get("/unidades", s.handleListUnidades)
	r.Get("/unidades/{unidadeID}/cardapio", s.handleCardapioPublico)
	r.Get("/chat/saudacao", s.handleSaudacao)
	r.Delete("/chat/{sessionID}", s.handleResetChat)

	// Rotas mutáveis com idempotência opcional (Idempotency-Key).
	r.Group(func(r chi.Router) {
		r.Use(s.idempotency)
		r.Post("/chat", s.handleChat)
	})

	// API interna, consumida pelo serviço de IA (worker Python).
	r.Route("/internal", func(r chi.Router) {
		r.Get("/cardapio/{unidadeID}/{data}", s.handleCardapioInterno)
		r.Get("/usuario/{usuarioID}/perfil", s.handlePerfilInterno)
		r.Get("/medidas-caseiras", s.handleMedidasInterno)
	})

	return r
}

func (s *Server) cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Idempotency-Key")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
