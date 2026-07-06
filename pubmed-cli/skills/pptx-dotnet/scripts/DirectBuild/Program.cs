using System.Text.Json;
using SkiaSharp;
using DirectBuild;

if (args.Length < 2)
{
    Console.Error.WriteLine("Usage: dotnet run -- slides.json output.pptx [--aspect 16:9|4:3|16:10]");
    return 1;
}

var jsonPath = args[0];
var outputPath = args[1];
var aspect = "16:9";
for (int i = 2; i < args.Length; i++)
    if (args[i] == "--aspect" && i + 1 < args.Length) aspect = args[++i];

if (!File.Exists(jsonPath)) { Console.Error.WriteLine($"Not found: {jsonPath}"); return 1; }

var json = File.ReadAllText(jsonPath);
var opts = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
var deck = JsonSerializer.Deserialize<SlideSpec[]>(json, opts);
if (deck == null || deck.Length == 0) { Console.Error.WriteLine("No slides in JSON"); return 1; }

// Validate
var errors = new List<string>();
var slideH = aspect switch { "4:3" => 7.5, "16:10" => 6.25, _ => 5.625 };

for (int i = 0; i < deck.Length; i++)
{
    var slide = deck[i];
    var textEls = slide.Elements?.Where(e => e.Type is "text" or "list").ToList() ?? [];

    // 1. Text overflow own box — measure actual rendered height with SkiaSharp
    foreach (var el in textEls)
    {
        // 1.3x safety factor: PowerPoint renders wider/taller than SkiaSharp measures
        var measuredH = MeasureTextHeight(el) * 1.3;
        if (measuredH > el.H + 0.05) // 0.05" tolerance
        {
            var label = (el.Text ?? el.Items?.FirstOrDefault()?.Text ?? "?")[..Math.Min(30, (el.Text ?? el.Items?.FirstOrDefault()?.Text ?? "?").Length)];
            errors.Add($"Slide {i}: text \"{label}\" overflows its box (needs {measuredH:F2}\" but allocated {el.H:F2}\")");
        }
    }

    // 2. Box-to-box overlap detection
    for (int a = 0; a < textEls.Count; a++)
    for (int b = a + 1; b < textEls.Count; b++)
    {
        var ea = textEls[a]; var eb = textEls[b];
        bool overlaps = !(ea.X + ea.W <= eb.X || eb.X + eb.W <= ea.X ||
                          ea.Y + ea.H <= eb.Y || eb.Y + eb.H <= ea.Y);
        if (overlaps)
            errors.Add($"Slide {i}: [{ea.Text?[..Math.Min(25, ea.Text?.Length ?? 0)]}] overlaps [{eb.Text?[..Math.Min(25, eb.Text?.Length ?? 0)]}]");
    }

    // 3. Bottom margin
    foreach (var el in textEls)
    {
        var bottom = el.Y + el.H;
        if (el.FontSize > 12 && slideH - bottom < 0.5)
            errors.Add($"Slide {i}: text too close to bottom ({(slideH - bottom):F2}\" margin)");
    }
}

// Measure rendered text height using SkiaSharp font metrics + word wrap
static double MeasureTextHeight(ElementSpec el)
{
    var fontSize = (float)el.FontSize;
    var fontName = el.FontName ?? "Arial";
    var boxWidthPt = (float)(el.W * 72); // inches to points

    if (el.Type == "list" && el.Items != null)
    {
        float totalH = 0;
        foreach (var item in el.Items)
        {
            var itemFs = (float)(item.FontSize ?? el.FontSize);
            var lineH = itemFs * 1.4f; // line height with spacing
            var indent = itemFs * 2.5f; // bullet indent
            var lines = WrapText(item.Text, itemFs, fontName, boxWidthPt - indent, item.Bold);
            totalH += lines * lineH;
        }
        return totalH / 72.0; // points to inches
    }

    if (el.Runs != null && el.Runs.Length > 0)
    {
        // Rich text: concatenate all runs, measure with largest font
        var allText = string.Join("", el.Runs.Select(r => r.Text));
        var maxFs = (float)el.Runs.Max(r => r.FontSize ?? el.FontSize);
        var lineH = maxFs * 1.4f;
        var lines = WrapText(allText, maxFs, fontName, boxWidthPt, el.Bold);
        return (lines * lineH) / 72.0;
    }

    if (el.Text != null)
    {
        var lineH = fontSize * 1.4f;
        float totalH = 0;
        foreach (var paragraph in el.Text.Split('\n'))
        {
            var lines = WrapText(paragraph, fontSize, fontName, boxWidthPt, el.Bold);
            totalH += Math.Max(1, lines) * lineH;
        }
        return totalH / 72.0;
    }

    return 0;
}

static int WrapText(string text, float fontSizePt, string fontName, float boxWidthPt, bool bold)
{
    if (string.IsNullOrEmpty(text)) return 1;

    var typeface = SKTypeface.FromFamilyName(fontName,
        bold ? SKFontStyleWeight.Bold : SKFontStyleWeight.Normal,
        SKFontStyleWidth.Normal, SKFontStyleSlant.Upright);

    using var paint = new SKPaint
    {
        Typeface = typeface,
        TextSize = fontSizePt,
        IsAntialias = true
    };

    var words = text.Split(' ');
    int lines = 1;
    float currentWidth = 0;

    foreach (var word in words)
    {
        var wordWidth = paint.MeasureText(word + " ");
        if (currentWidth + wordWidth > boxWidthPt && currentWidth > 0)
        {
            lines++;
            currentWidth = wordWidth;
        }
        else
        {
            currentWidth += wordWidth;
        }
    }
    return lines;
}

if (errors.Count > 0)
{
    Console.Error.WriteLine("Validation errors:");
    foreach (var e in errors) Console.Error.WriteLine($"  - {e}");
    return 1;
}

Console.WriteLine($"DirectBuild — {deck.Length} slide(s), {aspect}, output: {outputPath}");

var scaffoldName = aspect switch
{
    "4:3" => "scaffold-4-3.pptx",
    "16:10" => "scaffold-16-10.pptx",
    _ => "scaffold-16-9.pptx"
};
// Resolve skill root by walking up from the DLL location until we find assets/
var dllDir = Path.GetDirectoryName(typeof(Program).Assembly.Location) ?? AppContext.BaseDirectory;
var skillDir = dllDir;
for (int i = 0; i < 6 && !Directory.Exists(Path.Combine(skillDir, "assets")); i++)
    skillDir = Path.GetDirectoryName(skillDir) ?? skillDir;
var scaffoldPath = Path.Combine(skillDir, "assets", scaffoldName);
if (!File.Exists(scaffoldPath))
    throw new FileNotFoundException($"Scaffold not found: {scaffoldPath}");

var builder = new PptxDirectBuilder(scaffoldPath);
builder.Build(deck, outputPath);
Console.WriteLine($"  done → {outputPath}");
return 0;
