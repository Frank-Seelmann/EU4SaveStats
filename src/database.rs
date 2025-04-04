#![allow(dead_code)] // hide warnings

use serde::{Deserialize, Serialize};
use serde_json;
use sha2::{Digest, Sha256};
use sqlx::{Error, MySql, MySqlPool, Row, Executor};
use std::collections::BTreeMap;

#[derive(Serialize, Deserialize, Debug, sqlx::FromRow)]
pub struct CurrentState {
    pub date: String,
    pub income: Vec<f64>,
    pub manpower: f64,
    pub max_manpower: f64,
    pub trade_income: f64,
    pub annual_income: BTreeMap<String, f64>,
}

#[derive(Serialize, Deserialize, Debug, sqlx::FromRow)]
pub struct HistoricalEvent {
    pub date: String,
    pub event_type: String,
    pub details: String,
}

#[derive(Debug, sqlx::FromRow)]
pub struct User {
    pub id: i64,
    pub username: String,
    pub email: String,
    pub password_hash: String,
}

#[derive(Debug, sqlx::FromRow)]
pub struct FriendRequest {
    pub id: i64,
    pub user_id: i64,
    pub friend_id: i64,
    pub status: String,
}

#[derive(Debug, sqlx::FromRow)]
pub struct FilePermission {
    pub id: i64,
    pub file_id: i64,
    pub user_id: i64,
    pub permission_type: String,
}

/// Creates all required database tables if they don't exist
pub async fn create_schema(pool: &MySqlPool) -> Result<(), Error> {
    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_checksum VARCHAR(64) NOT NULL UNIQUE,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        "#,
    )
    .execute(pool)
    .await?;

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
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS historical_events (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_checksum TEXT NOT NULL,
            country_tag TEXT NOT NULL,
            date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details TEXT NOT NULL
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS annual_income (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_checksum TEXT NOT NULL,
            country_tag TEXT NOT NULL,
            year TEXT NOT NULL,
            income FLOAT NOT NULL
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS user_friends (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            friend_id INT NOT NULL,
            status ENUM('pending', 'accepted') NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (friend_id) REFERENCES users(id),
            UNIQUE KEY unique_friendship (user_id, friend_id)
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS user_file_permissions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_id INT NOT NULL,
            user_id INT NOT NULL,
            permission_type ENUM('owner', 'shared') NOT NULL,
            FOREIGN KEY (file_id) REFERENCES uploaded_files(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE KEY unique_permission (file_id, user_id)
        )
        "#,
    )
    .execute(pool)
    .await?;

    Ok(())
}

/// User-related functions
pub async fn create_user(
    pool: &MySqlPool,
    username: &str,
    email: &str,
    password_hash: &str,
) -> Result<User, Error> {
    let mut tx = pool.begin().await?;

    let result = sqlx::query("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)")
        .bind(username)
        .bind(email)
        .bind(password_hash)
        .execute(&mut tx)
        .await?;

    let user_id = result.last_insert_id() as i64;
    let user = get_user_by_id(&mut tx, user_id).await?;

    tx.commit().await?;
    Ok(user)
}

pub async fn get_user_by_username(pool: &MySqlPool, username: &str) -> Result<User, Error> {
    let user = sqlx::query_as::<_, User>(
        "SELECT id, username, email, password_hash FROM users WHERE username = ?",
    )
    .bind(username)
    .fetch_one(pool)
    .await?;

    Ok(user)
}

pub async fn get_user_by_id(
    executor: impl sqlx::Executor<'_, Database = MySql>,
    user_id: i64,
) -> Result<User, Error> {
    let user = sqlx::query_as::<_, User>(
        "SELECT id, username, email, password_hash FROM users WHERE id = ?",
    )
    .bind(user_id)
    .fetch_one(executor)
    .await?;

    Ok(user)
}

/// File-related functions
pub async fn check_existing_file(pool: &MySqlPool, checksum: &str) -> Result<bool, Error> {
    let existing = sqlx::query("SELECT id FROM uploaded_files WHERE file_checksum = ?")
        .bind(checksum)
        .fetch_optional(pool)
        .await?;

    Ok(existing.is_some())
}

pub async fn insert_file_metadata(
    pool: &MySqlPool,  // Keep as pool since we need to begin a transaction
    name: &str,
    checksum: &str,
    user_id: i64,
) -> Result<i64, Error> {
    let mut tx = pool.begin().await?;

    let file_result = sqlx::query("INSERT INTO uploaded_files (file_name, file_checksum) VALUES (?, ?)")
        .bind(name)
        .bind(checksum)
        .execute(&mut tx)
        .await?;

    let file_id = file_result.last_insert_id() as i64;

    sqlx::query(
        "INSERT INTO user_file_permissions (file_id, user_id, permission_type) VALUES (?, ?, 'owner')"
    )
    .bind(file_id)
    .bind(user_id)
    .execute(&mut tx)
    .await?;

    tx.commit().await?;
    Ok(file_id)
}

pub async fn save_current_state(
    executor: impl Executor<'_, Database = MySql>,
    checksum: &str,
    country_tag: &str,
    state: &CurrentState,
) -> Result<(), Box<dyn std::error::Error>> {
    let income_json = serde_json::to_string(&state.income)?;

    sqlx::query(
        "INSERT INTO current_state (file_checksum, country_tag, date, income, manpower, max_manpower, trade_income) VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    .bind(checksum)
    .bind(country_tag)
    .bind(&state.date)
    .bind(income_json)
    .bind(state.manpower)
    .bind(state.max_manpower)
    .bind(state.trade_income)
    .execute(executor)
    .await?;

    Ok(())
}

pub async fn save_historical_event(
    executor: impl sqlx::Executor<'_, Database = MySql>,
    checksum: &str,
    country_tag: &str,
    event: &HistoricalEvent,
) -> Result<(), Error> {
    sqlx::query(
        "INSERT INTO historical_events (file_checksum, country_tag, date, event_type, details) VALUES (?, ?, ?, ?, ?)"
    )
    .bind(checksum)
    .bind(country_tag)
    .bind(&event.date)
    .bind(&event.event_type)
    .bind(&event.details)
    .execute(executor)
    .await?;

    Ok(())
}

pub async fn save_annual_income(
    executor: impl sqlx::Executor<'_, Database = MySql>,
    checksum: &str,
    country_tag: &str,
    year: &str,
    income: f64,
) -> Result<(), Error> {
    sqlx::query(
        "INSERT INTO annual_income (file_checksum, country_tag, year, income) VALUES (?, ?, ?, ?)",
    )
    .bind(checksum)
    .bind(country_tag)
    .bind(year)
    .bind(income)
    .execute(executor)
    .await?;

    Ok(())
}

/// Friend-related functions
pub async fn add_friend_request(
    pool: &MySqlPool,
    user_id: i64,
    friend_id: i64,
) -> Result<(), Error> {
    sqlx::query("INSERT INTO user_friends (user_id, friend_id, status) VALUES (?, ?, 'pending')")
        .bind(user_id)
        .bind(friend_id)
        .execute(pool)
        .await?;

    Ok(())
}

pub async fn accept_friend_request(
    pool: &MySqlPool,
    user_id: i64,
    friend_id: i64,
) -> Result<(), Error> {
    sqlx::query("UPDATE user_friends SET status = 'accepted' WHERE user_id = ? AND friend_id = ?")
        .bind(friend_id)
        .bind(user_id)
        .execute(pool)
        .await?;

    Ok(())
}

pub async fn get_friends(pool: &MySqlPool, user_id: i64) -> Result<Vec<User>, Error> {
    let friends = sqlx::query_as::<_, User>(
        r#"
        SELECT u.id, u.username, u.email, u.password_hash 
        FROM user_friends uf
        JOIN users u ON (
            (uf.user_id = u.id AND uf.friend_id = ?) OR 
            (uf.friend_id = u.id AND uf.user_id = ?)
        )
        WHERE uf.status = 'accepted'
        "#,
    )
    .bind(user_id)
    .bind(user_id)
    .fetch_all(pool)
    .await?;

    Ok(friends)
}

pub async fn get_pending_requests(
    pool: &MySqlPool,
    user_id: i64,
) -> Result<Vec<FriendRequest>, Error> {
    let requests = sqlx::query_as::<_, FriendRequest>(
        "SELECT id, user_id, friend_id, status FROM user_friends WHERE friend_id = ? AND status = 'pending'"
    )
    .bind(user_id)
    .fetch_all(pool)
    .await?;

    Ok(requests)
}

/// File permission functions
pub async fn add_file_permission(
    pool: &MySqlPool,
    file_id: i64,
    user_id: i64,
    permission_type: &str,
) -> Result<(), Error> {
    sqlx::query(
        "INSERT INTO user_file_permissions (file_id, user_id, permission_type) VALUES (?, ?, ?)",
    )
    .bind(file_id)
    .bind(user_id)
    .bind(permission_type)
    .execute(pool)
    .await?;

    Ok(())
}

pub async fn get_user_files(
    pool: &MySqlPool,
    user_id: i64,
) -> Result<Vec<(i64, String, String)>, Error> {
    let rows = sqlx::query(
        r#"
        SELECT uf.id, uf.file_name, uf.upload_time 
        FROM uploaded_files uf
        JOIN user_file_permissions ufp ON uf.id = ufp.file_id
        WHERE ufp.user_id = ?
        "#,
    )
    .bind(user_id)
    .fetch_all(pool)
    .await?;

    let mut files = Vec::new();
    for row in rows {
        files.push((
            row.try_get::<i64, _>("id")?,
            row.try_get::<String, _>("file_name")?,
            row.try_get::<String, _>("upload_time")?,
        ));
    }

    Ok(files)
}

pub async fn check_file_permission(
    pool: &MySqlPool,
    file_id: i64,
    user_id: i64,
) -> Result<bool, Error> {
    let permission =
        sqlx::query("SELECT 1 FROM user_file_permissions WHERE file_id = ? AND user_id = ?")
            .bind(file_id)
            .bind(user_id)
            .fetch_optional(pool)
            .await?;

    Ok(permission.is_some())
}

pub async fn get_file_owner(pool: &MySqlPool, file_id: i64) -> Result<i64, Error> {
    let row = sqlx::query(
        "SELECT user_id FROM user_file_permissions WHERE file_id = ? AND permission_type = 'owner'",
    )
    .bind(file_id)
    .fetch_one(pool)
    .await?;

    Ok(row.try_get::<i64, _>("user_id")?)
}

/// Utility functions
pub fn calculate_checksum(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    format!("{:x}", hasher.finalize())
}
