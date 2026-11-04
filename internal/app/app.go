package app

import (
	"context"
	"fmt"
	"github.com/Serega71RUS/testhttp/config"
	"github.com/Serega71RUS/testhttp/pkg/httpserver"
	"github.com/rs/zerolog/log"
	"net/http"
	"time"
)

func NewHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		_, _ = w.Write([]byte("hello world\n"))
	})
	return mux
}
func Run(ctx context.Context, c config.Config) error {
	server := httpserver.New(NewHandler(), c.HTTP)
	done := make(chan error, 1)
	go func() { done <- server.Run() }()
	log.Info().Str("port", c.HTTP.Port).Msg("starting HTTP server")
	select {
	case err := <-done:
		return err
	case <-ctx.Done():
		log.Info().Msg("shutting down HTTP server")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
		defer cancel()
		if err := server.Close(shutdownCtx); err != nil {
			return fmt.Errorf("shutdown HTTP server: %w", err)
		}
		return <-done
	}
}
