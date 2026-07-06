namespace DirectBuild;

/// <summary>JSON spec for a slide deck. Array of SlideSpec = one presentation.</summary>
public record SlideSpec
{
    public string? Background { get; init; }       // hex color e.g. "003D44"
    public string? BackgroundImage { get; init; }   // file path
    public ElementSpec[]? Elements { get; init; }
    public string? Notes { get; init; }            // speaker notes (plain text)
}

/// <summary>One visual element on a slide. All positions in inches.</summary>
public record ElementSpec
{
    // Common
    public string Type { get; init; } = "text";    // text, list, shape, image, line
    public double X { get; init; }                  // left edge (inches)
    public double Y { get; init; }                  // top edge (inches)
    public double W { get; init; }                  // width (inches)
    public double H { get; init; }                  // height (inches)

    // Text
    public string? Text { get; init; }
    public double FontSize { get; init; } = 18;     // pt
    public string? FontName { get; init; }           // default Arial
    public string? Color { get; init; }              // hex without #
    public bool Bold { get; init; }
    public bool Italic { get; init; }
    public bool Underline { get; init; }
    public string? Align { get; init; }              // left, center, right, justify
    public double Rotation { get; init; }
    public TextRunSpec[]? Runs { get; init; }        // rich text (overrides Text)

    // List
    public string? ListType { get; init; }           // ul or ol
    public ListItemSpec[]? Items { get; init; }

    // Shape
    public string? Fill { get; init; }               // hex
    public string? BorderColor { get; init; }
    public double BorderWidth { get; init; }
    public double BorderRadius { get; init; }        // pt
    public string? ShadowColor { get; init; }
    public double ShadowBlur { get; init; }
    public double ShadowX { get; init; }
    public double ShadowY { get; init; }

    // Image
    public string? Src { get; init; }
    public string? Alt { get; init; }              // alt text for accessibility
    public string? Source { get; init; }            // source URL (embedded in alt text as provenance)

    // Line
    public double X2 { get; init; }
    public double Y2 { get; init; }
    public string? LineColor { get; init; }
    public double LineWidth { get; init; } = 1;
}

public record TextRunSpec
{
    public string Text { get; init; } = "";
    public bool Bold { get; init; }
    public bool Italic { get; init; }
    public bool Underline { get; init; }
    public string? Color { get; init; }
    public double? FontSize { get; init; }
    public string? FontName { get; init; }
}

[System.Text.Json.Serialization.JsonConverter(typeof(ListItemSpecConverter))]
public record ListItemSpec
{
    public string Text { get; init; } = "";
    public int Level { get; init; }
    public bool Bold { get; init; }
    public string? Color { get; init; }
    public double? FontSize { get; init; }
}
