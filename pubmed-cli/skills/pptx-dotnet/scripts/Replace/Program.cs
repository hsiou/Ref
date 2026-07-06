using System.Text.Json;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Presentation;
using D = DocumentFormat.OpenXml.Drawing;

if (args.Length < 3)
{
    Console.Error.WriteLine("Usage: dotnet run -- input.pptx replacements.json output.pptx");
    return 1;
}

var inputPath = args[0];
var jsonPath = args[1];
var outputPath = args[2];

if (!File.Exists(inputPath)) { Console.Error.WriteLine($"Not found: {inputPath}"); return 1; }
if (!File.Exists(jsonPath)) { Console.Error.WriteLine($"Not found: {jsonPath}"); return 1; }

const long EmuPerIn = 914400;
const long EmuPerPt = 12700;

// Load replacements
var jsonText = File.ReadAllText(jsonPath);
var replacements = JsonSerializer.Deserialize<Dictionary<string, Dictionary<string, JsonElement>>>(jsonText);
if (replacements == null) { Console.Error.WriteLine("Invalid JSON"); return 1; }

// Copy input to output
File.Copy(inputPath, outputPath, true);

using var doc = PresentationDocument.Open(outputPath, true);
var presentation = doc.PresentationPart!.Presentation;
var slideIds = presentation.SlideIdList!.Elements<SlideId>().ToList();

var errors = new List<string>();

foreach (var (slideKey, shapeReplacements) in replacements)
{
    if (!slideKey.StartsWith("slide-") || !int.TryParse(slideKey[6..], out var slideIdx))
    {
        errors.Add($"Invalid slide key: {slideKey}");
        continue;
    }
    if (slideIdx < 0 || slideIdx >= slideIds.Count)
    {
        errors.Add($"{slideKey}: index out of range (have {slideIds.Count} slides)");
        continue;
    }

    var slidePart = (SlidePart)doc.PresentationPart!.GetPartById(slideIds[slideIdx].RelationshipId!);
    var shapes = GetTextShapes(slidePart);

    foreach (var (shapeKey, replacement) in shapeReplacements)
    {
        if (!shapeKey.StartsWith("shape-") || !int.TryParse(shapeKey[6..], out var shapeIdx))
        {
            errors.Add($"{slideKey}/{shapeKey}: invalid shape key");
            continue;
        }
        if (shapeIdx < 0 || shapeIdx >= shapes.Count)
        {
            errors.Add($"{slideKey}/{shapeKey}: index out of range (have {shapes.Count} shapes). Available: " +
                string.Join(", ", shapes.Select((s, i) =>
                    $"shape-{i} (\"{string.Join("", s.TextBody!.Descendants<D.Text>().Select(t => t.Text))[..Math.Min(30, string.Join("", s.TextBody!.Descendants<D.Text>().Select(t => t.Text)).Length)]}...\")")));
            continue;
        }

        if (!replacement.TryGetProperty("paragraphs", out var parasJson))
        {
            errors.Add($"{slideKey}/{shapeKey}: missing 'paragraphs' array");
            continue;
        }

        var shape = shapes[shapeIdx];
        var txBody = shape.TextBody!;

        // Clear existing paragraphs
        txBody.RemoveAllChildren<D.Paragraph>();

        foreach (var paraJson in parasJson.EnumerateArray())
        {
            var para = new D.Paragraph();
            var pPr = new D.ParagraphProperties();

            // Bullet
            if (paraJson.TryGetProperty("bullet", out var bullet) && bullet.GetBoolean())
            {
                var level = paraJson.TryGetProperty("level", out var lvl) ? lvl.GetInt32() : 0;
                pPr.Level = level;
                pPr.Append(new D.CharacterBullet { Char = level == 0 ? "•" : "–" });

                var fs = paraJson.TryGetProperty("font_size", out var fsVal) ? fsVal.GetDouble() : 18;
                pPr.LeftMargin = (int)((fs * (1.6 + level * 1.6)) * EmuPerPt);
                pPr.Indent = (int)(-fs * 0.8 * EmuPerPt);
            }

            // Alignment
            if (paraJson.TryGetProperty("alignment", out var align))
            {
                pPr.Alignment = align.GetString()?.ToUpper() switch
                {
                    "CENTER" => D.TextAlignmentTypeValues.Center,
                    "RIGHT" => D.TextAlignmentTypeValues.Right,
                    "JUSTIFY" => D.TextAlignmentTypeValues.Justified,
                    _ => null
                };
            }

            // Spacing
            if (paraJson.TryGetProperty("space_before", out var sb))
                pPr.Append(new D.SpaceBefore(new D.SpacingPoints { Val = (int)(sb.GetDouble() * 100) }));
            if (paraJson.TryGetProperty("space_after", out var sa))
                pPr.Append(new D.SpaceAfter(new D.SpacingPoints { Val = (int)(sa.GetDouble() * 100) }));

            para.Append(pPr);

            // Text run
            var text = paraJson.TryGetProperty("text", out var t) ? t.GetString() ?? "" : "";
            var rPr = new D.RunProperties { Language = "en-US", Dirty = false };

            if (paraJson.TryGetProperty("font_size", out var fontSize))
                rPr.FontSize = (int)(fontSize.GetDouble() * 100);
            if (paraJson.TryGetProperty("bold", out var bold) && bold.GetBoolean())
                rPr.Bold = true;
            if (paraJson.TryGetProperty("italic", out var italic) && italic.GetBoolean())
                rPr.Italic = true;
            if (paraJson.TryGetProperty("underline", out var underline) && underline.GetBoolean())
                rPr.Underline = D.TextUnderlineValues.Single;

            if (paraJson.TryGetProperty("color", out var color))
            {
                var hex = color.GetString()?.TrimStart('#').ToUpperInvariant() ?? "000000";
                rPr.Append(new D.SolidFill(new D.RgbColorModelHex { Val = hex }));
            }

            if (paraJson.TryGetProperty("theme_color", out var themeColor))
            {
                var val = Enum.TryParse<D.SchemeColorValues>(themeColor.GetString(), true, out var sc)
                    ? sc : D.SchemeColorValues.Text1;
                rPr.Append(new D.SolidFill(new D.SchemeColor { Val = val }));
            }

            if (paraJson.TryGetProperty("font_name", out var fontName))
                rPr.Append(new D.LatinFont { Typeface = fontName.GetString() });

            para.Append(new D.Run(rPr, new D.Text(text)));
            para.Append(new D.EndParagraphRunProperties { Language = "en-US", Dirty = false });

            txBody.Append(para);
        }
    }

    slidePart.Slide.Save();
}

if (errors.Count > 0)
{
    Console.Error.WriteLine("Errors:");
    foreach (var err in errors)
        Console.Error.WriteLine($"  - {err}");
    // Clean up failed output
    File.Delete(outputPath);
    return 1;
}

doc.Dispose();
Console.WriteLine($"Replaced text → {outputPath}");
return 0;

List<Shape> GetTextShapes(SlidePart slidePart)
{
    var shapes = new List<(double top, double left, Shape shape)>();
    foreach (var shape in slidePart.Slide.CommonSlideData!.ShapeTree!.Elements<Shape>())
    {
        var txBody = shape.TextBody;
        if (txBody == null) continue;
        var text = string.Join("", txBody.Descendants<D.Text>().Select(t => t.Text));
        if (string.IsNullOrWhiteSpace(text)) continue;

        var ph = shape.NonVisualShapeProperties?.ApplicationNonVisualDrawingProperties?
            .GetFirstChild<PlaceholderShape>();
        if (ph?.Type?.Value == PlaceholderValues.SlideNumber) continue;

        var xfrm = shape.ShapeProperties?.GetFirstChild<D.Transform2D>();
        var top = (double)(xfrm?.Offset?.Y ?? 0) / EmuPerIn;
        var left = (double)(xfrm?.Offset?.X ?? 0) / EmuPerIn;
        shapes.Add((top, left, shape));
    }

    shapes.Sort((a, b) =>
    {
        var rowA = (int)(a.top / 0.5);
        var rowB = (int)(b.top / 0.5);
        if (rowA != rowB) return rowA.CompareTo(rowB);
        return a.left.CompareTo(b.left);
    });

    return shapes.Select(s => s.shape).ToList();
}
