// Package mesh provides MeSH term lookup via NCBI E-utilities.
package mesh

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/henrybloomingdale/pubmed-cli/internal/ncbi"
)

// MeSHRecord represents a MeSH descriptor record.
type MeSHRecord struct {
	UI          string   `json:"ui"`
	Name        string   `json:"name"`
	ScopeNote   string   `json:"scope_note"`
	TreeNumbers []string `json:"tree_numbers"`
	EntryTerms  []string `json:"entry_terms"`
	Annotation  string   `json:"annotation,omitempty"`
}

// Client provides MeSH lookup functionality.
// It embeds ncbi.BaseClient for shared rate limiting and common parameters.
type Client struct {
	*ncbi.BaseClient
}

// NewClient creates a new MeSH lookup client using an existing NCBI base client.
func NewClient(base *ncbi.BaseClient) *Client {
	return &Client{BaseClient: base}
}

// esearchResult for parsing MeSH search.
type meshSearchResponse struct {
	Result meshSearchResult `json:"esearchresult"`
}

type meshSearchResult struct {
	Count  string   `json:"count"`
	IDList []string `json:"idlist"`
}

// Lookup searches for a MeSH term and returns its record.
func (c *Client) Lookup(ctx context.Context, term string) (*MeSHRecord, error) {
	if term == "" {
		return nil, fmt.Errorf("MeSH term cannot be empty")
	}

	// Step 1: Search for the term in MeSH database
	ids, err := c.searchMeSH(ctx, term)
	if err != nil {
		return nil, err
	}
	if len(ids) == 0 {
		return nil, fmt.Errorf("MeSH term %q not found", term)
	}

	// Step 2: Fetch the full record
	record, err := c.fetchMeSH(ctx, ids[0])
	if err != nil {
		return nil, err
	}

	return record, nil
}

func (c *Client) searchMeSH(ctx context.Context, term string) ([]string, error) {
	// Try exact MeSH heading match first, fall back to broad search
	for _, query := range []string{
		fmt.Sprintf("%q[MeSH Terms]", term),
		term,
	} {
		params := map[string][]string{
			"db":      {"mesh"},
			"term":    {query},
			"retmode": {"json"},
		}

		resp, err := c.DoGet(ctx, "esearch.fcgi", params)
		if err != nil {
			return nil, fmt.Errorf("MeSH search failed: %w", err)
		}

		var result meshSearchResponse
		if err := json.Unmarshal(resp, &result); err != nil {
			return nil, fmt.Errorf("parsing MeSH search response: %w", err)
		}

		if len(result.Result.IDList) > 0 {
			return result.Result.IDList, nil
		}
	}

	return nil, nil
}

// esummaryResponse wraps the JSON returned by esummary.fcgi for the MeSH db.
type esummaryResponse struct {
	Result map[string]json.RawMessage `json:"result"`
}

// esummaryRecord holds the fields we need from a single MeSH esummary record.
type esummaryRecord struct {
	UID       string   `json:"uid"`
	ScopeNote string   `json:"ds_scopenote"`
	MeshTerms []string `json:"ds_meshterms"`
	MeshUI    string   `json:"ds_meshui"`
	IdxLinks  []struct {
		TreeNum string `json:"treenum"`
	} `json:"ds_idxlinks"`
}

func (c *Client) fetchMeSH(ctx context.Context, uid string) (*MeSHRecord, error) {
	params := make(map[string][]string)
	vals := map[string]string{
		"db":      "mesh",
		"id":      uid,
		"retmode": "json",
	}
	for k, v := range vals {
		params[k] = []string{v}
	}

	body, err := c.DoGet(ctx, "esummary.fcgi", params)
	if err != nil {
		return nil, fmt.Errorf("MeSH fetch failed: %w", err)
	}

	var resp esummaryResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("parsing MeSH summary: %w", err)
	}

	raw, ok := resp.Result[uid]
	if !ok {
		return nil, fmt.Errorf("MeSH UID %s not found in response", uid)
	}

	var rec esummaryRecord
	if err := json.Unmarshal(raw, &rec); err != nil {
		return nil, fmt.Errorf("parsing MeSH record %s: %w", uid, err)
	}

	record := &MeSHRecord{
		UI:        rec.MeshUI,
		ScopeNote: rec.ScopeNote,
	}

	// First term is the heading; rest are entry terms
	if len(rec.MeshTerms) > 0 {
		record.Name = rec.MeshTerms[0]
		if len(rec.MeshTerms) > 1 {
			record.EntryTerms = rec.MeshTerms[1:]
		}
	}

	for _, link := range rec.IdxLinks {
		if link.TreeNum != "" {
			record.TreeNumbers = append(record.TreeNumbers, link.TreeNum)
		}
	}

	return record, nil
}
