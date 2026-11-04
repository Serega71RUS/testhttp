package httpserver

import (
	"context"
	"errors"
	"net"
	"net/http"
	"time"
)

type Config struct {
	Port string `default:"8080" envconfig:"HTTP_PORT"`
}
type Server struct{ server *http.Server }

func New(handler http.Handler, c Config) *Server {
	return &Server{server: &http.Server{
		Handler:           handler,
		Addr:              net.JoinHostPort("", c.Port),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       20 * time.Second,
		WriteTimeout:      20 * time.Second,
		IdleTimeout:       60 * time.Second,
	}}
}
func (s *Server) Run() error {
	err := s.server.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}
func (s *Server) Close(ctx context.Context) error {
	if err := s.server.Shutdown(ctx); err != nil {
		_ = s.server.Close()
		return err
	}
	return nil
}
