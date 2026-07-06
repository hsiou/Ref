//go:build integration

package mesh

import (
	"context"
	"os"
	"testing"
)

func TestIntegration_MeSHLookup(t *testing.T) {
	apiKey := os.Getenv("NCBI_API_KEY")
	c := NewClient("https://eutils.ncbi.nlm.nih.gov/entrez/eutils", apiKey, "pubmed-cli", "pubmed-cli@users.noreply.github.com")

	record, err := c.Lookup(context.Background(), "Fragile X Syndrome")
	if err != nil {
		t.Fatalf("MeSH lookup failed: %v", err)
	}

	if record.Name == "" {
		t.Error("expected non-empty name")
	}
	if record.UI == "" {
		t.Error("expected non-empty UI")
	}
	if record.ScopeNote == "" {
		t.Error("expected non-empty scope note")
	}
	if len(record.TreeNumbers) == 0 {
		t.Error("expected at least one tree number")
	}

	t.Logf("MeSH: %s (UI: %s)", record.Name, record.UI)
	t.Logf("Trees: %v", record.TreeNumbers)
	t.Logf("Entry terms: %v", record.EntryTerms)
}
