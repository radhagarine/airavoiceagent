"""Direct raw query script to test Supabase connection."""

import os
import requests
import json
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def direct_supabase_query():
    """Make a direct query to Supabase API to verify authentication."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url:
        logger.error("SUPABASE_URL environment variable is not set")
        return
        
    if not key:
        logger.error("SUPABASE_KEY environment variable is not set")
        return
    
    logger.info(f"Using Supabase URL: {url}")
    logger.info(f"Using Supabase Key: {key[:5]}...{key[-5:] if len(key) > 10 else ''}")
    
    # Construct the URL to query the business_v2 table
    api_url = f"{url}/rest/v1/business_v2?select=id,name,phone"
    
    # Setup headers with authentication
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}"
    }
    
    try:
        # Make the request
        response = requests.get(api_url, headers=headers)
        logger.info(f"Response status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Retrieved {len(data)} records:")
            for business in data:
                logger.info(f"ID: {business.get('id')} | Name: {business.get('name')} | Phone: {business.get('phone')}")
        else:
            logger.error(f"Error response: {response.text}")
            
    except Exception as e:
        logger.error(f"Request error: {str(e)}")

if __name__ == "__main__":
    direct_supabase_query()