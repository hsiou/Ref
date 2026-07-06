using System.Text.Json;
using System.Text.Json.Serialization;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Presentation;
using D = DocumentFormat.OpenXml.Drawing;

if (args.Length < 2)
{
    Console.Error.WriteLine("Usage: dotnet run -- input.pptx output.json [--issues-only]");
    return 1;
}

var inputPath = args[0];
var outputPath = args[1];
var issuesOnly = args.Any(a => a == "--issues-only");

if (!File.Exists(inputPath))
{
    Console.Error.WriteLine($"File not found: {inputPath}");
    return 1;
}

const long EmuPerIn = 914400;
const long EmuPerPt = 12700;

using var doc = PresentationDocument.Open(inputPath, false);
var presentation = doc.PresentationPart!.Presentation;
var slideIds = presentation.SlideIdList!.Elements<SlideId>().ToList();

var inventory = new Dictionary<string, Dictionary<string, object>>();

for (int slideIdx = 0; slideIdx < slideIds.Count; slideIdx++)
{
    var slideId = slideIds[slideIdx];
    var slidePart = (SlidePart)doc.PresentationPart!.GetPartById(slideId.RelationshipId!);
    var shapes = new List<(int order, string key, Dictionary<string, object> data)>();

    CollectShapes(slidePart.Slide.CommonSlideData!.ShapeTree!, 0, 0, shapes);

    // Sort: top-to-bottom (with 0.5" row grouping), then left-to-right
    shapes.Sort((a, b) =>
    {
        var aPos = (Dictionary<string, object>)a.data["position"];
        var bPos = (Dictionary<string, object>)b.data["position"];
        var aTop = (double)aPos["top_in"];
        var bTop = (double)bPos["top_in"];
        var rowA = (int)(aTop / 0.5);
        var rowB = (int)(bTop / 0.5);
        if (rowA != rowB) return rowA.CompareTo(rowB);
        return ((double)aPos["left_in"]).CompareTo((double)bPos["left_in"]);
    });

    var slideShapes = new Dictionary<string, object>();
    for (int i = 0; i < shapes.Count; i++)
    {
        var shapeData = shapes[i].data;
        if (issuesOnly)
        {
            var hasIssues = shapeData.ContainsKey("overflow_bottom") ||
                            shapeData.ContainsKey("overflow_right") ||
                            shapeData.ContainsKey("overlaps");
            if (!hasIssues) continue;
        }
        slideShapes[$"shape-{i}"] = shapeData;
    }

    if (slideShapes.Count > 0)
        inventory[$"slide-{slideIdx}"] = slideShapes;
}

var json = JsonSerializer.Serialize(inventory, new JsonSerializerOptions
{
    WriteIndented = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
});
File.WriteAllText(outputPath, json);
Console.WriteLine($"Inventory: {slideIds.Count} slides → {outputPath}");
return 0;

void CollectShapes(ShapeTree tree, long offsetX, long offsetY,
    List<(int, string, Dictionary<string, object>)> results)
{
    int order = 0;
    foreach (var child in tree.Elements<Shape>())
    {
        var nvSpPr = child.NonVisualShapeProperties;
        if (nvSpPr == null) continue;

        var txBody = child.TextBody;
        if (txBody == null) continue;

        var text = string.Join("", txBody.Descendants<D.Text>().Select(t => t.Text));
        if (string.IsNullOrWhiteSpace(text)) continue;

        // Skip slide number and numeric footer placeholders
        var ph = nvSpPr.ApplicationNonVisualDrawingProperties?
            .GetFirstChild<PlaceholderShape>();
        if (ph?.Type?.Value == PlaceholderValues.SlideNumber) continue;
        if (ph?.Type?.Value == PlaceholderValues.Footer && double.TryParse(text.Trim(), out _)) continue;

        var spPr = child.ShapeProperties;
        var xfrm = spPr?.GetFirstChild<D.Transform2D>();
        if (xfrm?.Offset == null || xfrm.Extents == null) continue;

        var x = (xfrm.Offset.X ?? 0) + offsetX;
        var y = (xfrm.Offset.Y ?? 0) + offsetY;
        var cx = xfrm.Extents.Cx ?? 0;
        var cy = xfrm.Extents.Cy ?? 0;

        var paragraphs = new List<Dictionary<string, object?>>();
        foreach (var para in txBody.Elements<D.Paragraph>())
        {
            var pData = ExtractParagraph(para);
            if (pData != null) paragraphs.Add(pData);
        }

        if (paragraphs.Count == 0) continue;

        var shapeData = new Dictionary<string, object>
        {
            ["position"] = new Dictionary<string, object>
            {
                ["left_in"] = Math.Round((double)x / EmuPerIn, 3),
                ["top_in"] = Math.Round((double)y / EmuPerIn, 3),
                ["width_in"] = Math.Round((double)cx / EmuPerIn, 3),
                ["height_in"] = Math.Round((double)cy / EmuPerIn, 3),
                ["left_emu"] = x,
                ["top_emu"] = y,
                ["width_emu"] = cx,
                ["height_emu"] = cy
            },
            ["paragraphs"] = paragraphs
        };

        if (ph?.Type != null)
            shapeData["placeholder_type"] = ph.Type.Value.ToString();

        var name = nvSpPr.NonVisualDrawingProperties?.Name ?? "";
        results.Add((order++, name, shapeData));
    }
}

Dictionary<string, object?>? ExtractParagraph(D.Paragraph para)
{
    var runs = para.Elements<D.Run>().ToList();
    var text = string.Join("", runs.Select(r => r.GetFirstChild<D.Text>()?.Text ?? ""));
    if (string.IsNullOrWhiteSpace(text)) return null;

    var pPr = para.GetFirstChild<D.ParagraphProperties>();
    var result = new Dictionary<string, object?> { ["text"] = text };

    // Bullet detection
    var hasBulletChar = pPr?.GetFirstChild<D.CharacterBullet>() != null;
    var hasBulletNum = pPr?.GetFirstChild<D.AutoNumberedBullet>() != null;
    if (hasBulletChar || hasBulletNum) result["bullet"] = true;
    if (pPr?.Level != null) result["level"] = pPr.Level.Value;

    // Alignment
    if (pPr?.Alignment != null)
    {
        var alignVal = pPr.Alignment.Value;
        string? align = null;
        if (alignVal == D.TextAlignmentTypeValues.Center) align = "CENTER";
        else if (alignVal == D.TextAlignmentTypeValues.Right) align = "RIGHT";
        else if (alignVal == D.TextAlignmentTypeValues.Justified) align = "JUSTIFY";
        if (align != null) result["alignment"] = align;
    }

    // Spacing
    var spcBef = pPr?.GetFirstChild<D.SpaceBefore>()?.GetFirstChild<D.SpacingPoints>();
    if (spcBef != null) result["space_before"] = spcBef.Val! / 100.0;
    var spcAft = pPr?.GetFirstChild<D.SpaceAfter>()?.GetFirstChild<D.SpacingPoints>();
    if (spcAft != null) result["space_after"] = spcAft.Val! / 100.0;

    // Font from first run
    var firstRun = runs.FirstOrDefault();
    var rPr = firstRun?.GetFirstChild<D.RunProperties>();
    if (rPr != null)
    {
        if (rPr.FontSize != null) result["font_size"] = rPr.FontSize.Value / 100.0;
        if (rPr.Bold != null && rPr.Bold.HasValue && rPr.Bold.Value) result["bold"] = true;
        if (rPr.Italic != null && rPr.Italic.HasValue && rPr.Italic.Value) result["italic"] = true;
        if (rPr.Underline != null && rPr.Underline.HasValue && rPr.Underline.Value != D.TextUnderlineValues.None)
            result["underline"] = true;

        var latin = rPr.GetFirstChild<D.LatinFont>();
        if (latin?.Typeface != null) result["font_name"] = latin.Typeface.Value;

        var solidFill = rPr.GetFirstChild<D.SolidFill>();
        var rgb = solidFill?.GetFirstChild<D.RgbColorModelHex>();
        if (rgb?.Val != null) result["color"] = rgb.Val.Value;

        var scheme = solidFill?.GetFirstChild<D.SchemeColor>();
        if (scheme?.Val != null) result["theme_color"] = scheme.Val.Value.ToString();
    }

    return result;
}
