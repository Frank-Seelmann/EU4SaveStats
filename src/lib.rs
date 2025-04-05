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