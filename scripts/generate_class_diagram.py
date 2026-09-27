"""Generate a deterministic Mermaid class diagram without importing the app."""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import tokenize

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "Class_diagram.generated.md"


def read_sources(root: Path) -> dict[str, str]:
    """Only root-level application modules; never traverse venvs or tests."""
    sources = {}
    for path in sorted(root.glob("*.py")):
        if not path.name.startswith("test_"):
            with tokenize.open(path) as stream:
                sources[path.stem] = stream.read()
    return sources


def render_diagram(sources: dict[str, str]) -> str:
    trees = {name: ast.parse(source, filename=f"{name}.py")
             for name, source in sorted(sources.items())}
    classes = {(module, node.name): node
               for module, tree in trees.items() for node in tree.body
               if isinstance(node, ast.ClassDef)}
    identifiers = {key: f"C{index}" for index, key in enumerate(sorted(classes))}
    lines = ["# クラス図（自動生成）", "",
             "`python scripts/generate_class_diagram.py` で更新。直接編集しないでください。", "",
             "ルート直下のアプリモジュールのトップレベルクラスと公開メソッド・プロパティを表示します。",
             "破線はクラス内の名前参照（型注釈を含む）であり、所有関係や実行時の呼び出しを意味しません。",
             "動的参照、文字列型注釈、別名の型定義経由の参照は解決しません。", "", "```mermaid", "classDiagram"]
    for key in sorted(classes):
        node = classes[key]
        identifier = identifiers[key]
        lines.append(f'    class {identifier}["{key[0]}.{key[1]}"] {{')
        members = set()
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name.startswith("_"):
                    continue
                is_property = any(isinstance(d, ast.Name) and d.id == "property"
                                  for d in child.decorator_list)
                members.add(f"+{child.name}" + ("" if is_property else "()"))
        lines.extend(f"        {member}" for member in sorted(members))
        lines.append("    }")
    edges = set()
    for (module, name), node in classes.items():
        bindings = {class_name: identifiers[(module, class_name)]
                    for source_module, class_name in classes if source_module == module}
        for statement in trees[module].body:
            if isinstance(statement, ast.ImportFrom) and statement.level == 0:
                for alias in statement.names:
                    target = identifiers.get((statement.module, alias.name))
                    if target:
                        bindings[alias.asname or alias.name] = target
            elif isinstance(statement, ast.Import):
                for alias in statement.names:
                    for (source_module, class_name), target in identifiers.items():
                        if source_module == alias.name:
                            bindings[f"{alias.asname or alias.name}.{class_name}"] = target
        source = identifiers[(module, name)]
        bases = {bindings.get(ast.unparse(base)) for base in node.bases}
        references = {bindings.get(ast.unparse(item)) for item in ast.walk(node)
                      if isinstance(item, (ast.Name, ast.Attribute))}
        for target in references - {None, source}:
            edges.add(f"    {target} <|-- {source}" if target in bases
                      else f"    {source} ..> {target} : references")
    lines.extend(sorted(edges))
    lines.extend(["```", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the saved diagram is stale")
    args = parser.parse_args(argv)
    rendered = render_diagram(read_sources(ROOT))
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            print("Class diagram is stale: run python scripts/generate_class_diagram.py")
            return 1
        print("Class diagram is current")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Generated {OUTPUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
