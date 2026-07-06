package output

import (
	"encoding/csv"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/henrybloomingdale/pubmed-cli/internal/eutils"
	"github.com/henrybloomingdale/pubmed-cli/internal/mesh"
)

func TestWriteSearchCSV_WithArticles(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "search.csv")

	result := &eutils.SearchResult{
		Count: 2,
		IDs:   []string{"111", "222"},
	}
	articles := []eutils.Article{
		{
			PMID:             "111",
			Title:            "First Article",
			Year:             "2024",
			Journal:          "J One",
			DOI:              "10.1/a",
			PublicationTypes: []string{"Review"},
		},
		{
			PMID:             "222",
			Title:            "Second Article",
			Year:             "2023",
			Journal:          "J Two",
			DOI:              "10.2/b",
			PublicationTypes: []string{"Journal Article", "Meta-Analysis"},
		},
	}

	err := writeSearchCSV(path, result, articles)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	rows := readCSV(t, path)
	// Header + 2 data rows
	if len(rows) != 3 {
		t.Fatalf("expected 3 rows (header + 2 data), got %d", len(rows))
	}

	// Header
	expectHeader := []string{"PMID", "Title", "Year", "Journal", "DOI", "Type"}
	for i, h := range expectHeader {
		if rows[0][i] != h {
			t.Errorf("header[%d]: expected %q, got %q", i, h, rows[0][i])
		}
	}

	// Row 1
	if rows[1][0] != "111" {
		t.Errorf("row 1 PMID: expected '111', got %q", rows[1][0])
	}
	if rows[1][1] != "First Article" {
		t.Errorf("row 1 Title: expected 'First Article', got %q", rows[1][1])
	}
	if rows[1][2] != "2024" {
		t.Errorf("row 1 Year: expected '2024', got %q", rows[1][2])
	}

	// Row 2 — multi-value type should be joined
	if rows[2][5] != "Journal Article; Meta-Analysis" {
		t.Errorf("row 2 Type: expected 'Journal Article; Meta-Analysis', got %q", rows[2][5])
	}
}

func TestWriteSearchCSV_WithoutArticles(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "search_ids.csv")

	result := &eutils.SearchResult{
		Count: 2,
		IDs:   []string{"111", "222"},
	}

	err := writeSearchCSV(path, result, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	rows := readCSV(t, path)
	if len(rows) != 3 {
		t.Fatalf("expected 3 rows (header + 2 data), got %d", len(rows))
	}

	if rows[0][0] != "Rank" || rows[0][1] != "PMID" {
		t.Errorf("expected header [Rank, PMID], got %v", rows[0])
	}
	if rows[1][0] != "1" || rows[1][1] != "111" {
		t.Errorf("expected row [1, 111], got %v", rows[1])
	}
}

func TestWriteArticlesCSV(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "articles.csv")

	articles := []eutils.Article{
		{
			PMID:     "12345",
			Title:    "Test Article With, Commas",
			Abstract: "Background: test\n\nMethods: stuff",
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

	err := writeArticlesCSV(path, articles)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	rows := readCSV(t, path)
	if len(rows) != 2 {
		t.Fatalf("expected 2 rows (header + 1 data), got %d", len(rows))
	}

	// Header
	expectHeader := []string{"PMID", "Title", "Authors", "Journal", "Year", "DOI", "Abstract", "MeSH"}
	for i, h := range expectHeader {
		if rows[0][i] != h {
			t.Errorf("header[%d]: expected %q, got %q", i, h, rows[0][i])
		}
	}

	// Data
	if rows[1][0] != "12345" {
		t.Errorf("PMID: expected '12345', got %q", rows[1][0])
	}
	if rows[1][1] != "Test Article With, Commas" {
		t.Errorf("Title: expected 'Test Article With, Commas', got %q", rows[1][1])
	}
	if rows[1][2] != "John Smith; Jane Doe" {
		t.Errorf("Authors: expected 'John Smith; Jane Doe', got %q", rows[1][2])
	}
	if rows[1][7] != "Humans; *FXS" {
		t.Errorf("MeSH: expected 'Humans; *FXS', got %q", rows[1][7])
	}
}

func TestWriteLinksCSV(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "links.csv")

	result := &eutils.LinkResult{
		SourceID: "12345",
		Links: []eutils.LinkItem{
			{ID: "111", Score: 99},
			{ID: "222", Score: 0},
		},
	}

	err := writeLinksCSV(path, result)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	rows := readCSV(t, path)
	if len(rows) != 3 {
		t.Fatalf("expected 3 rows, got %d", len(rows))
	}

	if rows[0][0] != "PMID" || rows[0][1] != "Score" {
		t.Errorf("expected header [PMID, Score], got %v", rows[0])
	}
	if rows[1][0] != "111" || rows[1][1] != "99" {
		t.Errorf("expected row [111, 99], got %v", rows[1])
	}
	if rows[2][0] != "222" || rows[2][1] != "" {
		t.Errorf("expected row [222, ], got %v", rows[2])
	}
}

func TestWriteMeSHCSV(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mesh.csv")

	record := &mesh.MeSHRecord{
		UI:          "D005600",
		Name:        "Fragile X Syndrome",
		ScopeNote:   "A condition...",
		TreeNumbers: []string{"C10.597", "C16.320"},
		EntryTerms:  []string{"FXS", "Martin-Bell"},
	}

	err := writeMeSHCSV(path, record)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	rows := readCSV(t, path)
	if len(rows) != 2 {
		t.Fatalf("expected 2 rows, got %d", len(rows))
	}

	if rows[0][0] != "UI" {
		t.Errorf("expected header starting with 'UI', got %q", rows[0][0])
	}
	if rows[1][0] != "D005600" {
		t.Errorf("UI: expected 'D005600', got %q", rows[1][0])
	}
	if !strings.Contains(rows[1][3], "C10.597") {
		t.Errorf("TreeNumbers should contain 'C10.597', got %q", rows[1][3])
	}
}

// readCSV is a test helper that reads and parses a CSV file.
func readCSV(t *testing.T, path string) [][]string {
	t.Helper()
	f, err := os.Open(path)
	if err != nil {
		t.Fatalf("failed to open CSV: %v", err)
	}
	defer f.Close()

	r := csv.NewReader(f)
	rows, err := r.ReadAll()
	if err != nil {
		t.Fatalf("failed to parse CSV: %v", err)
	}
	return rows
}
