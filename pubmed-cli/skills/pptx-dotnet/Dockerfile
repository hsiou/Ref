# ── Build stage ──────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

COPY scripts/Directory.Build.props scripts/
COPY scripts/HtmlBuild/HtmlBuild.csproj scripts/HtmlBuild/
RUN dotnet restore scripts/HtmlBuild/HtmlBuild.csproj

COPY scripts/HtmlBuild/ scripts/HtmlBuild/
RUN dotnet publish scripts/HtmlBuild/HtmlBuild.csproj \
    -c Release -o /app --no-restore

COPY assets/ /app/assets/

# ── Chromium install stage (uses SDK + published Playwright) ─
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
# The SDK image already has PowerShell; use Playwright's install script
RUN ls /app/.playwright/node/linux-*/node 2>/dev/null && \
    NODE=$(ls /app/.playwright/node/linux-*/node | head -1) && \
    $NODE /app/.playwright/package/cli.js install --with-deps chromium || \
    { echo "Fallback: using dotnet to install Chromium"; \
      dotnet new console -o /tmp/pw-install --no-restore && \
      echo 'Microsoft.Playwright.Program.Main(new[]{"install","chromium","--with-deps"});' > /tmp/pw-install/Program.cs && \
      cp /app/Microsoft.Playwright.dll /tmp/pw-install/ && \
      dotnet add /tmp/pw-install package Microsoft.Playwright --version 1.49.0 && \
      dotnet run --project /tmp/pw-install; }

# ── Runtime stage ────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/runtime:8.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 libxcomposite1 \
    libxdamage1 libxfixes3 libxkbcommon0 libxrandr2 \
    fonts-liberation fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_INSTALL=1

COPY --from=build /ms-playwright /ms-playwright
COPY --from=build /app /app

WORKDIR /data
ENTRYPOINT ["dotnet", "/app/HtmlBuild.dll"]
