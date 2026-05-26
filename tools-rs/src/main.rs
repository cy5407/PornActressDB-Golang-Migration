mod commands;
mod json_db;
mod migrate;
mod query;
mod runtime_import;
mod sqlite_db;
mod v3_schema;
mod verify;

use anyhow::Result;
use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "db-tool")]
#[command(
    about = "SQLite tooling for the actress classifier: legacy shadow-DB subcommands (db-init / db-import-json / db-stats / db-compare-json / db-benchmark / query) plus v3 runtime helpers (db-import-json-v3 / db-verify / db-migrate)."
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
#[allow(clippy::enum_variant_names)] // Db prefix maps to CLI namespace (db-init / db-import-json / ...).
enum Command {
    DbInit {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long, default_value_t = false)]
        replace: bool,
    },
    DbImportJson {
        #[arg(
            long,
            help = "JSON DB source. Auto journal inference only applies when the file name is exactly data.json."
        )]
        json: PathBuf,
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(
            long,
            help = "Journal path to validate. Required for non-standard JSON file names if journal consistency should be checked."
        )]
        journal: Option<PathBuf>,
        #[arg(long, default_value_t = false)]
        replace: bool,
        #[arg(long, default_value_t = false)]
        allow_dirty_journal: bool,
    },
    /// Import a JSON DB into the runtime v3 SQLite schema.
    DbImportJsonV3 {
        #[arg(long)]
        json: PathBuf,
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long, default_value_t = false)]
        replace: bool,
        #[arg(long, default_value_t = false)]
        auto_create_missing_actresses: bool,
    },
    DbStats {
        #[arg(long)]
        sqlite: PathBuf,
    },
    DbCompareJson {
        #[arg(
            long,
            help = "JSON DB source. Auto journal inference only applies when the file name is exactly data.json."
        )]
        json: PathBuf,
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(
            long,
            help = "Journal path to validate. Required for non-standard JSON file names if journal consistency should be checked."
        )]
        journal: Option<PathBuf>,
        #[arg(long, default_value_t = false)]
        allow_dirty_journal: bool,
        #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
        fail_on_mismatch: bool,
    },
    DbBenchmark {
        #[arg(long)]
        json: PathBuf,
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long, default_value_t = 10)]
        iterations: usize,
    },
    /// Read-only diagnostic queries against the shadow DB.
    Query {
        #[command(subcommand)]
        sub: query::QueryCmd,
    },
    /// Verify structural integrity of a v3 runtime SQLite database.
    DbVerify {
        #[arg(long)]
        sqlite: PathBuf,
    },
    /// Migrate a v3 runtime SQLite database (only v3 → v3 no-op today).
    DbMigrate {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long, default_value_t = v3_schema::V3_SCHEMA_VERSION)]
        target: i32,
    },
}

fn main() {
    if let Err(err) = run() {
        eprintln!("{err:#}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    match Cli::parse().command {
        Command::DbInit { sqlite, replace } => commands::db_init(&sqlite, replace),
        Command::DbImportJson {
            json,
            sqlite,
            journal,
            replace,
            allow_dirty_journal,
        } => commands::db_import_json(
            &json,
            &sqlite,
            journal.as_deref(),
            replace,
            allow_dirty_journal,
        ),
        Command::DbImportJsonV3 {
            json,
            sqlite,
            replace,
            auto_create_missing_actresses,
        } => runtime_import::run(
            &json,
            &sqlite,
            runtime_import::ImportOptions {
                replace,
                auto_create_missing_actresses,
            },
        ),
        Command::DbStats { sqlite } => commands::db_stats(&sqlite),
        Command::DbCompareJson {
            json,
            sqlite,
            journal,
            allow_dirty_journal,
            fail_on_mismatch,
        } => commands::db_compare_json(
            &json,
            &sqlite,
            journal.as_deref(),
            allow_dirty_journal,
            fail_on_mismatch,
        ),
        Command::DbBenchmark {
            json,
            sqlite,
            iterations,
        } => commands::db_benchmark(&json, &sqlite, iterations),
        Command::Query { sub } => query::run(sub),
        Command::DbVerify { sqlite } => verify::run(&sqlite),
        Command::DbMigrate { sqlite, target } => migrate::run(&sqlite, target),
    }
}
