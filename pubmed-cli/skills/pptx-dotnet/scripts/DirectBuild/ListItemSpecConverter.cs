using System.Text.Json;
using System.Text.Json.Serialization;

namespace DirectBuild;

/// <summary>
/// Accepts both plain strings and full ListItemSpec objects for list items.
/// LLMs commonly produce ["text"] instead of [{"Text": "text"}] — this
/// converter handles both without requiring a retry round.
/// </summary>
public sealed class ListItemSpecConverter : JsonConverter<ListItemSpec>
{
    public override ListItemSpec Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.String)
        {
            return new ListItemSpec { Text = reader.GetString() ?? "" };
        }

        if (reader.TokenType == JsonTokenType.StartObject)
        {
            using var doc = JsonDocument.ParseValue(ref reader);
            var root = doc.RootElement;

            return new ListItemSpec
            {
                Text = root.TryGetProperty("Text", out var t) ? t.GetString() ?? ""
                     : root.TryGetProperty("text", out var t2) ? t2.GetString() ?? "" : "",
                Level = root.TryGetProperty("Level", out var l) ? l.GetInt32()
                      : root.TryGetProperty("level", out var l2) ? l2.GetInt32() : 0,
                Bold = root.TryGetProperty("Bold", out var b) ? b.GetBoolean()
                     : root.TryGetProperty("bold", out var b2) ? b2.GetBoolean() : false,
                Color = root.TryGetProperty("Color", out var c) ? c.GetString()
                      : root.TryGetProperty("color", out var c2) ? c2.GetString() : null,
                FontSize = root.TryGetProperty("FontSize", out var fs) ? fs.GetDouble()
                         : root.TryGetProperty("fontSize", out var fs2) ? fs2.GetDouble() : null
            };
        }

        throw new JsonException($"Expected string or object for ListItemSpec, got {reader.TokenType}");
    }

    public override void Write(Utf8JsonWriter writer, ListItemSpec value, JsonSerializerOptions options)
    {
        JsonSerializer.Serialize(writer, value, options);
    }
}
