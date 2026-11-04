package config

import (
	"errors"
	"fmt"
	"github.com/Serega71RUS/testhttp/pkg/httpserver"
	"github.com/joho/godotenv"
	"github.com/kelseyhightower/envconfig"
	"os"
	"strconv"
)

type Config struct{ HTTP httpserver.Config }

func New() (Config, error) {
	var c Config
	// A local .env is optional; containers receive configuration via environment.
	if err := godotenv.Load(".env"); err != nil && !errors.Is(err, os.ErrNotExist) {
		return c, fmt.Errorf("load .env: %w", err)
	}
	if err := envconfig.Process("", &c); err != nil {
		return c, fmt.Errorf("read environment: %w", err)
	}
	port, err := strconv.Atoi(c.HTTP.Port)
	if err != nil || port < 1 || port > 65535 {
		return c, fmt.Errorf("HTTP_PORT must be between 1 and 65535")
	}
	return c, nil
}
