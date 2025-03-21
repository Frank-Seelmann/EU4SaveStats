use eu4save::{Eu4File, SegmentedResolver, query::Query};
use eu4save::models::CountryEvent;
use std::{fs, error::Error};
use serde::{Serialize, Deserialize};
use serde_json;
use std::collections::BTreeMap;
use sha2::{Sha256, Digest};
use std::env;
use sqlx::MySqlPool;
use aws_sdk_s3::Client;
use std::fs::File;
use std::io::Write;
use aws_config::meta::region::RegionProviderChain;
use dotenv::dotenv;

#[derive(Serialize, Deserialize, Debug)]
struct CurrentState {
    date: String,
    income: Vec<f64>,
    manpower: f64,
    max_manpower: f64,
    trade_income: f64,
    annual_income: BTreeMap<String, f64>,
}

#[derive(Serialize, Deserialize, Debug)]
struct HistoricalEvent {
    date: String,
    event_type: String,
    details: String,
}

async fn download_from_s3(client: &Client, bucket: &str, key: &str, file_path: &str) -> Result<(), Box<dyn std::error::Error>> {
    let response = client
        .get_object()
        .bucket(bucket)
        .key(key)
        .send()
        .await?;

    let mut file = File::create(file_path)?;
    let bytes = response.body.collect().await?;
    file.write_all(&bytes.into_bytes())?;
    Ok(())
}

// Table to track uploaded files
async fn create_schema(pool: &MySqlPool) -> Result<(), sqlx::Error> {
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

// Calculate the SHA-256 checksum of a file
fn calculate_checksum(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    let result = hasher.finalize();
    format!("{:x}", result)
}

pub async fn run(path: &str) -> Result<(), Box<dyn Error>> {
    let data = fs::read(path)?;

    // Calculate the checksum of the file
    let file_checksum = calculate_checksum(&data);
    let file_name = std::path::Path::new(path)
        .file_name()
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();

    // Connect to MySQL database
    let db_host = env::var("DB_HOST").expect("DB_HOST not set in .env");
    let db_user = env::var("DB_USER").expect("DB_USER not set in .env");
    let db_password = env::var("DB_PASSWORD").expect("DB_PASSWORD not set in .env");
    let db_name = env::var("DB_NAME").expect("DB_NAME not set in .env");

    let db_url = format!("mysql://{}:{}@{}/{}", db_user, db_password, db_host, db_name);

    println!("Checking if database exists at: {}", db_url);

    // Create the database if it doesn't exist
    let admin_db_url = format!("mysql://{}:{}@{}", db_user, db_password, db_host);
    let admin_pool = MySqlPool::connect(&admin_db_url).await?;
    sqlx::query(&format!("CREATE DATABASE IF NOT EXISTS {}", db_name))
        .execute(&admin_pool)
        .await?;

    let pool = MySqlPool::connect(&db_url).await?;
    create_schema(&pool).await?;

    // Check if the file has already been processed
    let existing_file = sqlx::query(
        "SELECT id FROM uploaded_files WHERE file_checksum = ?"
    )
    .bind(&file_checksum)
    .fetch_optional(&pool)
    .await?;

    if existing_file.is_some() {
        println!("File '{}' has already been processed. Skipping...", file_name);
        return Ok(());
    }

    // Insert the file metadata into the database
    sqlx::query(
        "INSERT INTO uploaded_files (file_name, file_checksum) VALUES (?, ?)"
    )
    .bind(&file_name)
    .bind(&file_checksum)
    .execute(&pool)
    .await?;

    // Parse the save file
    let file = Eu4File::from_slice(&data)?;
    let resolver = SegmentedResolver::empty();
    let save = file.parse_save(&resolver)?;

    // Debug: Print metadata and player tag
    println!("Processing file: {}", file_name);
    println!("Player tag: {}", save.meta.player);
    println!("Date: {:?}", save.meta.date);

    // Get the current date from metadata
    let current_date = save.meta.date;

    // Create a Query object for extracting data
    let save_query = Query::from_save(save.clone());

    // Get province owners and nation events
    let province_owners = save_query.province_owners();
    let nation_events = save_query.nation_events(&province_owners);

    // Get player histories to identify all player-controlled countries
    let player_histories = save_query.player_histories(&nation_events);

    // Debug: Print player histories
    println!("Player histories:");
    for player_history in &player_histories {
        println!(
            "Initial: {}, Latest: {}, Stored: {}, Is Human: {}, Player Names: {:?}",
            player_history.history.initial,
            player_history.history.latest,
            player_history.history.stored,
            player_history.is_human,
            player_history.player_names
        );
    }

    // Iterate over all player-controlled countries
    for player_history in player_histories {
        let country_tag = player_history.history.latest.to_string();
        println!("Processing player-controlled country: {}", country_tag);

        // Find the country in the save
        if let Some((_, country)) = save.game.countries.iter().find(|(tag, _)| tag.to_string() == country_tag) {
             // Debug: Print country data
            println!("Country found: {}", country_tag);
            println!("Income: {:?}", country.ledger.income);
            println!("Manpower: {}", country.manpower);
            println!("Max Manpower: {}", country.max_manpower);

            // Extract current state data
            let country_query = save_query.country(&country_tag.parse()?).ok_or("Country not found")?;
            let income = &country.ledger.income;
            let manpower = country.manpower;
            let max_manpower = country.max_manpower;
            let income_breakdown = save_query.country_income_breakdown(&country_query);
            let trade_income = income_breakdown.trade;

            // Extract historical income data
            let player_nation_events = nation_events
                .iter()
                .find(|x| x.initial.to_string() == country_tag || x.latest.to_string() == country_tag)
                .ok_or("Player nation events not found")?;

            let income_statistics = save_query.income_statistics_ledger(player_nation_events);

            // Group income data by year and calculate annual income
            let mut annual_income = BTreeMap::new();
            for point in income_statistics {
                if point.tag.to_string() == country_tag {
                    let annual_value = point.value as f64 * 12.0;
                    annual_income.insert(point.year.to_string(), annual_value);
                }
            }

            // Create current state data
            let current_state = CurrentState {
                date: format!("{:?}", current_date),
                income: income.iter().map(|&i| i as f64).collect(),
                manpower: manpower as f64,
                max_manpower: max_manpower as f64,
                trade_income: trade_income as f64,
                annual_income,
            };

            // Debug: Print current state data
            println!("Current state data for {}: {:?}", country_tag, current_state);

            // Insert current state data
            let income_json = serde_json::to_string(&current_state.income)?;
            sqlx::query(
                "INSERT INTO current_state (file_checksum, country_tag, date, income, manpower, max_manpower, trade_income) VALUES (?, ?, ?, ?, ?, ?, ?)"
            )
            .bind(&file_checksum)
            .bind(&country_tag)
            .bind(&current_state.date)
            .bind(income_json)
            .bind(current_state.manpower)
            .bind(current_state.max_manpower)
            .bind(current_state.trade_income)
            .execute(&pool)
            .await?;

            // Debug: Confirm insertion
            println!("Data for country {} inserted into database.", country_tag);

            // Extract historical events
            let mut historical_events = Vec::new();
            for event in &country.history.events {
                let (event_date, country_event) = event;

                let (event_type, details) = match country_event {
                    CountryEvent::Monarch(monarch) => (
                        "Monarch",
                        format!("Name: {}, Dip: {}, Adm: {}, Mil: {}", monarch.name, monarch.dip, monarch.adm, monarch.mil),
                    ),
                    CountryEvent::Heir(heir) => (
                        "Heir",
                        format!("Name: {}, Dip: {}, Adm: {}, Mil: {}", heir.name, heir.dip, heir.adm, heir.mil),
                    ),
                    CountryEvent::Leader(leader) => (
                        "Leader",
                        format!("Name: {}, Kind: {:?}", leader.name, leader.kind),
                    ),
                    CountryEvent::Capital(province_id) => (
                        "Capital",
                        format!("Province ID: {}", province_id),
                    ),
                    CountryEvent::ChangedCountryNameFrom(name) => (
                        "ChangedCountryNameFrom",
                        format!("From: {}", name),
                    ),
                    CountryEvent::ChangedCountryAdjectiveFrom(adjective) => (
                        "ChangedCountryAdjectiveFrom",
                        format!("From: {}", adjective),
                    ),
                    CountryEvent::ChangedCountryMapColorFrom(color) => (
                        "ChangedCountryMapColorFrom",
                        format!("From: {:?}", color),
                    ),
                    CountryEvent::Queen(queen) => (
                        "Queen",
                        format!("Name: {}, Dip: {}, Adm: {}, Mil: {}", queen.name, queen.dip, queen.adm, queen.mil),
                    ),
                    CountryEvent::NationalFocus(focus) => (
                        "NationalFocus",
                        format!("Focus: {:?}", focus),
                    ),
                    CountryEvent::AddAcceptedCulture(culture) => (
                        "AddAcceptedCulture",
                        format!("Culture: {}", culture),
                    ),
                    _ => (
                        "Unknown",
                        format!("{:?}", country_event),
                    ),
                };

                historical_events.push(HistoricalEvent {
                    date: format!("{:?}", event_date),
                    event_type: event_type.to_string(),
                    details,
                });
            }

            // Insert historical events
            for event in historical_events {
                sqlx::query(
                    "INSERT INTO historical_events (file_checksum, country_tag, date, event_type, details) VALUES (?, ?, ?, ?, ?)"
                )
                .bind(&file_checksum)
                .bind(&country_tag)
                .bind(event.date)
                .bind(event.event_type)
                .bind(event.details)
                .execute(&pool)
                .await?;
            }

            // Insert annual income data
            for (year, income) in current_state.annual_income {
                sqlx::query(
                    "INSERT INTO annual_income (file_checksum, country_tag, year, income) VALUES (?, ?, ?, ?)"
                )
                .bind(&file_checksum)
                .bind(&country_tag)
                .bind(year)
                .bind(income)
                .execute(&pool)
                .await?;
            }

            println!("Data for country {} successfully written to SQLite database.", country_tag);
        } else {
            println!("Error: Country '{}' not found in save.", country_tag);
        }
    }

    println!("File '{}' processed successfully.", file_name);
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Load environment variables from .env file
    dotenv().ok();

    // Access environment variables
    let db_host = env::var("DB_HOST").expect("DB_HOST not set in .env");
    let db_user = env::var("DB_USER").expect("DB_USER not set in .env");
    let db_password = env::var("DB_PASSWORD").expect("DB_PASSWORD not set in .env");
    let db_name = env::var("DB_NAME").expect("DB_NAME not set in .env");

    let db_url = format!("mysql://{}:{}@{}/{}", db_user, db_password, db_host, db_name);

    let args: Vec<String> = env::args().collect();

    if args.len() > 1 && args[1] == "--init-db" {
        // Initialize the database schema
        let admin_db_url = format!("mysql://{}:{}@{}", db_user, db_password, db_host);
        let admin_pool = MySqlPool::connect(&admin_db_url).await?;
        sqlx::query(&format!("CREATE DATABASE IF NOT EXISTS {}", db_name))
            .execute(&admin_pool)
            .await?;

        let pool = MySqlPool::connect(&db_url).await?;
        create_schema(&pool).await?;
        println!("Database schema initialized successfully.");
        return Ok(());
    }

    if args.len() > 1 && args[1] == "--help" {
        println!("Usage: {} <s3_key>", args[0]);
        return Ok(());
    }

    // Normal execution (process a file)
    if args.len() < 2 {
        eprintln!("Usage: {} <s3_key>", args[0]);
        return Ok(());
    }

    let s3_key = &args[1];
    let s3_bucket = "eusavestats-bucket";
    let local_file_path = format!("/tmp/{}", s3_key.split('/').last().unwrap_or("file.eu4"));

    let config = aws_config::load_from_env().await;
    let client = Client::new(&config);

    // Ensure the download_from_s3 function is awaited
    download_from_s3(&client, s3_bucket, s3_key, &local_file_path).await?;

    if let Err(e) = run(&local_file_path).await {
        eprintln!("Error: {}", e);
    }

    std::fs::remove_file(local_file_path)?;

    Ok(())
}