package config

import (
	"os"
	"strconv"

	"github.com/joho/godotenv"
)

// Config reúne toda a configuração do serviço, lida de variáveis de ambiente.
type Config struct {
	HTTPPort     string
	DatabaseURL  string
	RabbitURL    string
	AIBaseURL    string // usado pelo worker, se precisar chamar o serviço de IA via HTTP
	ChatTimeout  int    // segundos para aguardar a resposta do worker de IA (RPC)
	InternalAddr string // host:port exposto internamente para o serviço de IA
}

// Load carrega o .env (se existir) e monta a Config com defaults sensatos.
func Load() Config {
	_ = godotenv.Load() // silencioso: em produção as vars vêm do ambiente

	return Config{
		HTTPPort:     env("API_HTTP_PORT", "8080"),
		DatabaseURL:  env("DATABASE_URL", "postgres://menuai:menuai@localhost:5432/menuai?sslmode=disable"),
		RabbitURL:    env("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
		AIBaseURL:    env("AI_BASE_URL", "http://localhost:8000"),
		ChatTimeout:  envInt("CHAT_TIMEOUT_SECONDS", 60),
		InternalAddr: env("API_INTERNAL_ADDR", ":8080"),
	}
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}
