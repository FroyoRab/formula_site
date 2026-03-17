from __future__ import annotations

import csv
import html
import json
import re
import urllib.parse
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "formulas.csv"
FIELDNAMES = ["id", "name", "content", "created_at"]
COMMENTS_FILE = DATA_DIR / "comments.csv"
COMMENT_FIELDNAMES = ["id", "formula_id", "content", "created_at"]
HOST = "0.0.0.0"
PORT = 65521
BASE_PATH = "/12sagittarius_ghpishbc"


def app_url(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{BASE_PATH}{normalized}"


def ensure_data_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        with DATA_FILE.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
    if not COMMENTS_FILE.exists():
        with COMMENTS_FILE.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COMMENT_FIELDNAMES).writeheader()


def load_formulas() -> List[Dict[str, str]]:
    ensure_data_file()
    with DATA_FILE.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_comments() -> List[Dict[str, str]]:
    ensure_data_file()
    with COMMENTS_FILE.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_formulas(rows: List[Dict[str, str]]) -> None:
    with DATA_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_comments(rows: List[Dict[str, str]]) -> None:
    with COMMENTS_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COMMENT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def next_id(rows: List[Dict[str, str]]) -> int:
    return 1 if not rows else max(int(row["id"]) for row in rows) + 1


def create_formula(name: str, content: str) -> str:
    rows = load_formulas()
    new_id = str(next_id(rows))
    rows.append(
        {
            "id": new_id,
            "name": name.strip() or "未命名配方",
            "content": content.strip(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    write_formulas(rows)
    return new_id


def update_formula(formula_id: str, name: str, content: str) -> bool:
    rows = load_formulas()
    updated = False
    for row in rows:
        if row["id"] == formula_id:
            row["name"] = name.strip() or "未命名配方"
            row["content"] = content.strip()
            updated = True
            break
    if updated:
        write_formulas(rows)
    return updated


def delete_formula(formula_id: str) -> bool:
    rows = load_formulas()
    kept_rows = [row for row in rows if row["id"] != formula_id]
    if len(kept_rows) == len(rows):
        return False
    write_formulas(kept_rows)
    delete_comments_by_formula(formula_id)
    return True


def get_formula(formula_id: str) -> Optional[Dict[str, str]]:
    rows = load_formulas()
    for row in rows:
        if row["id"] == formula_id:
            return row
    return None


def list_comments_by_formula(formula_id: str) -> List[Dict[str, str]]:
    comments = [row for row in load_comments() if row["formula_id"] == formula_id]
    return sorted(comments, key=lambda row: int(row["id"]))


def add_comment(formula_id: str, content: str) -> Optional[Dict[str, str]]:
    clean_content = content.strip()
    if not clean_content or not get_formula(formula_id):
        return None

    comments = load_comments()
    next_comment_id = 1 if not comments else max(int(row["id"]) for row in comments) + 1
    row = {
        "id": str(next_comment_id),
        "formula_id": formula_id,
        "content": clean_content,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    comments.append(row)
    write_comments(comments)
    return row


def delete_comments_by_formula(formula_id: str) -> None:
    rows = load_comments()
    kept_rows = [row for row in rows if row["formula_id"] != formula_id]
    if len(kept_rows) != len(rows):
        write_comments(kept_rows)


MAX_SEARCH_LENGTH = 120


def normalize_text(text: str) -> str:
    # 统一大小写与 Unicode 形态，提升中英文混输时的匹配稳定性。
    return unicodedata.normalize("NFKC", text).casefold().strip()


def tokenize(text: str) -> List[str]:
    return [token for token in re.split(r"\s+", normalize_text(text)) if token]


def similarity_score(query: str, target: str) -> float:
    if not query or not target:
        return 0.0
    return SequenceMatcher(None, query, target).ratio()


def rank_formula(query: str, query_tokens: List[str], row: Dict[str, str]) -> tuple[float, float]:
    name = normalize_text(row.get("name", ""))
    content = normalize_text(row.get("content", ""))

    name_score = 0.0
    content_score = 0.0

    if query == name:
        name_score += 2.0
    if name.startswith(query):
        name_score += 1.0
    if query in name:
        name_score += 0.8
    if query in content:
        content_score += 0.35

    if query_tokens:
        token_name_hits = sum(1 for token in query_tokens if token in name) / len(query_tokens)
        token_content_hits = sum(1 for token in query_tokens if token in content) / len(query_tokens)
        name_score += token_name_hits * 0.8
        content_score += token_content_hits * 0.3

    name_score += similarity_score(query, name) * 0.7
    return name_score, content_score


def search_formulas(keyword: str) -> List[Dict[str, str]]:
    rows = load_formulas()[::-1]
    clean_keyword = keyword.strip()[:MAX_SEARCH_LENGTH]
    if not clean_keyword:
        return rows

    query = normalize_text(clean_keyword)
    query_tokens = tokenize(query)

    scored: List[tuple[float, float, Dict[str, str]]] = []
    for row in rows:
        name_score, content_score = rank_formula(query, query_tokens, row)
        # 名称优先：名称分数作为第一排序键；内容分数仅作为次级召回和次排序。
        if name_score >= 0.45 or content_score >= 0.3:
            scored.append((name_score, content_score, row))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [row for _, _, row in scored]


def excerpt(text: str, limit: int = 70) -> str:
    cleaned = " ".join(text.splitlines())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


def shell_html(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>{html.escape(title)}</title>
  <link rel=\"stylesheet\" href=\"{app_url('/static/style.css')}\">
</head>
<body>
  <div class=\"site\">{body}</div>
</body>
</html>"""


def render_home(keyword: str, rows: List[Dict[str, str]]) -> str:
    items = []
    for row in rows:
        items.append(
            f"""
            <a class=\"formula-row\" href=\"{app_url(f"/formula/{row['id']}")}\">
              <div class=\"formula-main\">
                <h3>{html.escape(row['name'])}</h3>
                <p>{html.escape(excerpt(row['content']))}</p>
              </div>
              <span class=\"time\">{html.escape(row['created_at'])}</span>
            </a>
            """
        )
    if not items:
        items.append('<div class="empty">暂无配方，点击右侧“添加”创建。</div>')

    body = f"""
      <section class=\"home\">
        <form class=\"top-bar\" method=\"get\" action=\"{app_url('/')}\">
          <input type=\"text\" name=\"q\" value=\"{html.escape(keyword)}\" placeholder=\"搜索配方名称\">
          <button class=\"btn primary\" type=\"submit\">搜索</button>
          <a class=\"btn add\" href=\"{app_url('/formula/new')}\">添加</a>
        </form>
        <div class=\"list\">{''.join(items)}</div>
      </section>
    """
    return shell_html("配方首页", body)


def render_detail(formula: Dict[str, str], is_new: bool = False) -> str:
    formula_id = formula.get("id", "new")
    title = "新建配方" if is_new else f"配方详情 #{formula_id}"
    save_action = app_url('/formula/create') if is_new else app_url(f"/formula/{formula_id}/save")
    delete_btn = ""
    if not is_new:
        delete_btn = f"""
        <form method=\"post\" action=\"{app_url(f'/formula/{formula_id}/delete')}\" class=\"inline-form\">
          <button type=\"submit\" class=\"btn danger\">删除</button>
        </form>
        """

    comments = [] if is_new else list_comments_by_formula(str(formula_id))
    comment_lines = "\n".join(
        f"[{comment['created_at']}] {comment['content']}" for comment in comments
    )

    body = f"""
      <section class=\"detail\">
        <header class=\"detail-head\">
          <h2>{html.escape(title)}</h2>
          <a class=\"btn\" href=\"{app_url('/')}\">返回</a>
        </header>

        <div class=\"detail-body\">
          <div class=\"editor\">
            <form method=\"post\" action=\"{save_action}\">
              <label>配方名称</label>
              <input name=\"name\" type=\"text\" value=\"{html.escape(formula.get('name', ''))}\" required>

              <label>配方内容</label>
              <textarea name=\"content\" rows=\"18\" required>{html.escape(formula.get('content', ''))}</textarea>

              <div class=\"actions\">
                <button type=\"submit\" class=\"btn primary\">保存</button>
              </div>
            </form>
            {delete_btn}
          </div>

          <aside class=\"comments\">
            <h3>评论区</h3>
            <div id=\"comment-list\" class=\"comment-list\">{html.escape(comment_lines) if comment_lines else '暂无评论'}</div>
            <form id=\"comment-form\" class=\"comment-form\">
              <input id=\"comment-input\" type=\"text\" placeholder=\"输入评论内容\" required>
              <button type=\"submit\" class=\"btn primary\">提交</button>
            </form>
          </aside>
        </div>
      </section>

      <script>
        (() => {{
          const recipeId = {json.dumps(str(formula_id), ensure_ascii=False)};
          const listEl = document.getElementById('comment-list');
          const formEl = document.getElementById('comment-form');
          const inputEl = document.getElementById('comment-input');
          const endpoint = {json.dumps(app_url(f'/formula/{formula_id}/comment'), ensure_ascii=False)};

          if (recipeId === 'new') {{
            formEl.addEventListener('submit', (event) => event.preventDefault());
            inputEl.disabled = true;
            inputEl.placeholder = '请先保存配方后再评论';
            return;
          }}

          function appendComment(comment) {{
            const line = `[${{comment.created_at}}] ${{comment.content}}`;
            const current = listEl.textContent.trim();
            if (!current || current === '暂无评论') {{
              listEl.textContent = line;
              return;
            }}
            listEl.textContent += `\n${{line}}`;
          }}

          formEl.addEventListener('submit', async (event) => {{
            event.preventDefault();
            const text = inputEl.value.trim();
            if (!text) return;

            const params = new URLSearchParams();
            params.set('content', text);

            const response = await fetch(endpoint, {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' }},
              body: params.toString(),
            }});
            if (!response.ok) return;
            const data = await response.json();
            if (!data.comment) return;
            appendComment(data.comment);
            inputEl.value = '';
          }});
        }})();
      </script>
    """
    return shell_html("配方详情", body)


class FormulaHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.redirect(f"{BASE_PATH}/")
            return
        if path in {BASE_PATH, f"{BASE_PATH}/"}:
            query = urllib.parse.parse_qs(parsed.query)
            raw_keyword = query.get("q", [""])[0]
            keyword = raw_keyword.strip()[:MAX_SEARCH_LENGTH]
            self.html_response(render_home(keyword, search_formulas(keyword)))
            return

        if not path.startswith(BASE_PATH):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        app_path = path[len(BASE_PATH):] or "/"
        if app_path == "/static/style.css":
            css = Path("static/style.css").read_text(encoding="utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.end_headers()
            self.wfile.write(css.encode("utf-8"))
            return

        if app_path == "/formula/new":
            self.html_response(render_detail({"name": "", "content": ""}, is_new=True))
            return

        match = re.fullmatch(r"/formula/(\d+)", app_path)
        if match:
            formula = get_formula(match.group(1))
            if not formula:
                self.send_error(HTTPStatus.NOT_FOUND, "Formula not found")
                return
            self.html_response(render_detail(formula))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if not path.startswith(BASE_PATH):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        app_path = path[len(BASE_PATH):] or "/"
        form = self.parse_form_data()
        if form is None:
            return

        if app_path == "/formula/create":
            name = form.get("name", [""])[0]
            content = form.get("content", [""])[0]
            create_formula(name, content)
            self.redirect(app_url("/"))
            return

        save_match = re.fullmatch(r"/formula/(\d+)/save", app_path)
        if save_match:
            formula_id = save_match.group(1)
            name = form.get("name", [""])[0]
            content = form.get("content", [""])[0]
            if not update_formula(formula_id, name, content):
                self.send_error(HTTPStatus.NOT_FOUND, "Formula not found")
                return
            self.redirect(app_url("/"))
            return

        delete_match = re.fullmatch(r"/formula/(\d+)/delete", app_path)
        if delete_match:
            formula_id = delete_match.group(1)
            if not delete_formula(formula_id):
                self.send_error(HTTPStatus.NOT_FOUND, "Formula not found")
                return
            self.redirect(app_url("/"))
            return

        comment_match = re.fullmatch(r"/formula/(\d+)/comment", app_path)
        if comment_match:
            formula_id = comment_match.group(1)
            content = form.get("content", [""])[0]
            new_comment = add_comment(formula_id, content)
            if not new_comment:
                self.send_error(HTTPStatus.BAD_REQUEST, "Comment create failed")
                return
            self.json_response({"ok": True, "comment": new_comment})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def parse_form_data(self) -> Optional[Dict[str, List[str]]]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_data = self.rfile.read(length).decode("utf-8")
            return urllib.parse.parse_qs(raw_data)
        except Exception:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid form data")
            return None

    def html_response(self, content: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def json_response(self, payload: Dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()


if __name__ == "__main__":
    ensure_data_file()
    server = ThreadingHTTPServer((HOST, PORT), FormulaHandler)
    print(f"Serving on http://{HOST}:{PORT}{BASE_PATH}/")
    server.serve_forever()
