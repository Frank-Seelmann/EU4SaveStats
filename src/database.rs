use sqlx::{MySqlPool, Error};
use serde_json;
use sha2::{Sha256, Digest};
use std::collections::BTreeMap;
use serde::{Serialize, Deserialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct CurrentState {
    pub date: String,
    pub income: Vec<f64>,
    pub manpower: f64,
    pub max_manpower: f64,
    pub trade_income: f64,
    pub annual_income: BTreeMap<String, f64>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct HistoricalEvent {
    pub date: String,
    pub event_type: String,
    pub details: String,
}

/// Creates all required database tables if they don't exist
pub async fn create_schema(pool: &MySqlPool) -> Result<(), Error> {
    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_checksum VARCHAR(64) NOT NULL UNIQUE,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        "#
    ).execute(pool).await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS current_state (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_checksum TEXT NOT NULL,
            country_tag TEXT NOT NULL,
            date TEXT NOT NULL,
            income TEXT NOT NULL,
            manpower FLOAT NOT NULL,
            max_manpower FLOAT NOT NULL,
            trade_income FLOAT NOT NULL
        );
        "#
    ).execute(pool).await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS historical_events (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_checksum TEXT NOT NULL,
            country_tag TEXT NOT NULL,
            date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details TEXT NOT NULL
        );
        "#
    ).execute(pool).await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS annual_income (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_checksum TEXT NOT NULL,
            country_tag TEXT NOT NULL,
            year TEXT NOT NULL,
            income FLOAT NOT NULL
        );
        "#
    ).execute(pool).await?;

    Ok(())
}

/// Checks if a file with the given checksum has already been processed
pub async fn check_existing_file(pool: &MySqlPool, checksum: &str) -> Result<bool, Error> {
    let existing = sqlx::query(
        "SELECT id FROM uploaded_files WHERE file_checksum = ?"
    )
    .bind(checksum)
    .fetch_optional(pool)
    .await?;
    
    Ok(existing.is_some())
}

/// Records file metadata in the database
pub async fn insert_file_metadata(pool: &MySqlPool, name: &str, checksum: &str) -> Result<(), Error> {
    sqlx::query(
        "INSERT INTO uploaded_files (file_name, file_checksum) VALUES (?, ?)"
    )
    .bind(name)
    .bind(checksum)
    .execute(pool)
    .await?;
    Ok(())
}

/// Saves current state data for a country
pub async fn save_current_state(
    pool: &MySqlPool, 
    checksum: &str, 
    country_tag: &str, 
    state: &CurrentState
) -> Result<(), Box<dyn std::error::Error>> {
    let income_json = serde_json::to_string(&state.income)
        .map_err(|e| Box::new(e) as Box<dyn std::error::Error>)?;
    
    sqlx::query(
        "INSERT INTO current_state (file_checksum, country_tag, date, income, manpower, max_manpower, trade_income) VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    .bind(checksum)
    .bind(country_tag)
    .bind(&state.date)
    .bind(income_json)
    .bind(state.manpower)
    .bind(state.max_manpower)
    .bind(state.trade_income)
    .execute(pool)
    .await?;
    Ok(())
}

/// Saves a historical event for a country
pub async fn save_historical_event(pool: &MySqlPool, checksum: &str, country_tag: &str, event: &HistoricalEvent) -> Result<(), Error> {
    sqlx::query(
        "INSERT INTO historical_events (file_checksum, country_tag, date, event_type, details) VALUES (?, ?, ?, ?, ?)"
    )
    .bind(checksum)
    .bind(country_tag)
    .bind(&event.date)
    .bind(&event.event_type)
    .bind(&event.details)
    .execute(pool)
    .await?;
    Ok(())
}

/// Saves annual income data for a country
pub async fn save_annual_income(pool: &MySqlPool, checksum: &str, country_tag: &str, year: &str, income: f64) -> Result<(), Error> {
    sqlx::query(
        "INSERT INTO annual_income (file_checksum, country_tag, year, income) VALUES (?, ?, ?, ?)"
    )
    .bind(checksum)
    .bind(country_tag)
    .bind(year)
    .bind(income)
    .execute(pool)
    .await?;
    Ok(())
}

/// Calculates SHA-256 checksum of file data
pub fn calculate_checksum(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    format!("{:x}", hasher.finalize())
}