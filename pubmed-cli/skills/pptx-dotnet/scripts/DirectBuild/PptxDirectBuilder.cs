using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Presentation;
using D = DocumentFormat.OpenXml.Drawing;

namespace DirectBuild;

public class PptxDirectBuilder
{
    private readonly string _scaffoldPath;
    private const long EMU_PER_IN = 914400;
    private const long EMU_PER_PT = 12700;

    public PptxDirectBuilder(string scaffoldPath) => _scaffoldPath = scaffoldPath;

    static long In(double inches) => (long)(inches * EMU_PER_IN);
    static long Pt(double pt) => (long)(pt * EMU_PER_PT);
    static int PtH(double pt) => (int)(pt * 100); // hundredths of a point
    static string Hex(string? c) => (c ?? "000000").TrimStart('#').ToUpperInvariant();

    public void Build(SlideSpec[] slides, string outputPath)
    {
        File.Copy(_scaffoldPath, outputPath, true);
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

            var grpSpPr = new GroupShapeProperties(new D.TransformGroup(
                new D.Offset { X = 0, Y = 0 }, new D.Extents { Cx = 0, Cy = 0 },
                new D.ChildOffset { X = 0, Y = 0 }, new D.ChildExtents { Cx = 0, Cy = 0 }));

            var slide = new Slide(new CommonSlideData(new ShapeTree(
                new NonVisualGroupShapeProperties(
                    new NonVisualDrawingProperties { Id = 1, Name = "" },
                    new NonVisualGroupShapeDrawingProperties(),
                    new ApplicationNonVisualDrawingProperties()),
                grpSpPr)));

            var tree = slide.CommonSlideData!.ShapeTree!;

            // Background
            if (spec.Background != null)
            {
                slide.CommonSlideData.Background = new Background(
                    new BackgroundProperties(
                        new D.SolidFill(new D.RgbColorModelHex { Val = Hex(spec.Background) }),
                        new D.EffectList()));
            }

            uint id = 2;
            foreach (var el in spec.Elements ?? [])
            {
                switch (el.Type)
                {
                    case "text": AddText(tree, el, ref id); break;
                    case "list": AddList(tree, el, ref id); break;
                    case "shape": AddShape(tree, el, ref id); break;
                    case "image": AddImage(tree, el, slidePart, ref id); break;
                    case "line": AddLine(tree, el, ref id); break;
                }
            }

            slidePart.Slide = slide;

            // Speaker notes
            if (!string.IsNullOrWhiteSpace(spec.Notes))
            {
                var notesPart = slidePart.AddNewPart<NotesSlidePart>();
                notesPart.NotesSlide = new NotesSlide(
                    new CommonSlideData(new ShapeTree(
                        new NonVisualGroupShapeProperties(
                            new NonVisualDrawingProperties { Id = 1, Name = "" },
                            new NonVisualGroupShapeDrawingProperties(),
                            new ApplicationNonVisualDrawingProperties()),
                        new GroupShapeProperties(),
                        new Shape(
                            new NonVisualShapeProperties(
                                new NonVisualDrawingProperties { Id = 2, Name = "Notes" },
                                new NonVisualShapeDrawingProperties(),
                                new ApplicationNonVisualDrawingProperties(
                                    new PlaceholderShape { Type = PlaceholderValues.Body, Index = 1 })),
                            new ShapeProperties(),
                            new TextBody(
                                new D.BodyProperties(),
                                new D.ListStyle(),
                                new D.Paragraph(
                                    MakeRun(spec.Notes, 12, "Arial", null, false, false, false),
                                    new D.EndParagraphRunProperties { Language = "en-US" }))))));
                notesPart.NotesSlide.Save();
            }

            slidePart.Slide.Save();
            pres.SlideIdList!.Append(new SlideId
            {
                Id = slideId++,
                RelationshipId = presPart.GetIdOfPart(slidePart)
            });
        }

        pres.Save();
    }

    void AddText(ShapeTree tree, ElementSpec el, ref uint id)
    {
        var paragraph = new D.Paragraph();
        var pPr = new D.ParagraphProperties();
        if (el.Align != null)
            pPr.Alignment = el.Align.ToLower() switch
            {
                "center" => D.TextAlignmentTypeValues.Center,
                "right" => D.TextAlignmentTypeValues.Right,
                "justify" => D.TextAlignmentTypeValues.Justified,
                _ => null
            };
        paragraph.Append(pPr);

        if (el.Runs != null && el.Runs.Length > 0)
        {
            foreach (var run in el.Runs)
                paragraph.Append(MakeRun(run.Text, run.FontSize ?? el.FontSize, run.FontName ?? el.FontName,
                    run.Color ?? el.Color, run.Bold || el.Bold, run.Italic || el.Italic, run.Underline || el.Underline));
        }
        else if (el.Text != null)
        {
            // Support line breaks
            var lines = el.Text.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                if (i > 0) paragraph.Append(new D.Break());
                paragraph.Append(MakeRun(lines[i], el.FontSize, el.FontName, el.Color, el.Bold, el.Italic, el.Underline));
            }
        }

        paragraph.Append(new D.EndParagraphRunProperties { Language = "en-US", Dirty = false });

        var shape = new Shape(
            new NonVisualShapeProperties(
                new NonVisualDrawingProperties { Id = id++, Name = $"Text {id}" },
                new NonVisualShapeDrawingProperties(new D.ShapeLocks { NoGrouping = true }) { TextBox = true },
                new ApplicationNonVisualDrawingProperties()),
            new ShapeProperties(
                new D.Transform2D(
                    new D.Offset { X = In(el.X), Y = In(el.Y) },
                    new D.Extents { Cx = In(el.W), Cy = In(el.H) })
                { Rotation = el.Rotation != 0 ? (int)(el.Rotation * 60000) : 0 },
                new D.PresetGeometry(new D.AdjustValueList()) { Preset = D.ShapeTypeValues.Rectangle },
                new D.NoFill()),
            new TextBody(
                new D.BodyProperties { Wrap = D.TextWrappingValues.Square, RightToLeftColumns = false },
                new D.ListStyle(),
                paragraph));

        tree.Append(shape);
    }

    void AddList(ShapeTree tree, ElementSpec el, ref uint id)
    {
        var bodyPr = new D.BodyProperties { Wrap = D.TextWrappingValues.Square };
        var parts = new List<OpenXmlElement> { bodyPr, new D.ListStyle() };

        foreach (var item in el.Items ?? [])
        {
            var para = new D.Paragraph();
            var pPr = new D.ParagraphProperties { Level = item.Level };

            if (el.ListType == "ol")
                pPr.Append(new D.AutoNumberedBullet { Type = D.TextAutoNumberSchemeValues.ArabicPeriod });
            else
                pPr.Append(new D.CharacterBullet { Char = item.Level == 0 ? "\u2022" : "\u2013" });

            var fs = item.FontSize ?? el.FontSize;
            pPr.LeftMargin = (int)((fs * (1.6 + item.Level * 1.6)) * EMU_PER_PT);
            pPr.Indent = (int)(-fs * 0.8 * EMU_PER_PT);
            para.Append(pPr);

            para.Append(MakeRun(item.Text, fs, el.FontName, item.Color ?? el.Color, item.Bold, false, false));
            para.Append(new D.EndParagraphRunProperties { Language = "en-US", Dirty = false });
            parts.Add(para);
        }

        var shape = new Shape(
            new NonVisualShapeProperties(
                new NonVisualDrawingProperties { Id = id++, Name = $"List {id}" },
                new NonVisualShapeDrawingProperties(new D.ShapeLocks { NoGrouping = true }) { TextBox = true },
                new ApplicationNonVisualDrawingProperties()),
            new ShapeProperties(
                new D.Transform2D(
                    new D.Offset { X = In(el.X), Y = In(el.Y) },
                    new D.Extents { Cx = In(el.W), Cy = In(el.H) }),
                new D.PresetGeometry(new D.AdjustValueList()) { Preset = D.ShapeTypeValues.Rectangle },
                new D.NoFill()),
            new TextBody(parts.ToArray()));

        tree.Append(shape);
    }

    void AddShape(ShapeTree tree, ElementSpec el, ref uint id)
    {
        var geom = el.BorderRadius > 0
            ? new D.PresetGeometry(new D.AdjustValueList(
                new D.ShapeGuide { Name = "adj", Formula = $"val {(int)(el.BorderRadius / Math.Min(el.W * 72, el.H * 72) * 50000)}" }
              )) { Preset = D.ShapeTypeValues.RoundRectangle }
            : new D.PresetGeometry(new D.AdjustValueList()) { Preset = D.ShapeTypeValues.Rectangle };

        var spPr = new ShapeProperties(
            new D.Transform2D(
                new D.Offset { X = In(el.X), Y = In(el.Y) },
                new D.Extents { Cx = In(el.W), Cy = In(el.H) }),
            geom);

        if (el.Fill != null)
            spPr.Append(new D.SolidFill(new D.RgbColorModelHex { Val = Hex(el.Fill) }));
        else
            spPr.Append(new D.NoFill());

        if (el.BorderColor != null && el.BorderWidth > 0)
            spPr.Append(new D.Outline(
                new D.SolidFill(new D.RgbColorModelHex { Val = Hex(el.BorderColor) })
            ) { Width = (int)(el.BorderWidth * EMU_PER_PT) });

        if (el.ShadowColor != null)
        {
            var dist = Math.Sqrt(el.ShadowX * el.ShadowX + el.ShadowY * el.ShadowY);
            var dir = Math.Atan2(el.ShadowY, el.ShadowX) * 180 / Math.PI * 60000;
            spPr.Append(new D.EffectList(
                new D.OuterShadow(
                    new D.RgbColorModelHex { Val = Hex(el.ShadowColor) }
                ) { BlurRadius = Pt(el.ShadowBlur), Distance = (long)(dist * EMU_PER_PT), Direction = (int)dir }));
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

    static readonly byte[] PngMagic = [0x89, 0x50, 0x4E, 0x47];
    static readonly byte[] JpegMagic = [0xFF, 0xD8, 0xFF];
    static readonly byte[] GifMagic = [0x47, 0x49, 0x46];

    const double MaxImageWidth = 4.5;  // inches — never full-bleed
    const double MaxImageHeight = 3.5; // inches — leave room for title + footer

    void AddImage(ShapeTree tree, ElementSpec el, SlidePart slidePart, ref uint id)
    {
        if (el.Src == null || !File.Exists(el.Src)) return;

        // Validate magic bytes — reject HTML redirects disguised as images
        var header = new byte[4];
        using (var fs = File.OpenRead(el.Src)) fs.Read(header, 0, 4);
        if (!header.AsSpan(0, 4).SequenceEqual(PngMagic) &&
            !header.AsSpan(0, 3).SequenceEqual(JpegMagic) &&
            !header.AsSpan(0, 3).SequenceEqual(GifMagic))
        {
            Console.Error.WriteLine($"  warning: skipping {el.Src} — not a valid image (got HTML or corrupt data)");
            return;
        }

        // Enforce max image size — prevent full-bleed images that crowd out text
        if (el.W > MaxImageWidth || el.H > MaxImageHeight)
        {
            var scale = Math.Min(MaxImageWidth / el.W, MaxImageHeight / el.H);
            Console.Error.WriteLine($"  warning: image {Path.GetFileName(el.Src)} resized from {el.W:F1}x{el.H:F1} to {el.W * scale:F1}x{el.H * scale:F1} (max {MaxImageWidth}x{MaxImageHeight})");
            el = el with { W = el.W * scale, H = el.H * scale };
        }

        var ext = Path.GetExtension(el.Src).ToLower();
        var ct = ext switch { ".png" => "image/png", ".jpg" or ".jpeg" => "image/jpeg", ".gif" => "image/gif", _ => "image/png" };
        var imgPart = slidePart.AddImagePart(ct);
        using (var s = File.OpenRead(el.Src)) imgPart.FeedData(s);

        // Build alt text: combine user alt text + source URL for provenance
        var altParts = new List<string>();
        if (!string.IsNullOrEmpty(el.Alt)) altParts.Add(el.Alt);
        if (!string.IsNullOrEmpty(el.Source)) altParts.Add($"Source: {el.Source}");
        var description = altParts.Count > 0 ? string.Join(" | ", altParts) : null;

        var nvPicPr = new NonVisualPictureProperties(
            new NonVisualDrawingProperties
            {
                Id = id++,
                Name = $"Img {id}",
                Description = description
            },
            new NonVisualPictureDrawingProperties(new D.PictureLocks { NoChangeAspect = true }),
            new ApplicationNonVisualDrawingProperties());

        tree.Append(new Picture(
            nvPicPr,
            new BlipFill(new D.Blip { Embed = slidePart.GetIdOfPart(imgPart) },
                new D.Stretch(new D.FillRectangle())),
            new ShapeProperties(
                new D.Transform2D(
                    new D.Offset { X = In(el.X), Y = In(el.Y) },
                    new D.Extents { Cx = In(el.W), Cy = In(el.H) }),
                new D.PresetGeometry(new D.AdjustValueList()) { Preset = D.ShapeTypeValues.Rectangle })));
    }

    void AddLine(ShapeTree tree, ElementSpec el, ref uint id)
    {
        tree.Append(new ConnectionShape(
            new NonVisualConnectionShapeProperties(
                new NonVisualDrawingProperties { Id = id++, Name = $"Line {id}" },
                new NonVisualConnectorShapeDrawingProperties(),
                new ApplicationNonVisualDrawingProperties()),
            new ShapeProperties(
                new D.Transform2D(
                    new D.Offset { X = In(el.X), Y = In(el.Y) },
                    new D.Extents { Cx = In(el.X2 - el.X), Cy = In(el.Y2 - el.Y) }),
                new D.PresetGeometry(new D.AdjustValueList()) { Preset = D.ShapeTypeValues.Line },
                new D.Outline(
                    new D.SolidFill(new D.RgbColorModelHex { Val = Hex(el.LineColor) })
                ) { Width = (int)(el.LineWidth * EMU_PER_PT) })));
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
