use crate::database::{CurrentState, HistoricalEvent};
use eu4save::models::{CountryEvent, Eu4Save};
use eu4save::query::Query;
use eu4save::{Eu4File, SegmentedResolver};
use std::error::Error;

/// Parses EU4 save file and returns parsed data structures
pub fn parse_save_file(data: &[u8]) -> Result<(Eu4Save, Query, SegmentedResolver), Box<dyn Error>> {
    let file = Eu4File::from_slice(data)?;
    let resolver = SegmentedResolver::empty();
    let save = file.parse_save(&resolver)?;
    let query = Query::from_save(save.clone());
    Ok((save, query, resolver))
}

/// Extracts current state data from parsed save file
pub fn extract_current_state(
    query: &Query,
    country_tag: &str,
    current_date: &str,
    income_breakdown: &eu4save::query::CountryIncomeLedger,
) -> Result<CurrentState, Box<dyn Error>> {
    println!("[EXTRACT] Extracting data for country: {}", country_tag);
    let country = query
        .country(&country_tag.parse()?)
        .ok_or("Country not found")?;
    println!("[EXTRACT] Income ledger: {:?}", country.ledger.income);
    println!("[EXTRACT] Manpower: {}/{}", country.manpower, country.max_manpower);
    let income = &country.ledger.income;
    let manpower = country.manpower;
    let max_manpower = country.max_manpower;
    let trade_income = income_breakdown.trade;

    // Group income data by year and calculate annual income
    let mut annual_income = std::collections::BTreeMap::new();
    let province_owners = query.province_owners();
    let nation_events = query.nation_events(&province_owners);

    let nation_events_ref = nation_events.first().ok_or("No nation events found")?;
    for point in query
        .income_statistics_ledger(nation_events_ref)
        .iter()
        .filter(|point| point.tag.to_string() == country_tag)
    {
        let annual_value = point.value as f64 * 12.0;
        annual_income.insert(point.year.to_string(), annual_value);
    }

    Ok(CurrentState {
        date: current_date.to_string(),
        income: income.iter().map(|&i| i as f64).collect(),
        manpower: manpower as f64,
        max_manpower: max_manpower as f64,
        trade_income: trade_income as f64,
        annual_income,
    })
}

/// Extracts historical events from country data
pub fn extract_historical_events(
    events: &[(eu4save::Eu4Date, eu4save::models::CountryEvent)],
) -> Vec<HistoricalEvent> {
    let mut historical_events = Vec::new();

    for (date, event) in events {
        let (event_type, details) = match event {
            CountryEvent::Monarch(monarch) => (
                "Monarch",
                format!(
                    "Name: {}, Dip: {}, Adm: {}, Mil: {}",
                    monarch.name, monarch.dip, monarch.adm, monarch.mil
                ),
            ),
            CountryEvent::Heir(heir) => (
                "Heir",
                format!(
                    "Name: {}, Dip: {}, Adm: {}, Mil: {}",
                    heir.name, heir.dip, heir.adm, heir.mil
                ),
            ),
            CountryEvent::Leader(leader) => (
                "Leader",
                format!("Name: {}, Kind: {:?}", leader.name, leader.kind),
            ),
            CountryEvent::Capital(province_id) => {
                ("Capital", format!("Province ID: {}", province_id))
            }
            CountryEvent::ChangedCountryNameFrom(name) => {
                ("ChangedCountryNameFrom", format!("From: {}", name))
            }
            CountryEvent::ChangedCountryAdjectiveFrom(adjective) => (
                "ChangedCountryAdjectiveFrom",
                format!("From: {}", adjective),
            ),
            CountryEvent::ChangedCountryMapColorFrom(color) => {
                ("ChangedCountryMapColorFrom", format!("From: {:?}", color))
            }
            CountryEvent::Queen(queen) => (
                "Queen",
                format!(
                    "Name: {}, Dip: {}, Adm: {}, Mil: {}",
                    queen.name, queen.dip, queen.adm, queen.mil
                ),
            ),
            CountryEvent::NationalFocus(focus) => ("NationalFocus", format!("Focus: {:?}", focus)),
            CountryEvent::AddAcceptedCulture(culture) => {
                ("AddAcceptedCulture", format!("Culture: {}", culture))
            }
            _ => ("Unknown", format!("{:?}", event)),
        };

        historical_events.push(HistoricalEvent {
            date: format!("{:?}", date),
            event_type: event_type.to_string(),
            details,
        });
    }

    historical_events
}
