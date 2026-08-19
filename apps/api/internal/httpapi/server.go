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
	store      *store.Store
	chat       *chat.Service
	log        *slog.Logger
	adminToken string
	// rabbitOK reporta se a conexão com o RabbitMQ está viva (checado em /ready).
	// Opcional: se nil, /ready só verifica o Postgres.
	rabbitOK func() bool
}

func NewServer(st *store.Store, chatSvc *chat.Service, log *slog.Logger, adminToken string) *Server {
	return &Server{store: st, chat: chatSvc, log: log, adminToken: adminToken}
}

// SetRabbitCheck registra a checagem de readiness do RabbitMQ (chamada em /ready).
func (s *Server) SetRabbitCheck(fn func() bool) { s.rabbitOK = fn }

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.Recoverer)
	r.Use(s.cors)

	r.Get("/health", s.handleHealth)
	r.Get("/ready", s.handleReady)

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
		r.Post("/consumo/calcular", s.handleConsumoCalcular)
	})

	// API de admin (gestão de catálogo de alimentos e cardápio). Gate via X-Admin-Token.
	r.Route("/admin", func(r chi.Router) {
		r.Use(s.adminAuth)

		r.Get("/unidades/{unidadeID}/alimentos", s.handleListAlimentos)
		r.Post("/unidades/{unidadeID}/alimentos", s.handleCreateAlimento)
		r.Put("/alimentos/{alimentoID}", s.handleUpdateAlimento)
		r.Patch("/alimentos/{alimentoID}/ativo", s.handleSetAlimentoAtivo)

		r.Get("/nutri-alimentos", s.handleSearchNutri)
		r.Get("/nutri-alimentos/{nutriID}", s.handleGetNutri)
		r.Post("/nutri-alimentos", s.handleCreateNutri)

		r.Get("/unidades/{unidadeID}/cardapio-semana", s.handleGetCardapioSemana)
		r.Put("/unidades/{unidadeID}/cardapio-dia/{data}/itens", s.handleSetCardapioItens)
		r.Post("/unidades/{unidadeID}/cardapio-semana/copiar", s.handleCopiarSemana)
	})

	return r
}

func (s *Server) cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Idempotency-Key, X-Admin-Token")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
