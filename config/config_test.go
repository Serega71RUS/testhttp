package config

import "testing"

func TestNewWithoutDotEnv(t *testing.T) {
	t.Chdir(t.TempDir())
	t.Setenv("HTTP_PORT", "9090")
	c, err := New()
	if err != nil {
		t.Fatal(err)
	}
	if c.HTTP.Port != "9090" {
		t.Fatalf("port = %q, want 9090", c.HTTP.Port)
	}
}

func TestNewInvalidPort(t *testing.T) {
	t.Chdir(t.TempDir())
	for _, port := range []string{"abc", "0", "65536"} {
		t.Run(port, func(t *testing.T) {
			t.Setenv("HTTP_PORT", port)
			if _, err := New(); err == nil {
				t.Fatal("expected invalid port error")
			}
		})
	}
}
