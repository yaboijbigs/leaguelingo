# config.py

import os

class Config:
    # Database connection string
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', '')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # OpenAI API key
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# You can add more configurations here as needed
