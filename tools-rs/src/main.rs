mod commands;
mod json_db;
mod sqlite_db;

use anyhow::Result;
use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "db-tool")]
#[command(about = "SQLite shadow database tools for the actress classifier JSON DB")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
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
    }
}
