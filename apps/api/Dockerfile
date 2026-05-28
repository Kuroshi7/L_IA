# Build multi-stage do serviço Go (api, worker, seed num único binário multi-cmd).
FROM golang:1.25 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/api  ./cmd/api  \
 && CGO_ENABLED=0 go build -o /out/worker ./cmd/worker \
 && CGO_ENABLED=0 go build -o /out/seed  ./cmd/seed

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /out/api /app/api
COPY --from=build /out/worker /app/worker
COPY --from=build /out/seed /app/seed
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1
CMD ["/app/api"]
