use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

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

pub mod parser;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_current_state_serialization() {
        let state = CurrentState {
            date: "1444.11.11".to_string(),
            income: vec![10.5, 20.3],
            manpower: 1000.0,
            max_manpower: 1500.0,
            trade_income: 50.0,
            annual_income: [("1444".to_string(), 120.0)].iter().cloned().collect(),
        };

        let serialized = serde_json::to_string(&state).unwrap();
        assert!(serialized.contains("\"date\":\"1444.11.11\""));
        assert!(serialized.contains("\"manpower\":1000.0"));
    }
}