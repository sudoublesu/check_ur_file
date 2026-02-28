---
name: planning-proofreader
description: >
  城乡规划文件校对工具，专用于上海市控制性详细规划（控规）及相关规划文件的审查与校对。
  当用户提供规划说明书、图则、公文、请示、汇报PPT等规划成果文件（.docx、.pdf），
  需要进行内容校对、格式规范审查、数据一致性核验、用地分类核查、错别字检查，或需要生成校对报告时使用。
  触发关键词：校对、审查、核对、检查文件、规划文本、控规、说明书、图则、成果规范、错别字。
---

# 规划文件校对工具

## 工作流程

### Step 1：读取文件

项目目录约定：`input/` 存放待校对文件，`temp/` 存放工作中间文件，`output/` 存放报告和批注版。

根据文件类型选择脚本：

```bash
# .docx 文件
python skills/planning-proofreader/scripts/read_docx.py input/<文件名>.docx temp/doc_content.json

# .pdf 文件
python skills/planning-proofreader/scripts/read_pdf.py input/<文件名>.pdf temp/doc_content.json
```

输出 `temp/doc_content.json`，包含段落（含段落索引 `index`）、表格、页眉页脚的结构化内容。

### Step 2：提取并交叉核验数字指标

```bash
python skills/planning-proofreader/scripts/check_numbers.py temp/doc_content.json temp/numbers.json
```

输出 `temp/numbers.json`，包含所有面积、容积率、年份、人口等数字，供数据一致性核查使用。

### Step 2.5：错别字及语言问题检查

```bash
python skills/planning-proofreader/scripts/check_typos.py temp/doc_content.json temp/typos.json
```

输出 `temp/typos.json`，包含：
- **错别字**：形近字/音近字误用（如「一下」→「以下」、「绿化率」→「绿地率」）
- **术语一致性**：行政区划名称、规划专业术语的全文一致性
- **格式问题**：年份连接号、括号格式、列举标点不一致、面积单位混用

> 参照 `references/common-errors.md` 查阅常见错误清单及规范说明。
> 注意：自动检查结果含误报，需人工逐条核实后再纳入校对报告。

### Step 3：加载对应参考文件

根据文件类型和校对需求，按需读取以下参考文件（不必全部加载）：

| 参考文件 | 何时加载 |
|---|---|
| `references/proofread-rules.md` | 了解本所校对职责和检查项清单 |
| `references/sh-land-classification.md` | 核查用地性质代码、用地名称是否符合上海标准 |
| `references/chengguo-guifan.md` | 核查控规成果的命名、图则格式、指标表填写规范 |
| `references/common-errors.md` | 查阅常见错别字、术语误用、格式规范说明 |

### Step 4：执行校对

按以下维度逐项检查，参照 `references/proofread-rules.md` 的7项基础检查清单：

1. **完整性**：成果构成是否齐全，顺序是否正确
2. **逐项核对**：文字、数据、图表、引用逐项核对
3. **格式一致**：术语、单位、编号格式全文统一
4. **语言规范**：语法、标点、表述规范性；结合 typos.json 复核错别字
5. **图文一致**：图题与图内容对应，图内文字与图题一致
6. **数据准确**：前后数据逻辑一致（结合 Step 2 输出）
7. **图纸基础**：比例尺、风玫瑰、路名、图例、图名、图纸序号

重点核查项：
- 用地代码是否符合上海市分类标准（对照 `sh-land-classification.md`）
- 指标一览表字段格式是否符合成果规范（对照 `chengguo-guifan.md`）
- 项目命名是否符合规范格式

### Step 5：输出报告

**始终输出 Markdown 格式报告**，参照 `assets/report-template.md` 模板结构：
- 总体评估（问题数量汇总）
- 错误（必须修改）
- 警告（建议修改）
- 建议（格式/语言优化，含错别字和格式问题）
- 数字/指标交叉核验表

**如原文件为 .docx，额外生成带批注的 Word 文件：**

先将问题整理为 `temp/issues.json`：
```json
[
  {"para_index": 2, "comment": "「绿化率」应改为「绿地率」", "severity": "error"},
  {"para_index": 5, "comment": "容积率应保留两位小数，改为1.50", "severity": "warning"}
]
```

然后运行：
```bash
python skills/planning-proofreader/scripts/add_comments.py input/<文件名>.docx temp/issues.json output/<文件名>_批注.docx
```

Markdown 报告保存至 `output/校对报告.md`。

## 参考文件说明

- `references/proofread-rules.md` — 本所校对规则（7项检查清单）
- `references/sh-land-classification.md` — 上海市控规用地分类完整表（11大类、50中类、54小类）
- `references/chengguo-guifan.md` — 成果规范要点（命名、图则、指标表格式）
- `references/common-errors.md` — 常见错别字、术语误用、格式规范说明
- 原始 PDF 文件保存在 `references/` 目录，可用 `read_pdf.py` 按需提取特定页面内容

## 脚本说明

| 脚本 | 用途 |
|---|---|
| `scripts/read_docx.py` | 提取 .docx 结构化内容（段落、表格、页眉页脚）|
| `scripts/read_pdf.py` | 提取 .pdf 文本内容（按页）|
| `scripts/check_numbers.py` | 提取全文数字/规划指标，辅助交叉核验 |
| `scripts/check_typos.py` | 检查错别字、术语一致性、格式问题，输出 typos.json |
| `scripts/add_comments.py` | 向 .docx 插入 Word 审阅批注 |
