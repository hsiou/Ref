// Validate: render PPTX slides to PNG for visual inspection
// Pure C# — reads PPTX with Open XML SDK, renders with SkiaSharp
// No LibreOffice, no PowerPoint, no external processes
// Usage: dotnet run -- input.pptx [--outdir dir] [--width 1920]

using System.Text.RegularExpressions;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Presentation;
using SkiaSharp;
using D = DocumentFormat.OpenXml.Drawing;

if (args.Length < 1)
{
    Console.Error.WriteLine("Usage: dotnet run -- input.pptx [--outdir dir] [--width N]");
    return 1;
}

var pptxPath = Path.GetFullPath(args[0]);
var outDir = ".";
var renderWidth = 1920;

for (int i = 1; i < args.Length; i++)
{
    if (args[i] == "--outdir" && i + 1 < args.Length) outDir = args[++i];
    if (args[i] == "--width" && i + 1 < args.Length) renderWidth = int.Parse(args[++i]);
}

if (!File.Exists(pptxPath)) { Console.Error.WriteLine($"Not found: {pptxPath}"); return 1; }
Directory.CreateDirectory(outDir);

using var doc = PresentationDocument.Open(pptxPath, false);
var presPart = doc.PresentationPart!;
var slideIds = presPart.Presentation.SlideIdList!.Elements<SlideId>().ToList();

// Get slide size
var sldSz = presPart.Presentation.SlideSize!;
var slideWidthEmu = (long)(sldSz.Cx?.Value ?? 9144000);
var slideHeightEmu = (long)(sldSz.Cy?.Value ?? 5143500);
float aspect = (float)slideHeightEmu / slideWidthEmu;
int renderHeight = (int)(renderWidth * aspect);

Console.WriteLine($"Validate: {slideIds.Count} slide(s), {renderWidth}x{renderHeight}px");

var outputFiles = new List<string>();

for (int si = 0; si < slideIds.Count; si++)
{
    var slidePart = (SlidePart)presPart.GetPartById(slideIds[si].RelationshipId!);
    var slide = slidePart.Slide;

    using var surface = SKSurface.Create(new SKImageInfo(renderWidth, renderHeight));
    var canvas = surface.Canvas;
    canvas.Clear(SKColors.White);

    float scaleX = (float)renderWidth / slideWidthEmu;
    float scaleY = (float)renderHeight / slideHeightEmu;

    // Background
    var bg = slide.CommonSlideData?.Background?.BackgroundProperties;
    if (bg != null)
    {
        var fill = bg.GetFirstChild<D.SolidFill>();
        var bgColor = ResolveColor(fill);
        if (bgColor != null)
            canvas.Clear(bgColor.Value);
    }

    // Render shapes
    var tree = slide.CommonSlideData?.ShapeTree;
    if (tree != null)
    {
        foreach (var element in tree.ChildElements)
        {
            if (element is Shape sp)
                RenderShape(canvas, sp, slidePart, scaleX, scaleY);
            else if (element is Picture pic)
                RenderPicture(canvas, pic, slidePart, scaleX, scaleY);
            else if (element is ConnectionShape cxn)
                RenderLine(canvas, cxn, scaleX, scaleY);
        }
    }

    // Save
    var fileName = $"slide-{si + 1:D2}.png";
    var filePath = Path.Combine(outDir, fileName);
    using var image = surface.Snapshot();
    using var data = image.Encode(SKEncodedImageFormat.Png, 90);
    using var stream = File.OpenWrite(filePath);
    data.SaveTo(stream);
    outputFiles.Add(filePath);
    Console.WriteLine($"  {fileName}");
}

Console.WriteLine($"\n{outputFiles.Count} slides → {Path.GetFullPath(outDir)}");
foreach (var f in outputFiles) Console.WriteLine(f);
return 0;

// ============================================================
// Rendering helpers
// ============================================================

void RenderShape(SKCanvas canvas, Shape sp, SlidePart slidePart, float sx, float sy)
{
    var spPr = sp.ShapeProperties;
    if (spPr == null) return;

    var xfrm = spPr.GetFirstChild<D.Transform2D>();
    if (xfrm?.Offset == null || xfrm.Extents == null) return;

    float x = (xfrm.Offset.X ?? 0) * sx;
    float y = (xfrm.Offset.Y ?? 0) * sy;
    float w = (xfrm.Extents.Cx ?? 0) * sx;
    float h = (xfrm.Extents.Cy ?? 0) * sy;

    if (w < 1 || h < 1) return;

    var rect = new SKRect(x, y, x + w, y + h);

    // Rounded corners?
    float radius = 0;
    var geom = spPr.GetFirstChild<D.PresetGeometry>();
    if (geom?.Preset?.Value == D.ShapeTypeValues.RoundRectangle)
    {
        var adj = geom.GetFirstChild<D.AdjustValueList>()?.GetFirstChild<D.ShapeGuide>();
        if (adj?.Formula != null)
        {
            var m = Regex.Match(adj.Formula.Value ?? "", @"val (\d+)");
            if (m.Success)
                radius = float.Parse(m.Groups[1].Value) / 50000f * Math.Min(w, h) * 0.5f;
        }
        if (radius < 1) radius = Math.Min(w, h) * 0.1f;
    }

    // Fill
    var solidFill = spPr.GetFirstChild<D.SolidFill>();
    var noFill = spPr.GetFirstChild<D.NoFill>();
    if (solidFill != null && noFill == null)
    {
        var color = ResolveColor(solidFill);
        if (color != null)
        {
            using var paint = new SKPaint { Color = color.Value, IsAntialias = true };
            if (radius > 0)
                canvas.DrawRoundRect(rect, radius, radius, paint);
            else
                canvas.DrawRect(rect, paint);
        }
    }

    // Border
    var outline = spPr.GetFirstChild<D.Outline>();
    if (outline != null)
    {
        var lineColor = ResolveColor(outline.GetFirstChild<D.SolidFill>());
        if (lineColor != null)
        {
            float lineW = Math.Max(1, (outline.Width ?? 12700) / 914400f * renderWidth / 10f);
            using var paint = new SKPaint
            {
                Color = lineColor.Value, IsAntialias = true,
                Style = SKPaintStyle.Stroke, StrokeWidth = lineW
            };
            if (radius > 0)
                canvas.DrawRoundRect(rect, radius, radius, paint);
            else
                canvas.DrawRect(rect, paint);
        }
    }

    // Text
    var txBody = sp.TextBody;
    if (txBody == null) return;

    float textX = x + 4;
    float textY = y;
    float maxWidth = w - 8;

    foreach (var para in txBody.Elements<D.Paragraph>())
    {
        float lineHeight = 0;
        var runs = para.Elements<D.Run>().ToList();
        if (runs.Count == 0) { textY += 8; continue; }

        // Check for bullets
        var pPr = para.GetFirstChild<D.ParagraphProperties>();
        bool hasBullet = pPr?.GetFirstChild<D.CharacterBullet>() != null ||
                         pPr?.GetFirstChild<D.AutoNumberedBullet>() != null;
        int level = pPr?.Level ?? 0;
        float indent = level * 15 + (hasBullet ? 15 : 0);

        float runX = textX + indent;

        // Draw bullet
        if (hasBullet)
        {
            var bulletChar = pPr?.GetFirstChild<D.CharacterBullet>()?.Char ?? "\u2022";
            var firstRun = runs.FirstOrDefault()?.GetFirstChild<D.RunProperties>();
            float bulletPt = (firstRun?.FontSize ?? 1400) / 100f;
            float bulletSize = bulletPt * ((float)renderHeight / (slideHeightEmu / 914400f)) / 72f;
            var bulletColor = ResolveColor(firstRun?.GetFirstChild<D.SolidFill>()) ?? SKColors.Black;
            using var bulletPaint = new SKPaint
            {
                Color = bulletColor, TextSize = bulletSize, IsAntialias = true
            };
            canvas.DrawText(bulletChar, textX + level * 15, textY + bulletSize, bulletPaint);
        }

        foreach (var run in runs)
        {
            var rPr = run.GetFirstChild<D.RunProperties>();
            var text = run.GetFirstChild<D.Text>()?.Text ?? "";
            if (string.IsNullOrEmpty(text)) continue;

            float fontPt = (rPr?.FontSize ?? 1800) / 100f;
            float fontSize = fontPt * ((float)renderHeight / (slideHeightEmu / 914400f)) / 72f;
            var color = ResolveColor(rPr?.GetFirstChild<D.SolidFill>()) ?? SKColors.Black;
            bool bold = rPr?.Bold?.Value ?? false;
            bool italic = rPr?.Italic?.Value ?? false;

            var typeface = SKTypeface.FromFamilyName(
                rPr?.GetFirstChild<D.LatinFont>()?.Typeface ?? "Arial",
                bold ? SKFontStyleWeight.Bold : SKFontStyleWeight.Normal,
                SKFontStyleWidth.Normal,
                italic ? SKFontStyleSlant.Italic : SKFontStyleSlant.Upright);

            using var paint = new SKPaint
            {
                Color = color, TextSize = fontSize, IsAntialias = true,
                Typeface = typeface
            };

            lineHeight = Math.Max(lineHeight, fontSize * 1.3f);

            // Word wrap
            var words = text.Split(' ');
            var currentLine = "";
            foreach (var word in words)
            {
                var test = currentLine.Length == 0 ? word : currentLine + " " + word;
                if (paint.MeasureText(test) > maxWidth - indent && currentLine.Length > 0)
                {
                    canvas.DrawText(currentLine, runX, textY + lineHeight, paint);
                    textY += lineHeight;
                    currentLine = word;
                }
                else
                {
                    currentLine = test;
                }
            }
            if (currentLine.Length > 0)
            {
                canvas.DrawText(currentLine, runX, textY + lineHeight, paint);
            }
        }

        textY += lineHeight > 0 ? lineHeight : 8;
    }
}

void RenderPicture(SKCanvas canvas, Picture pic, SlidePart slidePart, float sx, float sy)
{
    var spPr = pic.ShapeProperties;
    var xfrm = spPr?.GetFirstChild<D.Transform2D>();
    if (xfrm?.Offset == null || xfrm.Extents == null) return;

    float x = (xfrm.Offset.X ?? 0) * sx;
    float y = (xfrm.Offset.Y ?? 0) * sy;
    float w = (xfrm.Extents.Cx ?? 0) * sx;
    float h = (xfrm.Extents.Cy ?? 0) * sy;

    var blipFill = pic.BlipFill;
    var blip = blipFill?.Blip;
    if (blip?.Embed?.Value == null) return;

    try
    {
        var imagePart = (ImagePart)slidePart.GetPartById(blip.Embed.Value);
        using var imgStream = imagePart.GetStream();
        using var skImg = SKBitmap.Decode(imgStream);
        if (skImg != null)
        {
            canvas.DrawBitmap(skImg, new SKRect(x, y, x + w, y + h));
        }
    }
    catch
    {
        // Draw placeholder for missing image
        using var paint = new SKPaint { Color = new SKColor(200, 200, 200), IsAntialias = true };
        canvas.DrawRect(x, y, w, h, paint);
        using var textPaint = new SKPaint { Color = SKColors.Gray, TextSize = 14, IsAntialias = true };
        canvas.DrawText("[image]", x + 10, y + h / 2, textPaint);
    }
}

void RenderLine(SKCanvas canvas, ConnectionShape cxn, float sx, float sy)
{
    var spPr = cxn.ShapeProperties;
    var xfrm = spPr?.GetFirstChild<D.Transform2D>();
    if (xfrm?.Offset == null || xfrm.Extents == null) return;

    float x1 = (xfrm.Offset.X ?? 0) * sx;
    float y1 = (xfrm.Offset.Y ?? 0) * sy;
    float x2 = x1 + (xfrm.Extents.Cx ?? 0) * sx;
    float y2 = y1 + (xfrm.Extents.Cy ?? 0) * sy;

    var outline = spPr?.GetFirstChild<D.Outline>();
    var color = ResolveColor(outline?.GetFirstChild<D.SolidFill>()) ?? SKColors.Black;
    float lineW = Math.Max(1, (outline?.Width ?? 12700) / 914400f * renderWidth / 10f);

    using var paint = new SKPaint
    {
        Color = color, StrokeWidth = lineW,
        Style = SKPaintStyle.Stroke, IsAntialias = true
    };
    canvas.DrawLine(x1, y1, x2, y2, paint);
}

static SKColor? ResolveColor(D.SolidFill? fill)
{
    if (fill == null) return null;

    var rgb = fill.GetFirstChild<D.RgbColorModelHex>();
    if (rgb?.Val?.Value != null)
    {
        var hex = rgb.Val.Value.TrimStart('#');
        if (hex.Length >= 6)
        {
            var r = Convert.ToByte(hex[0..2], 16);
            var g = Convert.ToByte(hex[2..4], 16);
            var b = Convert.ToByte(hex[4..6], 16);
            return new SKColor(r, g, b);
        }
    }

    // Fallback for scheme colors
    var scheme = fill.GetFirstChild<D.SchemeColor>();
    if (scheme?.Val?.Value != null)
    {
        var sv = scheme.Val.Value;
        if (sv == D.SchemeColorValues.Text1 || sv == D.SchemeColorValues.Dark1) return SKColors.Black;
        if (sv == D.SchemeColorValues.Background1 || sv == D.SchemeColorValues.Light1) return SKColors.White;
        if (sv == D.SchemeColorValues.Accent1) return new SKColor(0x25, 0x63, 0xEB);
        if (sv == D.SchemeColorValues.Accent2) return new SKColor(0xC0, 0x50, 0x4D);
        return SKColors.Gray;
    }

    return null;
}
