"""Debug script to test Supabase authentication and check database records."""

import os
import json
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def check_supabase_auth():
    """Test Supabase authentication and connection."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url:
        logger.error("SUPABASE_URL environment variable is not set")
        return False
        
    if not key:
        logger.error("SUPABASE_KEY environment variable is not set")
        return False
    
    logger.info(f"Using Supabase URL: {url}")
    logger.info(f"Using Supabase Key: {key[:5]}...{key[-5:] if len(key) > 10 else ''}")
    
    try:
        supabase = create_client(url, key)
        
        # Try a simple query to check authentication
        response = supabase.table("business_v2").select("count").execute()
        logger.info(f"Authentication successful - response: {response}")
        return True
    except Exception as e:
        logger.error(f"Supabase authentication error: {str(e)}")
        return False

def list_all_businesses():
    """Get all businesses from the database."""
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            logger.error("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
            return
        
        supabase = create_client(url, key)
        response = supabase.table("business_v2").select("id,name,phone").execute()
        
        if not response.data:
            logger.error("No businesses found in the database")
            return
            
        logger.info(f"Found {len(response.data)} businesses:")
        for business in response.data:
            logger.info(f"ID: {business.get('id')} | Name: {business.get('name')} | Phone: {business.get('phone')}")
            
        # Try specific phone number lookups
        test_phones = ["18554494055", "+18554494055", "1(855) 449-4055"]
        
        for phone in test_phones:
            logger.info(f"\nTesting lookup with phone: {phone}")
            response = supabase.table("business_v2").select("id,name,phone").eq("phone", phone).execute()
            logger.info(f"Direct EQ query result: {json.dumps(response.data, indent=2)}")
            
            # Try ILIKE for special characters
            if any(c in phone for c in ['+', '(', ')', ' ', '-']):
                # Escape special characters for LIKE pattern
                like_pattern = phone.replace('+', '\\+').replace('(', '\\(').replace(')', '\\)').replace('-', '\\-')
                logger.info(f"Using ILIKE with pattern: {like_pattern}")
                response = supabase.table("business_v2").select("id,name,phone").ilike("phone", like_pattern).execute()
                logger.info(f"ILIKE query result: {json.dumps(response.data, indent=2)}")
                
    except Exception as e:
        logger.error(f"Error listing businesses: {str(e)}")

def main():
    """Run the Supabase debug tests."""
    logger.info("Starting Supabase debug tests")
    
    # First check authentication
    if check_supabase_auth():
        logger.info("Supabase authentication successful")
        
        # List all businesses
        list_all_businesses()
    else:
        logger.error("Supabase authentication failed - check your credentials")

if __name__ == "__main__":
    main()