import mysql.connector
from mysql.connector import errorcode
from .config import Config
from typing import Dict, Any, List, Optional
import json

class Database:
    def __init__(self):
        self.config = {
            'host': Config.DB_HOST,
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD,
            'database': Config.DB_NAME
        }
        self._ensure_database_exists()
        self._create_tables()

    def _get_connection(self):
        """Get a new database connection"""
        return mysql.connector.connect(**self.config)

    def _ensure_database_exists(self):
        """Create database if it doesn't exist"""
        try:
            # Connect without specifying a database
            conn = mysql.connector.connect(
                host=self.config['host'],
                user=self.config['user'],
                password=self.config['password']
            )
            cursor = conn.cursor()

            # Create database if not exists
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.config['database']}")
            cursor.close()
            conn.close()
        except mysql.connector.Error as err:
            print(f"Failed creating database: {err}")
            raise

    def _create_tables(self):
        """Create all required tables if they don't exist"""
        tables = {
            'users': ("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL UNIQUE,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """, "users table created"),
            'uploaded_files': ("""
                CREATE TABLE uploaded_files (
                id INT AUTO_INCREMENT PRIMARY KEY,
                original_filename VARCHAR(255) NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                json_path TEXT NOT NULL,
                user_id INT NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """, "uploaded_files table created"),
            'current_state': ("""
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
            """, "current_state table created"),
            'historical_events': ("""
                CREATE TABLE IF NOT EXISTS historical_events (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    file_checksum TEXT NOT NULL,
                    country_tag TEXT NOT NULL,
                    date TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT NOT NULL
                )
            """, "historical_events table created"),
            'annual_income': ("""
                CREATE TABLE IF NOT EXISTS annual_income (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    file_checksum TEXT NOT NULL,
                    country_tag TEXT NOT NULL,
                    year TEXT NOT NULL,
                    income FLOAT NOT NULL
                )
            """, "annual_income table created"),
            'user_friends': ("""
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
            """, "user_friends table created"),
            'user_file_permissions': ("""
                CREATE TABLE IF NOT EXISTS user_file_permissions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    file_id INT NOT NULL,
                    user_id INT NOT NULL,
                    permission_type ENUM('owner', 'shared') NOT NULL,
                    FOREIGN KEY (file_id) REFERENCES uploaded_files(id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE KEY unique_permission (file_id, user_id)
                )
            """, "user_file_permissions table created"),
            'topics': ("""
                CREATE TABLE IF NOT EXISTS topics (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    user_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """, "topics table created"),
            'posts': ("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    content TEXT NOT NULL,
                    user_id INT NOT NULL,
                    topic_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
                )
            """, "posts table created")
        }

        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Enable foreign key constraints
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        
        for table_name, (ddl, msg) in tables.items():
            try:
                cursor.execute(ddl)
                #print(msg)
            except mysql.connector.Error as err:
                if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
                    print(f"Table '{table_name}' already exists - skipping")
                else:
                    print(f"Error creating table '{table_name}': {err}")
                    raise
        
        cursor.close()
        conn.close()

    # User methods
    def create_user(self, username: str, email: str, password_hash: str) -> int:
        """Create a new user and return user ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                (username, email, password_hash)
            )
            user_id = cursor.lastrowid
            conn.commit()
            return user_id
        except mysql.connector.Error as err:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute(
                "SELECT * FROM users WHERE username = %s",
                (username,)
            )
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    # File processing methods
    def register_file_processing(self, conn, original_filename: str, checksum: str, json_path: str, user_id: int) -> None:
        """Register a file processing in the database (no commit)"""
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO uploaded_files 
                (original_filename, checksum, json_path, user_id, processed_at)
                VALUES (%s, %s, %s, %s, NOW())
            ''', (original_filename, checksum, json_path, user_id))
        except Exception as e:
            raise
        finally:
            cursor.close()

    def save_current_state(self, conn, checksum: str, country_data: Dict[str, Any]) -> None:
        """Save current state data for a country (no commit)"""
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO current_state 
                (file_checksum, country_tag, date, income, manpower, max_manpower, trade_income) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    checksum,
                    country_data['country_tag'],
                    country_data['current_state']['date'],
                    json.dumps(country_data['current_state']['income']),
                    country_data['current_state']['manpower'],
                    country_data['current_state']['max_manpower'],
                    country_data['current_state']['trade_income']
                )
            )
        except Exception as e:
            raise
        finally:
            cursor.close()

    def save_historical_events(self, conn, checksum: str, country_data: Dict[str, Any]) -> None:
        """Save historical events for a country (no commit)"""
        cursor = conn.cursor()
        try:
            for event in country_data['historical_events']:
                cursor.execute(
                    """INSERT INTO historical_events 
                    (file_checksum, country_tag, date, event_type, details) 
                    VALUES (%s, %s, %s, %s, %s)""",
                    (
                        checksum,
                        country_data['country_tag'],
                        event['date'],
                        event['event_type'],
                        event['details']
                    )
                )
        except Exception as e:
            raise
        finally:
            cursor.close()

    def save_annual_income(self, conn, checksum: str, country_data: Dict[str, Any]) -> None:
        """Save annual income data for a country (no commit)"""
        cursor = conn.cursor()
        try:
            annual_income = country_data.get('annual_income', [])
            
            # Handle both list and dict formats
            if isinstance(annual_income, list):
                for income_entry in annual_income:
                    cursor.execute(
                        """INSERT INTO annual_income 
                        (file_checksum, country_tag, year, income) 
                        VALUES (%s, %s, %s, %s)""",
                        (
                            checksum, 
                            country_data['country_tag'],
                            income_entry['year'],
                            income_entry['income']
                        )
                    )
            else:  # Assume it's a dict
                for year, income in annual_income.items():
                    cursor.execute(
                        """INSERT INTO annual_income 
                        (file_checksum, country_tag, year, income) 
                        VALUES (%s, %s, %s, %s)""",
                        (checksum, country_data['country_tag'], year, income)
                    )
        except Exception as e:
            raise
        finally:
            cursor.close()

    def save_all_country_data(self, conn, checksum: str, country_data: Dict[str, Any]) -> None:
        """Save all data for a country in a single transaction (no commit)"""
        try:
            if 'current_state' in country_data:
                self.save_current_state(conn, checksum, country_data)
            if 'historical_events' in country_data:
                self.save_historical_events(conn, checksum, country_data)
            if 'annual_income' in country_data:
                # Handle empty annual_income case
                if country_data['annual_income']:  # Only save if not empty
                    self.save_annual_income(conn, checksum, country_data)
        except Exception as e:
            raise

    def check_existing_file(self, checksum: str) -> bool:
        """Check if a file with this checksum already exists"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT id FROM uploaded_files WHERE file_checksum = %s",
                (checksum,)
            )
            return cursor.fetchone() is not None
        finally:
            cursor.close()
            conn.close()

    def get_file_owner(self, file_id: int) -> int:
        """Get the owner user ID for a file"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """SELECT user_id FROM user_file_permissions 
                   WHERE file_id = %s AND permission_type = 'owner'""",
                (file_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            cursor.close()
            conn.close()

    def add_friend_request(self, user_id: int, friend_id: int) -> None:
        """Add a friend request"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO user_friends 
                   (user_id, friend_id, status) 
                   VALUES (%s, %s, 'pending')""",
                (user_id, friend_id)
            )
            conn.commit()
        except mysql.connector.Error as err:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def accept_friend_request(self, user_id: int, friend_id: int) -> None:
        """Accept a friend request"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """UPDATE user_friends SET status = 'accepted' 
                   WHERE user_id = %s AND friend_id = %s""",
                (friend_id, user_id)
            )
            conn.commit()
        except mysql.connector.Error as err:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def get_friends(self, user_id: int) -> List[Dict[str, Any]]:
        """Get list of friends for a user"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute(
                """SELECT u.id, u.username, u.email 
                   FROM user_friends uf
                   JOIN users u ON (
                       (uf.user_id = u.id AND uf.friend_id = %s) OR 
                       (uf.friend_id = u.id AND uf.user_id = %s)
                   WHERE uf.status = 'accepted'""",
                (user_id, user_id)
            )
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def share_file(self, file_id: int, user_id: int) -> None:
        """Share a file with another user"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO user_file_permissions 
                   (file_id, user_id, permission_type) 
                   VALUES (%s, %s, 'shared')""",
                (file_id, user_id)
            )
            conn.commit()
        except mysql.connector.Error as err:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def get_shared_files(self, user_id: int) -> List[Dict[str, Any]]:
        """Get files shared with a user"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT uf.*, u.username as owner_name
                FROM uploaded_files uf
                JOIN user_file_permissions ufp ON uf.id = ufp.file_id
                JOIN users u ON uf.user_id = u.id
                WHERE ufp.user_id = %s 
                AND ufp.permission_type = 'shared'
                AND uf.user_id != %s
                ORDER BY uf.processed_at DESC
            """, (user_id, user_id))
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def get_user_files(self, user_id: int) -> List[Dict[str, Any]]:
        """Get list of processed files for a user"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT * FROM uploaded_files 
                WHERE user_id = %s 
                ORDER BY processed_at DESC
            ''', (user_id,))
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def get_file_by_checksum(self, checksum: str, user_id: int) -> Optional[dict]:
        """Get file details by checksum and user ID (either owner or shared)"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT uf.* FROM uploaded_files uf
                LEFT JOIN user_file_permissions ufp ON uf.id = ufp.file_id
                WHERE uf.checksum = %s
                AND (uf.user_id = %s OR ufp.user_id = %s)
            ''', (checksum, user_id, user_id))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    def get_current_state(self, checksum: str, country_tag: str) -> Optional[Dict[str, Any]]:
        """Get current state for a specific country"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT * FROM current_state 
                WHERE file_checksum = %s AND country_tag = %s
                ORDER BY date DESC LIMIT 1
            ''', (checksum, country_tag))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    def get_annual_income(self, checksum: str, country_tag: str) -> List[Dict[str, Any]]:
        """Get annual income data for a country"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT year, income FROM annual_income 
                WHERE file_checksum = %s AND country_tag = %s
                ORDER BY year
            ''', (checksum, country_tag))
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def get_historical_events(self, checksum: str, country_tag: str) -> List[Dict[str, Any]]:
        """Get historical events for a country"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT date, event_type, details FROM historical_events 
                WHERE file_checksum = %s AND country_tag = %s
                ORDER BY date
            ''', (checksum, country_tag))
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def get_friends_list(self, user_id: int) -> List[Dict[str, Any]]:
        """Get accepted friends list (both directions)"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                (SELECT u.id, u.username 
                FROM user_friends uf
                JOIN users u ON uf.friend_id = u.id
                WHERE uf.user_id = %s AND uf.status = 'accepted')
                UNION
                (SELECT u.id, u.username 
                FROM user_friends uf
                JOIN users u ON uf.user_id = u.id
                WHERE uf.friend_id = %s AND uf.status = 'accepted')
            """, (user_id, user_id))
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def get_pending_requests(self, user_id: int) -> List[Dict[str, Any]]:
        """Get pending friend requests where user is the recipient"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT u.id, u.username 
                FROM user_friends uf
                JOIN users u ON uf.user_id = u.id
                WHERE uf.friend_id = %s AND uf.status = 'pending'
            """, (user_id,))
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def create_friend_request(self, user_id: int, friend_id: int) -> bool:
        """Create a new friend request"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Check if relationship already exists
            cursor.execute("""
                SELECT 1 FROM user_friends 
                WHERE (user_id = %s AND friend_id = %s)
                OR (user_id = %s AND friend_id = %s)
            """, (user_id, friend_id, friend_id, user_id))
            
            if cursor.fetchone():
                return False
            
            # Create new request
            cursor.execute("""
                INSERT INTO user_friends (user_id, friend_id, status)
                VALUES (%s, %s, 'pending')
            """, (user_id, friend_id))
            
            conn.commit()
            return True
        except mysql.connector.Error as err:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def accept_friend_request(self, user_id: int, friend_id: int) -> bool:
        """Accept a pending friend request"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE user_friends 
                SET status = 'accepted'
                WHERE user_id = %s AND friend_id = %s AND status = 'pending'
            """, (friend_id, user_id))
            
            affected = cursor.rowcount
            conn.commit()
            return affected > 0
        except mysql.connector.Error as err:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def share_file_with_all_friends(self, file_id: int, owner_id: int) -> None:
        """Share a file with all of the owner's friends"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get all friend IDs
            cursor.execute("""
                SELECT friend_id FROM user_friends 
                WHERE user_id = %s AND status = 'accepted'
                UNION
                SELECT user_id FROM user_friends 
                WHERE friend_id = %s AND status = 'accepted'
            """, (owner_id, owner_id))
            
            friend_ids = [row[0] for row in cursor.fetchall()]
            
            # Share with each friend
            for friend_id in friend_ids:
                try:
                    cursor.execute("""
                        INSERT INTO user_file_permissions 
                        (file_id, user_id, permission_type) 
                        VALUES (%s, %s, 'shared')
                        ON DUPLICATE KEY UPDATE permission_type = 'shared'
                    """, (file_id, friend_id))
                except mysql.connector.Error as err:
                    # Log but continue with other friends
                    print(f"Error sharing with friend {friend_id}: {err}")
                    
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def delete_file(self, file_id: int, user_id: int) -> bool:
        """Delete a file and all its associated data if user is owner"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Verify user is the owner
            cursor.execute("""
                SELECT 1 FROM uploaded_files
                WHERE id = %s AND user_id = %s
            """, (file_id, user_id))

            if not cursor.fetchone():
                return False

            # Get checksum for cascading deletes
            cursor.execute("""
                SELECT checksum FROM uploaded_files WHERE id = %s
            """, (file_id,))
            checksum = cursor.fetchone()[0]

            # Start transaction only if not already in one
            if not conn.in_transaction:
                conn.start_transaction()

            # Delete from shared permissions first
            cursor.execute("""
                DELETE FROM user_file_permissions
                WHERE file_id = %s
            """, (file_id,))

            # Delete from current_state
            cursor.execute("""
                DELETE FROM current_state
                WHERE file_checksum = %s
            """, (checksum,))

            # Delete from historical_events
            cursor.execute("""
                DELETE FROM historical_events
                WHERE file_checksum = %s
            """, (checksum,))

            # Delete from annual_income
            cursor.execute("""
                DELETE FROM annual_income
                WHERE file_checksum = %s
            """, (checksum,))

            # Finally delete the file record
            cursor.execute("""
                DELETE FROM uploaded_files
                WHERE id = %s
            """, (file_id,))

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def create_topic(self, title: str, content: str, user_id: int) -> int:
        """Create a new forum topic and return topic ID"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO topics (title, content, user_id) VALUES (%s, %s, %s)",
                (title, content, user_id)
            )
            topic_id = cursor.lastrowid
            conn.commit()
            return topic_id
        except mysql.connector.Error as err:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def add_post(self, content: str, user_id: int, topic_id: int) -> int:
        """Add a post to a topic and return post ID"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO posts (content, user_id, topic_id) VALUES (%s, %s, %s)",
                (content, user_id, topic_id)
            )
            post_id = cursor.lastrowid
            conn.commit()
            return post_id
        except mysql.connector.Error as err:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def get_all_topics(self) -> List[Dict[str, Any]]:
        """Get all forum topics with author info"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT t.*, u.username
                FROM topics t
                JOIN users u ON t.user_id = u.id
                ORDER BY t.created_at DESC
            """)
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def get_topic_by_id(self, topic_id: int) -> Optional[Dict[str, Any]]:
        """Get a topic by ID with author info"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT t.*, u.username
                FROM topics t
                JOIN users u ON t.user_id = u.id
                WHERE t.id = %s
            """, (topic_id,))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    def get_posts_for_topic(self, topic_id: int) -> List[Dict[str, Any]]:
        """Get all posts for a topic with author info"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT p.*, u.username
                FROM posts p
                JOIN users u ON p.user_id = u.id
                WHERE p.topic_id = %s
                ORDER BY p.created_at ASC
            """, (topic_id,))
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def delete_topic(self, topic_id: int, user_id: int) -> bool:
        """Delete a topic if the user is the author"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Verify user is the author
            cursor.execute(
                "SELECT 1 FROM topics WHERE id = %s AND user_id = %s",
                (topic_id, user_id)
            )

            if not cursor.fetchone():
                return False

            # Delete the topic (posts will be deleted automatically due to ON DELETE CASCADE)
            cursor.execute(
                "DELETE FROM topics WHERE id = %s",
                (topic_id,)
            )

            conn.commit()
            return True
        except mysql.connector.Error as err:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def delete_post(self, post_id: int, user_id: int) -> bool:
        """Delete a post if the user is the author"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Verify user is the author
            cursor.execute(
                "SELECT 1 FROM posts WHERE id = %s AND user_id = %s",
                (post_id, user_id)
            )

            if not cursor.fetchone():
                return False

            # Delete the post
            cursor.execute(
                "DELETE FROM posts WHERE id = %s",
                (post_id,)
            )

            conn.commit()
            return True
        except mysql.connector.Error as err:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def get_post_topic(self, post_id: int) -> Optional[Dict[str, Any]]:
        """Get the topic ID for a post"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT topic_id FROM posts WHERE id = %s",
                (post_id,)
            )
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()