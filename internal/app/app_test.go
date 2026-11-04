package app

import (
	"context"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Serega71RUS/testhttp/config"
	"github.com/Serega71RUS/testhttp/pkg/httpserver"
)

func TestHandler(t *testing.T) {
	handler := NewHandler()
	for _, tc := range []struct {
		method string
		path   string
		status int
	}{
		{http.MethodGet, "/", http.StatusOK},
		{http.MethodGet, "/missing", http.StatusNotFound},
		{http.MethodPost, "/", http.StatusMethodNotAllowed},
	} {
		t.Run(tc.method+tc.path, func(t *testing.T) {
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, httptest.NewRequest(tc.method, tc.path, nil))
			if response.Code != tc.status {
				t.Fatalf("status = %d, want %d", response.Code, tc.status)
			}
			if tc.status == http.StatusOK {
				if response.Body.String() != "hello world\n" {
					t.Fatalf("unexpected body: %q", response.Body.String())
				}
				if response.Header().Get("Content-Type") != "text/plain; charset=utf-8" {
					t.Fatalf("unexpected content type: %q", response.Header().Get("Content-Type"))
				}
			}
		})
	}
}

func TestRunCanceledContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	done := make(chan error, 1)
	go func() {
		done <- Run(ctx, config.Config{HTTP: httpserver.Config{Port: "0"}})
	}()
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("application did not stop after cancellation")
	}
}

func TestRunOccupiedPort(t *testing.T) {
	listener, err := net.Listen("tcp", ":0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	_, port, err := net.SplitHostPort(listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := Run(ctx, config.Config{HTTP: httpserver.Config{Port: port}}); err == nil {
		t.Fatal("expected listen error for occupied port")
	}
}
