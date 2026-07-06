package eutils

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/henrybloomingdale/pubmed-cli/internal/ncbi"
)

func TestNewClient_Defaults(t *testing.T) {
	c := NewClient()
	if c.BaseURL != DefaultBaseURL {
		t.Errorf("expected base URL %q, got %q", DefaultBaseURL, c.BaseURL)
	}
	if c.Tool != DefaultTool {
		t.Errorf("expected tool %q, got %q", DefaultTool, c.Tool)
	}
	if c.Email != DefaultEmail {
		t.Errorf("expected email %q, got %q", DefaultEmail, c.Email)
	}
}

func TestNewClient_WithOptions(t *testing.T) {
	c := NewClient(
		WithBaseURL("http://localhost:9999"),
		WithAPIKey("test-key-123"),
		WithTool("my-tool"),
		WithEmail("test@example.com"),
	)
	if c.BaseURL != "http://localhost:9999" {
		t.Errorf("expected base URL %q, got %q", "http://localhost:9999", c.BaseURL)
	}
	if c.APIKey != "test-key-123" {
		t.Errorf("expected API key %q, got %q", "test-key-123", c.APIKey)
	}
	if c.Tool != "my-tool" {
		t.Errorf("expected tool %q, got %q", "my-tool", c.Tool)
	}
	if c.Email != "test@example.com" {
		t.Errorf("expected email %q, got %q", "test@example.com", c.Email)
	}
}

func TestClient_CommonParams(t *testing.T) {
	var receivedParams map[string]string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedParams = make(map[string]string)
		for k, v := range r.URL.Query() {
			receivedParams[k] = v[0]
		}
		w.Write([]byte(`{"esearchresult":{"count":"0","retmax":"20","retstart":"0","idlist":[],"querytranslation":"test"}}`))
	}))
	defer srv.Close()

	c := NewClient(
		WithBaseURL(srv.URL),
		WithAPIKey("my-api-key"),
		WithTool("pubmed-cli"),
		WithEmail("user@example.com"),
	)
	_, _ = c.Search(context.Background(), "test", nil)

	if receivedParams["api_key"] != "my-api-key" {
		t.Errorf("expected api_key %q, got %q", "my-api-key", receivedParams["api_key"])
	}
	if receivedParams["tool"] != "pubmed-cli" {
		t.Errorf("expected tool %q, got %q", "pubmed-cli", receivedParams["tool"])
	}
	if receivedParams["email"] != "user@example.com" {
		t.Errorf("expected email %q, got %q", "user@example.com", receivedParams["email"])
	}
}

func TestClient_RateLimiting(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping rate limit test in short mode")
	}
	var requestCount int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt64(&requestCount, 1)
		w.Write([]byte(`{"esearchresult":{"count":"0","retmax":"20","retstart":"0","idlist":[],"querytranslation":"test"}}`))
	}))
	defer srv.Close()

	// Client without API key: max 3 req/sec
	c := NewClient(WithBaseURL(srv.URL))

	start := time.Now()
	for i := 0; i < 4; i++ {
		_, _ = c.Search(context.Background(), "test", nil)
	}
	elapsed := time.Since(start)

	// 4 requests at 3/sec should take at least ~900ms (3 intervals of 333ms)
	if elapsed < 900*time.Millisecond {
		t.Errorf("rate limiting too fast: 4 requests completed in %v (expected >= 900ms)", elapsed)
	}
}

// TestClient_ConcurrentRateLimitNoKey is the critical concurrency test.
// It spins up 10 goroutines calling Search against httptest.Server,
// asserting ≤4 requests per second (rate=3, burst=1).
func TestClient_ConcurrentRateLimitNoKey(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping concurrent rate limit test in short mode")
	}

	var mu sync.Mutex
	var timestamps []time.Time

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		timestamps = append(timestamps, time.Now())
		mu.Unlock()
		w.Write([]byte(`{"esearchresult":{"count":"0","retmax":"20","retstart":"0","idlist":[],"querytranslation":"test"}}`))
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL)) // no API key = 3 req/sec

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, _ = c.Search(context.Background(), "test", nil)
		}()
	}
	wg.Wait()

	if len(timestamps) != 10 {
		t.Fatalf("expected 10 requests, got %d", len(timestamps))
	}

	sort.Slice(timestamps, func(i, j int) bool {
		return timestamps[i].Before(timestamps[j])
	})

	// With rate=3/sec and burst=1, no more than 4 requests should land
	// in any 1-second sliding window.
	for i := 0; i < len(timestamps); i++ {
		count := 1
		for j := i + 1; j < len(timestamps); j++ {
			if timestamps[j].Sub(timestamps[i]) < time.Second {
				count++
			}
		}
		if count > 4 {
			t.Errorf("rate limit violated: %d requests within 1 second starting at index %d (max 4 expected)", count, i)
			for k, ts := range timestamps {
				t.Logf("  request %d: +%v", k, ts.Sub(timestamps[0]))
			}
			break
		}
	}
}

func TestClient_ConcurrentRateLimitWithKey(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping concurrent rate limit test in short mode")
	}

	var mu sync.Mutex
	var timestamps []time.Time

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		timestamps = append(timestamps, time.Now())
		mu.Unlock()
		w.Write([]byte(`{"esearchresult":{"count":"0","retmax":"20","retstart":"0","idlist":[],"querytranslation":"test"}}`))
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL), WithAPIKey("test-key"))

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, _ = c.Search(context.Background(), "test", nil)
		}()
	}
	wg.Wait()

	if len(timestamps) != 10 {
		t.Fatalf("expected 10 requests, got %d", len(timestamps))
	}

	sort.Slice(timestamps, func(i, j int) bool {
		return timestamps[i].Before(timestamps[j])
	})

	// With rate=10/sec and burst=1, all 10 requests should complete
	// in about 1 second. Check no more than 11 in any 1-second window.
	for i := 0; i < len(timestamps); i++ {
		count := 1
		for j := i + 1; j < len(timestamps); j++ {
			if timestamps[j].Sub(timestamps[i]) < time.Second {
				count++
			}
		}
		if count > 11 {
			t.Errorf("rate limit violated: %d requests within 1 second (max 11 expected)", count)
			break
		}
	}
}

func TestClient_ResponseTooLarge(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(strings.Repeat("X", 2048)))
	}))
	defer srv.Close()

	c := NewClient(
		WithBaseURL(srv.URL),
		WithAPIKey("test"),
		ncbi.WithMaxResponseBytes(1024),
	)

	_, err := c.Search(context.Background(), "test", nil)
	if err == nil {
		t.Error("expected error for oversized response, got nil")
	}
	if !strings.Contains(err.Error(), "exceeds maximum size") {
		t.Errorf("expected 'exceeds maximum size' error, got: %v", err)
	}
}

func TestClient_ContextCancellation(t *testing.T) {
	// Pre-cancelled context should fail immediately
	c := NewClient(
		WithBaseURL("http://127.0.0.1:1"), // won't connect
		WithAPIKey("test"),
	)
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	_, err := c.Search(ctx, "test", nil)
	if err == nil {
		t.Error("expected error from cancelled context, got nil")
	}
}
