# Homebrew Maintenance Guide

This guide documents Homebrew metadata and release update steps for `pubmed-cli`.

Tap:
- `henrybloomingdale/tools`

Formula:
- `Formula/pubmed-cli.rb`

## Required formula metadata

Ensure the formula includes correct values for:
- `desc`
- `homepage`
- `license` (`"MIT"`)
- `version`
- `url` per OS/architecture (`darwin`, `linux`)
- `sha256` per OS/architecture

## Update workflow after a new GitHub release

1. Build and publish `vX.Y.Z` release artifacts.
2. Compute SHA256 for each artifact:

```bash
curl -sL https://github.com/drpedapati/pubmed-cli/releases/download/vX.Y.Z/pubmed-darwin-arm64 | shasum -a 256
curl -sL https://github.com/drpedapati/pubmed-cli/releases/download/vX.Y.Z/pubmed-darwin-amd64 | shasum -a 256
curl -sL https://github.com/drpedapati/pubmed-cli/releases/download/vX.Y.Z/pubmed-linux-amd64 | shasum -a 256
curl -sL https://github.com/drpedapati/pubmed-cli/releases/download/vX.Y.Z/pubmed-linux-arm64 | shasum -a 256
```

3. Update `Formula/pubmed-cli.rb` version, URLs, and checksums.
4. Validate locally:

```bash
brew update
brew audit --strict --online pubmed-cli
brew reinstall pubmed-cli
brew test pubmed-cli
pubmed --help
```

## Version notes

- **v0.6.0**: Adds the `refcheck` subcommand. `refcheck` requires `docx-review` as a
  runtime dependency — it is not bundled in the Homebrew formula, so users must install
  it separately.

## Example formula shape

```ruby
class PubmedCli < Formula
  desc "Production-focused PubMed CLI"
  homepage "https://github.com/drpedapati/pubmed-cli"
  version "0.5.1"
  license "MIT"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/drpedapati/pubmed-cli/releases/download/v#{version}/pubmed-darwin-arm64"
      sha256 "REPLACE_WITH_DARWIN_ARM64_SHA256"
    else
      url "https://github.com/drpedapati/pubmed-cli/releases/download/v#{version}/pubmed-darwin-amd64"
      sha256 "REPLACE_WITH_DARWIN_AMD64_SHA256"
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/drpedapati/pubmed-cli/releases/download/v#{version}/pubmed-linux-arm64"
      sha256 "REPLACE_WITH_LINUX_ARM64_SHA256"
    else
      url "https://github.com/drpedapati/pubmed-cli/releases/download/v#{version}/pubmed-linux-amd64"
      sha256 "REPLACE_WITH_LINUX_AMD64_SHA256"
    end
  end

  def install
    if OS.mac? && Hardware::CPU.arm?
      bin.install "pubmed-darwin-arm64" => "pubmed"
    elsif OS.mac?
      bin.install "pubmed-darwin-amd64" => "pubmed"
    elsif Hardware::CPU.arm?
      bin.install "pubmed-linux-arm64" => "pubmed"
    else
      bin.install "pubmed-linux-amd64" => "pubmed"
    end
  end

  test do
    assert_match "pubmed", shell_output("#{bin}/pubmed --help")
  end
end
```
