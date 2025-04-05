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

const DEBUG_NO_AUTH: bool = true;

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
    // Normalize the key path (remove leading/trailing slashes)
    let key = key.trim_matches('/');
    
    println!("[S3] Downloading s3://{}/{} to {}", bucket, key, file_path);

    // Verify object exists first
    let _head = client.head_object()
        .bucket(bucket)
        .key(key)
        .send()
        .await
        .map_err(|e| format!("S3 object not found: {} (Error: {})", key, e))?;

    let response = client.get_object()
        .bucket(bucket)
        .key(key)
        .send()
        .await?;

    let mut file = fs::File::create(file_path)
        .map_err(|e| format!("Failed to create local file: {} (Error: {})", file_path, e))?;

    let bytes = response.body.collect().await?;
    file.write_all(&bytes.into_bytes())?;
    
    println!("[S3] Download completed successfully");
    Ok(())
}

async fn upload_to_s3(
    client: &Client,
    bucket: &str,
    key: &str,
    file_path: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    use aws_sdk_s3::primitives::ByteStream;

    // Normalize the key path
    let key = key.trim_matches('/');
    
    println!("[S3] Uploading {} to s3://{}/{}", file_path, bucket, key);

    let body = ByteStream::from_path(file_path).await
        .map_err(|e| format!("Failed to read local file: {} (Error: {})", file_path, e))?;

    client.put_object()
        .bucket(bucket)
        .key(key)
        .body(body)
        .send()
        .await?;

    println!("[S3] Upload completed successfully");
    Ok(())
}

async fn handle_s3_operations(
    client: &Client,
    operation: &str,  // "download" or "upload"
    bucket: &str,
    key: &str,
    local_path: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    match operation {
        "download" => download_from_s3(client, bucket, key, local_path).await,
        "upload" => upload_to_s3(client, bucket, key, local_path).await,
        _ => Err("Invalid operation. Use 'download' or 'upload'".into()),
    }
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
            let response = auth::login_user(pool, &args[2], &args[3])
                .await
                .map_err(|e| -> Box<dyn std::error::Error> { Box::new(e) })?;
            
            // Print just the token
            println!("{}", response.token);
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
    // Initialize AWS client if needed
    let config = aws_config::load_from_env().await;
    let client = Client::new(&config);
    let bucket = "eusavestats-bucket";

    println!("[DEBUG] Starting file processing for: {}", path);

    // Handle both S3 and local paths
    let (data, file_checksum, file_name) = if path.starts_with("s3://") {
        // S3 path handling
        let key = path.trim_start_matches("s3://")
                     .trim_start_matches(bucket)
                     .trim_start_matches('/');
        
        println!("[DEBUG] Processing S3 file: s3://{}/{}", bucket, key);
        
        let temp_path = format!("/tmp/{}", key.split('/').last().unwrap_or("temp_save.eu4"));
        println!("[DEBUG] Downloading to temporary file: {}", temp_path);

        match download_from_s3(&client, bucket, key, &temp_path).await {
            Ok(_) => {
                let data = fs::read(&temp_path)?;
                println!("[DEBUG] Downloaded {} bytes from S3", data.len());
                let checksum = calculate_checksum(&data);
                let name = std::path::Path::new(key)
                    .file_name()
                    .unwrap()
                    .to_str()
                    .unwrap()
                    .to_string();
                
                // Clean up temp file
                let _ = fs::remove_file(temp_path);
                (data, checksum, name)
            }
            Err(e) => {
                println!("[ERROR] S3 download failed: {}", e);
                return Err(e);
            }
        }
    } else {
        // Local file handling
        println!("[DEBUG] Processing local file: {}", path);
        if !std::path::Path::new(path).exists() {
            println!("[ERROR] File not found at path: {}", path);
            return Err(format!("File not found at path: {}", path).into());
        }

        let data = fs::read(path)?;
        println!("[DEBUG] File read successfully, size: {} bytes", data.len());
        let checksum = calculate_checksum(&data);
        println!("[DEBUG] Calculated checksum: {}", checksum);
        let name = std::path::Path::new(path)
            .file_name()
            .unwrap()
            .to_str()
            .unwrap()
            .to_string();
        (data, checksum, name)
    };

    println!("[DEBUG] Starting processing for file: {}", file_name);

    // Database setup
    let db_url = format!(
        "mysql://{}:{}@{}/{}",
        env::var("DB_USER").map_err(|_| "DB_USER not set in .env")?,
        env::var("DB_PASSWORD").map_err(|_| "DB_PASSWORD not set in .env")?,
        env::var("DB_HOST").unwrap_or_else(|_| "localhost".to_string()),
        env::var("DB_NAME").map_err(|_| "DB_NAME not set in .env")?
    );

    println!("[DEBUG] Connecting to database at: {}", db_url);
    let pool = MySqlPool::connect(&db_url).await?;

    // Check if file already processed
    println!("[DEBUG] Checking if file already processed...");
    if check_existing_file(&pool, &file_checksum).await? {
        println!("File '{}' already processed. Skipping...", file_name);
        return Ok(());
    }

    // Start transaction for all write operations
    println!("[DEBUG] Starting database transaction...");
    let mut transaction = pool.begin().await?;

    // Process the file with user_id
    println!("[DEBUG] Inserting file metadata with transaction...");
    let _file_id = insert_file_metadata(&pool, &file_name, &file_checksum, user_id).await?;

    // Parse the save file
    println!("[DEBUG] Parsing save file...");
    let (save, save_query, _tokens) = parse_save_file(&data)?;

    println!("[DEBUG] Processing file: {}", file_name);
    println!("[DEBUG] Player tag: {}", save.meta.player);
    println!("[DEBUG] Game date: {:?}", save.meta.date);

    let province_owners = save_query.province_owners();
    let nation_events = save_query.nation_events(&province_owners);
    let player_histories = save_query.player_histories(&nation_events);
    println!("[DEBUG] Found {} player histories", player_histories.len());

    if player_histories.is_empty() {
        println!("[WARN] No player histories found in save file");
    }

    let mut processed_countries = 0;
    let mut processed_events = 0;
    let mut processed_income_entries = 0;

    for player_history in player_histories {
        let country_tag = player_history.history.latest.to_string();
        println!("[DEBUG] Processing country: {}", country_tag);

        match save.game.countries.iter().find(|(tag, _)| tag.to_string() == country_tag) {
            Some((_, country)) => {
                println!("[DEBUG] Found matching country data");
                
                let country_query = save_query.country(&country_tag.parse()?)
                    .ok_or(format!("Country {} not found in query", country_tag))?;
                
                let income_breakdown = save_query.country_income_breakdown(country_query);
                println!("[DEBUG] Income breakdown: {:?}", income_breakdown);

                // Process current state
                let current_state = extract_current_state(
                    &save_query,
                    &country_tag,
                    &format!("{:?}", save.meta.date),
                    &income_breakdown,
                )?;
                println!("[DEBUG] Current state extracted: {:?}", current_state);

                println!("[DEBUG] Saving current state...");
                save_current_state(&mut transaction, &file_checksum, &country_tag, &current_state).await?;
                println!("[DEBUG] Current state saved successfully");

                // Process historical events
                let events = extract_historical_events(&country.history.events);
                processed_events += events.len();
                println!("[DEBUG] Saving {} historical events...", events.len());
                for event in events {
                    save_historical_event(&mut transaction, &file_checksum, &country_tag, &event).await?;
                }

                // Process annual income
                processed_income_entries += current_state.annual_income.len();
                println!("[DEBUG] Saving {} annual income entries...", current_state.annual_income.len());
                for (year, income) in current_state.annual_income {
                    save_annual_income(&mut transaction, &file_checksum, &country_tag, &year, income).await?;
                }

                processed_countries += 1;
                println!("[DEBUG] Successfully processed data for {}", country_tag);
            }
            None => {
                println!("[WARN] No matching country found for tag: {}", country_tag);
            }
        }
    }

    println!("[DEBUG] Committing transaction...");
    transaction.commit().await?;
    println!("[DEBUG] Transaction committed successfully");

    println!("\n[SUCCESS] Processing complete:");
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
    println!("[START] Program started with args: {:?}", args);

    // Check for debug mode (enable with DEBUG_MODE=1 in .env or environment)
    let debug_mode = env::var("DEBUG_MODE").unwrap_or_default() == "1";
    if debug_mode {
        println!("[WARNING] DEBUG MODE ACTIVE - AUTHENTICATION CHECKS DISABLED");
    }

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
                Ok(())
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
                handle_auth_command(&pool, &args).await
            }
            "--local" => {
                println!("[DEBUG] Args received: {:?}", args);
                
                if args.len() < 3 {
                    eprintln!("Usage: {} --local <file_path> <user_id>", args[0]);
                    eprintln!("       {} --local token:<token> <file_path>", args[0]);
                    return Ok(());
                }

                // Connect to database first since we'll need it for both paths
                let db_url = format!(
                    "mysql://{}:{}@{}/{}",
                    env::var("DB_USER")?,
                    env::var("DB_PASSWORD")?,
                    env::var("DB_HOST")?,
                    env::var("DB_NAME")?
                );
                let pool = MySqlPool::connect(&db_url).await?;

                let (file_path, user_id) = if args[2].starts_with("token:") {
                    if debug_mode {
                        println!("[DEBUG] Skipping token verification in debug mode");
                        // Verify debug user exists in database
                        let debug_user = database::get_user_by_id(&pool, 1).await
                            .map_err(|_| "Debug user not found in database")?;
                        (args[3].to_string(), debug_user.id)
                    } else {
                        let token = args[2].trim_start_matches("token:");
                        println!("[DEBUG] Token after stripping prefix: '{}'", token);
                        
                        let user = auth::verify_auth_token(&pool, token).await?;
                        // Additional verification that user exists and is active
                        database::get_user_by_id(&pool, user.id).await?;
                        (args[3].to_string(), user.id)
                    }
                } else {
                    // For direct user_id usage, verify the user exists
                    let user_id: i64 = args[3].parse()?;
                    database::get_user_by_id(&pool, user_id).await?;
                    (args[2].to_string(), user_id)
                };

                run(&file_path, user_id).await
            }
            _ => {
                // File processing - with optional authentication
                if args.len() < 3 {
                    eprintln!("Usage: {} <auth_token> <s3_key>", args[0]);
                    return Ok(());
                }

                let user_id = if debug_mode {
                    println!("[DEBUG] Skipping authentication, using test user ID 1");
                    1 // Default test user ID
                } else {
                    let db_url = format!(
                        "mysql://{}:{}@{}/{}",
                        env::var("DB_USER")?,
                        env::var("DB_PASSWORD")?,
                        env::var("DB_HOST")?,
                        env::var("DB_NAME")?
                    );
                    let pool = MySqlPool::connect(&db_url).await?;
                    let user = auth::verify_auth_token(&pool, &args[1]).await?;
                    user.id
                };

                let s3_key = &args[2];
                let s3_bucket = "eusavestats-bucket";
                let local_file_path =
                    format!("/tmp/{}", s3_key.split('/').last().unwrap_or("file.eu4"));

                let config = aws_config::load_from_env().await;
                let client = Client::new(&config);

                download_from_s3(&client, s3_bucket, s3_key, &local_file_path).await?;

                let result = run(&local_file_path, user_id).await;
                fs::remove_file(local_file_path)?;
                result
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
        eprintln!("  --local <file_path> <user_id>  Process local file");
        eprintln!("  --local token:<token> <file_path>  Process local file with auth");
        Ok(())
    }
}