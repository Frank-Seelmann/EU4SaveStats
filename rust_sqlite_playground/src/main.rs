use std::result::Result;
use sqlx::{sqlite::SqliteQueryResult, Sqlite, SqlitePool, migrate::MigrateDatabase};

async fn create_schema(pool: &SqlitePool) -> Result<(), sqlx::Error> {
    sqlx::query(
        "PRAGMA foreign_keys = ON;"
    ).execute(pool).await?;

    sqlx::query(
        "CREATE TABLE IF NOT EXISTS settings (
            settings_id     INTEGER PRIMARY KEY NOT NULL,
            description     TEXT NOT NULL,
            created_on      DATETIME DEFAULT (datetime('now', 'localtime')),
            updated_on      DATETIME DEFAULT (datetime('now', 'localtime')),
            done            BOOLEAN NOT NULL DEFAULT 0
        );"
    ).execute(pool).await?;

    sqlx::query(
        "CREATE TABLE IF NOT EXISTS project (
            project_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name    TEXT,
            created_on      DATETIME DEFAULT (datetime('now', 'localtime')),
            updated_on      DATETIME DEFAULT (datetime('now', 'localtime')),
            img_directory   TEXT NOT NULL,
            out_directory   TEXT NOT NULL,
            status          TEXT NOT NULL,
            settings_id     INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (settings_id) REFERENCES settings (settings_id) 
            ON UPDATE SET NULL ON DELETE SET NULL
        );"
    ).execute(pool).await?;

    Ok(())
}

#[async_std::main]
async fn main() {
    let db_url = "sqlite://sqlite.db";

    if !Sqlite::database_exists(db_url).await.unwrap_or(false) {
        Sqlite::create_database(db_url).await.unwrap();
    }

    // Create a single connection pool
    let pool = SqlitePool::connect(db_url).await.unwrap();

    // Ensure schema is created
    if let Err(e) = create_schema(&pool).await {
        panic!("Failed to create schema: {}", e);
    }

    // Insert sample data
    let qry = "INSERT INTO settings (description) VALUES (?)";
    let result = sqlx::query(qry)
        .bind("testing")
        .execute(&pool)
        .await;

    pool.close().await;
    println!("{:?}", result);
}


/* 

Rust notes:

Why unwrap/unwrap_or?

    Rust has strong error handling, and functions that might fail return a Result<T, E> (for operations that can succeed or fail) or Option<T> (for operations that may return None).

    unwrap() extracts the successful value (T) from a Result<T, E> or Option<T>.
    If the result is an error (Err) or None, unwrap() panics (crashes the program).

    let maybe_number: Option<i32> = Some(42);
    let number = maybe_number.unwrap(); // Works fine because it's Some(42)
    let none_value: Option<i32> = None;
    let number = none_value.unwrap(); // This will panic!

    A safer alternative is using match or unwrap_or():
    let number = maybe_number.unwrap_or(0); // Returns 42 if Some(42), otherwise 0


What is {:?} ?

    Used in Rust's println! macro to format output for types that implement Debug. It helps print complex data structures in a readable way.

    #[derive(Debug)]
    struct Person {
        name: String,
        age: u32,
    }
    let p = Person {
        name: "Alice".to_string(),
        age: 30,
    };
    println!("{:?}", p); // Prints: Person { name: "Alice", age: 30 }
    println!("{:#?}", p); // Multi-line formatting


panic! is not like Python's exit()

    panic! crashes the program immediately with an error message.
    std::process::exit(code) is more like Python’s sys.exit(code), as it exits cleanly with a specific exit code.

    panic!("Something went wrong!"); // This crashes the program
    std::process::exit(1); // Exits with code 1 (error)


What is ! and ? used for, anyway?

    ! is used for macros, like println!, panic!, and vec!:

    println!("Hello, world!"); // Macro, not a function
    let my_vec = vec![1, 2, 3]; // Macro that creates a vector

    ? is used for error propagation - it returns errors without needing a match statement.
    fn read_file() -> Result<String, std::io::Error> {
        let content = std::fs::read_to_string("file.txt")?; // If an error occurs, it returns early
        Ok(content)
    }
    which is equivalent to:
    fn read_file() -> Result<String, std::io::Error> {
        match std::fs::read_to_string("file.txt") {
            Ok(content) => Ok(content),
            Err(e) => return Err(e),
        }
    }


Function vs Macros:

    Feature	    Function	            Macro (!)
    Syntax	    fn my_func()	        macro_name!()
    Arguments	Fixed type & number	    Can take variable arguments
    Expansion	Runs at runtime	        Expands at compile time
    Use case	Regular logic	        Code generation, variadic arguments

*/