use crate::database::{User, get_user_by_username, create_user, get_user_by_id};
use bcrypt::{hash, verify, DEFAULT_COST};
use serde::Serialize;
use rand;
use hex;
use sqlx::MySqlPool;
use std::error::Error;
use std::fmt;

#[derive(Debug)]
pub enum AuthError {
    HashingError,
    InvalidCredentials,
    DatabaseError(sqlx::Error),
    UserAlreadyExists,
}

#[derive(Serialize)]
pub struct LoginResponse {
    pub token: String,
    pub user_id: i64,
}

impl fmt::Display for AuthError {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            AuthError::HashingError => write!(f, "Password hashing failed"),
            AuthError::InvalidCredentials => write!(f, "Invalid credentials"),
            AuthError::DatabaseError(e) => write!(f, "Database error: {}", e),
            AuthError::UserAlreadyExists => write!(f, "User already exists"),
        }
    }
}

impl Error for AuthError {}

impl From<sqlx::Error> for AuthError {
    fn from(err: sqlx::Error) -> Self {
        AuthError::DatabaseError(err)
    }
}

pub async fn register_user(
    pool: &MySqlPool,
    username: &str,
    email: &str,
    password: &str,
) -> Result<User, AuthError> {
    if get_user_by_username(pool, username).await.is_ok() {
        return Err(AuthError::UserAlreadyExists);
    }

    let hashed = hash_password(password)?;
    create_user(pool, username, email, &hashed)
        .await
        .map_err(AuthError::from)
}

pub async fn login_user(
    pool: &MySqlPool,
    username: &str,
    password: &str,
) -> Result<LoginResponse, AuthError> {
    let user = get_user_by_username(pool, username).await?;
    if verify_password(&user.password_hash, password).is_ok() {
        let token = format!("{}-{}", user.id, hex::encode(rand::random::<[u8; 16]>()));
        Ok(LoginResponse {
            token,
            user_id: user.id,
        })
    } else {
        Err(AuthError::InvalidCredentials)
    }
}

pub async fn verify_user_password(
    pool: &MySqlPool,
    user_id: i64,
    password: &str,
) -> Result<bool, AuthError> {
    let user = get_user_by_id(pool, user_id).await?;
    Ok(verify_password(&user.password_hash, password).is_ok())
}

pub async fn verify_auth_token(pool: &MySqlPool, token: &str) -> Result<User, AuthError> {
    println!("[TOKEN DEBUG] Raw token: '{}'", token);
    println!("[TOKEN DEBUG] Token length: {} chars", token.len());
    println!("[TOKEN DEBUG] Hex dump: {:x?}", token.as_bytes());
    
    let parts: Vec<&str> = token.splitn(2, '-').collect();
    println!("[TOKEN DEBUG] Split parts: {:?} (count: {})", parts, parts.len());
    
    if parts.len() != 2 {
        println!(
            "Token is malformed (expected 2 parts, got {}) - '{}' (hex: {:x?})",
            parts.len(), token, token.as_bytes()
        );
        return Err(AuthError::InvalidCredentials);
    }
    
    if parts.len() < 2 {
        println!("[ERROR] Token missing separator");
        return Err(AuthError::InvalidCredentials);
    }

    let user_id = parts[0].parse().map_err(|_| {
        println!("[ERROR] Failed to parse user_id from '{}'", parts[0]);
        AuthError::InvalidCredentials
    })?;
    
    println!("[DEBUG] Extracted user_id: {}", user_id);
    
    get_user_by_id(pool, user_id).await.map_err(|e| {
        println!("[ERROR] User lookup failed: {}", e);
        AuthError::from(e)
    })
}

fn hash_password(password: &str) -> Result<String, AuthError> {
    hash(password, DEFAULT_COST).map_err(|_| AuthError::HashingError)
}

fn verify_password(hash: &str, password: &str) -> Result<(), AuthError> {
    verify(password, hash).map_err(|_| AuthError::InvalidCredentials)?;
    Ok(())
}