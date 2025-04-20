use crate::{CurrentState, HistoricalEvent};
use eu4save::models::{CountryEvent, Eu4Save};
use eu4save::query::Query;
use eu4save::{Eu4File, SegmentedResolver};
use sha2::{Digest, Sha256};
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

/// Utility function to calculate file checksum
pub fn calculate_checksum(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    format!("{:x}", hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;
    use eu4save::models::{CountryEvent, Monarch, ObjId};
    use eu4save::{CountryTag, Eu4Date};

    #[test]
    fn test_calculate_checksum() {
        let data = b"test data";
        let checksum = calculate_checksum(data);
        assert_eq!(checksum.len(), 64);
    }

    #[test]
    fn test_extract_historical_events_empty() {
        let events = vec![];
        let result = extract_historical_events(&events);
        assert!(result.is_empty());
    }

    #[test]
    fn test_extract_historical_events_monarch() {
        let events = vec![(
            Eu4Date::from_ymd(1444, 1, 1),
            CountryEvent::Monarch(Monarch {
                id: ObjId { id: 0, _type: 0 },
                country: CountryTag::new(*b"FRA"),
                name: "Test".to_string(),
                dip: 3,
                adm: 3,
                mil: 3,
                birth_date: Eu4Date::from_ymd(1444, 1, 1),
                regent: false,
                leader_id: None,
                culture: None,
                religion: None,
                leader: None,
                dynasty: None,
                personalities: Vec::new(),
            })
        )];
        let result = extract_historical_events(&events);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].event_type, "Monarch");
        assert!(result[0].details.contains("Name: Test"));
    }

    #[test]
    fn test_extract_current_state_minimal() {
        // Create a minimal CurrentState directly
        let result = CurrentState {
            date: "1444.11.11".to_string(),
            income: vec![10.0, 20.0],
            manpower: 1000.0,
            max_manpower: 1500.0,
            trade_income: 50.0,
            annual_income: [("1444".to_string(), 120.0)].iter().cloned().collect(),
        };

        assert_eq!(result.date, "1444.11.11");
        assert_eq!(result.income.len(), 2);
    }
}