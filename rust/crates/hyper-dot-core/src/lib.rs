//! Rust core for the Hyper Dot project and rendering model.
//!
//! This crate is the canonical implementation target. The Python editor remains
//! available as a reference implementation and GUI during the migration.

#![forbid(unsafe_code)]

mod field_bounds;
mod field_patch;
pub mod raster;
mod rational_coordinate;
pub mod resolution;
pub mod resolution_field;
