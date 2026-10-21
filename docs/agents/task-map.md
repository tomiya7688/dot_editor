# Task to source, tests and specification map

Consult this **only when the task's source and matching tests are not already obvious**. The table maps recurring dot_editor work; it is not an exhaustive code index. Read the source/test at the indicated path, confirm the current owner, and update a stale row along with the moved implementation.

| Change category | Start with source | Matching tests/verification | Contract when needed |
| --- | --- | --- | --- |
| Rust retained detail or resolution | [canvas.rs](../../rust/crates/hyper-dot-core/src/canvas.rs) | [retained projection](../../rust/crates/hyper-dot-core/tests/retained_projection.rs) | [resolution model](../Non_destructive_resolution.md) |
| Rust project JSON | [import module](../../rust/crates/hyper-dot-core/src/project_json_import.rs) | [Rust JSON import tests](../../rust/crates/hyper-dot-core/tests/project_json_import.rs), [Python↔Rust fixture check](../../scripts/test_rust_json_compat.py) | [project JSON compatibility](../Non_destructive_resolution.md) |
| Python CLI / Command API | [pixel_cli.py](../../src/pixel_cli.py), [pixel_commands.py](../../src/pixel_commands.py) | [CLI tests](../../tests/test_pixel_cli.py), [command tests](../../tests/test_commands.py) | [Command API](../Command_API.md), [detail operations](../CUI_detail_operations.md) |
| Python layers or save/load | [pixel_layers.py](../../src/pixel_layers.py), [pixel_backend.py](../../src/pixel_backend.py) | [layer tests](../../tests/test_pixel_layers.py), [JSON tests](../../tests/test_project_json.py) | [detail preservation](../Non_destructive_resolution.md) |
| GUI keyboard or menus | [dot_editor.py](../../src/dot_editor.py) | [focus tests](../../tests/test_keyboard_focus_regions.py), [menu tests](../../tests/test_menu_structure.py) | [user-visible behavior](../../README.md) |
| Packaging/CI | [CI workflow](../../.github/workflows/ci.yml), [Windows builder](../../scripts/build_windows.ps1) | [distribution smoke](../../scripts/smoke_distribution.py), [quickstart regression](../../tests/test_readme_quickstart.py) | [quality gates](quality-gates.md), [internal build steps](development.md) |
| Agent rules / documentation isolation | [policy checker](../../scripts/check_agent_policy.py) | [agent-policy tests](../../tests/test_agent_policy.py) | [collaboration](collaboration.md), [quality gates](quality-gates.md) |

If a change crosses a public API, Rust/Python project format or shared backend boundary, follow its consumers, fixtures and affected tests beyond the initial row. If the path is missing or the map appears out of date, use targeted search instead of inventing a replacement or treating the missing check as passed.
