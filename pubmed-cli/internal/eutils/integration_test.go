//go:build integration

package eutils

import (
	"context"
	"os"
	"testing"
)

func integrationClient(t *testing.T) *Client {
	t.Helper()
	apiKey := os.Getenv("NCBI_API_KEY")
	opts := []Option{}
	if apiKey != "" {
		opts = append(opts, WithAPIKey(apiKey))
	}
	return NewClient(opts...)
}

func TestIntegration_Search(t *testing.T) {
	c := integrationClient(t)
	result, err := c.Search(context.Background(), `"fragile x syndrome"[MeSH]`, &SearchOptions{Limit: 5})
	if err != nil {
		t.Fatalf("search failed: %v", err)
	}

	if result.Count == 0 {
		t.Error("expected non-zero count for fragile x syndrome search")
	}
	if len(result.IDs) == 0 {
		t.Error("expected at least one result ID")
	}
	t.Logf("Found %d results, showing %d", result.Count, len(result.IDs))
}

func TestIntegration_Fetch(t *testing.T) {
	c := integrationClient(t)
	// Use a well-known PMID (a landmark FXS paper)
	articles, err := c.Fetch(context.Background(), []string{"1709163"})
	if err != nil {
		t.Fatalf("fetch failed: %v", err)
	}

	if len(articles) != 1 {
		t.Fatalf("expected 1 article, got %d", len(articles))
	}

	a := articles[0]
	if a.PMID != "1709163" {
		t.Errorf("expected PMID '1709163', got %q", a.PMID)
	}
	if a.Title == "" {
		t.Error("expected non-empty title")
	}
	t.Logf("Fetched: %s", a.Title)
}

func TestIntegration_CitedBy(t *testing.T) {
	c := integrationClient(t)
	result, err := c.CitedBy(context.Background(), "1709163")
	if err != nil {
		t.Fatalf("cited-by failed: %v", err)
	}

	t.Logf("PMID 1709163 cited by %d papers", len(result.Links))
}

func TestIntegration_Related(t *testing.T) {
	c := integrationClient(t)
	result, err := c.Related(context.Background(), "1709163")
	if err != nil {
		t.Fatalf("related failed: %v", err)
	}

	if len(result.Links) == 0 {
		t.Error("expected at least one related article")
	}
	if result.Links[0].Score == 0 {
		t.Error("expected non-zero relevance score")
	}
	t.Logf("Found %d related articles", len(result.Links))
}
