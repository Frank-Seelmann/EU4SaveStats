use eu4save::{Eu4File, SegmentedResolver, query::Query, CountryTag};
use eu4save::models::CountryEvent;
use std::{fs, error::Error};
use serde::{Serialize, Deserialize};
use serde_json;
use std::collections::BTreeMap;
use sqlx::{sqlite::SqlitePool, Sqlite, migrate::MigrateDatabase};

#[derive(Serialize, Deserialize)]
struct CurrentState {
    date: String,
    income: Vec<f64>,
    manpower: f64,
    max_manpower: f64,
    trade_income: f64,
    annual_income: BTreeMap<String, f64>,
}

#[derive(Serialize, Deserialize)]
struct HistoricalEvent {
    date: String,
    event_type: String,
    details: String,
}

async fn create_schema(pool: &SqlitePool) -> Result<(), sqlx::Error> {
    sqlx::query(
        "PRAGMA foreign_keys = ON;"
    ).execute(pool).await?;

    sqlx::query(
        "CREATE TABLE IF NOT EXISTS current_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            income TEXT NOT NULL,
            manpower REAL NOT NULL,
            max_manpower REAL NOT NULL,
            trade_income REAL NOT NULL
        );"
    ).execute(pool).await?;

    sqlx::query(
        "CREATE TABLE IF NOT EXISTS historical_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details TEXT NOT NULL
        );"
    ).execute(pool).await?;

    sqlx::query(
        "CREATE TABLE IF NOT EXISTS annual_income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year TEXT NOT NULL,
            income REAL NOT NULL
        );"
    ).execute(pool).await?;

    Ok(())
}

pub async fn run(path: &str) -> Result<(), Box<dyn Error>> {
    let data = fs::read(path)?;

    // Parse the save file
    let file = Eu4File::from_slice(&data)?;
    let resolver = SegmentedResolver::empty();
    let save = file.parse_save(&resolver)?;

    // Get the player tag from metadata
    let player_tag = save.meta.player.clone();
    let country_tag = CountryTag::create(player_tag.as_bytes()).map_err(|_| "Invalid country tag.")?;

    // Create a Query object for extracting data
    let save_query = Query::from_save(save.clone());

    // Initialize current_date to the save date
    let current_date = save.meta.date;

    // Find the player's country in the save
    if let Some((_, country)) = save.game.countries.iter().find(|(tag, _)| *tag == country_tag) {
        // Extract current state data
        let country_query = save_query.country(&country_tag).ok_or("Country not found")?;
        let income = &country.ledger.income;
        let manpower = country.manpower;
        let max_manpower = country.max_manpower;
        let income_breakdown = save_query.country_income_breakdown(&country_query);
        let trade_income = income_breakdown.trade;

        // Extract historical income data
        let province_owners = save_query.province_owners();
        let nation_events = save_query.nation_events(&province_owners);
        let player_nation_events = nation_events
            .iter()
            .find(|x| x.initial == country_tag)
            .ok_or("Player nation events not found")?;

        let income_statistics = save_query.income_statistics_ledger(player_nation_events);

        // Group income data by year and calculate annual income
        let mut annual_income = BTreeMap::new();
        for point in income_statistics {
            if point.tag == country_tag {
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

        // Connect to SQLite database
        let db_url = "sqlite:///C:/Users/frank/Desktop/Cloud Computing/EU4SaveStats/sqlite.db";
        println!("Checking if database exists at: {}", db_url);

        if !Sqlite::database_exists(db_url).await.unwrap_or(false) {
            println!("Database does not exist. Creating it...");
            Sqlite::create_database(db_url).await.unwrap();
            println!("Database created successfully.");
        } else {
            println!("Database already exists.");
        }

        let pool = SqlitePool::connect(db_url).await.unwrap();
        create_schema(&pool).await?;

        // Insert current state data
        let income_json = serde_json::to_string(&current_state.income)?;
        sqlx::query(
            "INSERT INTO current_state (date, income, manpower, max_manpower, trade_income) VALUES (?, ?, ?, ?, ?)"
        )
        .bind(&current_state.date)
        .bind(income_json)
        .bind(current_state.manpower)
        .bind(current_state.max_manpower)
        .bind(current_state.trade_income)
        .execute(&pool)
        .await?;

        // Insert historical events
        for event in historical_events {
            sqlx::query(
                "INSERT INTO historical_events (date, event_type, details) VALUES (?, ?, ?)"
            )
            .bind(event.date)
            .bind(event.event_type)
            .bind(event.details)
            .execute(&pool)
            .await?;
        }

        // Insert annual income data
        for (year, income) in current_state.annual_income {
            sqlx::query(
                "INSERT INTO annual_income (year, income) VALUES (?, ?)"
            )
            .bind(year)
            .bind(income)
            .execute(&pool)
            .await?;
        }

        println!("Data successfully written to SQLite database.");
    } else {
        println!("Error: Player country '{}' not found in save.", player_tag);
    }

    Ok(())
}

#[async_std::main] // Use async_std::main to enable async main
async fn main() {
    if let Err(e) = run("../stuff/mp_Scotland1474_07_04.eu4").await {
        eprintln!("Error: {}", e);
    }
}