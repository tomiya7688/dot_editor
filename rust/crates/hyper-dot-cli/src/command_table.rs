//! The complete command tree of `pixel-cli`, as data.

use crate::command_spec::{CommandSpec, FlagSpec, Handler};
use crate::{
    canvas_commands, detail_commands, export_commands, layer_commands, pixel_commands,
    project_commands, status_command,
};

const DISCARD: FlagSpec = FlagSpec {
    name: "--discard-detail",
    short: None,
    values: 0,
    summary: "discard retained detail instead of preserving it",
};
const CHILD: FlagSpec = FlagSpec {
    name: "--child",
    short: None,
    values: 2,
    summary: "target child cell CX CY (each 0 or 1) of a split cell",
};
const LAYER: FlagSpec = FlagSpec {
    name: "--layer",
    short: None,
    values: 1,
    summary: "layer name to act on (default: the selected layer)",
};
const FORCE: FlagSpec = FlagSpec {
    name: "--force",
    short: None,
    values: 0,
    summary: "replace the project file if it already exists",
};
const SIZE_NEW: FlagSpec = FlagSpec {
    name: "--size",
    short: None,
    values: 1,
    summary: "square canvas of N x N cells",
};
const RESOLUTION_NEW: FlagSpec = FlagSpec {
    name: "--resolution",
    short: None,
    values: 2,
    summary: "canvas of W x H cells",
};
const OUTPUT: FlagSpec = FlagSpec {
    name: "--output",
    short: Some("-o"),
    values: 1,
    summary: "PNG file to write (required)",
};
const SIZE_EXPORT: FlagSpec = FlagSpec {
    name: "--size",
    short: None,
    values: 1,
    summary: "enlarge the natural render to N x N (not smaller than natural)",
};
const RESOLUTION_EXPORT: FlagSpec = FlagSpec {
    name: "--resolution",
    short: None,
    values: 2,
    summary: "render retained detail directly at W x H",
};

/// 受け付けるすべてのコマンド。語の並びが長く一致したものが選ばれる。
pub static COMMANDS: [CommandSpec; 22] = [
    CommandSpec {
        path: &["project", "new"],
        summary: "create an empty project file",
        positionals: &[],
        flags: &[SIZE_NEW, RESOLUTION_NEW, FORCE],
        handler: Handler::Create(project_commands::new_project),
    },
    CommandSpec {
        path: &["project", "info"],
        summary: "describe the project",
        positionals: &[],
        flags: &[],
        handler: Handler::Read(project_commands::project_info),
    },
    CommandSpec {
        path: &["project", "validate"],
        summary: "check that the project loads and is consistent",
        positionals: &[],
        flags: &[],
        handler: Handler::Read(project_commands::validate_project),
    },
    CommandSpec {
        path: &["canvas", "info"],
        summary: "describe the canvas resolution and layers",
        positionals: &[],
        flags: &[],
        handler: Handler::Read(canvas_commands::canvas_info),
    },
    CommandSpec {
        path: &["canvas", "resolution", "set"],
        summary: "change the logical resolution of every layer",
        positionals: &["width", "height"],
        flags: &[DISCARD],
        handler: Handler::Edit(canvas_commands::set_resolution),
    },
    CommandSpec {
        path: &["pixel", "paint"],
        summary: "paint a cell of the selected layer",
        positionals: &["x", "y", "color"],
        flags: &[CHILD, DISCARD],
        handler: Handler::Edit(pixel_commands::paint_pixel),
    },
    CommandSpec {
        path: &["pixel", "erase"],
        summary: "make a cell of the selected layer transparent",
        positionals: &["x", "y"],
        flags: &[CHILD, DISCARD],
        handler: Handler::Edit(pixel_commands::erase_pixel),
    },
    CommandSpec {
        path: &["pixel", "fill"],
        summary: "fill the connected region of equal color",
        positionals: &["x", "y", "color"],
        flags: &[DISCARD],
        handler: Handler::Edit(pixel_commands::fill_region),
    },
    CommandSpec {
        path: &["pixel", "sample"],
        summary: "read the color of a cell of the selected layer",
        positionals: &["x", "y"],
        flags: &[CHILD],
        handler: Handler::Read(pixel_commands::sample_pixel),
    },
    CommandSpec {
        path: &["detail", "split"],
        summary: "split a cell into four child cells",
        positionals: &["x", "y"],
        flags: &[],
        handler: Handler::Edit(detail_commands::split_cell),
    },
    CommandSpec {
        path: &["detail", "split-region"],
        summary: "split every cell of a rectangle in one step",
        positionals: &["x", "y", "width", "height"],
        flags: &[],
        handler: Handler::Edit(detail_commands::split_region),
    },
    CommandSpec {
        path: &["detail", "discard"],
        summary: "discard the retained detail of a cell, keeping its color",
        positionals: &["x", "y"],
        flags: &[],
        handler: Handler::Edit(detail_commands::discard_detail),
    },
    CommandSpec {
        path: &["detail", "info"],
        summary: "report whether a cell is split or holds retained detail",
        positionals: &["x", "y"],
        flags: &[],
        handler: Handler::Read(detail_commands::detail_info),
    },
    CommandSpec {
        path: &["layer", "add"],
        summary: "add an empty layer on top and select it",
        positionals: &["name"],
        flags: &[],
        handler: Handler::Edit(layer_commands::add_layer),
    },
    CommandSpec {
        path: &["layer", "remove"],
        summary: "remove a layer (at least one must remain)",
        positionals: &[],
        flags: &[LAYER],
        handler: Handler::Edit(layer_commands::remove_layer),
    },
    CommandSpec {
        path: &["layer", "select"],
        summary: "select the layer that edits apply to",
        positionals: &["name"],
        flags: &[],
        handler: Handler::Edit(layer_commands::select_layer),
    },
    CommandSpec {
        path: &["layer", "rename"],
        summary: "rename a layer",
        positionals: &["new_name"],
        flags: &[LAYER],
        handler: Handler::Edit(layer_commands::rename_layer),
    },
    CommandSpec {
        path: &["layer", "move"],
        summary: "move a layer one step `up` or `down` in compositing order",
        positionals: &["direction"],
        flags: &[LAYER],
        handler: Handler::Edit(layer_commands::move_layer),
    },
    CommandSpec {
        path: &["layer", "visibility"],
        summary: "show (`on`) or hide (`off`) a layer",
        positionals: &["state"],
        flags: &[LAYER],
        handler: Handler::Edit(layer_commands::set_visibility),
    },
    CommandSpec {
        path: &["layer", "list"],
        summary: "list layers from bottom to top",
        positionals: &[],
        flags: &[],
        handler: Handler::Read(layer_commands::list_layers),
    },
    CommandSpec {
        path: &["export", "render"],
        summary: "composite the visible layers into a PNG file",
        positionals: &[],
        flags: &[OUTPUT, SIZE_EXPORT, RESOLUTION_EXPORT],
        handler: Handler::Export(export_commands::render_png),
    },
    CommandSpec {
        path: &["status"],
        summary: "show resolution, selected layer and layers at once",
        positionals: &[],
        flags: &[],
        handler: Handler::Read(status_command::status),
    },
];
