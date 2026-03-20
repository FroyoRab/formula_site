# formula_site

基于 **Python API + CSV 文件数据库 + 动态页面** 的配方站。

## 功能
- 根路径：`/changeme/`。
- 首页：顶部搜索栏 + 右侧“添加”按钮。
- 搜索安全：查询词统一转义处理，避免特殊字符影响页面与匹配过程。
- 搜索能力：支持相似搜索（拼写接近也可命中）。
- 首页列表：展示所有配方名称与简要内容，点击整行进入详情。
- 详情页：
  - 左侧可编辑配方名称和配方内容。
  - 左侧底部包含“保存”和“删除”。
  - 右上角有“返回”按钮。
  - 右侧评论区提交后不刷新页面，并保存到新的 CSV 文件。
  - 每次打开详情页会按配方 `id` 读取并展示所有评论，评论使用换行分隔。
- 点击“保存”后持久化到 CSV 并自动返回首页。

## 安全性说明（SQL 注入）
- 本项目**不使用 SQL 数据库**（仅使用 `csv` 文件读写：`data/formulas.csv`、`data/comments.csv`），后端中不存在 SQL 语句拼接与执行，因此传统 SQL 注入攻击面不成立。
- 搜索与详情渲染路径中，用户输入会经过后端规范化处理（如长度限制、Unicode 归一化、大小写归一化）后再参与匹配，避免特殊字符影响搜索流程。
- 页面输出对用户可见文本统一使用 HTML 转义，降低脚本注入风险。

### 建议的快速自检
可使用以下命令验证“SQL 注入风格输入”不会触发异常查询行为：

```bash
# 搜索注入风格关键字（应返回 200 页面，不会执行任何 SQL）
curl -i 'http://127.0.0.1:65521/changeme/?q=%27%20OR%201%3D1%20--'

# 提交包含注入风格文本的配方名（应按普通文本保存）
curl -i -X POST \
  -d 'name=%27%20OR%201%3D1%20--&content=test' \
  'http://127.0.0.1:65521/changeme/formula/create'
```

## 启动
```bash
python app.py
```

访问：<http://127.0.0.1:65521/changeme/>

CSV 文件：`data/formulas.csv`（配方）和 `data/comments.csv`（评论）。

## 批量导入脚本
仓库提供 `import_formulas.py`，可把“每段一个配方、段落间空行分隔”的文本批量导入到远程站点：

```bash
# 先检查解析结果
python import_formulas.py formulas.txt --dry-run

# 直接导入到默认目标 8.153.76.179:65521
python import_formulas.py formulas.txt

# 自定义目标地址
python import_formulas.py formulas.txt --host 127.0.0.1:65521 --base-path /12sagittarius_ghpishbc
```
