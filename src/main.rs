mod auth;
mod database;
mod parser;

use aws_sdk_s3::Client;
use database::*;
use dotenv::dotenv;
use parser::*;
use serde::Serialize;
use sqlx::MySqlPool;
use std::error::Error;
use std::io::Write;
use std::{env, fs};

#[derive(Serialize)]
struct AuthResponse {
    id: i64,
    username: String,
    email: String,
    password_hash: String,
}

async fn download_from_s3(
    client: &Client,
    bucket: &str,
    key: &str,
    file_path: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let response = client.get_object().bucket(bucket).key(key).send().await?;

    let mut file = fs::File::create(file_path)?;
    let bytes = response.body.collect().await?;
    file.write_all(&bytes.into_bytes())?;
    Ok(())
}

async fn handle_auth_command(
    pool: &MySqlPool,
    args: &[String],
) -> Result<(), Box<dyn std::error::Error>> {
    match args[1].as_str() {
        "register" => {
            if args.len() < 5 {
                eprintln!("Usage: {} register <username> <email> <password>", args[0]);
                return Ok(());
            }
            let user = match auth::register_user(pool, &args[2], &args[3], &args[4]).await {
                Ok(user) => user,
                Err(e) => return Err(Box::new(e) as Box<dyn std::error::Error>),
            };

            let response = AuthResponse {
                id: user.id,
                username: user.username,
                email: user.email,
                password_hash: user.password_hash,
            };
            println!("{}", serde_json::to_string(&response)?);
        }
        "login" => {
            if args.len() < 4 {
                eprintln!("Usage: {} login <username> <password>", args[0]);
                return Ok(());
            }
            let user = auth::login_user(pool, &args[2], &args[3])
                .await
                .map_err(|e| -> Box<dyn std::error::Error> { Box::new(e) })?;

            let response = AuthResponse {
                id: user.id,
                username: user.username,
                email: user.email,
                password_hash: user.password_hash,
            };
            println!("{}", serde_json::to_string(&response)?);
        }
        "verify" => {
            if args.len() < 4 {
                eprintln!("Usage: {} verify <user_id> <password>", args[0]);
                return Ok(());
            }
            let user_id = args[2].parse()?;
            let password = &args[3];
            let is_valid = auth::verify_user_password(pool, user_id, password)
                .await
                .map_err(|e| -> Box<dyn std::error::Error> { Box::new(e) })?;
            println!("{}", is_valid);
        }
        _ => {
            eprintln!("Unknown auth command: {}", args[1]);
        }
    }
    Ok(())
}

pub async fn run(path: &str, user_id: i64) -> Result<(), Box<dyn Error>> {
    // Verify file exists
    if !std::path::Path::new(path).exists() {
        return Err(format!("File not found at path: {}", path).into());
    }

    let data = fs::read(path)?;
    let file_checksum = calculate_checksum(&data);
    let file_name = std::path::Path::new(path)
        .file_name()
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();

    println!("Starting processing for file: {}", file_name);

    // Database setup
    let db_host = env::var("DB_HOST").expect("DB_HOST not set in .env");
    let db_user = env::var("DB_USER").expect("DB_USER not set in .env");
    let db_password = env::var("DB_PASSWORD").expect("DB_PASSWORD not set in .env");
    let db_name = env::var("DB_NAME").expect("DB_NAME not set in .env");

    let db_url = format!(
        "mysql://{}:{}@{}/{}",
        db_user, db_password, db_host, db_name
    );

    let pool = MySqlPool::connect(&db_url).await?;

    // Check if file already processed (outside transaction)
    if check_existing_file(&pool, &file_checksum).await? {
        println!("File '{}' already processed. Skipping...", file_name);
        return Ok(());
    }

    // Start transaction for all write operations
    let mut transaction = pool.begin().await?;

    // Process the file with user_id
    let _file_id = insert_file_metadata(&pool, &file_name, &file_checksum, user_id).await?;

    // Parse the save file
    let (save, save_query, _tokens) = parse_save_file(&data)?;

    println!("Processing file: {}", file_name);
    println!("Player tag: {}", save.meta.player);
    println!("Date: {:?}", save.meta.date);

    let province_owners = save_query.province_owners();
    let nation_events = save_query.nation_events(&province_owners);
    let player_histories = save_query.player_histories(&nation_events);

    if player_histories.is_empty() {
        eprintln!("Warning: No player histories found in save file");
    }

    let mut processed_countries = 0;
    let mut processed_events = 0;
    let mut processed_income_entries = 0;

    for player_history in player_histories {
        let country_tag = player_history.history.latest.to_string();
        println!("Processing country: {}", country_tag);

        match save.game.countries.iter().find(|(tag, _)| tag.to_string() == country_tag) {
            Some((_, country)) => {
                println!("Found country data for {}", country_tag);
                
                let country_query = save_query.country(&country_tag.parse()?)
                    .ok_or(format!("Country {} not found in query", country_tag))?;
                
                let income_breakdown = save_query.country_income_breakdown(country_query);

                // Process current state
                let current_state = extract_current_state(
                    &save_query,
                    &country_tag,
                    &format!("{:?}", save.meta.date),
                    &income_breakdown,
                )?;

                save_current_state(&mut transaction, &file_checksum, &country_tag, &current_state).await?;

                // Process historical events
                let events = extract_historical_events(&country.history.events);
                processed_events += events.len();
                for event in events {
                    save_historical_event(&mut transaction, &file_checksum, &country_tag, &event).await?;
                }

                // Process annual income
                processed_income_entries += current_state.annual_income.len();
                for (year, income) in current_state.annual_income {
                    save_annual_income(&mut transaction, &file_checksum, &country_tag, &year, income).await?;
                }

                processed_countries += 1;
                println!("Successfully processed data for {}", country_tag);
            }
            None => {
                eprintln!("No country found for tag: {}", country_tag);
            }
        }
    }

    // Commit the transaction
    transaction.commit().await?;

    println!("\nProcessing complete:");
    println!("- Countries processed: {}", processed_countries);
    println!("- Historical events saved: {}", processed_events);
    println!("- Annual income entries saved: {}", processed_income_entries);
    println!("File processed successfully and data committed to database");

    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    dotenv().ok();

    let args: Vec<String> = env::args().collect();

    if args.len() > 1 {
        match args[1].as_str() {
            "--init-db" => {
                // Database initialization
                let db_host = env::var("DB_HOST").expect("DB_HOST not set in .env");
                let db_user = env::var("DB_USER").expect("DB_USER not set in .env");
                let db_password = env::var("DB_PASSWORD").expect("DB_PASSWORD not set in .env");
                let db_name = env::var("DB_NAME").expect("DB_NAME not set in .env");

                let admin_db_url = format!("mysql://{}:{}@{}", db_user, db_password, db_host);
                let admin_pool = MySqlPool::connect(&admin_db_url).await?;
                sqlx::query(&format!("CREATE DATABASE IF NOT EXISTS {}", db_name))
                    .execute(&admin_pool)
                    .await?;

                let db_url = format!(
                    "mysql://{}:{}@{}/{}",
                    db_user, db_password, db_host, db_name
                );
                let pool = MySqlPool::connect(&db_url).await?;
                create_schema(&pool).await?;
                println!("Database initialized");
                return Ok(());
            }
            "register" | "login" | "verify" => {
                let db_url = format!(
                    "mysql://{}:{}@{}/{}",
                    env::var("DB_USER")?,
                    env::var("DB_PASSWORD")?,
                    env::var("DB_HOST")?,
                    env::var("DB_NAME")?
                );
                let pool = MySqlPool::connect(&db_url).await?;
                return handle_auth_command(&pool, &args).await;
            }
            _ => {
                // File processing - require authentication first
                if args.len() < 3 {
                    eprintln!("Usage: {} <auth_token> <s3_key>", args[0]);
                    return Ok(());
                }

                let db_url = format!(
                    "mysql://{}:{}@{}/{}",
                    env::var("DB_USER")?,
                    env::var("DB_PASSWORD")?,
                    env::var("DB_HOST")?,
                    env::var("DB_NAME")?
                );
                let pool = MySqlPool::connect(&db_url).await?;

                // Verify the auth token and get user ID
                let user = auth::verify_auth_token(&pool, &args[1]).await?;
                let user_id = user.id;

                let s3_key = &args[2];
                let s3_bucket = "eusavestats-bucket";
                let local_file_path =
                    format!("/tmp/{}", s3_key.split('/').last().unwrap_or("file.eu4"));

                let config = aws_config::load_from_env().await;
                let client = Client::new(&config);

                download_from_s3(&client, s3_bucket, s3_key, &local_file_path).await?;

                if let Err(e) = run(&local_file_path, user_id).await {
                    eprintln!("Error: {}", e);
                }

                fs::remove_file(local_file_path)?;
            }
        }
    } else {
        eprintln!("Usage: {} <command> [args]", args[0]);
        eprintln!("Commands:");
        eprintln!("  --init-db           Initialize database");
        eprintln!("  register <user> <email> <pass>  Register new user");
        eprintln!("  login <user> <pass>            Login user");
        eprintln!("  verify <user_id> <pass>        Verify password");
        eprintln!("  <auth_token> <s3_key>  Process EU4 save file (authenticated)");
    }

    Ok(())
}