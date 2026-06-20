#!/usr/bin/env python3
import os
import re
import sys

def build_gas():
    # 경로 설정
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_dir = os.path.join(project_root, "app")
    gas_dir = os.path.join(project_root, "gas")

    index_path = os.path.join(app_dir, "index.html")
    css_path = os.path.join(app_dir, "styles.css")
    js_path = os.path.join(app_dir, "app.js")

    print("Building Apps Script template...")

    # 파일 존재 여부 확인
    for p in [index_path, css_path, js_path]:
        if not os.path.exists(p):
            print(f"Error: Required file not found at {p}", file=sys.stderr)
            sys.exit(1)

    # 내용 읽기
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()

    # CSS 인라인화
    # <link rel="stylesheet" href="./styles.css"> 태그 찾아서 치환
    css_pattern = re.compile(r'<link\s+[^>]*href=["\'](?:\./)?styles\.css(?:\?[^"\']*)?["\'][^>]*>')
    css_match = css_pattern.search(html)
    if css_match:
        matched_tag = css_match.group(0)
        html = html.replace(matched_tag, f"<style>\n{css}\n</style>")
        print("✔ Successfully inlined CSS.")
    else:
        print("⚠ Warning: CSS link not found in index.html, skipping inlining.")

    # JS 인라인화
    # <script src="./app.js?v=..."></script> 태그 찾아서 치환
    js_pattern = re.compile(r'<script\s+[^>]*src=["\'](?:\./)?app\.js(?:\?[^"\']*)?["\'][^>]*>\s*</script>')
    js_match = js_pattern.search(html)
    if js_match:
        matched_tag = js_match.group(0)
        html = html.replace(matched_tag, f"<script>\n{js}\n</script>")
        print("✔ Successfully inlined JS.")
    else:
        print("⚠ Warning: JS script tag not found in index.html, skipping inlining.")

    # gas 디렉토리가 없으면 생성
    if not os.path.exists(gas_dir):
        os.makedirs(gas_dir)
        print(f"Created directory: {gas_dir}")

    # 빌드 결과물 저장
    out_path = os.path.join(gas_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"🎉 Build completed successfully! Output: {out_path}")

if __name__ == "__main__":
    build_gas()
