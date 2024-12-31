"""Test configuration and fixtures."""

import os
import pytest
from dotenv import load_dotenv

def load_env_file(env_file):
    """Load environment variables from file."""
    if os.path.exists(env_file):
        load_dotenv(env_file)
    else:
        raise FileNotFoundError(f"Environment file not found: {env_file}")

@pytest.fixture(scope="session")
def test_db_config():
    """Get test database configuration from environment."""
    load_env_file(".env.test")
    
    config = {
        'dbname': os.getenv('POSTGRES_DB'),
        'user': os.getenv('POSTGRES_USER'),
        'password': os.getenv('POSTGRES_PASSWORD'),
        'host': os.getenv('POSTGRES_HOST'),
        'port': os.getenv('POSTGRES_PORT')
    }
    
    # Validate required config
    required = ['dbname', 'user', 'host', 'port']
    missing = [k for k in required if not config.get(k)]
    if missing:
        raise ValueError(f"Missing required database config: {', '.join(missing)}")
        
    return config
