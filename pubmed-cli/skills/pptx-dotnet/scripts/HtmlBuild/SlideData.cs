using System.Text.Json;
using System.Text.Json.Serialization;

namespace HtmlBuild;

public record SlideData(
    [property: JsonPropertyName("background")] BackgroundData? Background,
    [property: JsonPropertyName("elements")] ElementData[] Elements,
    [property: JsonPropertyName("placeholders")] PlaceholderData[] Placeholders,
    [property: JsonPropertyName("errors")] string[] Errors);

public record BackgroundData(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("value")] string? Value,
    [property: JsonPropertyName("path")] string? Path);

public record ElementData(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("position")] PositionData? Position,
    [property: JsonPropertyName("style")] StyleData? Style,
    [property: JsonPropertyName("text"), JsonConverter(typeof(TextConverter))] object? Text,
    [property: JsonPropertyName("items")] TextRunData[]? Items,
    [property: JsonPropertyName("shape")] ShapeStyleData? Shape,
    [property: JsonPropertyName("src")] string? Src,
    // Line-specific
    [property: JsonPropertyName("x1")] double? X1,
    [property: JsonPropertyName("y1")] double? Y1,
    [property: JsonPropertyName("x2")] double? X2,
    [property: JsonPropertyName("y2")] double? Y2,
    [property: JsonPropertyName("width")] double? LineWidth,
    [property: JsonPropertyName("color")] string? LineColor);

public record PositionData(
    [property: JsonPropertyName("x")] double X,
    [property: JsonPropertyName("y")] double Y,
    [property: JsonPropertyName("w")] double W,
    [property: JsonPropertyName("h")] double H);

public record StyleData(
    [property: JsonPropertyName("fontSize")] double FontSize,
    [property: JsonPropertyName("fontFace")] string? FontFace,
    [property: JsonPropertyName("color")] string? Color,
    [property: JsonPropertyName("align")] string? Align,
    [property: JsonPropertyName("bold")] bool? Bold,
    [property: JsonPropertyName("italic")] bool? Italic,
    [property: JsonPropertyName("underline")] bool? Underline,
    [property: JsonPropertyName("lineSpacing")] double? LineSpacing,
    [property: JsonPropertyName("paraSpaceBefore")] double? ParaSpaceBefore,
    [property: JsonPropertyName("paraSpaceAfter")] double? ParaSpaceAfter,
    [property: JsonPropertyName("rotate")] double? Rotate,
    [property: JsonPropertyName("transparency")] int? Transparency,
    [property: JsonPropertyName("margin")] double[]? Margin);

public record TextRunData(
    [property: JsonPropertyName("text")] string Text,
    [property: JsonPropertyName("options")] TextRunOptions? Options);

public record TextRunOptions(
    [property: JsonPropertyName("bold")] bool? Bold,
    [property: JsonPropertyName("italic")] bool? Italic,
    [property: JsonPropertyName("underline")] bool? Underline,
    [property: JsonPropertyName("color")] string? Color,
    [property: JsonPropertyName("fontSize")] double? FontSize,
    [property: JsonPropertyName("transparency")] int? Transparency,
    [property: JsonPropertyName("bullet")] bool? Bullet,
    [property: JsonPropertyName("indentLevel")] int? IndentLevel,
    [property: JsonPropertyName("breakLine")] bool? BreakLine);

public record ShapeStyleData(
    [property: JsonPropertyName("fill")] string? Fill,
    [property: JsonPropertyName("line")] LineStyleData? Line,
    [property: JsonPropertyName("rectRadius")] double RectRadius,
    [property: JsonPropertyName("shadow")] ShadowData? Shadow,
    [property: JsonPropertyName("transparency")] int? Transparency);

public record LineStyleData(
    [property: JsonPropertyName("color")] string Color,
    [property: JsonPropertyName("width")] double Width);

public record ShadowData(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("angle")] int Angle,
    [property: JsonPropertyName("blur")] double Blur,
    [property: JsonPropertyName("color")] string Color,
    [property: JsonPropertyName("offset")] double Offset,
    [property: JsonPropertyName("opacity")] double Opacity);

public record PlaceholderData(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("x")] double X,
    [property: JsonPropertyName("y")] double Y,
    [property: JsonPropertyName("w")] double W,
    [property: JsonPropertyName("h")] double H);

/// <summary>
/// The text field can be either a plain string or an array of TextRunData (rich text).
/// This converter handles both cases.
/// </summary>
public class TextConverter : JsonConverter<object?>
{
    public override object? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.Null) return null;
        if (reader.TokenType == JsonTokenType.String) return reader.GetString();
        if (reader.TokenType == JsonTokenType.StartArray)
        {
            var runs = new List<TextRunData>();
            while (reader.Read())
            {
                if (reader.TokenType == JsonTokenType.EndArray) break;
                var run = JsonSerializer.Deserialize<TextRunData>(ref reader, options);
                if (run != null) runs.Add(run);
            }
            return runs.ToArray();
        }
        reader.Skip();
        return null;
    }

    public override void Write(Utf8JsonWriter writer, object? value, JsonSerializerOptions options)
    {
        JsonSerializer.Serialize(writer, value, options);
    }
}
