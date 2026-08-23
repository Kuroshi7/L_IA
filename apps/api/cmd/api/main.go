package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/tamy-ai/menu-ai/api/internal/chat"
	"github.com/tamy-ai/menu-ai/api/internal/config"
	"github.com/tamy-ai/menu-ai/api/internal/db"
	"github.com/tamy-ai/menu-ai/api/internal/httpapi"
	"github.com/tamy-ai/menu-ai/api/internal/queue"
	"github.com/tamy-ai/menu-ai/api/internal/store"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	cfg := config.Load()

	// Admin sem token = área administrativa aberta. Nunca silencioso: ou há token,
	// ou o operador desligou o gate explicitamente (só para desenvolvimento local).
	if cfg.AdminToken == "" {
		if os.Getenv("ADMIN_AUTH_DISABLED") != "1" {
			log.Error("ADMIN_TOKEN vazio — defina ADMIN_TOKEN ou, apenas em dev, ADMIN_AUTH_DISABLED=1")
			os.Exit(1)
		}
		log.Warn("ADMIN_AUTH_DISABLED=1 — rotas /admin SEM autenticação (somente desenvolvimento)")
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	pool, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Error("conectar ao banco", "err", err)
		os.Exit(1)
	}
	defer pool.Close()

	if err := db.Migrate(ctx, pool); err != nil {
		log.Error("aplicar migrations", "err", err)
		os.Exit(1)
	}
	log.Info("migrations aplicadas")

	st := store.New(pool)

	rabbit, err := queue.Connect(cfg.RabbitURL)
	if err != nil {
		log.Error("conectar ao rabbitmq", "err", err)
		os.Exit(1)
	}
	defer rabbit.Close()

	chatClient, err := queue.NewChatClient(rabbit)
	if err != nil {
		log.Error("criar cliente de chat (rpc)", "err", err)
		os.Exit(1)
	}

	relay, err := queue.NewRelay(rabbit, st, log)
	if err != nil {
		log.Error("criar outbox relay", "err", err)
		os.Exit(1)
	}
	go relay.Run(ctx)
	log.Info("outbox relay iniciado")

	chatSvc := chat.New(st, chatClient, time.Duration(cfg.ChatTimeout)*time.Second)
	srv := httpapi.NewServer(st, chatSvc, log, cfg.AdminToken)
	srv.SetRabbitCheck(func() bool { return rabbit.Conn != nil && !rabbit.Conn.IsClosed() })

	// GC das chaves de idempotência (>30 dias): passada no boot + diária.
	go func() {
		purge := func() {
			c, cancel := context.WithTimeout(ctx, 30*time.Second)
			defer cancel()
			n, err := st.PurgeIdempotentKeys(c, 30*24*time.Hour)
			if err != nil {
				log.Error("gc idempotency", "err", err)
				return
			}
			if n > 0 {
				log.Info("gc idempotency", "removidas", n)
			}
		}
		purge()
		ticker := time.NewTicker(24 * time.Hour)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				purge()
			}
		}
	}()

	httpServer := &http.Server{
		Addr:              ":" + cfg.HTTPPort,
		Handler:           srv.Router(),
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		log.Info("api ouvindo", "port", cfg.HTTPPort)
		if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error("http server", "err", err)
			stop()
		}
	}()

	<-ctx.Done()
	log.Info("desligando...")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpServer.Shutdown(shutdownCtx)
}
