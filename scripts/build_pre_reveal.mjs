import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, "..");

const sourcePath = path.join(rootDir, "docs", "新版pre完整报告.md");
const vendorRoot = path.join(rootDir, "slides", "_vendor", "reveal.js-6.0.1", "package");
const vendorDist = path.join(vendorRoot, "dist");
const vendorCss = path.join(vendorRoot, "css");
const outputDir = path.join(rootDir, "slides", "新版pre完整报告-reveal");
const outputRevealDir = path.join(outputDir, "reveal");
const outputCssDir = path.join(outputDir, "reveal-css");

const CONTENT_MAX_UNITS = 15.4;
const LONG_TABLE_ROWS = 8;
const CODE_LINES_PER_SLIDE = 20;
const QUOTE_LINES_PER_SLIDE = 14;
const LIST_ITEMS_PER_SLIDE = 7;
const INLINE_LEVEL4_MAX_UNITS = 4.9;

function normalizeText(value) {
  return String(value ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/\n/g, "&#10;");
}

function renderEmphasisSegments(text) {
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function renderNonCodeInlineMarkdown(text) {
  const source = String(text ?? "");
  const parts = [];
  const linkPattern = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let lastIndex = 0;
  let match;

  while ((match = linkPattern.exec(source)) !== null) {
    if (match.index > lastIndex) {
      parts.push(renderEmphasisSegments(source.slice(lastIndex, match.index)));
    }
    parts.push(
      `<a class="inline-link" href="${escapeAttr(match[2])}" target="_blank" rel="noreferrer noopener">${renderEmphasisSegments(match[1])}</a>`
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < source.length) {
    parts.push(renderEmphasisSegments(source.slice(lastIndex)));
  }

  return parts.join("");
}

function renderInlineMarkdown(text) {
  const source = String(text ?? "");
  const parts = [];
  const codePattern = /`([^`\n]+)`/g;
  let lastIndex = 0;
  let match;

  while ((match = codePattern.exec(source)) !== null) {
    if (match.index > lastIndex) {
      parts.push(renderNonCodeInlineMarkdown(source.slice(lastIndex, match.index)));
    }
    parts.push(`<code class="inline-code">${escapeHtml(match[1])}</code>`);
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < source.length) {
    parts.push(renderNonCodeInlineMarkdown(source.slice(lastIndex)));
  }

  return parts.join("");
}

function slugify(value) {
  const base = String(value ?? "")
    .replace(/[`~!@#$%^&*()+=\[\]{}|\\:;"'<>,.?/]/g, " ")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return base || "slide";
}

function isBlank(line) {
  return /^\s*$/.test(line);
}

function isHeading(line) {
  return /^(#{1,4})\s+(.+?)\s*$/.test(line);
}

function isFenceStart(line) {
  return /^(```|~~~)/.test(line);
}

function isTableLine(line) {
  return /^\|.*\|\s*$/.test(line);
}

function isAlignmentLine(line) {
  return /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|\s*$/.test(line);
}

function isOrderedItem(line) {
  return /^\s*\d+\.\s+/.test(line);
}

function isUnorderedItem(line) {
  return /^\s*[-*+]\s+/.test(line);
}

function blockTypeStarts(line) {
  return (
    isHeading(line) ||
    isFenceStart(line) ||
    isTableLine(line) ||
    isOrderedItem(line) ||
    isUnorderedItem(line) ||
    /^\s*>/.test(line)
  );
}

function splitTableRow(rowLine) {
  const trimmed = rowLine.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function parseMarkdown(lines) {
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const lineNo = i + 1;

    if (isBlank(line)) {
      i += 1;
      continue;
    }

    const headingMatch = line.match(/^(#{1,4})\s+(.+?)\s*$/);
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2],
        raw: line,
        startLine: lineNo,
        endLine: lineNo,
      });
      i += 1;
      continue;
    }

    const fenceMatch = line.match(/^(```|~~~)\s*(.*)$/);
    if (fenceMatch) {
      const fence = fenceMatch[1];
      const info = fenceMatch[2] || "";
      const contentLines = [];
      const rawLines = [line];
      i += 1;
      while (i < lines.length) {
        rawLines.push(lines[i]);
        if (lines[i].startsWith(fence)) {
          break;
        }
        contentLines.push(lines[i]);
        i += 1;
      }
      blocks.push({
        type: "code",
        fence,
        info,
        contentLines,
        rawLines,
        startLine: lineNo,
        endLine: i + 1,
      });
      i += 1;
      continue;
    }

    if (isTableLine(line)) {
      const rawLines = [];
      while (i < lines.length && isTableLine(lines[i])) {
        rawLines.push(lines[i]);
        i += 1;
      }
      const rows = rawLines.map(splitTableRow);
      const hasAlignment = rawLines.length > 1 && isAlignmentLine(rawLines[1]);
      blocks.push({
        type: "table",
        rawLines,
        header: rows[0],
        alignRow: hasAlignment ? rows[1] : null,
        bodyRows: rows.slice(hasAlignment ? 2 : 1),
        startLine: lineNo,
        endLine: i,
      });
      continue;
    }

    if (/^\s*>/.test(line)) {
      const rawLines = [];
      const quoteLines = [];
      while (i < lines.length && (/^\s*>/.test(lines[i]) || isBlank(lines[i]))) {
        rawLines.push(lines[i]);
        if (isBlank(lines[i])) {
          quoteLines.push("");
        } else {
          quoteLines.push(lines[i].replace(/^\s*>\s?/, ""));
        }
        i += 1;
      }
      blocks.push({
        type: "blockquote",
        rawLines,
        lines: quoteLines,
        startLine: lineNo,
        endLine: i,
      });
      continue;
    }

    if (isOrderedItem(line) || isUnorderedItem(line)) {
      const ordered = isOrderedItem(line);
      const items = [];
      const rawLines = [];
      while (i < lines.length) {
        const candidate = lines[i];
        if (isBlank(candidate)) {
          rawLines.push(candidate);
          i += 1;
          break;
        }
        if ((ordered && !isOrderedItem(candidate)) || (!ordered && !isUnorderedItem(candidate))) {
          if (!/^\s{2,}\S/.test(candidate)) {
            break;
          }
        }
        rawLines.push(candidate);
        if (ordered ? isOrderedItem(candidate) : isUnorderedItem(candidate)) {
          items.push(candidate.replace(/^\s*(?:\d+\.|[-*+])\s+/, ""));
        } else if (items.length) {
          items[items.length - 1] += "\n" + candidate.trim();
        }
        i += 1;
      }
      blocks.push({
        type: "list",
        ordered,
        items,
        rawLines,
        startLine: lineNo,
        endLine: i,
      });
      continue;
    }

    const paragraphLines = [];
    while (i < lines.length && !isBlank(lines[i]) && !blockTypeStarts(lines[i])) {
      paragraphLines.push(lines[i]);
      i += 1;
    }
    blocks.push({
      type: "paragraph",
      lines: paragraphLines,
      rawText: paragraphLines.join("\n"),
      startLine: lineNo,
      endLine: i,
    });
  }

  return blocks;
}

function estimateParagraphUnits(block) {
  const length = block.lines.join(" ").length;
  return 1.25 + Math.max(0.8, Math.ceil(length / 95) * 0.78);
}

function estimateListUnits(block) {
  const charUnits = block.items.reduce((sum, item) => sum + Math.ceil(item.length / 90) * 0.35, 0);
  return 0.8 + block.items.length * 0.85 + charUnits;
}

function estimateTableUnits(block) {
  const longestRow = [block.header, ...block.bodyRows].reduce((max, row) => {
    const joined = row.join(" ");
    return Math.max(max, joined.length);
  }, 0);
  return 1.6 + block.bodyRows.length * 0.95 + Math.ceil(longestRow / 120) * 0.25;
}

function estimateCodeUnits(block) {
  return 1.2 + block.contentLines.length * 0.55;
}

function estimateQuoteUnits(block) {
  return 1.1 + block.lines.filter((line) => line !== "").length * 0.72;
}

function estimateBlockUnits(block) {
  switch (block.type) {
    case "subheading":
      return 1.1;
    case "paragraph":
      return estimateParagraphUnits(block);
    case "list":
      return estimateListUnits(block);
    case "table":
      return estimateTableUnits(block);
    case "code":
      return estimateCodeUnits(block);
    case "blockquote":
      return estimateQuoteUnits(block);
    default:
      return 1;
  }
}

function sliceLargeBlock(block) {
  if (block.type === "code" && block.contentLines.length > CODE_LINES_PER_SLIDE) {
    const segments = [];
    for (let idx = 0; idx < block.contentLines.length; idx += CODE_LINES_PER_SLIDE) {
      const chunk = block.contentLines.slice(idx, idx + CODE_LINES_PER_SLIDE);
      segments.push({
        ...block,
        contentLines: chunk,
        segmentIndex: Math.floor(idx / CODE_LINES_PER_SLIDE) + 1,
        segmentCount: Math.ceil(block.contentLines.length / CODE_LINES_PER_SLIDE),
      });
    }
    return segments;
  }

  if (block.type === "table" && block.bodyRows.length > LONG_TABLE_ROWS) {
    const segments = [];
    for (let idx = 0; idx < block.bodyRows.length; idx += LONG_TABLE_ROWS) {
      segments.push({
        ...block,
        bodyRows: block.bodyRows.slice(idx, idx + LONG_TABLE_ROWS),
        segmentIndex: Math.floor(idx / LONG_TABLE_ROWS) + 1,
        segmentCount: Math.ceil(block.bodyRows.length / LONG_TABLE_ROWS),
      });
    }
    return segments;
  }

  if (block.type === "blockquote" && block.lines.length > QUOTE_LINES_PER_SLIDE) {
    const segments = [];
    for (let idx = 0; idx < block.lines.length; idx += QUOTE_LINES_PER_SLIDE) {
      segments.push({
        ...block,
        lines: block.lines.slice(idx, idx + QUOTE_LINES_PER_SLIDE),
        segmentIndex: Math.floor(idx / QUOTE_LINES_PER_SLIDE) + 1,
        segmentCount: Math.ceil(block.lines.length / QUOTE_LINES_PER_SLIDE),
      });
    }
    return segments;
  }

  if (block.type === "list" && block.items.length > LIST_ITEMS_PER_SLIDE) {
    const segments = [];
    for (let idx = 0; idx < block.items.length; idx += LIST_ITEMS_PER_SLIDE) {
      segments.push({
        ...block,
        items: block.items.slice(idx, idx + LIST_ITEMS_PER_SLIDE),
        segmentIndex: Math.floor(idx / LIST_ITEMS_PER_SLIDE) + 1,
        segmentCount: Math.ceil(block.items.length / LIST_ITEMS_PER_SLIDE),
      });
    }
    return segments;
  }

  return [block];
}

function contentWeightForHeading(context) {
  if (context.headingLevel === 4) {
    return 2.6;
  }
  if (context.headingLevel === 3) {
    return 2.3;
  }
  return 1.1;
}

function createSlideModel(options) {
  return {
    id: options.id,
    kind: options.kind,
    chapterTitle: options.chapterTitle,
    sectionTitle: options.sectionTitle ?? "",
    subsectionTitle: options.subsectionTitle ?? "",
    headingText: options.headingText ?? "",
    headingLevel: options.headingLevel ?? 0,
    continued: Boolean(options.continued),
    blocks: [],
    sourceRefs: [],
    usedUnits: contentWeightForHeading(options),
  };
}

function pushSourceRef(slide, ref) {
  const key = `${ref.type}:${ref.startLine}-${ref.endLine}`;
  if (!slide.sourceRefs.some((existing) => `${existing.type}:${existing.startLine}-${existing.endLine}` === key)) {
    slide.sourceRefs.push(ref);
  }
}

function splitIntoChapters(blocks) {
  const h1 = blocks.find((block) => block.type === "heading" && block.level === 1);
  const chapters = [];
  let currentChapter = null;
  const frontBlocks = [];

  for (const block of blocks) {
    if (block.type === "heading" && block.level === 1) {
      continue;
    }
    if (block.type === "heading" && block.level === 2) {
      currentChapter = {
        title: block.text,
        startLine: block.startLine,
        endLine: block.endLine,
        blocks: [],
      };
      chapters.push(currentChapter);
      continue;
    }
    if (!currentChapter) {
      frontBlocks.push(block);
      continue;
    }
    currentChapter.blocks.push(block);
    currentChapter.endLine = block.endLine;
  }

  return {
    title: h1?.text ?? "新版 pre 完整报告",
    titleLine: h1?.startLine ?? 1,
    frontBlocks,
    chapters,
  };
}

function inspectLevel4Subsection(chapterBlocks, headingIndex) {
  const contentBlocks = [];
  let idx = headingIndex + 1;

  while (idx < chapterBlocks.length) {
    const block = chapterBlocks[idx];
    if (block.type === "heading" && block.level <= 4) {
      break;
    }
    contentBlocks.push(block);
    idx += 1;
  }

  const expandedBlocks = contentBlocks.flatMap((block) => sliceLargeBlock(block));
  const totalUnits = expandedBlocks.reduce((sum, block) => sum + estimateBlockUnits(block), 0);

  return {
    contentBlocks,
    expandedBlocks,
    totalUnits,
    hasCode: contentBlocks.some((block) => block.type === "code"),
    hasTable: contentBlocks.some((block) => block.type === "table"),
  };
}

function generateSlides(deck) {
  const slidesByChapter = [];
  let slideCounter = 0;

  const coverSlide = {
    id: `slide-${String(++slideCounter).padStart(3, "0")}-${slugify(deck.title)}`,
    kind: "cover",
    chapterTitle: "",
    sectionTitle: "",
    subsectionTitle: "",
    headingText: deck.title,
    headingLevel: 1,
    continued: false,
    blocks: deck.frontBlocks.flatMap((block) => sliceLargeBlock(block)),
    sourceRefs: [
      { type: "heading", startLine: deck.titleLine, endLine: deck.titleLine },
      ...deck.frontBlocks.map((block) => ({
        type: block.type,
        startLine: block.startLine,
        endLine: block.endLine,
      })),
    ],
    usedUnits: 0,
  };

  for (const chapter of deck.chapters) {
    const chapterSlides = [];
    chapterSlides.push({
      id: `slide-${String(++slideCounter).padStart(3, "0")}-${slugify(chapter.title)}`,
      kind: "chapter",
      chapterTitle: chapter.title,
      sectionTitle: "",
      subsectionTitle: "",
      headingText: chapter.title,
      headingLevel: 2,
      continued: false,
      blocks: [],
      sourceRefs: [{ type: "heading", startLine: chapter.startLine, endLine: chapter.startLine }],
      usedUnits: 0,
    });

    let context = {
      chapterTitle: chapter.title,
      sectionTitle: "",
      subsectionTitle: "",
      headingText: "",
      headingLevel: 0,
    };
    let currentSlide = null;

    const startContinuation = (overrides = {}) => {
      const slideLabel = overrides.headingText ?? context.headingText ?? "content";
      currentSlide = createSlideModel({
        id: `slide-${String(++slideCounter).padStart(3, "0")}-${slugify(
          `${chapter.title}-${slideLabel}`
        )}`,
        kind: "content",
        chapterTitle: chapter.title,
        sectionTitle: overrides.sectionTitle ?? context.sectionTitle,
        subsectionTitle: overrides.subsectionTitle ?? context.subsectionTitle,
        headingText: overrides.headingText ?? context.headingText,
        headingLevel: overrides.headingLevel ?? context.headingLevel,
        continued: Boolean(overrides.continued),
      });
      chapterSlides.push(currentSlide);
      return currentSlide;
    };

    for (let blockIndex = 0; blockIndex < chapter.blocks.length; blockIndex += 1) {
      const block = chapter.blocks[blockIndex];
      if (block.type === "heading" && block.level === 3) {
        context = {
          chapterTitle: chapter.title,
          sectionTitle: block.text,
          subsectionTitle: "",
          headingText: block.text,
          headingLevel: 3,
        };
        currentSlide = startContinuation({
          headingText: block.text,
          headingLevel: 3,
          continued: false,
        });
        pushSourceRef(currentSlide, {
          type: "heading",
          startLine: block.startLine,
          endLine: block.endLine,
        });
        continue;
      }

      if (block.type === "heading" && block.level === 4) {
        const level4Info = inspectLevel4Subsection(chapter.blocks, blockIndex);
        const canInlineLevel4 =
          !level4Info.hasCode &&
          !level4Info.hasTable &&
          level4Info.contentBlocks.length > 0 &&
          level4Info.totalUnits <= INLINE_LEVEL4_MAX_UNITS;

        if (canInlineLevel4) {
          if (!currentSlide) {
            currentSlide = startContinuation({
              headingText: context.sectionTitle || "",
              headingLevel: context.sectionTitle ? 3 : 0,
              continued: false,
            });
          } else if (
            currentSlide.blocks.length > 0 &&
            currentSlide.usedUnits + estimateBlockUnits({ type: "subheading" }) + level4Info.totalUnits > CONTENT_MAX_UNITS
          ) {
            currentSlide = startContinuation({
              headingText: context.sectionTitle || "",
              headingLevel: context.sectionTitle ? 3 : 0,
              sectionTitle: context.sectionTitle,
              subsectionTitle: "",
              continued: true,
            });
          }

          const subheadingBlock = {
            type: "subheading",
            level: 4,
            text: block.text,
            startLine: block.startLine,
            endLine: block.endLine,
          };
          currentSlide.blocks.push(subheadingBlock);
          currentSlide.usedUnits += estimateBlockUnits(subheadingBlock);
          pushSourceRef(currentSlide, {
            type: "heading",
            startLine: block.startLine,
            endLine: block.endLine,
          });
          continue;
        }

        context = {
          chapterTitle: chapter.title,
          sectionTitle: context.sectionTitle,
          subsectionTitle: block.text,
          headingText: block.text,
          headingLevel: 4,
        };
        currentSlide = startContinuation({
          headingText: block.text,
          headingLevel: 4,
          subsectionTitle: block.text,
          continued: false,
        });
        pushSourceRef(currentSlide, {
          type: "heading",
          startLine: block.startLine,
          endLine: block.endLine,
        });
        continue;
      }

      if (!currentSlide) {
        currentSlide = startContinuation({
          headingText: "",
          headingLevel: 0,
          continued: false,
        });
      }

      const blockSegments = sliceLargeBlock(block);
      for (const segment of blockSegments) {
        const blockUnits = estimateBlockUnits(segment);
        const forceOwnSlide = segment.type === "table" || segment.type === "code";

        if (forceOwnSlide && currentSlide.blocks.length > 0) {
          currentSlide = startContinuation({ continued: true });
        } else if (currentSlide.blocks.length > 0 && currentSlide.usedUnits + blockUnits > CONTENT_MAX_UNITS) {
          currentSlide = startContinuation({ continued: true });
        }

        currentSlide.blocks.push(segment);
        currentSlide.usedUnits += blockUnits;
        pushSourceRef(currentSlide, {
          type: block.type,
          startLine: block.startLine,
          endLine: block.endLine,
        });
      }
    }

    slidesByChapter.push(chapterSlides);
  }

  return { coverSlide, slidesByChapter };
}

function paragraphHtml(block) {
  const text = block.lines.join("\n");
  const isDense = text.length > 170;
  return `<p class="block-paragraph${isDense ? " dense" : ""}">${renderInlineMarkdown(text)}</p>`;
}

function subheadingHtml(block) {
  return `<h5 class="inline-subheading">${renderInlineMarkdown(block.text)}</h5>`;
}

function listHtml(block) {
  const tag = block.ordered ? "ol" : "ul";
  const items = block.items
    .map((item) => `<li>${renderInlineMarkdown(item).replace(/\n/g, "<br>")}</li>`)
    .join("\n");
  return `<${tag} class="block-list">${items}</${tag}>`;
}

function tableHtml(block) {
  const headerHtml = block.header.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("");
  const rowHtml = block.bodyRows
    .map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`)
    .join("\n");
  const denseClass = block.bodyRows.length >= 6 || block.header.length >= 5 ? " dense" : "";
  return `
    <div class="table-wrap${denseClass}">
      <table class="block-table${denseClass}">
        <thead><tr>${headerHtml}</tr></thead>
        <tbody>${rowHtml}</tbody>
      </table>
    </div>
  `;
}

function codeHtml(block) {
  const info = block.info ? `<div class="code-label">${escapeHtml(block.info)}</div>` : "";
  const code = block.contentLines.map((line) => escapeHtml(line)).join("\n");
  return `
    <div class="code-wrap">
      ${info}
      <pre class="block-code"><code>${code}</code></pre>
    </div>
  `;
}

function blockquoteHtml(block) {
  const rendered = block.lines.map((line) => renderInlineMarkdown(line)).join("<br>");
  return `<blockquote class="block-quote">${rendered}</blockquote>`;
}

function renderBlock(block) {
  switch (block.type) {
    case "subheading":
      return subheadingHtml(block);
    case "paragraph":
      return paragraphHtml(block);
    case "list":
      return listHtml(block);
    case "table":
      return tableHtml(block);
    case "code":
      return codeHtml(block);
    case "blockquote":
      return blockquoteHtml(block);
    default:
      return "";
  }
}

function renderChrome(slide) {
  const crumbs = [slide.chapterTitle, slide.sectionTitle, slide.subsectionTitle].filter(Boolean);
  const crumbHtml = crumbs.map((item) => `<span class="crumb">${renderInlineMarkdown(item)}</span>`).join("");
  return `<div class="slide-chrome">${crumbHtml}</div>`;
}

function renderSlide(slide) {
  if (slide.kind === "cover") {
    const coverBlocksHtml = slide.blocks.length
      ? `<div class="cover-notes">${slide.blocks.map(renderBlock).join("\n")}</div>`
      : "";
    return `
      <section id="${slide.id}" data-chapter="" data-section="" data-subsection="" class="cover-slide">
        <div class="slide-shell cover-shell">
          <div class="cover-kicker">新版 pre 完整报告</div>
          <h1 class="cover-title">${renderInlineMarkdown(slide.headingText)}</h1>
          ${coverBlocksHtml}
        </div>
      </section>
    `;
  }

  if (slide.kind === "chapter") {
    return `
      <section id="${slide.id}" data-chapter="${escapeAttr(slide.chapterTitle)}" data-section="" data-subsection="" class="chapter-slide">
        <div class="slide-shell chapter-shell">
          <div class="chapter-index">章节</div>
          <h2 class="chapter-title">${renderInlineMarkdown(slide.headingText)}</h2>
        </div>
      </section>
    `;
  }

  const titleTag = slide.headingLevel === 4 ? "h4" : slide.headingLevel === 3 ? "h3" : "div";
  const titleClass = slide.headingLevel ? `content-title level-${slide.headingLevel}` : "content-spacer";
  const titleHtml = slide.headingText
    ? `<${titleTag} class="${titleClass}">${renderInlineMarkdown(slide.headingText)}</${titleTag}>`
    : `<div class="${titleClass}"></div>`;
  const blocksHtml = slide.blocks.map(renderBlock).join("\n");

  return `
    <section
      id="${slide.id}"
      data-chapter="${escapeAttr(slide.chapterTitle)}"
      data-section="${escapeAttr(slide.sectionTitle)}"
      data-subsection="${escapeAttr(slide.subsectionTitle)}"
      class="content-slide${slide.continued ? " continued" : ""}"
    >
      <div class="slide-shell content-shell">
        ${renderChrome(slide)}
        ${titleHtml}
        <div class="content-body">
          ${blocksHtml}
        </div>
      </div>
    </section>
  `;
}

function renderHtml(deck, generated) {
  const chapterSections = generated.slidesByChapter
    .map((chapterSlides) => {
      const inner = chapterSlides.map(renderSlide).join("\n");
      return `<section class="chapter-stack">\n${inner}\n</section>`;
    })
    .join("\n");

  return `<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>${escapeHtml(deck.title)} - reveal.js</title>
    <link rel="stylesheet" href="./reveal/reset.css">
    <link rel="stylesheet" href="./reveal/reveal.css">
    <link rel="stylesheet" href="./reveal/theme/white.css">
    <link rel="stylesheet" href="./deck.css">
  </head>
  <body>
    <div class="reveal">
      <div class="slides">
        ${renderSlide(generated.coverSlide)}
        ${chapterSections}
      </div>
    </div>
    <script src="./reveal/reveal.js"></script>
    <script>
      Reveal.initialize({
        width: 1600,
        height: 900,
        margin: 0.04,
        minScale: 0.2,
        maxScale: 1.5,
        hash: true,
        history: true,
        transition: "fade",
        controls: true,
        progress: true,
        slideNumber: "c/t",
        center: false,
        overview: true,
        pdfSeparateFragments: false,
        mouseWheel: false
      });
    </script>
  </body>
</html>
`;
}

function deckCss() {
  return `:root {
  --paper: #f5efe3;
  --paper-strong: #fbf7ef;
  --ink: #29231f;
  --muted: #7a6d60;
  --accent: #8a5a44;
  --accent-soft: rgba(138, 90, 68, 0.14);
  --line: rgba(93, 74, 59, 0.22);
  --shadow: 0 20px 55px rgba(64, 43, 27, 0.12);
}

html,
body {
  background:
    radial-gradient(circle at top left, rgba(173, 139, 112, 0.16), transparent 32%),
    linear-gradient(180deg, #f8f2e7 0%, #efe4d4 100%);
}

.reveal {
  font-family: "Noto Serif SC", "Songti SC", "STSong", "SimSun", serif;
  color: var(--ink);
}

.reveal .slides {
  text-align: left;
}

.reveal .slides section {
  box-sizing: border-box;
  min-height: 100%;
}

.reveal .slides > section,
.reveal .slides > section > section {
  min-height: 100%;
}

.reveal .slides section .slide-shell {
  box-sizing: border-box;
  width: 100%;
  min-height: 100%;
  height: 100%;
  padding: 26px 34px 28px;
  display: flex;
  flex-direction: column;
}

.cover-shell,
.chapter-shell {
  justify-content: flex-start;
  align-items: flex-start;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.82), rgba(248, 239, 226, 0.93)),
    linear-gradient(180deg, var(--paper-strong), var(--paper));
  border: 1px solid rgba(114, 87, 69, 0.14);
  box-shadow: var(--shadow);
}

.cover-kicker,
.chapter-index {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
  padding: 6px 12px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 18px;
  letter-spacing: 0.08em;
}

.cover-title {
  margin: 0;
  max-width: 92%;
  font-size: 68px;
  line-height: 1.14;
  color: var(--ink);
  letter-spacing: -0.01em;
}

.cover-notes {
  margin-top: auto;
  width: min(720px, 68%);
  max-width: none;
}

.cover-notes .block-quote,
.cover-notes .block-paragraph,
.cover-notes .block-list {
  font-size: 25px;
  line-height: 1.7;
}

.cover-notes .block-quote {
  box-sizing: border-box;
  width: 100%;
  margin: 0;
  padding: 22px 26px;
  border-left-width: 6px;
  background: rgba(255, 251, 244, 0.82);
  box-shadow: 0 10px 30px rgba(64, 43, 27, 0.06);
}

.chapter-title {
  margin: 0;
  max-width: 84%;
  font-size: 56px;
  line-height: 1.2;
  color: var(--ink);
}

.content-shell {
  background:
    linear-gradient(180deg, rgba(255, 252, 246, 0.96), rgba(250, 244, 235, 0.98)),
    linear-gradient(180deg, var(--paper-strong), var(--paper));
  border: 1px solid rgba(114, 87, 69, 0.12);
  box-shadow: var(--shadow);
}

.slide-chrome {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
  color: var(--muted);
  font-size: 15px;
  letter-spacing: 0.04em;
}

.slide-chrome .crumb:not(:last-child)::after {
  content: " /";
  margin-left: 10px;
  color: rgba(122, 109, 96, 0.5);
}

.content-title {
  margin: 0 0 10px;
  color: var(--ink);
}

.content-title.level-3 {
  font-size: 36px;
  line-height: 1.2;
}

.content-title.level-4 {
  font-size: 31px;
  line-height: 1.22;
  color: #3b312b;
}

.content-spacer {
  min-height: 6px;
}

.content-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  flex: 1;
  justify-content: flex-start;
}

.block-paragraph,
.block-list,
.block-quote {
  margin: 0;
  font-size: 28px;
  line-height: 1.66;
}

.block-paragraph.dense,
.block-list.dense {
  font-size: 25px;
}

.reveal strong {
  font-weight: 700;
  color: #2f2723;
}

.reveal em {
  font-style: italic;
}

.inline-code {
  display: inline-block;
  padding: 0.08em 0.32em;
  border-radius: 0.3em;
  background: rgba(138, 90, 68, 0.1);
  color: #6f4433;
  font-family: "Cascadia Code", "Fira Code", Consolas, monospace;
  font-size: 0.88em;
  line-height: 1.2;
  vertical-align: 0.02em;
}

.block-list {
  padding-left: 1.3em;
}

.block-list li {
  margin-bottom: 6px;
}

.block-quote {
  padding: 18px 24px;
  border-left: 5px solid rgba(138, 90, 68, 0.4);
  background: rgba(255, 251, 244, 0.86);
  font-size: 25px;
  line-height: 1.82;
  white-space: normal;
}

.inline-subheading {
  margin: 6px 0 2px;
  padding-top: 10px;
  border-top: 1px solid rgba(138, 90, 68, 0.18);
  font-size: 25px;
  line-height: 1.35;
  color: #4a3a31;
  letter-spacing: 0.01em;
}

.code-wrap {
  padding: 16px 18px;
  border-radius: 18px;
  background: #201913;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08);
}

.code-label {
  margin-bottom: 10px;
  color: rgba(255,255,255,0.65);
  font-size: 15px;
  letter-spacing: 0.08em;
}

.block-code {
  margin: 0;
  white-space: pre-wrap;
  font-family: "Cascadia Code", "Fira Code", Consolas, monospace;
  font-size: 19px;
  line-height: 1.62;
  color: #f7f0e8;
}

.table-wrap {
  padding: 8px 0 0;
}

.block-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  background: rgba(255, 252, 248, 0.82);
}

.block-table th,
.block-table td {
  border: 1px solid var(--line);
  padding: 11px 12px;
  vertical-align: top;
  word-break: break-word;
  font-size: 21px;
  line-height: 1.46;
}

.block-table th {
  background: rgba(138, 90, 68, 0.12);
  color: #3f322b;
  font-weight: 700;
}

.block-table.dense th,
.block-table.dense td {
  font-size: 18px;
  padding: 8px 9px;
}

.reveal .progress {
  color: rgba(138, 90, 68, 0.55);
}

.reveal .slide-number {
  background: rgba(255, 251, 245, 0.92);
  color: #59463a;
  font-size: 14px;
  border: 1px solid rgba(114, 87, 69, 0.16);
  border-radius: 999px;
  padding: 6px 10px;
  right: 22px;
  bottom: 16px;
}

.reveal .controls {
  color: rgba(138, 90, 68, 0.68);
}

@media print {
  html,
  body {
    background: #ffffff;
  }

  .slide-shell {
    box-shadow: none !important;
    border: 1px solid rgba(114, 87, 69, 0.1) !important;
  }
}
`;
}

function collectSourceTextEntries(blocks, deckTitle) {
  const entries = [{ type: "heading", text: deckTitle }];
  for (const block of blocks) {
    if (block.type === "heading") {
      if (block.level === 1) {
        continue;
      }
      entries.push({ type: "heading", text: block.text });
    } else if (block.type === "paragraph") {
      entries.push({ type: "paragraph", text: block.lines.join("\n") });
    } else if (block.type === "code") {
      for (const line of block.contentLines) {
        entries.push({ type: "code-line", text: line });
      }
    } else if (block.type === "table") {
      for (const cell of block.header) {
        entries.push({ type: "table-cell", text: cell });
      }
      for (const row of block.bodyRows) {
        for (const cell of row) {
          entries.push({ type: "table-cell", text: cell });
        }
      }
    } else if (block.type === "list") {
      for (const item of block.items) {
        entries.push({ type: "list-item", text: item });
      }
    } else if (block.type === "blockquote") {
      for (const line of block.lines) {
        if (line !== "") {
          entries.push({ type: "quote-line", text: line });
        }
      }
    }
  }
  return entries.map((entry) => ({ ...entry, normalized: normalizeText(entry.text) }));
}

function collectRenderedTextEntries(generated) {
  const entries = [];
  const allSlides = [generated.coverSlide, ...generated.slidesByChapter.flat()];

  for (const slide of allSlides) {
    if (slide.headingText) {
      entries.push({ type: "heading", text: slide.headingText });
    }
    for (const block of slide.blocks) {
      if (block.type === "subheading") {
        entries.push({ type: "heading", text: block.text });
      } else if (block.type === "paragraph") {
        entries.push({ type: "paragraph", text: block.lines.join("\n") });
      } else if (block.type === "code") {
        for (const line of block.contentLines) {
          entries.push({ type: "code-line", text: line });
        }
      } else if (block.type === "table") {
        for (const cell of block.header) {
          entries.push({ type: "table-cell", text: cell });
        }
        for (const row of block.bodyRows) {
          for (const cell of row) {
            entries.push({ type: "table-cell", text: cell });
          }
        }
      } else if (block.type === "list") {
        for (const item of block.items) {
          entries.push({ type: "list-item", text: item });
        }
      } else if (block.type === "blockquote") {
        for (const line of block.lines) {
          if (line !== "") {
            entries.push({ type: "quote-line", text: line });
          }
        }
      }
    }
  }
  return entries.map((entry) => ({ ...entry, normalized: normalizeText(entry.text) }));
}

function countEntries(entries) {
  const counts = new Map();
  for (const entry of entries) {
    const key = `${entry.type}::${entry.normalized}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

function buildTextIntegrityCheck(sourceEntries, renderedEntries) {
  const sourceCounts = countEntries(sourceEntries);
  const renderedCounts = countEntries(renderedEntries);
  const missing = [];

  for (const [key, sourceCount] of sourceCounts.entries()) {
    const renderedCount = renderedCounts.get(key) ?? 0;
    if (renderedCount < sourceCount) {
      const [type, normalized] = key.split("::");
      missing.push({
        type,
        text: normalized,
        sourceCount,
        renderedCount,
      });
    }
  }

  return {
    ok: missing.length === 0,
    sourceEntries: sourceEntries.length,
    renderedEntries: renderedEntries.length,
    missing,
  };
}

function buildStructureCheck(blocks, generated) {
  const mapping = new Map();
  const allSlides = [generated.coverSlide, ...generated.slidesByChapter.flat()];
  for (const slide of allSlides) {
    for (const ref of slide.sourceRefs) {
      const key = `${ref.type}:${ref.startLine}-${ref.endLine}`;
      if (!mapping.has(key)) {
        mapping.set(key, []);
      }
      mapping.get(key).push(slide.id);
    }
  }

  const required = [];
  for (const block of blocks) {
    if (
      (block.type === "heading" && [2, 3, 4].includes(block.level)) ||
      block.type === "code" ||
      block.type === "table"
    ) {
      required.push({
        key: `${block.type}:${block.startLine}-${block.endLine}`,
        type: block.type === "heading" ? `heading-${block.level}` : block.type,
        startLine: block.startLine,
        endLine: block.endLine,
        text: block.type === "heading" ? block.text : undefined,
      });
    }
  }

  const missing = required.filter((item) => !mapping.has(item.key));

  return {
    ok: missing.length === 0,
    requiredMappings: required.length,
    missing,
  };
}

async function copyDir(source, target) {
  await fs.mkdir(target, { recursive: true });
  const entries = await fs.readdir(source, { withFileTypes: true });
  for (const entry of entries) {
    const sourcePath = path.join(source, entry.name);
    const targetPath = path.join(target, entry.name);
    if (entry.isDirectory()) {
      await copyDir(sourcePath, targetPath);
    } else {
      await fs.copyFile(sourcePath, targetPath);
    }
  }
}

async function ensureCleanDir(dir) {
  await fs.mkdir(dir, { recursive: true });
  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const entryPath = path.join(dir, entry.name);
    await fs.rm(entryPath, { recursive: true, force: true });
  }
}

function buildSlideMap(generated) {
  const allSlides = [generated.coverSlide, ...generated.slidesByChapter.flat()];
  return allSlides.map((slide, index) => ({
    index: index + 1,
    id: slide.id,
    kind: slide.kind,
    chapterTitle: slide.chapterTitle,
    sectionTitle: slide.sectionTitle,
    subsectionTitle: slide.subsectionTitle,
    headingText: slide.headingText,
    sourceRefs: slide.sourceRefs,
    blockTypes: slide.blocks.map((block) => block.type),
    continued: slide.continued,
  }));
}

async function main() {
  const [sourceMarkdown, sourceStat] = await Promise.all([
    fs.readFile(sourcePath, "utf8"),
    fs.stat(sourcePath),
  ]);

  await fs.access(vendorDist);
  await fs.access(vendorCss);

  const lines = sourceMarkdown.replace(/\r\n/g, "\n").split("\n");
  const blocks = parseMarkdown(lines);
  const deck = splitIntoChapters(blocks);
  const generated = generateSlides(deck);

  const html = renderHtml(deck, generated);
  const css = deckCss();
  const slideMap = buildSlideMap(generated);

  const sourceEntries = collectSourceTextEntries(blocks, deck.title);
  const renderedEntries = collectRenderedTextEntries(generated);
  const textIntegrity = buildTextIntegrityCheck(sourceEntries, renderedEntries);
  const structureCheck = buildStructureCheck(blocks, generated);
  const externalAssetHtml =
    /<(?:script|img)\b[^>]+(?:src)=["']https?:\/\//i.test(html) ||
    /<link\b[^>]+(?:href)=["']https?:\/\//i.test(html);
  const externalAssetCss = /url\(\s*["']?https?:\/\//i.test(css);
  const offlineCheck = {
    ok: !externalAssetHtml && !externalAssetCss,
  };

  await ensureCleanDir(outputDir);
  await copyDir(vendorDist, outputRevealDir);
  await copyDir(vendorCss, outputCssDir);

  await Promise.all([
    fs.writeFile(path.join(outputDir, "index.html"), html, "utf8"),
    fs.writeFile(path.join(outputDir, "deck.css"), css, "utf8"),
    fs.writeFile(path.join(outputDir, "slide-map.json"), JSON.stringify(slideMap, null, 2), "utf8"),
    fs.writeFile(
      path.join(outputDir, "build-report.json"),
      JSON.stringify(
        {
          source: {
            path: sourcePath,
            size: sourceStat.size,
            lines: lines.length,
            chapters: deck.chapters.length,
            blocks: {
              headings: blocks.filter((block) => block.type === "heading").length,
              code: blocks.filter((block) => block.type === "code").length,
              tables: blocks.filter((block) => block.type === "table").length,
              paragraphs: blocks.filter((block) => block.type === "paragraph").length,
              lists: blocks.filter((block) => block.type === "list").length,
              blockquotes: blocks.filter((block) => block.type === "blockquote").length,
            },
          },
          output: {
            dir: outputDir,
            slides: slideMap.length,
          },
          checks: {
            textIntegrity,
            structureCheck,
            offlineCheck,
          },
        },
        null,
        2
      ),
      "utf8"
    ),
    fs.writeFile(
      path.join(outputDir, "README.md"),
      `# 新版pre完整报告 reveal.js 离线版

- 入口文件：\`index.html\`
- 源文件：\`${sourcePath}\`
- 本地 reveal.js 资源：\`./reveal\`
- 打印/PDF 样式资源：\`./reveal-css\`
`,
      "utf8"
    ),
  ]);

  console.log(
    JSON.stringify(
      {
        ok: textIntegrity.ok && structureCheck.ok && offlineCheck.ok,
        outputDir,
        slideCount: slideMap.length,
        checks: {
          textIntegrity: textIntegrity.ok,
          structureCheck: structureCheck.ok,
          offlineCheck: offlineCheck.ok,
        },
      },
      null,
      2
    )
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
