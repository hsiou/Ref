using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Presentation;
using D = DocumentFormat.OpenXml.Drawing;

namespace HtmlBuild;

public class PptxHtmlBuilder
{
    private const long EMU_PER_IN = 914400;
    private const long EMU_PER_PT = 12700;

    static long In(double inches) => (long)(inches * EMU_PER_IN);
    static long Pt(double pt) => (long)(pt * EMU_PER_PT);
    static int PtH(double pt) => (int)(pt * 100);
    static string Hex(string? c) => (c ?? "000000").TrimStart('#').ToUpperInvariant();

    public void Build(SlideData[] slides, string scaffoldPath, string outputPath)
    {
        File.Copy(scaffoldPath, outputPath, true);
        using var doc = PresentationDocument.Open(outputPath, true);
        var presPart = doc.PresentationPart!;
        var pres = presPart.Presentation;

        // Remove scaffold blank slide
        foreach (var existing in pres.SlideIdList!.Elements<SlideId>().ToList())
        {
            presPart.DeletePart(existing.RelationshipId!.Value!);
            existing.Remove();
        }

        var layoutPart = presPart.SlideMasterParts.First().SlideLayoutParts.First();
        uint slideId = 256;

        foreach (var spec in slides)
        {
            var slidePart = presPart.AddNewPart<SlidePart>();
            slidePart.CreateRelationshipToPart(layoutPart);

            var slide = new Slide(new CommonSlideData(new ShapeTree(
                new NonVisualGroupShapeProperties(
                    new NonVisualDrawingProperties { Id = 1, Name = "" },
                    new NonVisualGroupShapeDrawingProperties(),
                    new ApplicationNonVisualDrawingProperties()),
                new GroupShapeProperties(new D.TransformGroup(
                    new D.Offset { X = 0, Y = 0 }, new D.Extents { Cx = 0, Cy = 0 },
                    new D.ChildOffset { X = 0, Y = 0 }, new D.ChildExtents { Cx = 0, Cy = 0 })))));

            var tree = slide.CommonSlideData!.ShapeTree!;

            // Background
            if (spec.Background != null)
            {
                if (spec.Background.Type == "color" && spec.Background.Value != null)
                {
                    slide.CommonSlideData.Background = new Background(
                        new BackgroundProperties(
                            new D.SolidFill(new D.RgbColorModelHex { Val = Hex(spec.Background.Value) }),
                            new D.EffectList()));
                }
            }

            uint id = 2;
            foreach (var el in spec.Elements)
            {
                switch (el.Type)
                {
                    case "shape": AddShape(tree, el, ref id); break;
                    case "image": AddImage(tree, el, slidePart, ref id); break;
                    case "line": AddLine(tree, el, ref id); break;
                    case "list": AddList(tree, el, ref id); break;
                    default: AddText(tree, el, ref id); break;
                }
            }

            slidePart.Slide = slide;
            slidePart.Slide.Save();
            pres.SlideIdList!.Append(new SlideId
            {
                Id = slideId++,
                RelationshipId = presPart.GetIdOfPart(slidePart)
            });
        }

        pres.Save();
    }

    void AddText(ShapeTree tree, ElementData el, ref uint id)
    {
        if (el.Position == null || el.Style == null) return;

        var paragraph = new D.Paragraph();
        var pPr = MakeParagraphProperties(el.Style);
        paragraph.Append(pPr);

        if (el.Text is TextRunData[] runs)
        {
            foreach (var run in runs)
                paragraph.Append(MakeRun(run.Text,
                    run.Options?.FontSize ?? el.Style.FontSize,
                    el.Style.FontFace,
                    run.Options?.Color ?? el.Style.Color,
                    run.Options?.Bold ?? false,
                    run.Options?.Italic ?? false,
                    run.Options?.Underline ?? false));
        }
        else
        {
            var text = el.Text as string ?? "";
            paragraph.Append(MakeRun(text, el.Style.FontSize, el.Style.FontFace, el.Style.Color,
                el.Style.Bold ?? false, el.Style.Italic ?? false, el.Style.Underline ?? false));
        }

        paragraph.Append(new D.EndParagraphRunProperties { Language = "en-US", Dirty = false });

        // Adjust width for single-line text (2% wider)
        var pos = el.Position;
        var lineHeight = el.Style.LineSpacing ?? el.Style.FontSize * 1.2 / 72.0;
        var isSingleLine = pos.H <= lineHeight * 1.5 / 72.0;
        var adjustedX = pos.X;
        var adjustedW = pos.W;
        if (isSingleLine)
        {
            var increase = pos.W * 0.02;
            var align = el.Style.Align;
            if (align == "center") { adjustedX -= increase / 2; adjustedW += increase; }
            else if (align == "right") { adjustedX -= increase; adjustedW += increase; }
            else adjustedW += increase;
        }

        var bodyPr = new D.BodyProperties
        {
            Wrap = D.TextWrappingValues.Square,
            LeftInset = 0, RightInset = 0, TopInset = 0, BottomInset = 0
        };

        // Apply margin/inset if specified
        if (el.Style.Margin is { Length: >= 4 } margin)
        {
            bodyPr.LeftInset = (int)Pt(margin[0]);
            bodyPr.RightInset = (int)Pt(margin[1]);
            bodyPr.BottomInset = (int)Pt(margin[2]);
            bodyPr.TopInset = (int)Pt(margin[3]);
        }

        var xfrm = new D.Transform2D(
            new D.Offset { X = In(adjustedX), Y = In(pos.Y) },
            new D.Extents { Cx = In(adjustedW), Cy = In(pos.H) });
        if (el.Style.Rotate is > 0) xfrm.Rotation = (int)(el.Style.Rotate.Value * 60000);

        var shape = new Shape(
            new NonVisualShapeProperties(
                new NonVisualDrawingProperties { Id = id++, Name = $"Text {id}" },
                new NonVisualShapeDrawingProperties(new D.ShapeLocks { NoGrouping = true }) { TextBox = true },
                new ApplicationNonVisualDrawingProperties()),
            new ShapeProperties(xfrm,
                new D.PresetGeometry(new D.AdjustValueList()) { Preset = D.ShapeTypeValues.Rectangle },
                new D.NoFill()),
            new TextBody(bodyPr, new D.ListStyle(), paragraph));

        tree.Append(shape);
    }

    void AddList(ShapeTree tree, ElementData el, ref uint id)
    {
        if (el.Position == null || el.Items == null) return;

        var bodyPr = new D.BodyProperties
        {
            Wrap = D.TextWrappingValues.Square,
            LeftInset = 0, RightInset = 0, TopInset = 0, BottomInset = 0
        };
        var parts = new List<OpenXmlElement> { bodyPr, new D.ListStyle() };

        var currentPara = new D.Paragraph();
        var fontSize = el.Style?.FontSize ?? 14;

        foreach (var item in el.Items)
        {
            var pPr = new D.ParagraphProperties();

            if (item.Options?.Bullet == true)
            {
                var level = item.Options?.IndentLevel ?? 0;
                pPr.Level = level;
                pPr.Append(new D.CharacterBullet { Char = level == 0 ? "\u2022" : "\u2013" });
                pPr.LeftMargin = (int)((fontSize * (1.6 + level * 1.6)) * EMU_PER_PT);
                pPr.Indent = (int)(-fontSize * 0.8 * EMU_PER_PT);
            }

            if (el.Style?.ParaSpaceAfter is > 0)
                pPr.Append(new D.SpaceAfter(new D.SpacingPoints { Val = (int)(el.Style.ParaSpaceAfter.Value * 100) }));

            currentPara.Append(pPr);
            currentPara.Append(MakeRun(item.Text,
                item.Options?.FontSize ?? fontSize,
                el.Style?.FontFace,
                item.Options?.Color ?? el.Style?.Color,
                item.Options?.Bold ?? false,
                item.Options?.Italic ?? false,
                item.Options?.Underline ?? false));
            currentPara.Append(new D.EndParagraphRunProperties { Language = "en-US", Dirty = false });

            if (item.Options?.BreakLine == true)
            {
                parts.Add(currentPara);
                currentPara = new D.Paragraph();
            }
        }
        parts.Add(currentPara);

        var shape = new Shape(
            new NonVisualShapeProperties(
                new NonVisualDrawingProperties { Id = id++, Name = $"List {id}" },
                new NonVisualShapeDrawingProperties(new D.ShapeLocks { NoGrouping = true }) { TextBox = true },
                new ApplicationNonVisualDrawingProperties()),
            new ShapeProperties(
                new D.Transform2D(
                    new D.Offset { X = In(el.Position.X), Y = In(el.Position.Y) },
                    new D.Extents { Cx = In(el.Position.W), Cy = In(el.Position.H) }),
                new D.PresetGeometry(new D.AdjustValueList()) { Preset = D.ShapeTypeValues.Rectangle },
                new D.NoFill()),
            new TextBody(parts.ToArray()));

        tree.Append(shape);
    }

    void AddShape(ShapeTree tree, ElementData el, ref uint id)
    {
        if (el.Position == null || el.Shape == null) return;

        var geom = el.Shape.RectRadius > 0
            ? new D.PresetGeometry(new D.AdjustValueList(
                new D.ShapeGuide { Name = "adj", Formula = $"val {(int)(el.Shape.RectRadius / Math.Min(el.Position.W, el.Position.H) * 50000)}" }
              )) { Preset = D.ShapeTypeValues.RoundRectangle }
            : new D.PresetGeometry(new D.AdjustValueList()) { Preset = D.ShapeTypeValues.Rectangle };

        var spPr = new ShapeProperties(
            new D.Transform2D(
                new D.Offset { X = In(el.Position.X), Y = In(el.Position.Y) },
                new D.Extents { Cx = In(el.Position.W), Cy = In(el.Position.H) }),
            geom);

        if (el.Shape.Fill != null)
        {
            var fill = new D.SolidFill(new D.RgbColorModelHex { Val = Hex(el.Shape.Fill) });
            if (el.Shape.Transparency is > 0)
            {
                fill.RgbColorModelHex!.Append(new D.Alpha { Val = (int)((100 - el.Shape.Transparency.Value) * 1000) });
            }
            spPr.Append(fill);
        }
        else
        {
            spPr.Append(new D.NoFill());
        }

        if (el.Shape.Line != null)
        {
            spPr.Append(new D.Outline(
                new D.SolidFill(new D.RgbColorModelHex { Val = Hex(el.Shape.Line.Color) })
            ) { Width = (int)(el.Shape.Line.Width * EMU_PER_PT) });
        }

        if (el.Shape.Shadow != null)
        {
            var s = el.Shape.Shadow;
            spPr.Append(new D.EffectList(
                new D.OuterShadow(
                    new D.RgbColorModelHex(new D.Alpha { Val = (int)(s.Opacity * 100000) }) { Val = Hex(s.Color) }
                ) { BlurRadius = Pt(s.Blur), Distance = (long)(s.Offset * EMU_PER_PT), Direction = s.Angle * 60000 }));
        }

        var shape = new Shape(
            new NonVisualShapeProperties(
                new NonVisualDrawingProperties { Id = id++, Name = $"Shape {id}" },
                new NonVisualShapeDrawingProperties(),
                new ApplicationNonVisualDrawingProperties()),
            spPr,
            new TextBody(new D.BodyProperties(), new D.ListStyle(),
                new D.Paragraph(new D.EndParagraphRunProperties { Language = "en-US", Dirty = false })));

        tree.Append(shape);
    }

    void AddImage(ShapeTree tree, ElementData el, SlidePart slidePart, ref uint id)
    {
        if (el.Position == null || el.Src == null) return;

        // Handle file:// URLs
        var src = el.Src.StartsWith("file://") ? el.Src[7..] : el.Src;
        if (!File.Exists(src)) { Console.Error.WriteLine($"  warning: image not found: {src}"); return; }

        var ext = Path.GetExtension(src).ToLower();
        var ct = ext switch { ".png" => "image/png", ".jpg" or ".jpeg" => "image/jpeg", ".gif" => "image/gif", _ => "image/png" };
        var imgPart = slidePart.AddImagePart(ct);
        using (var s = File.OpenRead(src)) imgPart.FeedData(s);

        tree.Append(new Picture(
            new NonVisualPictureProperties(
                new NonVisualDrawingProperties { Id = id++, Name = $"Img {id}" },
                new NonVisualPictureDrawingProperties(new D.PictureLocks { NoChangeAspect = true }),
                new ApplicationNonVisualDrawingProperties()),
            new BlipFill(new D.Blip { Embed = slidePart.GetIdOfPart(imgPart) },
                new D.Stretch(new D.FillRectangle())),
            new ShapeProperties(
                new D.Transform2D(
                    new D.Offset { X = In(el.Position.X), Y = In(el.Position.Y) },
                    new D.Extents { Cx = In(el.Position.W), Cy = In(el.Position.H) }),
                new D.PresetGeometry(new D.AdjustValueList()) { Preset = D.ShapeTypeValues.Rectangle })));
    }

    void AddLine(ShapeTree tree, ElementData el, ref uint id)
    {
        if (el.X1 == null || el.Y1 == null || el.X2 == null || el.Y2 == null) return;

        var x1 = el.X1.Value; var y1 = el.Y1.Value;
        var x2 = el.X2.Value; var y2 = el.Y2.Value;

        tree.Append(new ConnectionShape(
            new NonVisualConnectionShapeProperties(
                new NonVisualDrawingProperties { Id = id++, Name = $"Line {id}" },
                new NonVisualConnectorShapeDrawingProperties(),
                new ApplicationNonVisualDrawingProperties()),
            new ShapeProperties(
                new D.Transform2D(
                    new D.Offset { X = In(Math.Min(x1, x2)), Y = In(Math.Min(y1, y2)) },
                    new D.Extents { Cx = In(Math.Abs(x2 - x1)), Cy = In(Math.Abs(y2 - y1)) }),
                new D.PresetGeometry(new D.AdjustValueList()) { Preset = D.ShapeTypeValues.Line },
                new D.Outline(
                    new D.SolidFill(new D.RgbColorModelHex { Val = Hex(el.LineColor) })
                ) { Width = (int)((el.LineWidth ?? 1) * EMU_PER_PT) })));
    }

    D.ParagraphProperties MakeParagraphProperties(StyleData style)
    {
        var pPr = new D.ParagraphProperties();

        if (style.Align != null)
            pPr.Alignment = style.Align.ToLower() switch
            {
                "center" => D.TextAlignmentTypeValues.Center,
                "right" => D.TextAlignmentTypeValues.Right,
                "justify" => D.TextAlignmentTypeValues.Justified,
                _ => null
            };

        if (style.ParaSpaceBefore is > 0)
            pPr.Append(new D.SpaceBefore(new D.SpacingPoints { Val = (int)(style.ParaSpaceBefore.Value * 100) }));
        if (style.ParaSpaceAfter is > 0)
            pPr.Append(new D.SpaceAfter(new D.SpacingPoints { Val = (int)(style.ParaSpaceAfter.Value * 100) }));
        if (style.LineSpacing is > 0)
            pPr.Append(new D.LineSpacing(new D.SpacingPoints { Val = (int)(style.LineSpacing.Value * 100) }));

        return pPr;
    }

    D.Run MakeRun(string text, double fontSize, string? fontName, string? color, bool bold, bool italic, bool underline)
    {
        fontName ??= "Arial";
        var isImpact = fontName.Equals("Impact", StringComparison.OrdinalIgnoreCase);
        var rPr = new D.RunProperties
        {
            Language = "en-US",
            FontSize = PtH(fontSize),
            Bold = (!isImpact && bold) ? true : null,
            Italic = italic ? true : null,
            Underline = underline ? D.TextUnderlineValues.Single : null,
            Dirty = false
        };
        if (color != null)
            rPr.Append(new D.SolidFill(new D.RgbColorModelHex { Val = Hex(color) }));
        rPr.Append(new D.LatinFont { Typeface = fontName });
        return new D.Run(rPr, new D.Text(text));
    }
}
