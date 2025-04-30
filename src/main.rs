mod parser;

use eu4_parser::{CurrentState, HistoricalEvent};
use serde::Serialize;
use std::error::Error;
use std::fs::File;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::{env, fs};

#[derive(Serialize)]
struct OutputData {
    original_filename: String,
    file_checksum: String,
    user_id: i64,
    processed_data: Vec<CountryData>,
}

#[derive(Serialize)]
struct CountryData {
    country_tag: String,
    current_state: CurrentState,
    historical_events: Vec<HistoricalEvent>,
    annual_income: Vec<AnnualIncomeEntry>,
}

#[derive(Serialize)]
struct AnnualIncomeEntry {
    year: String,
    income: f64,
}

pub async fn run(path: &str, user_id: i64) -> Result<(), Box<dyn Error>> {
    println!("[DEBUG] Starting file processing for: {}", path);

    // Create processed directory if it doesn't exist
    let processed_dir = Path::new("processed");
    if !processed_dir.exists() {
        fs::create_dir(processed_dir)?;
        println!("[DEBUG] Created processed directory");
    }

    let data = fs::read(path)?;
    println!("[DEBUG] File read successfully, size: {} bytes", data.len());
    
    let checksum = parser::calculate_checksum(&data);
    println!("[DEBUG] Calculated checksum: {}", checksum);
    
    let source_file = PathBuf::from(path);
    let file_name = source_file.file_name()
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();

    // Generate unique output filename with checksum
    let output_filename = format!(
        "{}_{}.json",
        source_file.file_stem().unwrap().to_str().unwrap(),
        &checksum[0..8] // Using first 8 chars of checksum for brevity
    );

    println!("[DEBUG] Starting processing for file: {}", file_name);

    // Parse the save file
    println!("[DEBUG] Parsing save file...");
    let (save, save_query, _tokens) = parser::parse_save_file(&data)?;

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

    let mut output_data = OutputData {
        original_filename: file_name.clone(),
        file_checksum: checksum,
        user_id,
        processed_data: Vec::new(),
    };

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

                let player_nation_events = nation_events
                    .iter()
                    .find(|x| x.initial.to_string() == country_tag || x.latest.to_string() == country_tag)
                    .ok_or("Player nation events not found")?;

                // Process current state
                let current_state = parser::extract_current_state(
                    &save_query,
                    &country_tag,
                    &format!("{:?}", save.meta.date),
                    &income_breakdown,
                    player_nation_events,
                )?;
                println!("[DEBUG] Current state extracted: {:?}", current_state);

                // Process historical events
                let historical_events = parser::extract_historical_events(&country.history.events);
                println!("[DEBUG] Found {} historical events", historical_events.len());

                // Process annual income
                let annual_income = current_state.annual_income.iter()
                    .map(|(year, income)| AnnualIncomeEntry {
                        year: year.clone(),
                        income: *income,
                    })
                    .collect();

                output_data.processed_data.push(CountryData {
                    country_tag: country_tag.clone(),
                    current_state,
                    historical_events,
                    annual_income,
                });

                println!("[DEBUG] Successfully processed data for {}", country_tag);
            }
            None => {
                println!("[WARN] No matching country found for tag: {}", country_tag);
            }
        }
    }

    // Create destination paths
    let json_output_path = processed_dir.join(&output_filename);
    let file_copy_path = processed_dir.join(&file_name);

    // Write output to JSON file
    let mut file = File::create(&json_output_path)?;
    let json = serde_json::to_string_pretty(&output_data)?;
    file.write_all(json.as_bytes())?;

    // Copy original file to processed directory
    fs::copy(path, &file_copy_path)?;

    println!("\n[SUCCESS] Processing complete:");
    println!("- Countries processed: {}", output_data.processed_data.len());
    println!("- Original file copied to: {}", file_copy_path.display());
    println!("- JSON output written to: {}", json_output_path.display());

    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    println!("[START] Program started with args: {:?}", args);

    if args.len() < 3 {
        eprintln!("Usage: {} <file_path> <user_id>", args[0]);
        return Ok(());
    }

    let file_path = &args[1];
    let user_id: i64 = args[2].parse()?;

    run(file_path, user_id).await
}

#[tokio::test]
async fn test_run_with_real_file() {
    // Use the real save file
    let path = "samples/mp_Byzantium1527_11_02.eu4";

    // Clean up any previous test runs
    let _ = std::fs::remove_dir_all("processed");

    // Run the processor
    let result = run(path, 1).await;
    assert!(result.is_ok(), "Failed to process real save file: {:?}", result.err());

    // Verify output was created by checking for any JSON file with the expected prefix
    let processed_dir = Path::new("processed");
    let output_files: Vec<_> = std::fs::read_dir(processed_dir)
        .unwrap()
        .filter_map(|entry| {
            let entry = entry.unwrap();
            let file_name = entry.file_name().into_string().unwrap();
            if file_name.starts_with("mp_Byzantium1527_11_02_") && file_name.ends_with(".json") {
                Some(entry.path())
            } else {
                None
            }
        })
        .collect();

    assert!(!output_files.is_empty(), "No JSON output file found in processed directory");

    // Verify the JSON content is valid
    let json_path = &output_files[0];
    let json_content = std::fs::read_to_string(json_path).unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&json_content).unwrap();

    // Basic content validation
    assert!(parsed["original_filename"].as_str().unwrap().contains("Byzantium"));
    assert!(parsed["processed_data"].is_array());
    assert!(parsed["processed_data"].as_array().unwrap().len() > 0);

    // Clean up
    let _ = std::fs::remove_dir_all("processed");
}