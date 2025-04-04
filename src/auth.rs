use crate::database::{create_user, get_user_by_id, get_user_by_username, User};
use bcrypt::{hash, verify, DEFAULT_COST};
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
    // Check if user exists first
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
) -> Result<User, AuthError> {
    let user = get_user_by_username(pool, username).await?;
    verify_password(&user.password_hash, password)?;
    Ok(user)
}

pub async fn verify_user_password(
    pool: &MySqlPool,
    user_id: i64,
    password: &str,
) -> Result<bool, AuthError> {
    let user = get_user_by_id(pool, user_id).await?;
    Ok(verify_password(&user.password_hash, password).is_ok())
}

fn hash_password(password: &str) -> Result<String, AuthError> {
    hash(password, DEFAULT_COST).map_err(|_| AuthError::HashingError)
}

fn verify_password(hash: &str, password: &str) -> Result<(), AuthError> {
    verify(password, hash).map_err(|_| AuthError::InvalidCredentials)?;
    Ok(())
}

pub async fn verify_auth_token(pool: &MySqlPool, token: &str) -> Result<User, AuthError> {
    // In a real application, you'd want to use proper JWT or session tokens
    // For simplicity, we'll just treat the token as the user ID here
    let user_id = token.parse().map_err(|_| AuthError::InvalidCredentials)?;
    get_user_by_id(pool, user_id).await.map_err(AuthError::from)
}
