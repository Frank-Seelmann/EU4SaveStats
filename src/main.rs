mod database;
mod parser;

use std::{fs, env};
use std::error::Error;
use std::io::Write;
use dotenv::dotenv;
use sqlx::MySqlPool;
use aws_sdk_s3::Client;
use parser::*;
use database::*;


/// Downloads file from S3 bucket
async fn download_from_s3(client: &Client, bucket: &str, key: &str, file_path: &str) -> Result<(), Box<dyn std::error::Error>> {
    let response = client
        .get_object()
        .bucket(bucket)
        .key(key)
        .send()
        .await?;

    let mut file = fs::File::create(file_path)?;
    let bytes = response.body.collect().await?;
    file.write_all(&bytes.into_bytes())?;
    Ok(())
}

/// Main processing function for EU4 save files
pub async fn run(path: &str) -> Result<(), Box<dyn Error>> {
    let data = fs::read(path)?;
    let file_checksum = calculate_checksum(&data);
    let file_name = std::path::Path::new(path)
        .file_name()
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();

    // Database setup
    let db_host = env::var("DB_HOST").expect("DB_HOST not set in .env");
    let db_user = env::var("DB_USER").expect("DB_USER not set in .env");
    let db_password = env::var("DB_PASSWORD").expect("DB_PASSWORD not set in .env");
    let db_name = env::var("DB_NAME").expect("DB_NAME not set in .env");

    let db_url = format!("mysql://{}:{}@{}/{}", db_user, db_password, db_host, db_name);
    let admin_db_url = format!("mysql://{}:{}@{}", db_user, db_password, db_host);
    
    // Initialize database connection
    let admin_pool = MySqlPool::connect(&admin_db_url).await?;
    sqlx::query(&format!("CREATE DATABASE IF NOT EXISTS {}", db_name))
        .execute(&admin_pool)
        .await?;

    let pool = MySqlPool::connect(&db_url).await?;
    create_schema(&pool).await?;

    // Check if file already processed
    if check_existing_file(&pool, &file_checksum).await? {
        println!("File '{}' already processed. Skipping...", file_name);
        return Ok(());
    }

    // Process the file
    insert_file_metadata(&pool, &file_name, &file_checksum).await?;
    let (save, save_query, _tokens) = parse_save_file(&data)?;
    
    println!("Processing file: {}", file_name);
    println!("Player tag: {}", save.meta.player);
    println!("Date: {:?}", save.meta.date);

    let province_owners = save_query.province_owners();
    let nation_events = save_query.nation_events(&province_owners);
    let player_histories = save_query.player_histories(&nation_events);

    for player_history in player_histories {
        let country_tag = player_history.history.latest.to_string();
        println!("Processing country: {}", country_tag);

        if let Some((_, country)) = save.game.countries.iter().find(|(tag, _)| tag.to_string() == country_tag) {
            let income_breakdown = save_query.country_income_breakdown(&save_query.country(&country_tag.parse()?).unwrap());
            
            // Process current state
            let current_state = extract_current_state(
                &save_query,
                &country_tag,
                &format!("{:?}", save.meta.date),
                &income_breakdown
            )?;
            
            save_current_state(&pool, &file_checksum, &country_tag, &current_state).await?;

            // Process historical events
            for event in extract_historical_events(&country.history.events) {
                save_historical_event(&pool, &file_checksum, &country_tag, &event).await?;
            }

            // Process annual income
            for (year, income) in current_state.annual_income {
                save_annual_income(&pool, &file_checksum, &country_tag, &year, income).await?;
            }

            println!("Data for {} saved successfully", country_tag);
        }
    }

    println!("File processed successfully");
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    dotenv().ok();

    // Handle command line arguments
    let args: Vec<String> = env::args().collect();
    
    if args.len() > 1 && args[1] == "--init-db" {
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

        let db_url = format!("mysql://{}:{}@{}/{}", db_user, db_password, db_host, db_name);
        let pool = MySqlPool::connect(&db_url).await?;
        create_schema(&pool).await?;
        println!("Database initialized");
        return Ok(());
    }

    if args.len() < 2 {
        eprintln!("Usage: {} <s3_key> or --init-db", args[0]);
        return Ok(());
    }

    // Normal file processing
    let s3_key = &args[1];
    let s3_bucket = "eusavestats-bucket";
    let local_file_path = format!("/tmp/{}", s3_key.split('/').last().unwrap_or("file.eu4"));

    let config = aws_config::load_from_env().await;
    let client = Client::new(&config);

    download_from_s3(&client, s3_bucket, s3_key, &local_file_path).await?;
    
    if let Err(e) = run(&local_file_path).await {
        eprintln!("Error: {}", e);
    }

    fs::remove_file(local_file_path)?;
    Ok(())
}