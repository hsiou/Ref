package output

import (
	"encoding/csv"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/henrybloomingdale/pubmed-cli/internal/eutils"
	"github.com/henrybloomingdale/pubmed-cli/internal/mesh"
)

// writeSearchCSV exports search results to CSV.
// If articles are provided, writes: PMID,Title,Year,Journal,DOI,Type.
// Otherwise writes: Rank,PMID.
func writeSearchCSV(path string, result *eutils.SearchResult, articles []eutils.Article) error {
	w, f, err := createCSV(path)
	if err != nil {
		return err
	}
	defer f.Close()

	if len(articles) > 0 {
		// Rich CSV with article details
		w.Write([]string{"PMID", "Title", "Year", "Journal", "DOI", "Type"})

		// Index articles by PMID for lookup
		byPMID := make(map[string]eutils.Article, len(articles))
		for _, a := range articles {
			byPMID[a.PMID] = a
		}

		for _, id := range result.IDs {
			a, ok := byPMID[id]
			if !ok {
				w.Write([]string{id, "", "", "", "", ""})
				continue
			}
			w.Write([]string{
				a.PMID,
				a.Title,
				a.Year,
				a.Journal,
				a.DOI,
				strings.Join(a.PublicationTypes, "; "),
			})
		}
	} else {
		// Simple PMID list
		w.Write([]string{"Rank", "PMID"})
		for i, id := range result.IDs {
			w.Write([]string{strconv.Itoa(i + 1), id})
		}
	}

	w.Flush()
	return w.Error()
}

// writeArticlesCSV exports article details to CSV.
// Columns: PMID,Title,Authors,Journal,Year,DOI,Abstract,MeSH
func writeArticlesCSV(path string, articles []eutils.Article) error {
	w, f, err := createCSV(path)
	if err != nil {
		return err
	}
	defer f.Close()

	w.Write([]string{"PMID", "Title", "Authors", "Journal", "Year", "DOI", "Abstract", "MeSH"})

	for _, a := range articles {
		// Authors: semicolon-separated full names
		names := make([]string, len(a.Authors))
		for i, au := range a.Authors {
			names[i] = au.FullName()
		}

		// MeSH: semicolon-separated, major topics prefixed with *
		meshTerms := make([]string, len(a.MeSHTerms))
		for i, m := range a.MeSHTerms {
			if m.MajorTopic {
				meshTerms[i] = "*" + m.Descriptor
			} else {
				meshTerms[i] = m.Descriptor
			}
		}

		w.Write([]string{
			a.PMID,
			a.Title,
			strings.Join(names, "; "),
			a.Journal,
			a.Year,
			a.DOI,
			a.Abstract,
			strings.Join(meshTerms, "; "),
		})
	}

	w.Flush()
	return w.Error()
}

// writeLinksCSV exports link results to CSV.
// Columns: PMID,Score
func writeLinksCSV(path string, result *eutils.LinkResult) error {
	w, f, err := createCSV(path)
	if err != nil {
		return err
	}
	defer f.Close()

	w.Write([]string{"PMID", "Score"})

	for _, link := range result.Links {
		score := ""
		if link.Score > 0 {
			score = strconv.Itoa(link.Score)
		}
		w.Write([]string{link.ID, score})
	}

	w.Flush()
	return w.Error()
}

// writeMeSHCSV exports a MeSH record to CSV.
// Columns: UI,Name,ScopeNote,TreeNumbers,EntryTerms,Annotation
func writeMeSHCSV(path string, record *mesh.MeSHRecord) error {
	w, f, err := createCSV(path)
	if err != nil {
		return err
	}
	defer f.Close()

	w.Write([]string{"UI", "Name", "ScopeNote", "TreeNumbers", "EntryTerms", "Annotation"})
	w.Write([]string{
		record.UI,
		record.Name,
		record.ScopeNote,
		strings.Join(record.TreeNumbers, "; "),
		strings.Join(record.EntryTerms, "; "),
		record.Annotation,
	})

	w.Flush()
	return w.Error()
}

func createCSV(path string) (*csv.Writer, *os.File, error) {
	f, err := os.Create(path)
	if err != nil {
		return nil, nil, fmt.Errorf("creating CSV file: %w", err)
	}
	return csv.NewWriter(f), f, nil
}
