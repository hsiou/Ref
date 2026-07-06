package eutils

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"testing"
)

func loadTestdata(t *testing.T, filename string) []byte {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("..", "..", "testdata", filename))
	if err != nil {
		t.Fatalf("failed to load testdata/%s: %v", filename, err)
	}
	return data
}

func TestSearch_BasicQuery(t *testing.T) {
	fixture := loadTestdata(t, "esearch_response.json")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		if got := q.Get("db"); got != "pubmed" {
			t.Errorf("expected db=pubmed, got %q", got)
		}
		if got := q.Get("term"); got != "fragile x syndrome" {
			t.Errorf("expected term='fragile x syndrome', got %q", got)
		}
		if got := q.Get("retmode"); got != "json" {
			t.Errorf("expected retmode=json, got %q", got)
		}
		if got := q.Get("retmax"); got != "20" {
			t.Errorf("expected retmax=20, got %q", got)
		}
		w.Write(fixture)
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL), WithAPIKey("test"))
	result, err := c.Search(context.Background(), "fragile x syndrome", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if result.Count != 1234 {
		t.Errorf("expected count 1234, got %d", result.Count)
	}
	if len(result.IDs) != 20 {
		t.Errorf("expected 20 IDs, got %d", len(result.IDs))
	}
	if result.IDs[0] != "38123456" {
		t.Errorf("expected first ID '38123456', got %q", result.IDs[0])
	}
	if result.QueryTranslation == "" {
		t.Error("expected non-empty query translation")
	}
	if result.WebEnv == "" {
		t.Error("expected non-empty WebEnv")
	}
}

func TestSearch_EmptyResults(t *testing.T) {
	fixture := loadTestdata(t, "esearch_empty.json")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(fixture)
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL), WithAPIKey("test"))
	result, err := c.Search(context.Background(), "nonexistent_term_xyz123", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if result.Count != 0 {
		t.Errorf("expected count 0, got %d", result.Count)
	}
	if len(result.IDs) != 0 {
		t.Errorf("expected 0 IDs, got %d", len(result.IDs))
	}
}

func TestSearch_EmptyQuery(t *testing.T) {
	c := NewClient(WithAPIKey("test"))
	_, err := c.Search(context.Background(), "", nil)
	if err == nil {
		t.Error("expected error for empty query, got nil")
	}
}

func TestSearch_WithOptions(t *testing.T) {
	var receivedParams url.Values

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedParams = r.URL.Query()
		w.Write(loadTestdata(t, "esearch_response.json"))
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL), WithAPIKey("test"))

	t.Run("custom limit", func(t *testing.T) {
		_, err := c.Search(context.Background(), "test", &SearchOptions{Limit: 50})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got := receivedParams.Get("retmax"); got != "50" {
			t.Errorf("expected retmax=50, got %q", got)
		}
	})

	t.Run("sort by date", func(t *testing.T) {
		_, err := c.Search(context.Background(), "test", &SearchOptions{Sort: "date"})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got := receivedParams.Get("sort"); got != "date" {
			t.Errorf("expected sort=date, got %q", got)
		}
	})

	t.Run("date range", func(t *testing.T) {
		_, err := c.Search(context.Background(), "test", &SearchOptions{
			MinDate: "2020/01/01",
			MaxDate: "2025/12/31",
		})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got := receivedParams.Get("datetype"); got != "pdat" {
			t.Errorf("expected datetype=pdat, got %q", got)
		}
		if got := receivedParams.Get("mindate"); got != "2020/01/01" {
			t.Errorf("expected mindate=2020/01/01, got %q", got)
		}
		if got := receivedParams.Get("maxdate"); got != "2025/12/31" {
			t.Errorf("expected maxdate=2025/12/31, got %q", got)
		}
	})
}

func TestSearch_InvalidCount(t *testing.T) {
	// Server returns a non-numeric count — should surface parsing error
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"esearchresult":{"count":"not-a-number","retmax":"20","retstart":"0","idlist":[],"querytranslation":"test"}}`))
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL), WithAPIKey("test"))
	_, err := c.Search(context.Background(), "test", nil)
	if err == nil {
		t.Error("expected error for invalid count, got nil")
	}
	if err != nil && !containsString(err.Error(), "count") {
		t.Errorf("expected error mentioning 'count', got: %v", err)
	}
}

func containsString(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func TestSearch_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL), WithAPIKey("test"))
	_, err := c.Search(context.Background(), "test", nil)
	if err == nil {
		t.Error("expected error for server error, got nil")
	}
}

func TestSearch_RateLimitError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL), WithAPIKey("test"))
	_, err := c.Search(context.Background(), "test", nil)
	if err == nil {
		t.Error("expected error for rate limit, got nil")
	}
}
