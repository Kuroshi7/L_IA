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
