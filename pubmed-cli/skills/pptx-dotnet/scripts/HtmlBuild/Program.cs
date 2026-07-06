using System.Reflection;
using System.Text.Json;
using Microsoft.Playwright;

namespace HtmlBuild;

class Program
{
    static async Task<int> Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.Error.WriteLine("Usage: dotnet run -- slide1.html [slide2.html ...] output.pptx [--aspect 16:9|4:3|16:10]");
            return 1;
        }

        // Parse args: HTML files, output path, optional --aspect
        var aspect = "16:9";
        var htmlFiles = new List<string>();
        string? outputPath = null;

        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--aspect" && i + 1 < args.Length)
            {
                aspect = args[++i];
                continue;
            }
            if (args[i].EndsWith(".pptx", StringComparison.OrdinalIgnoreCase))
                outputPath = args[i];
            else
                htmlFiles.Add(args[i]);
        }

        if (outputPath == null || htmlFiles.Count == 0)
        {
            Console.Error.WriteLine("Need at least one .html file and one .pptx output path.");
            return 1;
        }

        foreach (var f in htmlFiles)
        {
            if (!File.Exists(f))
            {
                Console.Error.WriteLine($"Not found: {f}");
                return 1;
            }
        }

        // Resolve scaffold path
        var scaffoldName = aspect switch
        {
            "4:3" => "scaffold-4-3.pptx",
            "16:10" => "scaffold-16-10.pptx",
            _ => "scaffold-16-9.pptx"
        };
        var scaffoldPath = ResolveAsset($"assets/{scaffoldName}");
        if (scaffoldPath == null)
        {
            Console.Error.WriteLine($"Scaffold not found: {scaffoldName}");
            return 1;
        }

        // Load extraction JavaScript from embedded resource
        var extractionJs = LoadEmbeddedResource("HtmlBuild.extract-slide.js");
        if (extractionJs == null)
        {
            Console.Error.WriteLine("Failed to load extract-slide.js embedded resource.");
            return 1;
        }

        // Install Playwright Chromium if not already cached
        if (Environment.GetEnvironmentVariable("PLAYWRIGHT_SKIP_INSTALL") != "1")
        {
            var cacheDir = Environment.GetEnvironmentVariable("PLAYWRIGHT_BROWSERS_PATH")
                ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".cache", "ms-playwright");
            if (!Directory.Exists(cacheDir) || !Directory.EnumerateDirectories(cacheDir, "chromium-*").Any())
                Microsoft.Playwright.Program.Main(new[] { "install", "chromium", "--with-deps" });
        }

        using var playwright = await Playwright.CreateAsync();
        await using var browser = await playwright.Chromium.LaunchAsync(new BrowserTypeLaunchOptions
        {
            Headless = true
        });

        var slides = new List<SlideData>();
        var allErrors = new List<string>();

        foreach (var htmlFile in htmlFiles)
        {
            var page = await browser.NewPageAsync();
            var filePath = Path.GetFullPath(htmlFile);

            await page.GotoAsync($"file://{filePath}");

            // Extract slide data via DOM evaluation
            // Use EvaluateAsync returning string to avoid Playwright serializer issues with Infinity/NaN
            var wrapperJs = $"(() => {{ const __r = {extractionJs}; return JSON.stringify(__r); }})()";
            var json = await page.EvaluateAsync<string>(wrapperJs);
            var result = JsonSerializer.Deserialize<SlideData>(json!, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            })!;

            if (result.Errors.Length > 0)
            {
                foreach (var err in result.Errors)
                    allErrors.Add($"{Path.GetFileName(htmlFile)}: {err}");
            }

            slides.Add(result);
            await page.CloseAsync();
        }

        if (allErrors.Count > 0)
        {
            Console.Error.WriteLine("Validation errors:");
            foreach (var err in allErrors)
                Console.Error.WriteLine($"  - {err}");
            return 1;
        }

        // Build PPTX
        var builder = new PptxHtmlBuilder();
        builder.Build(slides.ToArray(), scaffoldPath, outputPath);

        Console.WriteLine($"Created {slides.Count}-slide presentation → {outputPath}");
        return 0;
    }

    static string? ResolveAsset(string relativePath)
    {
        // Walk up from assembly location to find the skill root (contains assets/ dir)
        var dir = AppContext.BaseDirectory;
        for (int i = 0; i < 8 && dir != null; i++)
        {
            var candidate = Path.Combine(dir, relativePath);
            if (File.Exists(candidate)) return candidate;
            dir = Directory.GetParent(dir)?.FullName;
        }

        // Also try relative to CWD
        if (File.Exists(relativePath)) return Path.GetFullPath(relativePath);

        return null;
    }

    static string? LoadEmbeddedResource(string name)
    {
        var assembly = Assembly.GetExecutingAssembly();
        using var stream = assembly.GetManifestResourceStream(name);
        if (stream == null) return null;
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }
}
