# OOXML Reference for PowerPoint (.pptx)

A .pptx file is a ZIP archive containing XML files following the Office Open XML (OOXML) standard.

## Table of Contents

1. [File Structure](#file-structure)
2. [Slide XML Structure](#slide-xml-structure)
3. [Text and Formatting](#text-and-formatting)
4. [Shapes and Images](#shapes-and-images)
5. [Tables](#tables)
6. [Operations Guide](#operations-guide)
7. [Critical Rules](#critical-rules)

## File Structure

```
[Content_Types].xml          — MIME types for every part
_rels/.rels                  — top-level relationships
ppt/
  presentation.xml           — slide list, sizes, master refs
  _rels/presentation.xml.rels
  slides/
    slide1.xml ... slideN.xml
    _rels/slide1.xml.rels    — per-slide relationships (layout, media)
  slideLayouts/              — layout definitions
  slideMasters/              — master definitions
  theme/theme1.xml           — color schemes, fonts
  media/                     — images, audio, video
  notesSlides/               — speaker notes
  comments/                  — review comments
docProps/
  app.xml                    — slide count, app metadata
  core.xml                   — author, dates
```

## Slide XML Structure

```xml
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>...</p:nvGrpSpPr>
      <p:grpSpPr>...</p:grpSpPr>
      <!-- shapes, images, tables go here -->
    </p:spTree>
  </p:cSld>
</p:sld>
```

## Text and Formatting

### Text box with rich text

```xml
<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="2" name="TextBox 1"/>
    <p:cNvSpPr txBox="1"/>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm>
      <a:off x="914400" y="914400"/>   <!-- position in EMU -->
      <a:ext cx="7315200" cy="1371600"/> <!-- size in EMU -->
    </a:xfrm>
    <a:prstGeom prst="rect"/>
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square" rtlCol="0"/>
    <a:lstStyle/>
    <a:p>
      <a:pPr algn="ctr"/>
      <a:r>
        <a:rPr lang="en-US" sz="3600" b="1" dirty="0">
          <a:solidFill><a:srgbClr val="1A1A2E"/></a:solidFill>
          <a:latin typeface="Arial"/>
        </a:rPr>
        <a:t>Bold Title</a:t>
      </a:r>
    </a:p>
  </p:txBody>
</p:sp>
```

Key attributes on `<a:rPr>`:
- `sz` — font size in hundredths of a point (3600 = 36pt)
- `b="1"` — bold
- `i="1"` — italic
- `u="sng"` — single underline
- `dirty="0"` — always set to prevent "needs update" flag

### Bullet lists

```xml
<a:p>
  <a:pPr lvl="0">
    <a:buChar char="•"/>
  </a:pPr>
  <a:r><a:rPr lang="en-US" sz="1800" dirty="0"/><a:t>First item</a:t></a:r>
</a:p>
<a:p>
  <a:pPr lvl="1">
    <a:buChar char="–"/>
  </a:pPr>
  <a:r><a:rPr lang="en-US" sz="1600" dirty="0"/><a:t>Sub-item</a:t></a:r>
</a:p>
```

Numbered lists: `<a:buAutoNum type="arabicPeriod"/>` instead of `<a:buChar>`.

### Paragraph spacing

```xml
<a:pPr>
  <a:spcBef><a:spcPts val="600"/></a:spcBef>  <!-- 6pt before -->
  <a:spcAft><a:spcPts val="300"/></a:spcAft>   <!-- 3pt after -->
  <a:lnSpc><a:spcPts val="2400"/></a:lnSpc>    <!-- 24pt line spacing -->
</a:pPr>
```

## Shapes and Images

### Shape with fill and border

```xml
<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="3" name="Rectangle 1"/>
    <p:cNvSpPr/>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm>
      <a:off x="457200" y="1828800"/>
      <a:ext cx="8229600" cy="2743200"/>
    </a:xfrm>
    <a:prstGeom prst="roundRect">
      <a:avLst><a:gd name="adj" fmla="val 16667"/></a:avLst>
    </a:prstGeom>
    <a:solidFill><a:srgbClr val="006D77"/></a:solidFill>
    <a:ln w="25400">
      <a:solidFill><a:srgbClr val="83C5BE"/></a:solidFill>
    </a:ln>
  </p:spPr>
</p:sp>
```

Preset geometry values: `rect`, `roundRect`, `ellipse`, `triangle`, `diamond`, `hexagon`, `star5`, `rightArrow`, `line`.

### Image

```xml
<p:pic>
  <p:nvPicPr>
    <p:cNvPr id="4" name="Picture 1"/>
    <p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>
    <p:nvPr/>
  </p:nvPicPr>
  <p:blipFill>
    <a:blip r:embed="rId2"/>
    <a:stretch><a:fillRect/></a:stretch>
  </p:blipFill>
  <p:spPr>
    <a:xfrm>
      <a:off x="914400" y="2286000"/>
      <a:ext cx="3657600" cy="2743200"/>
    </a:xfrm>
    <a:prstGeom prst="rect"/>
  </p:spPr>
</p:pic>
```

The `r:embed="rId2"` references a relationship in `_rels/slideN.xml.rels` pointing to `../media/imageN.png`.

## Tables

```xml
<p:graphicFrame>
  <p:nvGraphicFramePr>
    <p:cNvPr id="5" name="Table 1"/>
    <p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr>
    <p:nvPr/>
  </p:nvGraphicFramePr>
  <p:xfrm>
    <a:off x="457200" y="1600200"/>
    <a:ext cx="8229600" cy="2400000"/>
  </p:xfrm>
  <a:graphic>
    <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">
      <a:tbl>
        <a:tblGrid>
          <a:gridCol w="2743200"/><a:gridCol w="2743200"/><a:gridCol w="2743200"/>
        </a:tblGrid>
        <a:tr h="600000">
          <a:tc>
            <a:txBody>
              <a:bodyPr/><a:lstStyle/>
              <a:p><a:r><a:rPr lang="en-US" sz="1400" b="1" dirty="0"/><a:t>Header</a:t></a:r></a:p>
            </a:txBody>
            <a:tcPr>
              <a:solidFill><a:srgbClr val="1D3557"/></a:solidFill>
            </a:tcPr>
          </a:tc>
          <!-- more cells -->
        </a:tr>
      </a:tbl>
    </a:graphicData>
  </a:graphic>
</p:graphicFrame>
```

## Operations Guide

### Add a slide

1. Create `ppt/slides/slideN.xml` with slide content
2. Add to `[Content_Types].xml`: `<Override PartName="/ppt/slides/slideN.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`
3. Add relationship in `ppt/_rels/presentation.xml.rels`: `<Relationship Id="rIdN" Type="...slide" Target="slides/slideN.xml"/>`
4. Add to `ppt/presentation.xml` `<p:sldIdLst>`: `<p:sldId id="UNIQUE" r:id="rIdN"/>`
5. Create `ppt/slides/_rels/slideN.xml.rels` linking to layout
6. Update `docProps/app.xml` slide count

### Delete a slide

Reverse of above. Do NOT renumber remaining slides.

### Reorder slides

Only reorder `<p:sldId>` elements within `<p:sldIdLst>` in `ppt/presentation.xml`.

## Critical Rules

1. **Element order in `<p:txBody>`**: `<a:bodyPr>` → `<a:lstStyle>` → `<a:p>` (always this order)
2. **`dirty="0"`** on every `<a:rPr>` and `<a:endParaRPr>` — prevents "needs update" rendering
3. **`xml:space="preserve"`** on `<a:t>` with leading/trailing whitespace
4. **Unicode escaping**: `"` → `&#8220;`, `"` → `&#8221;`, `'` → `&#8217;`, `—` → `&#8212;`
5. **No `#` prefix** on hex colors (use `1A1A2E` not `#1A1A2E`)
6. **Coordinate system**: all positions in EMU (English Metric Units). 1 inch = 914400 EMU, 1 pt = 12700 EMU, 1 px = 9525 EMU
7. **Clean up**: remove unused relationships, fix Content_Types, remove broken refs before saving
