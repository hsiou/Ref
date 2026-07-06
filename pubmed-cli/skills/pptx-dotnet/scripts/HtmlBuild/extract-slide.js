// DOM extraction script — runs inside Playwright page.evaluate()
// Extracts all visual elements from an HTML slide with positions and styles.
// Returns { background, elements, placeholders, errors }
(() => {
  const PX_PER_IN = 96;
  const PT_PER_PX = 0.75;
  const SINGLE_WEIGHT_FONTS = ['impact'];

  const shouldSkipBold = (fontFamily) => {
    if (!fontFamily) return false;
    return SINGLE_WEIGHT_FONTS.includes(fontFamily.toLowerCase().replace(/['"]/g, '').split(',')[0].trim());
  };

  const pxToInch = (px) => px / PX_PER_IN;
  const pxToPoints = (pxStr) => parseFloat(pxStr) * PT_PER_PX;
  const rgbToHex = (rgbStr) => {
    if (rgbStr === 'rgba(0, 0, 0, 0)' || rgbStr === 'transparent') return null;
    const match = rgbStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (!match) return null;
    return match.slice(1).map(n => parseInt(n).toString(16).padStart(2, '0')).join('').toUpperCase();
  };

  const extractAlpha = (rgbStr) => {
    const match = rgbStr.match(/rgba\(\d+,\s*\d+,\s*\d+,\s*([\d.]+)\)/);
    if (!match) return null;
    const alpha = parseFloat(match[1]);
    return Math.round((1 - alpha) * 100);
  };

  const applyTextTransform = (text, tt) => {
    if (tt === 'uppercase') return text.toUpperCase();
    if (tt === 'lowercase') return text.toLowerCase();
    if (tt === 'capitalize') return text.replace(/\b\w/g, c => c.toUpperCase());
    return text;
  };

  const getRotation = (transform, writingMode) => {
    let angle = 0;
    if (writingMode === 'vertical-rl') angle = 90;
    else if (writingMode === 'vertical-lr') angle = 270;
    if (transform && transform !== 'none') {
      const rotateMatch = transform.match(/rotate\((-?\d+(?:\.\d+)?)deg\)/);
      if (rotateMatch) angle += parseFloat(rotateMatch[1]);
      else {
        const matrixMatch = transform.match(/matrix\(([^)]+)\)/);
        if (matrixMatch) {
          const v = matrixMatch[1].split(',').map(parseFloat);
          angle += Math.round(Math.atan2(v[1], v[0]) * 180 / Math.PI);
        }
      }
    }
    angle = angle % 360;
    if (angle < 0) angle += 360;
    return angle === 0 ? null : angle;
  };

  const getPositionAndSize = (el, rect, rotation) => {
    if (rotation === null) return { x: rect.left, y: rect.top, w: rect.width, h: rect.height };
    const isVertical = rotation === 90 || rotation === 270;
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    if (isVertical) return { x: cx - rect.height / 2, y: cy - rect.width / 2, w: rect.height, h: rect.width };
    return { x: cx - el.offsetWidth / 2, y: cy - el.offsetHeight / 2, w: el.offsetWidth, h: el.offsetHeight };
  };

  const parseBoxShadow = (boxShadow) => {
    if (!boxShadow || boxShadow === 'none') return null;
    if (boxShadow.includes('inset')) return null;
    const colorMatch = boxShadow.match(/rgba?\([^)]+\)/);
    const parts = boxShadow.match(/([-\d.]+)(px|pt)/g);
    if (!parts || parts.length < 2) return null;
    const offsetX = parseFloat(parts[0]);
    const offsetY = parseFloat(parts[1]);
    const blur = parts.length > 2 ? parseFloat(parts[2]) : 0;
    let angle = 0;
    if (offsetX !== 0 || offsetY !== 0) {
      angle = Math.atan2(offsetY, offsetX) * (180 / Math.PI);
      if (angle < 0) angle += 360;
    }
    const offset = Math.sqrt(offsetX * offsetX + offsetY * offsetY) * PT_PER_PX;
    let opacity = 0.5;
    if (colorMatch) {
      const om = colorMatch[0].match(/[\d.]+\)$/);
      if (om) opacity = parseFloat(om[0].replace(')', ''));
    }
    return { type: 'outer', angle: Math.round(angle), blur: blur * 0.75, color: colorMatch ? rgbToHex(colorMatch[0]) || '000000' : '000000', offset, opacity };
  };

  const errors = [];

  const parseInlineFormatting = (element, baseOptions, runs, baseTransform) => {
    if (!runs) runs = [];
    if (!baseTransform) baseTransform = (x) => x;
    let prevNodeIsText = false;
    element.childNodes.forEach((node) => {
      let textTransform = baseTransform;
      const isText = node.nodeType === Node.TEXT_NODE || node.tagName === 'BR';
      if (isText) {
        const text = node.tagName === 'BR' ? '\n' : textTransform(node.textContent.replace(/\s+/g, ' '));
        const prevRun = runs[runs.length - 1];
        if (prevNodeIsText && prevRun) prevRun.text += text;
        else runs.push({ text, options: { ...baseOptions } });
      } else if (node.nodeType === Node.ELEMENT_NODE && node.textContent.trim()) {
        const tag = node.tagName;
        if (tag === 'SPAN' || tag === 'B' || tag === 'STRONG' || tag === 'I' || tag === 'EM' || tag === 'U') {
          const opts = { ...baseOptions };
          const cs = window.getComputedStyle(node);
          const isBold = cs.fontWeight === 'bold' || parseInt(cs.fontWeight) >= 600;
          if (isBold && !shouldSkipBold(cs.fontFamily)) opts.bold = true;
          if (cs.fontStyle === 'italic') opts.italic = true;
          if (cs.textDecoration && cs.textDecoration.includes('underline')) opts.underline = true;
          if (cs.color && cs.color !== 'rgb(0, 0, 0)') {
            opts.color = rgbToHex(cs.color);
            const t = extractAlpha(cs.color);
            if (t !== null) opts.transparency = t;
          }
          if (cs.fontSize) opts.fontSize = pxToPoints(cs.fontSize);
          if (cs.textTransform && cs.textTransform !== 'none') {
            const ts = cs.textTransform;
            textTransform = (t) => applyTextTransform(t, ts);
          }
          parseInlineFormatting(node, opts, runs, textTransform);
        }
      }
      prevNodeIsText = isText;
    });
    if (runs.length > 0) {
      runs[0].text = runs[0].text.replace(/^\s+/, '');
      runs[runs.length - 1].text = runs[runs.length - 1].text.replace(/\s+$/, '');
    }
    return runs.filter(r => r.text.length > 0);
  };

  // Extract background
  const body = document.body;
  const bodyStyle = window.getComputedStyle(body);
  const bgImage = bodyStyle.backgroundImage;
  const bgColor = bodyStyle.backgroundColor;

  if (bgImage && (bgImage.includes('linear-gradient') || bgImage.includes('radial-gradient'))) {
    errors.push('CSS gradients are not supported in PowerPoint. Rasterize as a PNG image first.');
  }

  let background;
  if (bgImage && bgImage !== 'none') {
    const urlMatch = bgImage.match(/url\(["']?([^"')]+)["']?\)/);
    background = urlMatch ? { type: 'image', path: urlMatch[1] } : { type: 'color', value: rgbToHex(bgColor) || 'FFFFFF' };
  } else {
    background = { type: 'color', value: rgbToHex(bgColor) || 'FFFFFF' };
  }

  // Check overflow
  const bodyWidth = parseFloat(bodyStyle.width);
  const bodyHeight = parseFloat(bodyStyle.height);
  const wOverflow = Math.max(0, body.scrollWidth - bodyWidth - 1) * PT_PER_PX;
  const hOverflow = Math.max(0, body.scrollHeight - bodyHeight - 1) * PT_PER_PX;
  if (wOverflow > 0 || hOverflow > 0) {
    const dirs = [];
    if (wOverflow > 0) dirs.push(`${wOverflow.toFixed(1)}pt horizontally`);
    if (hOverflow > 0) dirs.push(`${hOverflow.toFixed(1)}pt vertically`);
    errors.push(`Content overflows slide by ${dirs.join(' and ')}`);
  }

  const elements = [];
  const placeholders = [];
  const textTags = ['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'UL', 'OL', 'LI'];
  const processed = new Set();

  document.querySelectorAll('*').forEach((el) => {
    if (processed.has(el)) return;

    // Validate text elements don't have backgrounds/borders/shadows
    if (textTags.includes(el.tagName)) {
      const cs = window.getComputedStyle(el);
      const hasBg = cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)';
      const hasBorder = ['borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth']
        .some(p => parseFloat(cs[p]) > 0);
      const hasShadow = cs.boxShadow && cs.boxShadow !== 'none';
      if (hasBg || hasBorder || hasShadow) {
        errors.push(`<${el.tagName.toLowerCase()}> has ${hasBg ? 'background' : hasBorder ? 'border' : 'shadow'}. Only <div> supports these.`);
        return;
      }
    }

    // Placeholders
    if (el.className && typeof el.className === 'string' && el.className.includes('placeholder')) {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        placeholders.push({ id: el.id || `placeholder-${placeholders.length}`, x: pxToInch(rect.left), y: pxToInch(rect.top), w: pxToInch(rect.width), h: pxToInch(rect.height) });
      }
      processed.add(el);
      return;
    }

    // Images
    if (el.tagName === 'IMG') {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        elements.push({ type: 'image', src: el.src, position: { x: pxToInch(rect.left), y: pxToInch(rect.top), w: pxToInch(rect.width), h: pxToInch(rect.height) } });
        processed.add(el);
      }
      return;
    }

    // DIVs with backgrounds/borders → shapes
    if (el.tagName === 'DIV') {
      const cs = window.getComputedStyle(el);
      const hasBg = cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)';

      // Validate unwrapped text
      for (const node of el.childNodes) {
        if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
          errors.push(`DIV contains unwrapped text "${node.textContent.trim().substring(0, 50)}". Wrap in <p> or heading tags.`);
        }
      }

      const borders = ['borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth']
        .map(p => parseFloat(cs[p]) || 0);
      const hasBorder = borders.some(b => b > 0);
      const hasUniformBorder = hasBorder && borders.every(b => b === borders[0]);

      if (hasBorder && !hasUniformBorder) {
        const rect = el.getBoundingClientRect();
        const x = pxToInch(rect.left), y = pxToInch(rect.top), w = pxToInch(rect.width), h = pxToInch(rect.height);
        const sides = [
          { idx: 0, prop: 'borderTopColor', x1: x, y1: y, x2: x + w, y2: y },
          { idx: 1, prop: 'borderRightColor', x1: x + w, y1: y, x2: x + w, y2: y + h },
          { idx: 2, prop: 'borderBottomColor', x1: x, y1: y + h, x2: x + w, y2: y + h },
          { idx: 3, prop: 'borderLeftColor', x1: x, y1: y, x2: x, y2: y + h }
        ];
        sides.forEach(s => {
          if (borders[s.idx] > 0) {
            const widthPt = borders[s.idx] * PT_PER_PX;
            elements.push({ type: 'line', x1: s.x1, y1: s.y1, x2: s.x2, y2: s.y2, width: widthPt, color: rgbToHex(cs[s.prop]) || '000000' });
          }
        });
      }

      if (hasBg || hasUniformBorder) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          const shadow = parseBoxShadow(cs.boxShadow);
          const radiusVal = parseFloat(cs.borderRadius) || 0;
          let rectRadius = 0;
          if (radiusVal > 0) {
            if (cs.borderRadius.includes('%')) {
              rectRadius = radiusVal >= 50 ? 1 : (radiusVal / 100) * pxToInch(Math.min(rect.width, rect.height));
            } else if (cs.borderRadius.includes('pt')) {
              rectRadius = radiusVal / 72;
            } else {
              rectRadius = radiusVal / PX_PER_IN;
            }
          }
          elements.push({
            type: 'shape',
            position: { x: pxToInch(rect.left), y: pxToInch(rect.top), w: pxToInch(rect.width), h: pxToInch(rect.height) },
            shape: {
              fill: hasBg ? rgbToHex(cs.backgroundColor) : null,
              transparency: hasBg ? extractAlpha(cs.backgroundColor) : null,
              line: hasUniformBorder ? { color: rgbToHex(cs.borderColor) || '000000', width: pxToPoints(cs.borderWidth) } : null,
              rectRadius,
              shadow
            }
          });
          processed.add(el);
          return;
        }
      }

      if (!hasBg && !hasBorder) return; // Plain container div, skip
      processed.add(el);
      return;
    }

    // Lists
    if (el.tagName === 'UL' || el.tagName === 'OL') {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      const liElements = Array.from(el.querySelectorAll('li'));
      const items = [];
      const ulCs = window.getComputedStyle(el);
      const ulPadLeft = pxToPoints(ulCs.paddingLeft);
      const marginLeft = ulPadLeft * 0.5;
      const textIndent = ulPadLeft * 0.5;

      liElements.forEach((li, idx) => {
        const isLast = idx === liElements.length - 1;
        const runs = parseInlineFormatting(li, { breakLine: false });
        if (runs.length > 0) {
          runs[0].text = runs[0].text.replace(/^[•\-\*▪▸]\s*/, '');
          runs[0].options.bullet = true;
          runs[0].options.indentLevel = 0;
        }
        if (runs.length > 0 && !isLast) runs[runs.length - 1].options.breakLine = true;
        items.push(...runs);
      });

      const liCs = window.getComputedStyle(liElements[0] || el);
      elements.push({
        type: 'list',
        items,
        position: { x: pxToInch(rect.left), y: pxToInch(rect.top), w: pxToInch(rect.width), h: pxToInch(rect.height) },
        style: {
          fontSize: pxToPoints(liCs.fontSize),
          fontFace: liCs.fontFamily.split(',')[0].replace(/['"]/g, '').trim(),
          color: rgbToHex(liCs.color) || '000000',
          align: liCs.textAlign === 'start' ? 'left' : liCs.textAlign,
          lineSpacing: liCs.lineHeight && liCs.lineHeight !== 'normal' ? pxToPoints(liCs.lineHeight) : null,
          paraSpaceBefore: 0,
          paraSpaceAfter: pxToPoints(liCs.marginBottom),
          margin: [marginLeft, 0, 0, 0]
        }
      });
      liElements.forEach(li => processed.add(li));
      processed.add(el);
      return;
    }

    // Text elements
    if (!textTags.includes(el.tagName)) return;
    const rect = el.getBoundingClientRect();
    const text = el.textContent.trim();
    if (rect.width === 0 || rect.height === 0 || !text) return;

    if (el.tagName !== 'LI' && /^[•\-\*▪▸○●◆◇■□]\s/.test(text.trimStart())) {
      errors.push(`<${el.tagName.toLowerCase()}> starts with bullet symbol. Use <ul>/<ol> instead.`);
      return;
    }

    const cs = window.getComputedStyle(el);
    const rotation = getRotation(cs.transform, cs.writingMode);
    const pos = getPositionAndSize(el, rect, rotation);

    const baseStyle = {
      fontSize: pxToPoints(cs.fontSize),
      fontFace: cs.fontFamily.split(',')[0].replace(/['"]/g, '').trim(),
      color: rgbToHex(cs.color) || '000000',
      align: cs.textAlign === 'start' ? 'left' : cs.textAlign,
      lineSpacing: pxToPoints(cs.lineHeight),
      paraSpaceBefore: pxToPoints(cs.marginTop),
      paraSpaceAfter: pxToPoints(cs.marginBottom),
      margin: [pxToPoints(cs.paddingLeft), pxToPoints(cs.paddingRight), pxToPoints(cs.paddingBottom), pxToPoints(cs.paddingTop)]
    };
    const transparency = extractAlpha(cs.color);
    if (transparency !== null) baseStyle.transparency = transparency;
    if (rotation !== null) baseStyle.rotate = rotation;

    const hasFormatting = el.querySelector('b, i, u, strong, em, span, br');
    if (hasFormatting) {
      const runs = parseInlineFormatting(el, {}, [], (str) => applyTextTransform(str, cs.textTransform));
      elements.push({
        type: el.tagName.toLowerCase(),
        text: runs,
        position: { x: pxToInch(pos.x), y: pxToInch(pos.y), w: pxToInch(pos.w), h: pxToInch(pos.h) },
        style: baseStyle
      });
    } else {
      const isBold = cs.fontWeight === 'bold' || parseInt(cs.fontWeight) >= 600;
      elements.push({
        type: el.tagName.toLowerCase(),
        text: applyTextTransform(text, cs.textTransform),
        position: { x: pxToInch(pos.x), y: pxToInch(pos.y), w: pxToInch(pos.w), h: pxToInch(pos.h) },
        style: { ...baseStyle, bold: isBold && !shouldSkipBold(cs.fontFamily), italic: cs.fontStyle === 'italic', underline: cs.textDecoration.includes('underline') }
      });
    }
    processed.add(el);
  });

  return { background, elements, placeholders, errors };
})()
