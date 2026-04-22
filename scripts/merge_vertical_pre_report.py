import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FULL_REPORT = ROOT / "docs" / "新版pre完整报告.md"
VERTICAL_DRAFT = ROOT / "docs" / "新版pre竖向重构稿.md"

OLD_START = "## 二、AI 生成宋词的格律与结构准确性"
NEW_START = "## 二、按任务 prompt 逐个观察生成结果"
OLD_END = "## 五、AI 生成文本与真实宋词的相似性分析"
NEW_END = "## 四、AI 生成文本与真实宋词的相似性分析"

HEADING_RENAMES = {
    "## 五、AI 生成文本与真实宋词的相似性分析": "## 四、AI 生成文本与真实宋词的相似性分析",
    "## 六、AI 生成文本的内部同质化分析": "## 五、AI 生成文本的内部同质化分析",
    "## 七、针对 AI 宋词生成的实践建议": "## 六、针对 AI 宋词生成的实践建议",
}


def find_first(text: str, candidates: list[str], label: str) -> int:
    for candidate in candidates:
        idx = text.find(candidate)
        if idx != -1:
            return idx
    joined = " / ".join(candidates)
    raise SystemExit(f"未找到{label}：{joined}")


def renumber_later_sections(text: str) -> str:
    text = re.sub(r"^### 5\.", "### 4.", text, flags=re.MULTILINE)
    text = re.sub(r"^### 6\.", "### 5.", text, flags=re.MULTILINE)
    text = re.sub(r"^### 7\.", "### 6.", text, flags=re.MULTILINE)
    return text


def main() -> None:
    full_text = FULL_REPORT.read_text(encoding="utf-8")
    vertical_text = VERTICAL_DRAFT.read_text(encoding="utf-8")

    full_start = find_first(full_text, [OLD_START, NEW_START], "完整版起始章节")
    full_end = find_first(full_text, [OLD_END, NEW_END], "完整版结束章节")
    vertical_start = find_first(vertical_text, [NEW_START], "竖向重构稿的新第二章")

    merged = full_text[:full_start] + vertical_text[vertical_start:].strip() + "\n\n" + full_text[full_end:]

    for old_heading, new_heading in HEADING_RENAMES.items():
        if old_heading in merged:
            merged = merged.replace(old_heading, new_heading, 1)

    merged = renumber_later_sections(merged)

    FULL_REPORT.write_text(merged, encoding="utf-8")

    print(f"已完成替换：{FULL_REPORT}")
    print("新插入部分：新版pre竖向重构稿 的第二、三章")
    print("已顺延章节：原五/六/七章改为四/五/六章，并修正对应小节编号")


if __name__ == "__main__":
    main()
