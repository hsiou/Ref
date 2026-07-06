# Contributing

Thanks for contributing to `pubmed-cli`.

## Development setup

```bash
git clone https://github.com/drpedapati/pubmed-cli.git
cd pubmed-cli
go build ./...
go test ./...
```

Optional for integration-like testing:

```bash
export NCBI_API_KEY="your-key"
```

## Pull request checklist

1. Keep changes scoped and atomic.
2. Update docs when command behavior changes.
3. Add or update tests for behavior changes.
4. Run:

```bash
go build ./...
go test ./...
go vet ./...
```

## Commit and release notes

- Use clear commit messages.
- If user-facing behavior changed, update `CHANGELOG.md`.
- If install/release behavior changed, update `README.md`, `RELEASING.md`, and `docs/homebrew.md`.
