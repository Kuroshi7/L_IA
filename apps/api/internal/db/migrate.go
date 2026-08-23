package db

import (
	"context"
	"fmt"
	"io/fs"
	"sort"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tamy-ai/menu-ai/api/migrations"
)

// migrateLockKey é a chave fixa do advisory lock de migração. Duas instâncias da
// API subindo juntas (ex.: --scale api=2) disputam este lock: a segunda espera a
// primeira terminar, em vez de rodar o mesmo DDL concorrentemente.
const migrateLockKey int64 = 495_016_2025

// Migrate aplica, em ordem, as migrações .sql ainda não aplicadas.
// Cada arquivo é executado por inteiro (protocolo simples, sem parâmetros),
// permitindo múltiplos statements por arquivo.
//
// Toda a rotina roda numa ÚNICA conexão segurando um advisory lock — advisory
// locks são por sessão, então lock, migrações e unlock precisam da mesma conexão.
func Migrate(ctx context.Context, pool *pgxpool.Pool) error {
	conn, err := pool.Acquire(ctx)
	if err != nil {
		return fmt.Errorf("adquirir conexão para migração: %w", err)
	}
	// LIFO: Release registrado primeiro roda por último — unlock acontece antes.
	defer conn.Release()

	if _, err := conn.Exec(ctx, `SELECT pg_advisory_lock($1)`, migrateLockKey); err != nil {
		return fmt.Errorf("advisory lock de migração: %w", err)
	}
	defer func() {
		// contexto próprio: o unlock deve rodar mesmo se ctx foi cancelado.
		_, _ = conn.Exec(context.Background(), `SELECT pg_advisory_unlock($1)`, migrateLockKey)
	}()

	if _, err := conn.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version    TEXT PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)`); err != nil {
		return fmt.Errorf("create schema_migrations: %w", err)
	}

	entries, err := fs.ReadDir(migrations.FS, ".")
	if err != nil {
		return fmt.Errorf("read migrations dir: %w", err)
	}

	var files []string
	for _, e := range entries {
		if !e.IsDir() && len(e.Name()) > 4 && e.Name()[len(e.Name())-4:] == ".sql" {
			files = append(files, e.Name())
		}
	}
	sort.Strings(files)

	for _, name := range files {
		var exists bool
		if err := conn.QueryRow(ctx,
			`SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version = $1)`, name,
		).Scan(&exists); err != nil {
			return fmt.Errorf("check migration %s: %w", name, err)
		}
		if exists {
			continue
		}

		sqlBytes, err := migrations.FS.ReadFile(name)
		if err != nil {
			return fmt.Errorf("read migration %s: %w", name, err)
		}
		// aplicação + registro na MESMA transação (sem estado parcial), rodando na
		// conexão que já segura o advisory lock — mutual exclusion entre instâncias
		// da API + DDL atômico por migração.
		tx, err := conn.Begin(ctx)
		if err != nil {
			return fmt.Errorf("begin migration %s: %w", name, err)
		}
		if _, err := tx.Exec(ctx, string(sqlBytes)); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("apply migration %s: %w", name, err)
		}
		if _, err := tx.Exec(ctx,
			`INSERT INTO schema_migrations (version) VALUES ($1)`, name,
		); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("record migration %s: %w", name, err)
		}
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("commit migration %s: %w", name, err)
		}
	}
	return nil
}
