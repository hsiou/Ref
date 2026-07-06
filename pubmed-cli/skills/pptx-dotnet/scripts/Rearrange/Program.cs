using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Presentation;
using D = DocumentFormat.OpenXml.Drawing;

if (args.Length < 3)
{
    Console.Error.WriteLine("Usage: dotnet run -- template.pptx output.pptx 0,3,3,7,12");
    return 1;
}

var templatePath = args[0];
var outputPath = args[1];
var indexList = args[2].Split(',').Select(s => int.Parse(s.Trim())).ToList();

if (!File.Exists(templatePath)) { Console.Error.WriteLine($"Not found: {templatePath}"); return 1; }

File.Copy(templatePath, outputPath, true);

using var doc = PresentationDocument.Open(outputPath, true);
var presentation = doc.PresentationPart!.Presentation;
var slideIdList = presentation.SlideIdList!;
var originalSlides = slideIdList.Elements<SlideId>().ToList();

// Validate indices
foreach (var idx in indexList)
{
    if (idx < 0 || idx >= originalSlides.Count)
    {
        Console.Error.WriteLine($"Slide index {idx} out of range (have {originalSlides.Count} slides, 0-based)");
        return 1;
    }
}

// Find duplicates (indices appearing more than once)
var duplicateIndices = indexList.GroupBy(i => i).Where(g => g.Count() > 1).Select(g => g.Key).ToHashSet();

// Duplicate slides that need copies
var duplicatedParts = new Dictionary<int, List<SlidePart>>();
foreach (var idx in duplicateIndices)
{
    var count = indexList.Count(i => i == idx) - 1; // minus the original
    var sourcePart = (SlidePart)doc.PresentationPart!.GetPartById(originalSlides[idx].RelationshipId!);
    var copies = new List<SlidePart>();

    for (int c = 0; c < count; c++)
    {
        var newPart = doc.PresentationPart!.AddNewPart<SlidePart>();
        // Copy slide XML
        using (var sourceStream = sourcePart.GetStream(FileMode.Open))
        {
            newPart.FeedData(sourceStream);
        }

        // Copy relationships (layout, images, etc.)
        foreach (var rel in sourcePart.Parts)
        {
            if (rel.OpenXmlPart is SlideLayoutPart layoutPart)
            {
                newPart.AddPart(layoutPart);
            }
            else if (rel.OpenXmlPart is ImagePart imgPart)
            {
                var newImg = newPart.AddImagePart(imgPart.ContentType);
                using var imgStream = imgPart.GetStream(FileMode.Open);
                newImg.FeedData(imgStream);
                // Update blip references
                UpdateBlipReferences(newPart, rel.RelationshipId,
                    newPart.GetIdOfPart(newImg));
            }
        }

        // Copy external relationships
        foreach (var extRel in sourcePart.ExternalRelationships)
        {
            newPart.AddExternalRelationship(extRel.RelationshipType, extRel.Uri, extRel.Id);
        }

        // Add to slide list
        uint newId = (uint)(originalSlides.Max(s => s.Id!.Value) + copies.Count + c + 1);
        slideIdList.Append(new SlideId
        {
            Id = newId,
            RelationshipId = doc.PresentationPart!.GetIdOfPart(newPart)
        });

        copies.Add(newPart);
    }

    duplicatedParts[idx] = copies;
}

// Rebuild the target slide list
var targetSlideParts = new List<(uint id, string relId)>();
var dupCounters = duplicateIndices.ToDictionary(i => i, _ => 0);
uint nextId = 256;

foreach (var idx in indexList)
{
    if (duplicateIndices.Contains(idx) && dupCounters[idx] > 0)
    {
        // Use a duplicated copy
        var copyIdx = dupCounters[idx] - 1;
        var copyPart = duplicatedParts[idx][copyIdx];
        targetSlideParts.Add((nextId++, doc.PresentationPart!.GetIdOfPart(copyPart)));
    }
    else
    {
        // Use the original
        targetSlideParts.Add((nextId++, originalSlides[idx].RelationshipId!.Value!));
    }
    if (duplicateIndices.Contains(idx)) dupCounters[idx]++;
}

// Collect all target relIds
var targetRelIds = targetSlideParts.Select(t => t.relId).ToHashSet();

// Remove slides not in target set
var currentSlides = slideIdList.Elements<SlideId>().ToList();
foreach (var slide in currentSlides)
{
    if (!targetRelIds.Contains(slide.RelationshipId!.Value!))
    {
        slide.Remove();
        try { doc.PresentationPart!.DeletePart(slide.RelationshipId!); } catch { }
    }
}

// Clear and rebuild in target order
slideIdList.RemoveAllChildren<SlideId>();
foreach (var (id, relId) in targetSlideParts)
{
    slideIdList.Append(new SlideId { Id = id, RelationshipId = relId });
}

presentation.Save();
doc.Dispose();

Console.WriteLine($"Rearranged {indexList.Count} slides → {outputPath}");
Console.WriteLine($"  Sequence: [{string.Join(", ", indexList)}]");
return 0;

void UpdateBlipReferences(SlidePart part, string oldRelId, string newRelId)
{
    if (oldRelId == newRelId) return;
    var slide = part.Slide;
    foreach (var blip in slide.Descendants<D.Blip>())
    {
        if (blip.Embed?.Value == oldRelId)
            blip.Embed = newRelId;
    }
}
