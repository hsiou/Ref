package output

import (
	"bytes"
	"strings"
	"testing"

	"github.com/henrybloomingdale/pubmed-cli/internal/eutils"
	"github.com/henrybloomingdale/pubmed-cli/internal/mesh"
)

func TestFormatSearchHuman_WithArticles(t *testing.T) {
	result := &eutils.SearchResult{
		Count:            2,
		IDs:              []string{"111", "222"},
		QueryTranslation: "fragile x syndrome",
	}
	articles := []eutils.Article{
		{PMID: "111", Title: "EEG Biomarkers in FXS", Year: "2024", PublicationTypes: []string{"Review"}},
		{PMID: "222", Title: "Another Important Study on Fragile X Syndrome Treatment Outcomes", Year: "2023", PublicationTypes: []string{"Journal Article"}},
	}

	var buf bytes.Buffer
	err := formatSearchHuman(&buf, result, articles)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	out := buf.String()
	// Should contain key content
	if !strings.Contains(out, "2") {
		t.Error("expected output to contain result count")
	}
	if !strings.Contains(out, "111") {
		t.Error("expected output to contain PMID '111'")
	}
	if !strings.Contains(out, "222") {
		t.Error("expected output to contain PMID '222'")
	}
	if !strings.Contains(out, "EEG Biomarkers") {
		t.Error("expected output to contain article title")
	}
	if !strings.Contains(out, "2024") {
		t.Error("expected output to contain year")
	}
}

func TestTruncate_UTF8Safe(t *testing.T) {
	input := "αβγδεζηθικλμ"
	got := truncate(input, 6)

	if !strings.HasSuffix(got, "…") {
		t.Fatalf("expected ellipsis suffix, got %q", got)
	}

	// Ensure output remains valid UTF-8 and rune-limited.
	if !strings.Contains(got, "α") {
		t.Fatalf("expected retained UTF-8 runes, got %q", got)
	}
}

func TestFormatSearchHuman_Empty(t *testing.T) {
	result := &eutils.SearchResult{Count: 0, IDs: []string{}}

	var buf bytes.Buffer
	err := formatSearchHuman(&buf, result, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	out := buf.String()
	if !strings.Contains(out, "No results") && !strings.Contains(out, "0") {
		t.Error("expected output to indicate no results")
	}
}

func TestFormatSearchHuman_PMIDsOnly(t *testing.T) {
	result := &eutils.SearchResult{
		Count: 3,
		IDs:   []string{"111", "222", "333"},
	}

	var buf bytes.Buffer
	err := formatSearchHuman(&buf, result, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	out := buf.String()
	if !strings.Contains(out, "111") {
		t.Error("expected output to contain PMID '111'")
	}
	if !strings.Contains(out, "333") {
		t.Error("expected output to contain PMID '333'")
	}
}

func TestFormatArticlesHuman_Card(t *testing.T) {
	articles := []eutils.Article{
		{
			PMID:     "12345",
			Title:    "Test Article Title",
			Abstract: "This is a long abstract that should be shown in human mode. It contains detailed methods and results about the study.",
			Authors: []eutils.Author{
				{LastName: "Smith", ForeName: "John"},
				{LastName: "Doe", ForeName: "Jane"},
			},
			Journal:          "Test Journal",
			Year:             "2024",
			DOI:              "10.1234/test",
			MeSHTerms:        []eutils.MeSHTerm{{Descriptor: "Humans"}, {Descriptor: "FXS", MajorTopic: true}},
			PublicationTypes: []string{"Journal Article"},
		},
	}

	var buf bytes.Buffer
	err := formatArticlesHuman(&buf, articles, false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	out := buf.String()
	if !strings.Contains(out, "12345") {
		t.Error("expected PMID in output")
	}
	if !strings.Contains(out, "Test Article Title") {
		t.Error("expected title in output")
	}
	if !strings.Contains(out, "Smith") {
		t.Error("expected author in output")
	}
	if !strings.Contains(out, "10.1234/test") {
		t.Error("expected DOI in output")
	}
	if !strings.Contains(out, "Humans") {
		t.Error("expected MeSH term in output")
	}
	if !strings.Contains(out, "FXS") {
		t.Error("expected MeSH term 'FXS' in output")
	}
}

func TestFormatArticlesHuman_TruncatedAbstract(t *testing.T) {
	longAbstract := strings.Repeat("Word ", 200) // ~1000 chars
	articles := []eutils.Article{
		{
			PMID:     "99999",
			Title:    "Long Abstract Article",
			Abstract: longAbstract,
		},
	}

	// Without --full: abstract should be truncated
	var buf bytes.Buffer
	err := formatArticlesHuman(&buf, articles, false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	out := buf.String()
	if !strings.Contains(out, "...") || !strings.Contains(out, "full") {
		t.Error("expected truncated abstract with hint for --full")
	}

	// With --full: abstract should be complete
	var bufFull bytes.Buffer
	err = formatArticlesHuman(&bufFull, articles, true)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	outFull := bufFull.String()
	// Full output should be longer and contain the complete text
	if len(outFull) <= len(out) {
		t.Error("expected --full output to be longer than truncated output")
	}
}

func TestFormatArticlesHuman_Empty(t *testing.T) {
	var buf bytes.Buffer
	err := formatArticlesHuman(&buf, []eutils.Article{}, false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	out := buf.String()
	if !strings.Contains(out, "No articles") && !strings.Contains(out, "no articles") {
		t.Errorf("expected 'no articles' message, got %q", out)
	}
}

func TestFormatLinksHuman(t *testing.T) {
	result := &eutils.LinkResult{
		SourceID: "12345",
		Links: []eutils.LinkItem{
			{ID: "111", Score: 99},
			{ID: "222", Score: 88},
		},
	}

	var buf bytes.Buffer
	err := formatLinksHuman(&buf, result, "cited-by")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	out := buf.String()
	if !strings.Contains(out, "111") {
		t.Error("expected PMID '111' in output")
	}
	if !strings.Contains(out, "99") {
		t.Error("expected score '99' in output")
	}
	if !strings.Contains(out, "12345") {
		t.Error("expected source PMID in output")
	}
}

func TestFormatLinksHuman_Empty(t *testing.T) {
	result := &eutils.LinkResult{
		SourceID: "12345",
		Links:    []eutils.LinkItem{},
	}

	var buf bytes.Buffer
	err := formatLinksHuman(&buf, result, "related")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	out := buf.String()
	if !strings.Contains(out, "No") && !strings.Contains(out, "no") {
		t.Error("expected 'no results' message")
	}
}

func TestFormatMeSHHuman(t *testing.T) {
	record := &mesh.MeSHRecord{
		UI:          "D005600",
		Name:        "Fragile X Syndrome",
		ScopeNote:   "A genetic condition caused by expansion of CGG repeats.",
		TreeNumbers: []string{"C10.597.606.360", "C16.320.322"},
		EntryTerms:  []string{"FXS", "Martin-Bell Syndrome", "Fra(X)"},
		Annotation:  "Do not confuse with fragile X tremor.",
	}

	var buf bytes.Buffer
	err := formatMeSHHuman(&buf, record)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	out := buf.String()
	if !strings.Contains(out, "Fragile X Syndrome") {
		t.Error("expected name in output")
	}
	if !strings.Contains(out, "D005600") {
		t.Error("expected UI in output")
	}
	if !strings.Contains(out, "C10.597") {
		t.Error("expected tree number in output")
	}
	if !strings.Contains(out, "FXS") {
		t.Error("expected entry term in output")
	}
	if !strings.Contains(out, "CGG repeats") {
		t.Error("expected scope note content in output")
	}
}
