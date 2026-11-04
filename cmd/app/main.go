package main

import (
	"context"
	"github.com/Serega71RUS/testhttp/config"
	"github.com/Serega71RUS/testhttp/internal/app"
	"github.com/rs/zerolog/log"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	if err := run(); err != nil {
		log.Error().Err(err).Msg("application stopped")
		os.Exit(1)
	}
}
func run() error {
	c, err := config.New()
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	return app.Run(ctx, c)
}
