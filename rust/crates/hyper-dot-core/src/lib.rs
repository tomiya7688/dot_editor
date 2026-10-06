//! Rust core for the Hyper Dot project and rendering model.
//!
//! This crate is the canonical implementation target. The Python editor remains
//! available as a reference implementation and GUI during the migration.

#![forbid(unsafe_code)]

pub mod canvas;
mod field_bounds;
mod field_patch;
mod flood_region;
pub mod project_json;
mod project_json_error;
mod project_json_import;
pub mod raster;
mod rational_coordinate;
pub mod resolution;
pub mod resolution_field;
mod split_cell;
mod strict_json;
